// Run only against the dedicated isolated database after installing locked dependencies.
const assert = require('node:assert/strict');
const { spawn, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { getIsolationConfig } = require('../app/config/isolation');
const config = getIsolationConfig();
const results = [];
const children = new Set();
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let db;

function run(args, env = process.env) {
  return spawnSync(process.execPath, args, { env, encoding: 'utf8', timeout: 20000 });
}
function passed(name) { results.push({ name, passed: true }); console.log('PASS ' + name); }
async function start() {
  const child = spawn(process.execPath, ['index.js'], { env: process.env, stdio: ['ignore', 'pipe', 'pipe'] });
  children.add(child);
  let log = '';
  child.stdout.on('data', b => { log = (log + b).slice(-6000); });
  child.stderr.on('data', b => { log = (log + b).slice(-6000); });
  for (let i = 0; i < 100; i++) {
    if (child.exitCode !== null) throw Error('Application exited before ready: ' + log);
    if (log.includes('Isolated server ready')) return child;
    await pause(100);
  }
  throw Error('Readiness timeout: ' + log);
}
async function stop(child) {
  if (child.exitCode === null && child.signalCode === null) {
    child.kill('SIGTERM');
    await new Promise(resolve => child.once('exit', resolve));
  }
  children.delete(child);
}
async function snapshot() {
  return {
    blacklist: JSON.stringify(await db.blacklist.findAll({ order: [['id', 'ASC']], raw: true })),
    jobs: JSON.stringify(await db.uploadJob.findAll({ order: [['id', 'ASC']], raw: true })),
    failures: JSON.stringify(await db.failedUpload.findAll({ order: [['id', 'ASC']], raw: true }))
  };
}
async function main() {
  const guards = run(['index.js'], { ...process.env, DB_NAME: 'test' });
  assert.notEqual(guards.status, 0); assert.match(guards.stderr, /isolated netpro_luthfi_test_/);
  passed('actual application rejects live database name before starting');
  let r = run(['scripts/initialize-isolated-schema.js', '--create-empty-test-schema']);
  assert.equal(r.status, 0, r.stderr); passed('explicit empty-database bootstrap succeeds');
  db = require('../app/config/db.config');
  await db.blacklist.create({ domain: 'startup-preservation.example', name: 'stage1 sentinel' });
  await db.uploadJob.create({ filename: 'stage1-sentinel.csv', status: 'completed', total_records: 1, processed_records: 1 });
  const before = await snapshot();
  r = run(['scripts/initialize-isolated-schema.js', '--create-empty-test-schema']);
  assert.notEqual(r.status, 0); assert.match(r.stderr, /database is not empty/);
  assert.deepEqual(await snapshot(), before); passed('bootstrap refuses existing database without changing records');
  for (let i = 1; i <= 2; i++) {
    const child = await start();
    const response = await fetch(`http://127.0.0.1:${config.port}/`);
    assert.equal(response.status, 200);
    passed(`Ubuntu application loads all routes and serves HTTP 200 (start ${i})`);
    await stop(child);
    assert.deepEqual(await snapshot(), before);
    passed(`database records and timestamps unchanged after start/stop ${i}`);
  }
}
main().catch(error => { results.push({ name: error.message, passed: false }); console.error(error); process.exitCode = 1; })
  .finally(async () => {
    for (const child of children) await stop(child);
    if (db) await db.sequelize.close();
    fs.mkdirSync('evidence', { recursive: true });
    fs.writeFileSync(path.join('evidence', 'stage1-linux.json'), JSON.stringify({
      date: new Date().toISOString(), database: config.database, liveNetProModified: false, results
    }, null, 2), 'utf8');
  });
