// All SQL uses the guarded isolated database, never the live backend connection.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const { randomUUID } = require('node:crypto');
const db = require('../app/config/db.config');
const { BulkPolicyService, createRouter } = require('../../backend-candidate/src/integration/bulk-policy');
const results = [], sent = [];
const prefix = 'authoritative' + Date.now();
let server, unavailable = false;
const producer = { send: async request => { if (unavailable) throw Error('test broker outage'); sent.push(request); } };
const service = new BulkPolicyService(db.sequelize, producer);
function pass(name) { results.push({ name, passed: true }); console.log('PASS ' + name); }
async function main() {
  await db.sequelize.query(`CREATE TABLE IF NOT EXISTS ps_blocked_list(
    id UUID PRIMARY KEY,name VARCHAR(255) NOT NULL,domain VARCHAR(255) NOT NULL,
    ip_add VARCHAR(255),category VARCHAR(255) NOT NULL,hit_count INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMPTZ NOT NULL,"updatedAt" TIMESTAMPTZ NOT NULL)`);
  await service.migrate(); await service.migrate(); await service.ready();
  pass('explicit additive adapter migration is repeatable in isolated schema');
  const rows = [{ domain: prefix + '.example', ip_add: '192.0.2.21' }, { domain: prefix + '-domain.example' }];
  await assert.rejects(service.store(prefix, rows, { beforeCommit: async () => { throw Error('transaction fault'); } }));
  const [none] = await service.q('SELECT count(*)::int AS n FROM ps_blocked_list WHERE domain=$1', [rows[0].domain]);
  assert.equal(none.n, 0); assert.equal((await service.status(prefix)).stored, 0);
  pass('authoritative-model rows and publication receipts roll back together');
  const first = await service.store(prefix, rows), replay = await service.store(prefix, rows);
  assert.deepEqual(first.map(r => r.id), replay.map(r => r.id)); assert(replay.every(r => r.replay));
  assert.deepEqual(await service.status(prefix), { stored: 2, published: 0, existing_unverified: 0, applied: null, applicationVerified: false });
  pass('batch replay preserves UUIDs and one publication event per created policy');
  await assert.rejects(service.store(prefix, [{ ...rows[0], ip_add: '192.0.2.22' }]), /different policy fields/);
  await assert.rejects(service.store(prefix + '-bad', [{ domain: 'x'.repeat(63) + '.' + 'y'.repeat(63) + '.' + 'z'.repeat(50) + '.example' }]), /capacity/);
  pass('conflicting replay and current-consumer oversized rules fail explicitly');
  const parallelRows = [{ domain: prefix + '-parallel.example', ip_add: '192.0.2.23' }];
  const parallel = await Promise.all([service.store(prefix + '-parallel', parallelRows), service.store(prefix + '-parallel', parallelRows)]);
  assert.equal(parallel[0][0].id, parallel[1][0].id);
  pass('concurrent identical imports reuse the same authoritative-model row');
  unavailable = true; await assert.rejects(service.publishOne(), /broker outage/); unavailable = false;
  assert.equal((await service.status(prefix)).published, 0);
  await assert.rejects(service.publishOne({ afterSend: async () => { throw Error('post-ack fault'); } }));
  await service.publishOne();
  assert.equal(sent[0].messages[0].headers['netpro-event-id'], sent[1].messages[0].headers['netpro-event-id']);
  while (await service.publishOne()) {}
  const empty = sent.map(x => JSON.parse(x.messages[0].value)).find(x => x.createdBlockedList.domain === rows[1].domain);
  assert.equal(empty.createdBlockedList.ip_add, '');
  const [semantic] = await service.q('SELECT ip_add FROM ps_blocked_list WHERE domain=$1', [rows[1].domain]);
  assert.equal(semantic.ip_add, null);
  assert.equal((await service.status(prefix)).published, 2);
  pass('pending retries retain stable events; null database IP maps to string-only wire compatibility');
  const baseline = { domain: prefix + '-existing.example', ip_add: '192.0.2.24' };
  const baselineId = randomUUID();
  await service.q(`INSERT INTO ps_blocked_list(id,name,domain,ip_add,category,"createdAt","updatedAt")
    VALUES($1,'Existing metadata',$2,$3,'Other',NOW(),NOW())`, [baselineId, baseline.domain, baseline.ip_add]);
  const adopted = await service.store(prefix + '-adopt', [baseline]); assert.equal(adopted[0].created, false);
  assert.equal((await service.status(prefix + '-adopt')).existing_unverified, 1);
  assert.equal((await service.removeOwned(prefix + '-adopt')).length, 0);
  assert.equal((await service.q('SELECT id FROM ps_blocked_list WHERE id=$1', [baselineId])).length, 1);
  pass('pre-existing rules keep their metadata and cannot be removed by import cleanup');

  const app = require('express')(); app.use(require('express').json());
  const token = 'test-only-' + randomUUID(); app.use('/bulk', createRouter(service, token));
  server = http.createServer(app); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const url = 'http://127.0.0.1:' + server.address().port + '/bulk';
  assert.equal((await fetch(url + '/' + prefix)).status, 401);
  const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token }, body: JSON.stringify({ importKey: prefix, rows }) });
  assert.equal(response.status, 202); assert.equal((await response.json()).applicationVerified, false);
  pass('HTTP adapter requires authorization and never confuses publication with application');
  const deleted = await service.removeOwned(prefix); assert.equal(deleted.length, 2);
  while (await service.publishOne()) {}
  const deletions = sent.map(x => JSON.parse(x.messages[0].value)).filter(x => x.type === 'delete');
  assert.equal(deletions.length, 2); assert(deletions.some(x => x.deletedBlockedList.ip_add === ''));
  assert.equal((await service.status(prefix)).stored, 0);
  pass('owned-rule cleanup persists delete events and preserves domain-only wire semantics');
  const edited = await service.store(prefix + '-edited', [{ domain: prefix + '-edited.example' }]);
  await service.q('UPDATE ps_blocked_list SET name=$2 WHERE id=$1', [edited[0].id, 'Manually edited policy']);
  await assert.rejects(service.removeOwned(prefix + '-edited'), /changed since import/);
  assert.equal((await service.q('SELECT id FROM ps_blocked_list WHERE id=$1', [edited[0].id])).length, 1);
  await service.q('UPDATE ps_blocked_list SET name=domain WHERE id=$1', [edited[0].id]);
  await service.removeOwned(prefix + '-edited'); while (await service.publishOne()) {}
  pass('import removal refuses rules manually edited after activation');
}
main().catch(error => { results.push({ name: error.message, passed: false }); console.error(error); process.exitCode = 1; })
  .finally(async () => {
    if (server) { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
    await db.sequelize.close(); fs.mkdirSync('evidence', { recursive: true });
    fs.writeFileSync('evidence/stage4-authoritative-adapter.json', JSON.stringify({ date: new Date().toISOString(),
      database: 'isolated only', kafka: 'injected test producer; no live publication', results }, null, 2), 'utf8');
  });
