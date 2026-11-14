const { BulkPolicyService, createRouter } = require('./bulk-policy');
module.exports = async function bootstrap(app, db, producer, env = process.env) {
  if (env.NETPRO_BULK_IMPORT_ENABLED !== '1') return;
  if (!env.NETPRO_BULK_IMPORT_TOKEN || env.NETPRO_BULK_IMPORT_TOKEN.length < 32) throw Error('Private bulk-import authorization token is required');
  const service = new BulkPolicyService(db, producer);
  await service.ready(); // Never migrate schemas at application startup.
  app.use('/ps/import-policy-batch', createRouter(service, env.NETPRO_BULK_IMPORT_TOKEN));
  service.start();
  app.locals.bulkPolicyService = service;
  if (env.NETPRO_CSV_UPLOAD_ENABLED === '1') {
    const { CsvImports, createCsvRouter } = require('./csv-imports');
    const { authMiddleware } = require('../middleware/authMiddleware');
    const imports = new CsvImports(service);
    await imports.ready(); await imports.start();
    app.use('/ps/csv-imports', createCsvRouter(imports, authMiddleware));
    app.locals.csvImportService = imports;
  }
  console.log('Guarded bulk-policy adapter ready; publication is not application acknowledgement');
};
