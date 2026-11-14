// Explicit bootstrap of a NEW isolated database, not a production migration.
const db = require('../app/config/db.config');
async function main() {
  if (process.argv[2] !== '--create-empty-test-schema') throw new Error('Explicit --create-empty-test-schema argument required');
  await db.sequelize.authenticate();
  const tables = await db.sequelize.getQueryInterface().showAllTables();
  if (tables.length !== 0) throw new Error('Refusing schema bootstrap: database is not empty');
  await db.sequelize.sync(); // No force/alter; only the explicit empty-database bootstrap.
  console.log('Created isolated test schema. Startup never modifies schema.');
}
main().catch(error => { console.error(error.message); process.exitCode = 1; })
  .finally(() => db.sequelize.close());
