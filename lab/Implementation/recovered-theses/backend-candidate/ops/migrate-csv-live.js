if (process.argv[2] !== '--apply-live-additive-schema' || process.env.NETPRO_ALLOW_LIVE_SCHEMA !== '1') throw Error('Explicit migration opt-in required');
const db = require('/home/netpro/NetPro-Backend/src/config/dpdkDatabase');
const { BulkPolicyService } = require('../src/integration/bulk-policy');
const { CsvImports } = require('../src/integration/csv-imports');
async function main() {
  if (db.getDatabaseName() !== 'test') throw Error('Unexpected database');
  await new CsvImports(new BulkPolicyService(db, null)).migrate();
  console.log('Additive CSV job/staging/failure schema ready; live policies unchanged.');
}
main().catch(e => { console.error(e.message); process.exitCode = 1; }).finally(() => db.close());
