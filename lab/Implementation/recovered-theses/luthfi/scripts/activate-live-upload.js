// Explicit operator bridge for small verification uploads. No automatic publication.
// The 20-row cap deliberately prevents accidental activation of retained bulk fixtures.
const fs = require('node:fs');
const path = require('node:path');
const https = require('node:https');
const { X509Certificate } = require('node:crypto');
const db = require('../app/config/db.config');
const { csvBatches } = require('../app/services/csv-batches');
const { digest } = require('../app/services/persistent-upload.service');
const { toNetProPolicy } = require('../app/services/netpro-policy-contract');
const mode = process.argv[2], id = process.argv[3];
const base = path.resolve(__dirname, '..');
function api(endpoint, method = 'GET', body) {
  const env = Object.fromEntries(fs.readFileSync('/etc/netpro/bulk-import.env', 'utf8').split('\n').filter(l => l.includes('=')).map(l => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)]));
  const ca = fs.readFileSync('/home/ubuntu/cert/server.crt');
  const pin = new X509Certificate(ca).fingerprint256;
  return new Promise((resolve, reject) => {
    const request = https.request({ hostname: '127.0.0.1', port: 3000, path: endpoint, method, ca,
      checkServerIdentity: (_host, cert) => cert.fingerprint256 === pin ? undefined : Error('Backend certificate pin mismatch'),
      headers: { Authorization: 'Bearer ' + env.NETPRO_BULK_IMPORT_TOKEN, 'Content-Type': 'application/json' } }, response => {
      let text = ''; response.on('data', b => { text += b; });
      response.on('end', () => { try {
        const value = JSON.parse(text);
        if (response.statusCode < 200 || response.statusCode >= 300) reject(Error(value.message || 'Backend import failed'));
        else resolve(value);
      } catch (e) { reject(e); } });
    });
    request.setTimeout(10000, () => request.destroy(Error('Backend timeout')));
    request.on('error', reject); request.end(body === undefined ? undefined : JSON.stringify(body));
  });
}
async function main() {
  if (!/^\d+$/.test(id || '') || !['--activate-live', '--cleanup-live'].includes(mode)) throw Error('Explicit --activate-live JOB_ID or --cleanup-live JOB_ID required');
  const receiptPath = path.join(base, 'evidence', 'live-upload-' + id + '.json');
  if (mode === '--cleanup-live') {
    const receipt = JSON.parse(fs.readFileSync(receiptPath, 'utf8'));
    if (!receipt.importKey.startsWith('netpro-upload-' + id + '-')) throw Error('Invalid upload ownership receipt');
    console.log(JSON.stringify(await api('/ps/import-policy-batch/' + receipt.importKey, 'DELETE'))); return;
  }
  const job = await db.uploadJob.findByPk(Number(id));
  if (!job || job.status !== 'completed' || !job.input_path || job.failed_records) throw Error('A completed retained upload with no failed records is required');
  if (job.total_records < 1 || job.total_records > 20) throw Error('Verification bridge accepts only 1..20 rows; bulk activation is not enabled');
  if (await digest(job.input_path) !== job.input_sha256) throw Error('Retained input checksum changed');
  const rows = [];
  for await (const batch of csvBatches(job.input_path, 20)) for (const row of batch) {
    if (row.error) throw Error(row.error);
    rows.push(toNetProPolicy({ ...row.record, ip_add: row.original.ip_add }));
  }
  if (rows.length !== job.total_records || await digest(job.input_path) !== job.input_sha256) throw Error('Input changed before activation');
  const importKey = 'netpro-upload-' + id + '-' + job.input_sha256.slice(0, 16);
  const receipt = { jobId: Number(id), importKey, acceptedRows: rows.length, applicationVerified: false };
  fs.mkdirSync(path.dirname(receiptPath), { recursive: true });
  fs.writeFileSync(receiptPath, JSON.stringify(receipt), { mode: 0o600 });
  const result = await api('/ps/import-policy-batch', 'POST', { importKey, rows });
  let status;
  for (let i = 0; i < 30; i++) {
    status = await api('/ps/import-policy-batch/' + importKey);
    if (status.published === status.stored || status.existing_unverified > 0) break;
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  if (status.published !== status.stored && !status.existing_unverified) throw Error('Publication remains pending; ownership receipt retained');
  Object.assign(receipt, { rows: result.rows, ...status, state: status.existing_unverified ? 'existing_unverified' : 'published_not_application_acknowledged' });
  fs.writeFileSync(receiptPath, JSON.stringify(receipt, null, 2), { mode: 0o600 });
  console.log(JSON.stringify(receipt));
}
main().catch(error => { console.error(error.message); process.exitCode = 1; }).finally(() => db.sequelize.close());
