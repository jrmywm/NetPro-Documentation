// Explicit additive migration; protected by the isolated DB configuration guard.
const db = require('../app/config/db.config');
async function main() {
  if (process.argv[2] !== '--apply') throw Error('Explicit --apply required');
  await db.sequelize.authenticate();
  await db.sequelize.transaction(async transaction => {
    await db.sequelize.query('SELECT pg_advisory_xact_lock(20261030, 20)', { transaction });
    const qi = db.sequelize.getQueryInterface();
    const columns = await qi.describeTable('upload_jobs', { transaction });
    for (const [name, type] of [['input_path', db.Sequelize.TEXT], ['input_sha256', db.Sequelize.STRING(64)], ['input_batch_size', db.Sequelize.INTEGER]]) {
      if (!columns[name]) await qi.addColumn('upload_jobs', name, { type, allowNull: true }, { transaction });
    }
  });
  console.log('Isolated v2 additive migration applied; existing rows preserved.');
}
main().catch(error => { console.error(error.message); process.exitCode = 1; }).finally(() => db.sequelize.close());
