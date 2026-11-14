// Luthfi integration: bounded validation, durable jobs, explicit activation, owner-scoped progress.
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID, createHash } = require('node:crypto');
const { Client } = require('pg');
const { csvBatches } = require('./csv-batches');
const { validatePolicy } = require('./bulk-policy');
const { multer, Server } = require('./runtime');

function error(message, status = 409) { const e = Error(message); e.status = status; throw e; }
const uuid = value => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value || '');
const escaped = value => { let text = String(value == null ? '' : value); if (/^[=+\-@]/.test(text)) text = "'" + text; return '"' + text.replace(/"/g, '""') + '"'; };
class CsvImports {
  constructor(bulk, { root = '/var/lib/netpro-imports', validationBatch = 1000, activationBatch = 100, afterBatch } = {}) {
    this.bulk = bulk; this.db = bulk.db; this.root = root; this.validationBatch = validationBatch;
    this.activationBatch = activationBatch; this.afterBatch = afterBatch; this.stopping = false; this.lost = false;
  }
  q(sql, bind = [], t) { return this.bulk.q(sql, bind, t); }
  async migrate() {
    await this.db.transaction(async t => {
      await this.q('SELECT pg_advisory_xact_lock(20261030, 60)', [], t);
      await this.q(`CREATE TABLE IF NOT EXISTS netpro_csv_jobs(
        id UUID PRIMARY KEY,owner_id TEXT NOT NULL,filename TEXT NOT NULL,input_path TEXT NOT NULL,sha256 TEXT NOT NULL,
        source_key TEXT NOT NULL UNIQUE,status TEXT NOT NULL DEFAULT 'queued',error_phase TEXT,error_message TEXT,
        total_records INTEGER NOT NULL DEFAULT 0,processed_records INTEGER NOT NULL DEFAULT 0,
        valid_records INTEGER NOT NULL DEFAULT 0,duplicate_records INTEGER NOT NULL DEFAULT 0,invalid_records INTEGER NOT NULL DEFAULT 0,
        activated_records INTEGER NOT NULL DEFAULT 0,owned_records INTEGER NOT NULL DEFAULT 0,
        activation_cursor TEXT,removal_ids JSONB,batch_size INTEGER NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())`, [], t);
      await this.q(`CREATE TABLE IF NOT EXISTS netpro_csv_rows(
        job_id UUID NOT NULL REFERENCES netpro_csv_jobs(id) ON DELETE CASCADE,domain VARCHAR(253) NOT NULL,
        payload JSONB NOT NULL,row_number INTEGER NOT NULL,PRIMARY KEY(job_id,domain))`, [], t);
      await this.q(`CREATE TABLE IF NOT EXISTS netpro_csv_failures(
        job_id UUID NOT NULL REFERENCES netpro_csv_jobs(id) ON DELETE CASCADE,row_number INTEGER NOT NULL,
        domain TEXT NOT NULL,error_message TEXT NOT NULL,PRIMARY KEY(job_id,row_number))`, [], t);
    });
  }
  async ready() { await this.q('SELECT id FROM netpro_csv_jobs LIMIT 0'); }
  async hash(file) {
    if (path.dirname(await fs.promises.realpath(file)) !== path.resolve(this.root)) error('Retained input path is invalid');
    if (!(await fs.promises.lstat(file)).isFile()) error('Retained input is not a file');
    const hash = createHash('sha256'); for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
    return hash.digest('hex');
  }
  async checked(job) { if (await this.hash(job.input_path) !== job.sha256) error('Retained file changed; upload a new file'); }
  async enqueue(owner, files) {
    if (this.lost) error('Import worker unavailable', 503);
    const inputs = [];
    for (const file of files) {
      const id = randomUUID();
      inputs.push({ id, filename: file.originalname, file: path.resolve(file.path), hash: await this.hash(file.path), key: 'csv-' + id });
      await fs.promises.chmod(file.path, 0o400);
    }
    await this.db.transaction(async t => {
      for (const item of inputs) await this.q(`INSERT INTO netpro_csv_jobs(id,owner_id,filename,input_path,sha256,source_key,batch_size)
        VALUES($1,$2,$3,$4,$5,$6,$7)`, [item.id, String(owner), item.filename, item.file, item.hash, item.key, this.validationBatch], t);
    });
    return Promise.all(inputs.map(item => this.job(owner, item.id)));
  }
  async raw(id, owner) {
    if (!uuid(id)) error('Invalid upload job ID', 400);
    const [row] = await this.q('SELECT * FROM netpro_csv_jobs WHERE id=$1 AND ($2::text IS NULL OR owner_id=$2)', [id, owner == null ? null : String(owner)]);
    if (!row) error('Upload job not found', 404);
    return row;
  }
  async job(owner, id) {
    const job = await this.raw(id, owner);
    const progress = await this.bulk.status(job.source_key);
    job.removal_count = job.removal_ids ? job.removal_ids.length : 0;
    delete job.removal_ids;
    delete job.input_path; delete job.sha256;
    return { ...job, publication: progress, applicationVerified: false };
  }
  async list(owner) {
    const jobs = await this.q('SELECT id FROM netpro_csv_jobs WHERE owner_id=$1 ORDER BY created_at DESC LIMIT 50', [String(owner)]);
    return Promise.all(jobs.map(j => this.job(owner, j.id)));
  }
  async emit(id) {
    if (!this.io) return;
    const raw = await this.raw(id);
    this.io.to('user:' + raw.owner_id).emit('importProgress', await this.job(raw.owner_id, id));
  }
  async update(id, values) {
    const keys = Object.keys(values);
    await this.q(`UPDATE netpro_csv_jobs SET ${keys.map((k, i) => k + '=$' + (i + 2)).join(',')},updated_at=NOW() WHERE id=$1`, [id, ...keys.map(k => values[k])]);
    await this.emit(id);
  }
  async validate(job) {
    await this.checked(job);
    let total = 0; for await (const batch of csvBatches(job.input_path, job.batch_size)) total += batch.length;
    await this.update(job.id, { status: 'validating', total_records: total, error_message: null, error_phase: null });
    let position = 0;
    for await (const batch of csvBatches(job.input_path, job.batch_size)) {
      if (this.stopping) return;
      if (this.lost) throw Error('Worker lock lost');
      const begin = position; position += batch.length;
      await this.db.transaction(async t => {
        const [current] = await this.q('SELECT * FROM netpro_csv_jobs WHERE id=$1 FOR UPDATE', [job.id], t);
        if (current.status !== 'validating' || current.processed_records >= position) return;
        if (current.processed_records !== begin) throw Error('Validation checkpoint mismatch');
        const domains = batch.map(row => row.record.domain);
        const existing = await this.q('SELECT domain,payload FROM netpro_csv_rows WHERE job_id=$1 AND domain=ANY($2::text[])', [job.id, domains], t);
        const seen = new Map(existing.map(row => [row.domain, JSON.stringify(validatePolicy(row.payload))]));
        const valid = [], invalid = []; let duplicates = 0;
        for (const row of batch) {
          try {
            if (row.error) throw Error(row.error);
            const payload = validatePolicy({ ...row.record, ip_add: row.original.ip_add });
            const key = JSON.stringify(payload);
            if (seen.has(payload.domain)) {
              if (seen.get(payload.domain) !== key) throw Error('Duplicate domain has conflicting policy fields');
              duplicates++; continue;
            }
            seen.set(payload.domain, key); valid.push({ domain: payload.domain, payload, row_number: row.rowNumber });
          } catch (e) { invalid.push({ row_number: row.rowNumber, domain: row.record.domain, error_message: e.message }); }
        }
        if (valid.length) await this.q(`INSERT INTO netpro_csv_rows(job_id,domain,payload,row_number)
          SELECT $1,domain,payload,row_number FROM jsonb_to_recordset($2::jsonb) AS x(domain text,payload jsonb,row_number integer)`, [job.id, JSON.stringify(valid)], t);
        if (invalid.length) await this.q(`INSERT INTO netpro_csv_failures(job_id,row_number,domain,error_message)
          SELECT $1,row_number,domain,error_message FROM jsonb_to_recordset($2::jsonb) AS x(row_number integer,domain text,error_message text)`, [job.id, JSON.stringify(invalid)], t);
        await this.q(`UPDATE netpro_csv_jobs SET processed_records=$2,valid_records=valid_records+$3,
          duplicate_records=duplicate_records+$4,invalid_records=invalid_records+$5,updated_at=NOW() WHERE id=$1`,
          [job.id, position, valid.length, duplicates, invalid.length], t);
      });
      await this.emit(job.id); if (this.afterBatch) await this.afterBatch('validation', job.id);
    }
    const final = await this.raw(job.id);
    if (final.processed_records !== total || total !== final.valid_records + final.duplicate_records + final.invalid_records) throw Error('Validation accounting mismatch');
    await this.update(job.id, { status: 'ready' });
  }
  async activate(owner, id, options = {}) {
    const job = await this.raw(id, owner);
    if (this.lost) error('Import worker unavailable', 503);
    if (options.confirmation !== 'ACTIVATE') error('Explicit ACTIVATE confirmation required', 400);
    if (job.status !== 'ready') error('Only a validated, ready upload can be activated');
    if (!job.valid_records) error('No valid policies to activate');
    if (job.invalid_records && options.acceptInvalid !== true) error('Review failures and explicitly accept activating valid rows only');
    await this.checked(job);
    await this.q("UPDATE netpro_csv_jobs SET status='activating',updated_at=NOW() WHERE id=$1 AND status='ready'", [id]);
    await this.emit(id);
  }
  async activation(job) {
    for (;;) {
      if (this.stopping) return;
      if (this.lost) throw Error('Worker lock lost');
      const current = await this.raw(job.id);
      if (current.status !== 'activating') return;
      const rows = await this.q(`SELECT domain,payload FROM netpro_csv_rows WHERE job_id=$1
        AND ($2::text IS NULL OR domain>$2) ORDER BY domain LIMIT $3`, [job.id, current.activation_cursor, this.activationBatch]);
      if (!rows.length) {
        if (current.activated_records !== current.valid_records) throw Error('Activation checkpoint does not cover validated policies');
        await this.update(job.id, { status: 'publishing' }); return;
      }
      const stored = await this.bulk.store(job.source_key, rows.map(row => row.payload));
      await this.q(`UPDATE netpro_csv_jobs SET activation_cursor=$2,activated_records=activated_records+$3,
        owned_records=owned_records+$4,updated_at=NOW() WHERE id=$1 AND status='activating' AND activation_cursor IS NOT DISTINCT FROM $5`,
        [job.id, rows[rows.length - 1].domain, rows.length, stored.filter(row => row.owned).length, current.activation_cursor]);
      await this.emit(job.id); if (this.afterBatch) await this.afterBatch('activation', job.id);
    }
  }
  async retry(owner, id) {
    const job = await this.raw(id, owner);
    if (job.status !== 'failed') error('Only failed jobs can be retried');
    if (!['removal', 'publication'].includes(job.error_phase)) await this.checked(job);
    const status = job.error_phase === 'activation' ? 'activating' : job.error_phase === 'removal' ? 'removing' : job.error_phase === 'publication' ? 'publishing' : 'queued';
    await this.update(id, { status, error_message: null });
  }
  async requestRemoval(owner, id, confirmation) {
    if (confirmation !== 'REMOVE') error('Explicit REMOVE confirmation required', 400);
    const job = await this.raw(id, owner);
    if (!['completed', 'publishing', 'failed'].includes(job.status) || !(await this.bulk.status(job.source_key)).stored) error('No activated import to remove');
    await this.update(id, { status: 'removing', error_message: null });
  }
  async removal(job) {
    let ids = job.removal_ids;
    if (ids === null) {
      const owned = await this.q('SELECT policy_id FROM netpro_bulk_policy_keys WHERE source_key=$1 AND created_by_source=true', [job.source_key]);
      ids = owned.map(row => row.policy_id);
      await this.q('UPDATE netpro_csv_jobs SET removal_ids=$2::jsonb WHERE id=$1', [job.id, JSON.stringify(ids)]);
    }
    await this.bulk.removeOwned(job.source_key);
    if (ids.length) {
      const [events] = await this.q(`SELECT count(*)::int AS total,count(published_at)::int AS published FROM netpro_bulk_policy_events
        WHERE policy_id=ANY($1::uuid[]) AND kind='delete'`, [ids]);
      if (events.total !== ids.length) throw Error('Deletion publication record missing; inspect before retry');
      if (events.published !== ids.length) return;
    }
    await this.update(job.id, { status: 'removed' });
  }
  async tick() {
    const passive = await this.q("SELECT * FROM netpro_csv_jobs WHERE status IN ('publishing','removing') ORDER BY created_at LIMIT 20");
    for (const job of passive) {
      try {
        if (job.status === 'removing') await this.removal(job);
        else {
          const status = await this.bulk.status(job.source_key);
          if (status.stored !== job.valid_records) throw Error('Policy list changed during publication; inspect before retry');
          if (status.published + status.existing_unverified === status.stored) await this.update(job.id, { status: 'completed' }); else await this.emit(job.id);
        }
      } catch (e) { await this.update(job.id, { status: 'failed', error_phase: job.status === 'removing' ? 'removal' : 'publication', error_message: e.message }); }
    }
    const [job] = await this.q("SELECT * FROM netpro_csv_jobs WHERE status IN ('queued','validating','activating') ORDER BY created_at LIMIT 1");
    if (!job) return;
    try { if (job.status === 'activating') await this.activation(job); else await this.validate(job); }
    catch (e) { if (!this.lost) await this.update(job.id, { status: 'failed', error_phase: job.status === 'activating' ? 'activation' : 'validation', error_message: e.message }); }
  }
  async start() {
    fs.mkdirSync(this.root, { recursive: true, mode: 0o700 });
    const c = this.db.config;
    this.lock = new Client({ host: c.host, port: c.port, user: c.username, password: c.password, database: c.database });
    this.lock.on('error', () => { this.lost = true; this.stopping = true; clearTimeout(this.timer); });
    await this.lock.connect();
    const r = await this.lock.query('SELECT pg_try_advisory_lock(20261030,61) AS acquired');
    if (!r.rows[0].acquired) { await this.lock.end(); this.lock = null; throw Error('Another CSV worker owns the database'); }
    const poll = () => {
      if (this.stopping) return;
      this.timer = setTimeout(() => { this.active = this.tick().catch(e => console.error('CSV worker:', e.message)).finally(() => { this.active = null; poll(); }); }, 200);
    };
    poll();
  }
  async stop() { this.stopping = true; clearTimeout(this.timer); if (this.active) await this.active; if (this.lock) await this.lock.end(); if (this.io) await new Promise(resolve => this.io.close(resolve)); }
  attach(server, auth) {
    const io = new Server(server, { path: '/import-socket', serveClient: true }); this.io = io;
    io.use((socket, next) => {
      const req = { headers: { authorization: 'Bearer ' + (socket.handshake.auth.token || '') } };
      const res = { status: () => res, json: () => next(Error('Unauthorized')) };
      Promise.resolve(auth(req, res, () => { socket.data.owner = String(req.userId); next(); })).catch(next);
    });
    io.on('connection', socket => socket.join('user:' + socket.data.owner));
  }
}

function createCsvRouter(service, auth) {
  const router = require('express').Router(); router.use(auth);
  const upload = multer({ storage: multer.diskStorage({ destination: service.root, filename: (_r, _f, cb) => cb(null, randomUUID() + '.csv') }),
    limits: { files: 5, fileSize: 25 * 1024 * 1024, fields: 10 }, fileFilter: (_r, file, cb) => cb(path.extname(file.originalname).toLowerCase() === '.csv' ? null : Error('Only CSV files are accepted'), true) });
  const route = fn => (req, res, next) => Promise.resolve(fn(req, res)).catch(next);
  router.get('/template.csv', (_req, res) => res.type('text/csv').attachment('netpro-policy-template.csv').send('domain,ip_add,name,category\nexample.com,,Example domain-only rule,Other\n'));
  router.get('/', route(async (req, res) => res.json({ jobs: await service.list(req.userId) })));
  router.post('/', upload.array('files', 5), route(async (req, res) => {
    if (!req.files || !req.files.length) error('Select at least one CSV file', 400);
    try { res.status(202).json({ jobs: await service.enqueue(req.userId, req.files) }); }
    catch (e) { for (const file of req.files) await fs.promises.unlink(file.path).catch(() => {}); throw e; }
  }));
  router.get('/:id', route(async (req, res) => res.json({ job: await service.job(req.userId, req.params.id) })));
  router.get('/:id/preview', route(async (req, res) => {
    await service.raw(req.params.id, req.userId);
    res.json({ rows: await service.q('SELECT domain,payload,row_number FROM netpro_csv_rows WHERE job_id=$1 ORDER BY row_number LIMIT 20', [req.params.id]),
      failures: await service.q('SELECT row_number,domain,error_message FROM netpro_csv_failures WHERE job_id=$1 ORDER BY row_number LIMIT 20', [req.params.id]) });
  }));
  router.get('/:id/failures.csv', route(async (req, res) => {
    await service.raw(req.params.id, req.userId); res.type('text/csv').attachment('failed-rows.csv');
    res.write('row_number,domain,error\n'); let cursor = 0;
    for (;;) {
      const rows = await service.q('SELECT * FROM netpro_csv_failures WHERE job_id=$1 AND row_number>$2 ORDER BY row_number LIMIT 1000', [req.params.id, cursor]);
      if (!rows.length) break;
      for (const row of rows) { if (res.destroyed) return; if (!res.write([row.row_number, row.domain, row.error_message].map(escaped).join(',') + '\n')) await require('node:events').once(res, 'drain'); }
      cursor = rows[rows.length - 1].row_number;
    }
    res.end();
  }));
  router.post('/:id/activate', route(async (req, res) => { await service.activate(req.userId, req.params.id, req.body); res.status(202).json({ job: await service.job(req.userId, req.params.id) }); }));
  router.post('/:id/retry', route(async (req, res) => { await service.retry(req.userId, req.params.id); res.status(202).json({ job: await service.job(req.userId, req.params.id) }); }));
  router.post('/:id/remove', route(async (req, res) => { await service.requestRemoval(req.userId, req.params.id, req.body.confirmation); res.status(202).json({ job: await service.job(req.userId, req.params.id) }); }));
  router.use((e, _req, res, _next) => { if (!res.headersSent) res.status(e.code === 'LIMIT_FILE_SIZE' ? 413 : e.status || 400).json({ message: e.status || e.code || e.message.startsWith('Only CSV') ? e.message : 'Import request failed' }); else res.destroy(); });
  return router;
}
module.exports = { CsvImports, createCsvRouter };
