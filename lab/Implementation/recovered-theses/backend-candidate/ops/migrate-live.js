// Explicit live additive migration, invoked only after deployment has made a DB backup.
if (process.argv[2] !== '--apply-live-additive-schema' || process.env.NETPRO_ALLOW_LIVE_SCHEMA !== '1') throw Error('Explicit live migration opt-in required');
const root = '/home/netpro/NetPro-Backend';
const db = require(root + '/src/config/dpdkDatabase');
const { BulkPolicyService } = require('../src/integration/bulk-policy');
async function main() {
  if (db.getDatabaseName() !== 'test') throw Error('Unexpected authoritative database');
  const info = await db.getQueryInterface().describeTable('ps_blocked_list');
  if (!/UUID/i.test(info.id.type)) throw Error('Unexpected policy ID schema');
  await new BulkPolicyService(db, null).migrate();
  console.log('Authoritative additive outbox schema ready; existing policy rows unchanged.');
}
main().catch(e => { console.error(e.message); process.exitCode = 1; }).finally(() => db.close());
