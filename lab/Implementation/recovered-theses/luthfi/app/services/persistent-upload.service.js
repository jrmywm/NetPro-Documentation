// Labelled adaptation: DB-backed queue, retained inputs and committed batch resume.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { Client } = require('pg');
const db = require('../config/db.config');
const { getIsolationConfig } = require('../config/isolation');
const BoundedUploadService = require('./bounded-upload.service');

const inputRoot = path.resolve(__dirname, '../../retained-inputs');
async function digest(filePath) {
  const real = await fs.promises.realpath(filePath);
  if (path.dirname(real) !== inputRoot) throw Error('Input is outside retained-input directory');
  const stat = await fs.promises.lstat(filePath);
  if (!stat.isFile() || stat.isSymbolicLink()) throw Error('Input must be a regular retained file');
  const hash = crypto.createHash('sha256');
  for await (const chunk of fs.createReadStream(real)) hash.update(chunk);
  return hash.digest('hex');
}
class PersistentUploadService {
  constructor() { this.stopping = false; this.lost = false; this.timer = null; this.active = null; }
  async enqueue(files) {
    const inputs = [];
    for (const file of files) {
      inputs.push({ filename: file.originalname, input_path: path.resolve(file.path),
        input_sha256: await digest(file.path), input_batch_size: 1000, status: 'queued' });
      await fs.promises.chmod(file.path, 0o400);
    }
    return db.sequelize.transaction(transaction => db.uploadJob.bulkCreate(inputs, { transaction, returning: true }));
  }
  async retry(id) {
    const job = await db.uploadJob.findByPk(id);
    if (!job || job.status !== 'failed' || !job.input_path) throw Error('Only retained failed jobs can be retried');
    if (await digest(job.input_path) !== job.input_sha256) throw Error('Retained input checksum changed; refusing resume');
    const [changed] = await db.uploadJob.update({ status: 'queued', error_message: null,
      retry_count: job.retry_count + 1, last_retry_at: new Date() }, { where: { id, status: 'failed' } });
    if (!changed) throw Error('Job status changed; retry not queued');
  }
  async start() {
    const config = getIsolationConfig();
    // Dedicated session owns the single-worker lock; not a pooled connection.
    this.lock = new Client({ host: config.host, port: config.dbPort, user: config.username,
      password: config.password, database: config.database });
    this.lock.on('error', () => { this.lost = true; this.stopping = true; clearTimeout(this.timer); });
    await this.lock.connect();
    const { rows } = await this.lock.query('SELECT pg_try_advisory_lock(20261030, 21) AS acquired');
    if (!rows[0].acquired) { await this.lock.end(); this.lock = null; throw Error('Another upload worker already owns this database'); }
    this.schedule();
  }
  schedule() {
    if (this.stopping) return;
    this.timer = setTimeout(() => {
      this.active = this.tick().catch(error => console.error('Upload queue poll failed:', error.message))
        .finally(() => { this.active = null; this.schedule(); });
    }, 100);
  }
  async tick() {
    const job = await db.uploadJob.findOne({ where: {
      status: { [db.Sequelize.Op.in]: ['queued', 'processing'] },
      input_path: { [db.Sequelize.Op.ne]: null }
    }, order: [['id', 'ASC']] });
    if (!job) return;
    try {
      if (await digest(job.input_path) !== job.input_sha256) throw Error('Retained input checksum changed; refusing resume');
      const service = new BoundedUploadService({ batchSize: job.input_batch_size,
        beforeBatch: async () => { if (this.lost) throw Error('Upload worker database lock lost'); } });
      await service.process(job.input_path, job.id);
    } catch (error) {
      await db.uploadJob.update({ status: 'failed', error_message: error.message }, { where: { id: job.id } });
      if (global.io) global.io.emit('uploadProgress', { jobId: job.id, filename: job.filename, status: 'failed', error: error.message });
    }
  }
  async stop() {
    this.stopping = true; clearTimeout(this.timer);
    if (this.active) await this.active;
    if (this.lock) { await this.lock.end(); this.lock = null; }
  }
}
module.exports = { PersistentUploadService, inputRoot, digest };
