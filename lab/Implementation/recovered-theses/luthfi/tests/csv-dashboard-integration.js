// Isolated authoritative-schema/HTTP/Socket.IO test; no live Kafka or real policies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const { once } = require('node:events');
const { io } = require('socket.io-client');
const db = require('../app/config/db.config');
const { BulkPolicyService } = require('../../backend-candidate/src/integration/bulk-policy');
const { CsvImports, createCsvRouter } = require('../../backend-candidate/src/integration/csv-imports');
const results = [], messages = [], sockets = [];
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'netpro-csv-ui-'));
const prefix = 'csvui' + Date.now();
const bulk = new BulkPolicyService(db.sequelize, { send: async r => { messages.push(r); } });
let imports, server;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
function pass(name, details) { results.push({ name, passed: true, details }); console.log('PASS ' + name); }
const auth = (req, res, next) => {
  const token = req.headers.authorization;
  if (!['Bearer ownerA', 'Bearer ownerB'].includes(token)) return res.status(401).json({ message: 'Unauthorized' });
  req.userId = token.slice(7); next();
};
let base;
async function request(endpoint, { method = 'GET', data, owner = 'ownerA' } = {}) {
  const response = await fetch(base + endpoint, { method, headers: {
    Authorization: 'Bearer ' + owner, ...(data ? { 'Content-Type': 'application/json' } : {})
  }, body: data ? JSON.stringify(data) : undefined });
  return { status: response.status, data: response.headers.get('content-type')?.includes('json') ? await response.json() : await response.text() };
}
async function upload(content, name = 'fixture.csv') {
  const form = new FormData(); form.append('files', new Blob([content]), name);
  const r = await fetch(base, { method: 'POST', headers: { Authorization: 'Bearer ownerA' }, body: form });
  const body = await r.json(); assert.equal(r.status, 202, JSON.stringify(body)); return body.jobs[0].id;
}
async function wait(id, status) {
  for (let i = 0; i < 1000; i++) {
    const job = await imports.job('ownerA', id);
    if (job.status === status) return job;
    if (job.status === 'failed' && status !== 'failed') throw Error(job.error_message);
    if (['publishing', 'removing'].includes(job.status)) while ((await bulk.publishBatch(100)).length) {}
    await pause(30);
  }
  throw Error('Timed out: ' + status);
}
async function main() {
  await bulk.migrate();
  imports = new CsvImports(bulk, { root }); await imports.migrate(); await imports.migrate(); await imports.start();
  const app = require('express')(); app.use(require('express').json()); app.use('/imports', createCsvRouter(imports, auth));
  server = http.createServer(app); imports.attach(server, auth);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  base = 'http://127.0.0.1:' + server.address().port + '/imports';
  assert.equal((await fetch(base)).status, 401);
  const eventsA = [], eventsB = [];
  for (const [owner, events] of [['ownerA', eventsA], ['ownerB', eventsB]]) {
    const s = io('http://127.0.0.1:' + server.address().port, { path: '/import-socket', auth: { token: owner }, transports: ['websocket'] }); sockets.push(s);
    s.on('importProgress', event => events.push(event)); await once(s, 'connect');
  }
  const id = await upload(`domain,ip_add,name,category\n${prefix}.example,192.0.2.31,Example,Other\n${prefix}-sni.example,,SNI,Other\n${prefix}.example,192.0.2.31,Example,Other\n,,Missing,Other\nhttps://example.com,,URL,Other\n`);
  const ready = await wait(id, 'ready');
  assert.equal(ready.valid_records, 2); assert.equal(ready.duplicate_records, 1); assert.equal(ready.invalid_records, 2);
  assert.equal(ready.processed_records, 5); assert.equal(ready.input_path, undefined);
  assert(eventsA.some(e => e.id === id && e.status === 'ready')); assert.equal(eventsB.length, 0);
  assert.equal((await request('/' + id, { owner: 'ownerB' })).status, 404);
  pass('authenticated upload validates exact counts and scopes HTTP/Socket.IO data to owner');
  const preview = await request('/' + id + '/preview'); assert.equal(preview.data.rows.length, 2); assert.equal(preview.data.failures.length, 2);
  const csv = await request('/' + id + '/failures.csv'); assert(csv.data.includes('Domain is required'));
  pass('preview and failed-row CSV expose validation results before activation');
  assert.equal((await request('/' + id + '/activate', { method: 'POST', data: {} })).status, 400);
  assert.equal((await request('/' + id + '/activate', { method: 'POST', data: { confirmation: 'ACTIVATE' } })).status, 409);
  assert.equal((await request('/' + id + '/activate', { method: 'POST', data: { confirmation: 'ACTIVATE', acceptInvalid: true } })).status, 202);
  const done = await wait(id, 'completed'); assert.equal(done.publication.published, 2); assert.equal(done.applicationVerified, false);
  assert.equal(done.owned_records, 2); assert.equal(done.activated_records, 2);
  pass('explicit reviewed activation commits/publishes valid rows without claiming enforcement');
  assert.equal((await request('/' + id + '/remove', { method: 'POST', data: { confirmation: 'REMOVE' } })).status, 202);
  await wait(id, 'removed');
  assert.equal((await imports.job('ownerA', id)).removal_ids, undefined);
  assert.equal((await bulk.q('SELECT id FROM ps_blocked_list WHERE domain=ANY($1::text[])', [[prefix + '.example', prefix + '-sni.example']])).length, 0);
  pass('owner can remove exactly the import-created policies and publish their deletions');

  // Committed validation checkpoint recovery: fault after first batch, retry same immutable file.
  let faulted = false;
  imports.afterBatch = async (phase, job) => { if (phase === 'validation' && !faulted) { faulted = true; throw Error('simulated worker failure after commit'); } };
  const resume = await upload('domain\n' + Array.from({ length: 1501 }, (_, i) => `${prefix}-resume-${i}.example`).join('\n') + '\n', 'resume.csv');
  const failed = await wait(resume, 'failed'); assert.equal(failed.processed_records, 1000);
  imports.afterBatch = null;
  assert.equal((await request('/' + resume + '/retry', { method: 'POST' })).status, 202);
  const recovered = await wait(resume, 'ready'); assert.equal(recovered.valid_records, 1501); assert.equal(recovered.duplicate_records, 0);
  pass('validation retry resumes committed 1,000-row checkpoint without inflating duplicates');
  let activationFault = false;
  imports.afterBatch = async phase => { if (phase === 'activation' && !activationFault) { activationFault = true; throw Error('simulated activation failure after commit'); } };
  await request('/' + resume + '/activate', { method: 'POST', data: { confirmation: 'ACTIVATE' } });
  const partly = await wait(resume, 'failed'); assert.equal(partly.activated_records, 100);
  imports.afterBatch = null;
  await request('/' + resume + '/retry', { method: 'POST' });
  const resumed = await wait(resume, 'completed'); assert.equal(resumed.activated_records, 1501); assert.equal(resumed.owned_records, 1501);
  assert(messages.some(r => r.messages.length === 100)); assert(messages.every(r => r.messages.length <= 100));
  pass('activation retry resumes durable batch cursor through 1,501 policies with stable ownership counts');
  await request('/' + resume + '/remove', { method: 'POST', data: { confirmation: 'REMOVE' } }); await wait(resume, 'removed');

  const input = path.join(root, 'large.csv'), output = fs.createWriteStream(input); output.write('domain\n');
  for (let i = 0; i < 100000; i++) if (!output.write(`${prefix}-large-${i}.example\n`)) await once(output, 'drain');
  output.end(); await once(output, 'finish');
  const large = await upload(fs.readFileSync(input), 'large.csv');
  const validated = await wait(large, 'ready'); assert.equal(validated.valid_records, 100000); assert.equal(validated.processed_records, 100000);
  assert.equal((await bulk.status(validated.source_key)).stored, 0);
  pass('integrated HTTP pipeline validates/stages 100,000 rows without automatic rule activation', { rows: 100000, processRssMiB: +(process.memoryUsage().rss / 1048576).toFixed(2) });
}
main().catch(e => { results.push({ name: e.message, passed: false }); console.error(e); process.exitCode = 1; }).finally(async () => {
  for (const socket of sockets) socket.close(); if (imports) await imports.stop();
  if (server && server.listening) { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
  await db.sequelize.close(); fs.mkdirSync('evidence', { recursive: true });
  fs.writeFileSync('evidence/csv-dashboard-integration.json', JSON.stringify({ date: new Date().toISOString(), fixtureRoot: root,
    liveRulesUsed: false, results }, null, 2), 'utf8');
});
