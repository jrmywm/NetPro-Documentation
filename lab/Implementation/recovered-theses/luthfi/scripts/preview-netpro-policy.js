// Read-only contract preview. Deliberately has no backend credentials or publisher.
const { csvBatches } = require('../app/services/csv-batches');
const { toNetProPolicy } = require('../app/services/netpro-policy-contract');
async function main() {
  if (!process.argv[2]) throw Error('Supply a CSV path for read-only preview');
  let valid = 0, invalid = 0, domainOnly = 0;
  const examples = [], errors = [];
  for await (const batch of csvBatches(process.argv[2], 1000)) for (const row of batch) {
    try {
      if (row.error) throw Error(row.error);
      const policy = toNetProPolicy({ ...row.record, ip_add: row.original.ip_add });
      valid++; if (policy.ip_add === null) domainOnly++;
      if (examples.length < 3) examples.push(policy);
    } catch (error) { invalid++; if (errors.length < 10) errors.push({ record: row.rowNumber, message: error.message }); }
  }
  console.log(JSON.stringify({ mode: 'READ_ONLY_PREVIEW', policiesPublished: 0,
    valid, invalid, domainOnly, examples, errors,
    pendingGate: 'Durable publication and actual Policy Server application must be verified before live activation' }, null, 2));
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
