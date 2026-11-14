const db = require('../app/config/db.config');
const BoundedUploadService = require('../app/services/bounded-upload.service');
const service = new BoundedUploadService({ batchSize: 2,
  afterBatch: process.argv.includes('--exit-after-first-commit') ? () => process.exit(86) : undefined });
service.process(process.argv[2], Number(process.argv[3]))
  .then(() => { console.log('Completed retained-input job'); })
  .catch(error => { console.error(error.message); process.exitCode = 1; })
  .finally(() => db.sequelize.close());
