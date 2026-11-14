// Integration staging only: never connect this recovered app to live NetPro data.
function getIsolationConfig(env = process.env) {
  if (env.NETPRO_ISOLATED_TEST !== '1') throw new Error('NETPRO_ISOLATED_TEST=1 required; live integration is not enabled');
  if (!/^netpro_luthfi_test_[a-z0-9_]+$/.test(env.DB_NAME || '')) throw new Error('DB_NAME must use isolated netpro_luthfi_test_ prefix');
  if (env.DB_USER !== 'netpro_luthfi_test') throw new Error('Dedicated netpro_luthfi_test database role required');
  if (!env.DB_PASSWORD) throw new Error('DB_PASSWORD required');
  if (!['127.0.0.1', 'localhost'].includes(env.DB_HOST || '127.0.0.1')) throw new Error('Database must be loopback-only');
  const port = Number(env.PORT || 18080);
  if (!Number.isInteger(port) || port < 18080 || port > 18089) throw new Error('Application port must be 18080..18089');
  return { database: env.DB_NAME, username: env.DB_USER, password: env.DB_PASSWORD,
    host: env.DB_HOST || '127.0.0.1', dbPort: 5432, bindHost: '127.0.0.1', port };
}
module.exports = { getIsolationConfig };
