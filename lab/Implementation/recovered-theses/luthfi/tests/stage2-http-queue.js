const assert = require('node:assert/strict');
const fs = require('node:fs');
const { spawn } = require('node:child_process');
const { io } = require('socket.io-client');
const db = require('../app/config/db.config');
const { getIsolationConfig } = require('../app/config/isolation');
const config = getIsolationConfig();
const base = `http://127.0.0.1:${config.port}`;
const results = [];
const children = new Set();
const sockets = new Set();
const prefix = `http${Date.now()}`;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
function pass(name, details) { results.push({ name, passed: true, details }); console.log('PASS ' + name); }
async function start() {
  const child = spawn(process.execPath, ['index.js'], { env: process.env, stdio: ['ignore', 'pipe', 'pipe'] });
  children.add(child); let log = '';
  child.stdout.on('data', b => { log = (log + b).slice(-4000); });
  child.stderr.on('data', b => { log = (log + b).slice(-4000); });
  for (let i = 0; i < 150; i++) {
    if (child.exitCode !== null) throw Error('Candidate exited before readiness: ' + log);
    if (log.includes('Isolated server ready')) return child;
    await pause(100);
  }
  throw Error('Candidate readiness timeout: ' + log);
}
async function stop(child, signal = 'SIGTERM') {
  if (child.exitCode === null && child.signalCode === null) {
    const exited = new Promise(resolve => child.once('exit', resolve));
    child.kill(signal);
    await Promise.race([exited, pause(10000).then(() => { throw Error('Candidate shutdown timeout'); })]);
  }
  children.delete(child);
}
async function connectSocket() {
  const socket = io(base, { transports: ['websocket'], reconnection: false }); sockets.add(socket);
  await new Promise((resolve, reject) => { socket.once('connect', resolve); socket.once('connect_error', reject); });
  return socket;
}
async function upload(content, name = 'fixture.csv', route = '/massive-data/csv-upload', field = 'file') {
  const form = new FormData(); form.append(field, new Blob([content], { type: 'text/csv' }), name);
  const response = await fetch(base + route, { method: 'POST', body: form });
  const data = await response.json();
  assert.equal(response.status, 202, JSON.stringify(data));
  return data.data.jobId;
}
async function waitJob(id, expected = 'completed') {
  for (let i = 0; i < 400; i++) {
    const response = await fetch(base + '/jobs/' + id);
    const body = await response.json(); assert.equal(response.status, 200);
    assert.equal(body.data.input_path, undefined); assert.equal(body.data.input_sha256, undefined);
    if (body.data.status === expected) return body.data;
    if (body.data.status === 'failed' && expected !== 'failed') throw Error(body.data.error_message);
    await pause(50);
  }
  throw Error('Timed out waiting for job ' + id);
}
async function main() {
  await db.sequelize.authenticate();
  let child = await start();
  const socket = await connectSocket(); const events = [];
  socket.on('uploadProgress', event => events.push(event));
  const id = await upload(`domain,name\n${prefix}-a.example,A\n${prefix}-a.example,Duplicate\n,Missing\n${prefix}-b.example,B\n`);
  const done = await waitJob(id);
  assert.equal(done.processed_records, 4); assert.equal(done.unique_domains, 2);
  assert.equal(done.duplicate_domains, 1); assert.equal(done.failed_records, 1);
  await pause(100);
  assert(events.some(e => e.jobId === id && e.status === 'completed' && e.progress === 100));
  pass('HTTP multipart upload, persisted counts and real Socket.IO completion agree');
  const emptyId = await upload('domain,name\n', 'header-only.csv');
  assert.equal((await waitJob(emptyId)).total_records, 0);
  await pause(100);
  assert(events.some(e => e.jobId === emptyId && e.progress === 100 && e.status === 'completed'));
  pass('zero-row upload reports completed progress rather than remaining at zero');
  const second = spawn(process.execPath, ['index.js'], { env: { ...process.env, PORT: '18081' }, stdio: ['ignore', 'pipe', 'pipe'] });
  let secondLog = ''; second.stderr.on('data', b => { secondLog += b; });
  const secondExit = await Promise.race([new Promise(resolve => second.once('exit', resolve)), pause(10000).then(() => { second.kill('SIGKILL'); throw Error('Duplicate worker did not exit'); })]);
  assert.notEqual(secondExit, 0); assert.match(secondLog, /Another upload worker/);
  pass('second application instance cannot acquire the same database worker lock');

  const multiple = new FormData();
  for (let i = 0; i < 2; i++) multiple.append('files', new Blob([`domain\n${prefix}-multi-${i}.example\n`]), `multi-${i}.csv`);
  const multiResponse = await fetch(base + '/massive-data/csv-multiple-upload/safe', { method: 'POST', body: multiple });
  assert.equal(multiResponse.status, 202);
  const multi = await multiResponse.json();
  for (const job of multi.data.jobs) assert.equal((await waitJob(job.id)).unique_domains, 1);
  pass('multi-file HTTP route uses the same durable sequential queue');

  const noFile = await fetch(base + '/massive-data/csv-upload', { method: 'POST', body: new FormData() });
  assert.equal(noFile.status, 400);
  const badType = new FormData(); badType.append('file', new Blob(['text']), 'bad.txt');
  assert.equal((await fetch(base + '/massive-data/csv-upload', { method: 'POST', body: badType })).status, 400);
  pass('missing files and unsupported extension return controlled HTTP 400');
  const huge = new FormData(); huge.append('file', new Blob(['x'.repeat(10 * 1024 * 1024 + 1)]), 'too-large.csv');
  assert.equal((await fetch(base + '/massive-data/csv-upload', { method: 'POST', body: huge })).status, 413);
  pass('oversized upload is rejected with HTTP 413');

  let crashId;
  const crashSeen = new Promise(resolve => socket.on('uploadProgress', event => {
    if (event.jobId === crashId && event.processedRecords >= 1000 && event.status !== 'completed') {
      child.kill('SIGKILL'); resolve(event.processedRecords);
    }
  }));
  const content = 'domain\n' + Array.from({ length: 50000 }, (_, i) => `${prefix}-crash-${i}.example`).join('\n') + '\n';
  crashId = await upload(content, 'restart.csv');
  const committed = await Promise.race([crashSeen, pause(20000).then(() => { throw Error('No intermediate progress to interrupt'); })]);
  await stop(child, 'SIGKILL'); socket.close(); sockets.delete(socket);
  const interrupted = await db.uploadJob.findByPk(crashId);
  assert(interrupted.processed_records >= committed && interrupted.processed_records < 50000);
  child = await start();
  const recovered = await waitJob(crashId);
  assert.equal(recovered.processed_records, 50000); assert.equal(recovered.unique_domains, 50000);
  assert.equal(recovered.duplicate_domains, 0);
  pass('automatic application restart recovery completes interrupted HTTP job without replay inflation', { committedBeforeRestart: interrupted.processed_records, total: recovered.total_records });

  // Keep the worker idle by stopping the app, then add retained failed/pending fixtures.
  await stop(child);
  const { inputRoot, PersistentUploadService } = require('../app/services/persistent-upload.service');
  const crypto = require('node:crypto'); const path = require('node:path');
  const retryPath = path.join(inputRoot, crypto.randomUUID() + '.csv');
  const original = `domain\n${prefix}-retained.example\n`;
  fs.writeFileSync(retryPath, original);
  const queue = new PersistentUploadService();
  const [retained] = await queue.enqueue([{ path: retryPath, originalname: 'retained.csv' }]);
  fs.chmodSync(retryPath, 0o600); fs.writeFileSync(retryPath, original + `${prefix}-tampered.example\n`);
  child = await start();
  const rejected = await waitJob(retained.id, 'failed');
  assert.match(rejected.error_message, /checksum changed/); assert.equal(rejected.processed_records, 0);
  pass('changed retained input is rejected before importing any rows');
  fs.writeFileSync(retryPath, original); fs.chmodSync(retryPath, 0o400);
  const retried = await fetch(base + '/jobs/' + retained.id + '/retry', { method: 'POST' });
  assert.equal(retried.status, 202);
  const retryDone = await waitJob(retained.id);
  assert.equal(retryDone.unique_domains, 1); assert.equal(retryDone.retry_count, 1);
  pass('HTTP retry reuses retained verified input and preserves job identity');
  assert.equal((await fetch(base + '/jobs/' + retained.id + '/retry', { method: 'POST' })).status, 409);
  pass('completed jobs cannot be accidentally queued for retry');
  await stop(child);
}
main().catch(error => { results.push({ name: error.message, passed: false }); console.error(error); process.exitCode = 1; })
  .finally(async () => {
    for (const socket of sockets) socket.close();
    for (const child of children) await stop(child, 'SIGKILL');
    await db.sequelize.close();
    fs.mkdirSync('evidence', { recursive: true });
    fs.writeFileSync('evidence/stage2-http-queue.json', JSON.stringify({ date: new Date().toISOString(),
      automaticQueueRecoveryTested: true, httpUploadIntegrationTested: true, realBrowserTested: false,
      livePolicySyncTested: false, results }, null, 2), 'utf8');
  });
