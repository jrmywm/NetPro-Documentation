const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const db = require('../app/config/db.config');
async function main() {
  const job = await db.uploadJob.findOne({ where: { total_records: { [db.Sequelize.Op.gt]: 20 }, status: 'completed' } });
  if (!job) throw Error('Retained large fixture required for activation-cap test');
  const result = spawnSync(process.execPath, ['scripts/activate-live-upload.js', '--activate-live', String(job.id)], { env: process.env, encoding: 'utf8', timeout: 15000 });
  assert.notEqual(result.status, 0); assert.match(result.stderr, /Verification bridge accepts only 1\.\.20 rows/);
  console.log('PASS retained large import is refused before any live activation request');
}
main().catch(e => { console.error(e.message); process.exitCode = 1; }).finally(() => db.sequelize.close());
