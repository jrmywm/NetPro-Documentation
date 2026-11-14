const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { once } = require('node:events');
const { spawnSync } = require('node:child_process');
const db = require('../app/config/db.config');
const BoundedUploadService = require('../app/services/bounded-upload.service');
const { csvBatches } = require('../app/services/csv-batches');
const results = [];
const prefix = `t${Date.now()}`;
const fixtureDir = fs.mkdtempSync(path.join(os.tmpdir(), 'netpro-luthfi-stage2-'));
function pass(name, details) { results.push({ name, passed: true, details }); console.log('PASS ' + name); }
function fixture(name, content) { const p = path.join(fixtureDir, name); fs.writeFileSync(p, content, 'utf8'); return p; }
async function job(name) { return db.uploadJob.create({ filename: name, status: 'queued' }); }
function check(j, total, inserted, duplicate, failed) {
  assert.equal(j.status, 'completed'); assert.equal(j.total_records, total);
  assert.equal(j.processed_records, total); assert.equal(j.unique_domains, inserted);
  assert.equal(j.duplicate_domains, duplicate); assert.equal(j.failed_records, failed);
  assert.equal(j.processed_records, j.unique_domains + j.duplicate_domains + j.failed_records);
}
async function main() {
  await db.sequelize.authenticate();
  await db.blacklist.create({ domain: `${prefix}-existing.example` });
  const f = fixture('mixed.csv', `domain,name\n${prefix}-a.example,A\n${prefix}-b.example,B\n${prefix}-a.example,A again\n${prefix}-existing.example,Existing\n,Missing\nhttps://example.com,URL not hostname\n`);
  const j = await job('mixed.csv');
  const events = [];
  global.io = { emit: (name, data) => events.push({ name, ...data }) };
  const service = new BoundedUploadService({ batchSize: 2 });
  check(await service.process(f, j.id), 6, 2, 2, 2);
  const failures = await db.failedUpload.findAll({ where: { job_id: j.id }, order: [['row_number', 'ASC']] });
  assert.deepEqual(failures.map(row => row.row_number), [6, 7]);
  assert.equal(events.at(-1).progress, 100);
  pass('mixed valid/duplicate/invalid rows have exact accounting and original CSV line numbers');
  const first = await db.uploadJob.findByPk(j.id, { raw: true });
  await service.process(f, j.id);
  assert.deepEqual(await db.uploadJob.findByPk(j.id, { raw: true }), first);
  pass('completed-job replay does not change counters or timestamps');

  const header = fixture('header-only.csv', 'domain,name\n');
  const empty = await job('header-only.csv');
  check(await service.process(header, empty.id), 0, 0, 0, 0);
  pass('header-only CSV completes with zero records');

  const interrupted = fixture('resume.csv', 'domain\n' + Array.from({ length: 7 }, (_, i) => `${prefix}-resume-${i}.example`).join('\n') + '\n');
  const resumeJob = await job('resume.csv');
  let r = spawnSync(process.execPath, ['tests/bounded-worker.js', interrupted, String(resumeJob.id), '--exit-after-first-commit'], { encoding: 'utf8', timeout: 20000 });
  assert.equal(r.status, 86, r.stderr);
  const checkpoint = await db.uploadJob.findByPk(resumeJob.id);
  assert.equal(checkpoint.processed_records, 2); assert.equal(checkpoint.unique_domains, 2);
  r = spawnSync(process.execPath, ['tests/bounded-worker.js', interrupted, String(resumeJob.id)], { encoding: 'utf8', timeout: 20000 });
  assert.equal(r.status, 0, r.stderr);
  check(await db.uploadJob.findByPk(resumeJob.id), 7, 7, 0, 0);
  pass('separate worker resumes after forced process exit with retained input and committed checkpoint');
  const committed = await job('already-committed.csv');
  await service.process(interrupted, committed.id);
  await db.uploadJob.update({ status: 'failed' }, { where: { id: committed.id } });
  const resumedFinal = await service.process(interrupted, committed.id);
  check(resumedFinal, 7, 0, 7, 0);
  pass('resume after the final data commit still reaches completed status');

  const overlap = 'domain\n' + Array.from({ length: 20 }, (_, i) => `${prefix}-shared-${i}.example`).join('\n') + '\n';
  const fa = fixture('parallel-a.csv', overlap), fb = fixture('parallel-b.csv', overlap);
  const ja = await job('parallel-a.csv'), jb = await job('parallel-b.csv');
  await Promise.all([service.process(fa, ja.id), service.process(fb, jb.id)]);
  const a = await db.uploadJob.findByPk(ja.id), b = await db.uploadJob.findByPk(jb.id);
  check(a, 20, a.unique_domains, a.duplicate_domains, 0); check(b, 20, b.unique_domains, b.duplicate_domains, 0);
  assert.equal(a.unique_domains + b.unique_domains, 20);
  assert.equal(a.duplicate_domains + b.duplicate_domains, 20);
  pass('overlapping concurrent jobs attribute actual inserts and duplicates correctly');

  const largePath = path.join(fixtureDir, 'large.csv');
  const stream = fs.createWriteStream(largePath);
  stream.write('domain,name\n');
  for (let i = 0; i < 100000; i++) {
    if (!stream.write(`${prefix}-large-${i}.example,Name ${i}\n`)) await once(stream, 'drain');
  }
  stream.end(); await once(stream, 'finish');
  let rows = 0, maxBatch = 0, maxRss = process.memoryUsage().rss;
  for await (const batch of csvBatches(largePath, 1000)) {
    rows += batch.length; maxBatch = Math.max(maxBatch, batch.length);
    maxRss = Math.max(maxRss, process.memoryUsage().rss);
  }
  assert.equal(rows, 100000); assert.equal(maxBatch, 1000);
  pass('100,000-row parser fixture yields batches no larger than 1,000', { rows, maxBatch, observedProcessRssMiB: +(maxRss / 1048576).toFixed(2), note: 'Observed parser-process RSS, not a universal memory bound or full upload throughput benchmark' });
  const largeJob = await job('large.csv');
  check(await new BoundedUploadService({ batchSize: 1000 }).process(largePath, largeJob.id), 100000, 100000, 0, 0);
  pass('100,000-row PostgreSQL import completes with exact persisted accounting');
}
main().catch(error => { results.push({ name: error.message, passed: false }); console.error(error); process.exitCode = 1; })
  .finally(async () => {
    delete global.io;
    await db.sequelize.close();
    fs.mkdirSync('evidence', { recursive: true });
    fs.writeFileSync('evidence/stage2-bounded.json', JSON.stringify({ date: new Date().toISOString(),
      fixtureDir, automaticQueueRecoveryTested: false, httpUploadIntegrationTested: false, results }, null, 2), 'utf8');
  });
