// Explicit isolated staging only; never publishes to Kafka or activates live rules.
const db = require('../app/config/db.config');
const PolicyOutboxService = require('../app/services/policy-outbox.service');
async function main() {
  if (!/^\d+$/.test(process.argv[2] || '')) throw Error('Supply a completed retained upload job ID');
  console.log(JSON.stringify(await new PolicyOutboxService().stageCompletedUpload(Number(process.argv[2])), null, 2));
}
main().catch(error => { console.error(error.message); process.exitCode = 1; }).finally(() => db.sequelize.close());
