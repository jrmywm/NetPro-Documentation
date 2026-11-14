const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const db = require('../app/config/db.config');
async function snapshot() {
  const out = {};
  for (const table of ['blacklists', 'upload_jobs', 'failed_uploads']) {
    const [rows] = await db.sequelize.query(`SELECT COUNT(*)::int AS count,
      md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY id), '')) AS digest FROM "${table}" t`);
    out[table] = rows[0];
  }
  return out;
}
async function main() {
  const before = await snapshot();
  for (let i = 0; i < 2; i++) {
    const run = spawnSync(process.execPath, ['scripts/migrate-isolated-v2.js', '--apply'], { env: process.env, encoding: 'utf8', timeout: 20000 });
    assert.equal(run.status, 0, run.stderr);
    assert.deepEqual(await snapshot(), before);
  }
  fs.mkdirSync('evidence', { recursive: true });
  fs.writeFileSync('evidence/migration-v2.json', JSON.stringify({ passed: true,
    note: 'Idempotent migration replay preserves full-row hashes and counts; original addition already applied separately', snapshot: before }, null, 2), 'utf8');
  console.log('PASS migration replay twice preserves existing full-row hashes and counts');
}
main().catch(error => { console.error(error.message); process.exitCode = 1; }).finally(() => db.sequelize.close());
