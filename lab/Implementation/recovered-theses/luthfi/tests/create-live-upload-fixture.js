// Creates an isolated HTTP upload only. A separate explicit operator command activates it.
const { spawn } = require('node:child_process');
const { randomBytes } = require('node:crypto');
const db = require('../app/config/db.config');
const { getIsolationConfig } = require('../app/config/isolation');
const config = getIsolationConfig();
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let child;
async function main() {
  let log = '';
  child = spawn(process.execPath, ['index.js'], { env: process.env, stdio: ['ignore', 'pipe', 'pipe'] });
  child.stdout.on('data', b => { log = (log + b).slice(-4000); }); child.stderr.on('data', b => { log = (log + b).slice(-4000); });
  for (let i = 0; i < 100; i++) {
    if (log.includes('Isolated server ready')) break;
    if (child.exitCode !== null) throw Error(log);
    if (i === 99) throw Error('Candidate readiness timeout');
    await pause(100);
  }
  const suffix = randomBytes(6).toString('hex');
  const rows = [{ domain: 'csv-ip-' + suffix + '.example', ip_add: '192.0.2.242' }, { domain: 'csv-domain-' + suffix + '.example', ip_add: null }];
  const content = 'domain,ip_add,category\n' + [...rows, rows[0]].map(r => `${r.domain},${r.ip_add || ''},Other`).join('\n') + '\n';
  const form = new FormData(); form.append('file', new Blob([content]), 'owned-live-flow.csv');
  const response = await fetch(`http://127.0.0.1:${config.port}/massive-data/csv-upload`, { method: 'POST', body: form });
  if (response.status !== 202) throw Error(await response.text());
  const id = (await response.json()).data.jobId;
  for (let i = 0; i < 200; i++) {
    const job = await db.uploadJob.findByPk(id);
    if (job.status === 'failed') throw Error(job.error_message);
    if (job.status === 'completed') {
      if (job.unique_domains !== 2 || job.duplicate_domains !== 1 || job.failed_records !== 0) throw Error('Upload accounting mismatch');
      console.log(JSON.stringify({ jobId: id, rows, total: job.total_records, unique: job.unique_domains, duplicate: job.duplicate_domains })); return;
    }
    await pause(100);
  }
  throw Error('Upload completion timeout');
}
main().catch(error => { console.error(error.message); process.exitCode = 1; }).finally(async () => {
  if (child && child.exitCode === null && child.signalCode === null) { const ended = new Promise(resolve => child.once('exit', resolve)); child.kill('SIGTERM'); await ended; }
  await db.sequelize.close();
});
