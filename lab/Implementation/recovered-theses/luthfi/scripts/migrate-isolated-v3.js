// Isolated phase-three persistence/publication prototype. Does not touch ps_blocked_list.
const db = require('../app/config/db.config');
async function main() {
  if (process.argv[2] !== '--apply') throw Error('Explicit --apply required');
  await db.sequelize.transaction(async transaction => {
    await db.sequelize.query('SELECT pg_advisory_xact_lock(20261030, 30)', { transaction });
    for (const sql of [
      `CREATE TABLE IF NOT EXISTS netpro_policy_candidates (
        id UUID PRIMARY KEY, domain VARCHAR(253) NOT NULL UNIQUE,
        payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())`,
      `CREATE TABLE IF NOT EXISTS netpro_policy_outbox (
        event_id UUID PRIMARY KEY, policy_id UUID NOT NULL UNIQUE REFERENCES netpro_policy_candidates(id),
        payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        published_at TIMESTAMPTZ, attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT)`,
      `CREATE TABLE IF NOT EXISTS netpro_import_policy_links (
        import_key VARCHAR(200) NOT NULL, domain VARCHAR(253) NOT NULL,
        policy_id UUID NOT NULL REFERENCES netpro_policy_candidates(id), PRIMARY KEY(import_key, domain))`,
      `CREATE INDEX IF NOT EXISTS netpro_outbox_pending ON netpro_policy_outbox(created_at) WHERE published_at IS NULL`
    ]) await db.sequelize.query(sql, { transaction });
  });
  console.log('Isolated v3 candidate-policy/outbox schema ready. Live policies unchanged.');
}
main().catch(error => { console.error(error.message); process.exitCode = 1; }).finally(() => db.sequelize.close());
