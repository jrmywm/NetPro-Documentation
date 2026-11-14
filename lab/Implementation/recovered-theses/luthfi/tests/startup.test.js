const { test } = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { getIsolationConfig } = require('../app/config/isolation');
const { startServer } = require('../app/services/startup.service');
const good = { NETPRO_ISOLATED_TEST: '1', DB_NAME: 'netpro_luthfi_test_stage1',
  DB_USER: 'netpro_luthfi_test', DB_PASSWORD: 'test-only-placeholder' };

test('isolated configuration binds application to loopback', () => {
  assert.equal(getIsolationConfig(good).bindHost, '127.0.0.1');
});
for (const [name, change] of [
  ['missing opt-in', { NETPRO_ISOLATED_TEST: '' }],
  ['live database name', { DB_NAME: 'test' }],
  ['superuser role', { DB_USER: 'postgres' }],
  ['missing password', { DB_PASSWORD: '' }],
  ['remote database', { DB_HOST: '192.168.31.35' }],
  ['production port', { PORT: '3000' }],
  ['invalid port', { PORT: 'NaN' }]
]) test(`rejects ${name}`, () => assert.throws(() => getIsolationConfig({ ...good, ...change })));

function fixtures(failure) {
  const calls = [];
  const db = { sequelize: {
    authenticate: async () => { calls.push('authenticate'); if (failure === 'connection') throw Error('offline'); },
    sync: () => { throw Error('startup must never synchronize schema'); }
  }};
  for (const name of ['blacklist', 'account', 'uploadJob', 'failedUpload']) {
    db[name] = { findOne: async () => { calls.push(name); if (failure === name) throw Error('missing table'); },
      sync: () => { throw Error('startup must never synchronize models'); } };
  }
  const server = new EventEmitter();
  server.listen = (port, host) => {
    calls.push(`listen:${host}:${port}`);
    queueMicrotask(() => server.emit(failure === 'listen' ? 'error' : 'listening', Error('port in use')));
  };
  return { db, server, calls, port: 18080, host: '127.0.0.1' };
}
test('listens only after every database readiness check; no schema sync', async () => {
  const f = fixtures(); await startServer(f);
  assert.deepEqual(f.calls, ['authenticate', 'blacklist', 'account', 'uploadJob', 'failedUpload', 'listen:127.0.0.1:18080']);
});
for (const failure of ['connection', 'uploadJob']) {
  test(`does not listen on ${failure} failure`, async () => {
    const f = fixtures(failure); await assert.rejects(startServer(f));
    assert.equal(f.calls.some(x => x.startsWith('listen:')), false);
  });
}
test('propagates port conflict without claiming readiness', async () => {
  await assert.rejects(startServer(fixtures('listen')), /port in use/);
});
