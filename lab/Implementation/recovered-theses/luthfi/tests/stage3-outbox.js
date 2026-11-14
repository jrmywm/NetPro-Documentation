const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const db = require('../app/config/db.config');
const PolicyOutboxService = require('../app/services/policy-outbox.service');
const prefix = `outbox${Date.now()}`;
const topic = 'netpro-integration-test-outbox-20261030';
const service = new PolicyOutboxService();
const results = [];
function pass(name, details) { results.push({ name, passed: true, details }); console.log('PASS ' + name); }
async function main() {
  const input = { domain: prefix + '.example', ip_add: '192.0.2.10', category: 'Other' };
  await assert.rejects(service.stage(prefix + '-rollback', input, { beforeCommit: async () => { throw Error('simulated persistence failure'); } }));
  const [missing] = await db.sequelize.query('SELECT count(*)::int AS n FROM netpro_policy_candidates WHERE domain=$1', {
    bind: [input.domain], type: db.Sequelize.QueryTypes.SELECT });
  assert.equal(missing.n, 0);
  pass('policy and outbox roll back atomically on persistence failure');

  const policy = await service.stage(prefix, input);
  const replay = await service.stage(prefix, input);
  assert.equal(policy.id, replay.id); assert.equal(replay.created, false);
  assert.deepEqual(await service.status(prefix), { stored: 1, published: 0, applied: null, applicationVerified: false });
  pass('replayed import creates one stable candidate policy and pending event');
  await assert.rejects(service.stage(prefix, { ...input, name: 'conflicting replacement' }), /explicit update/);
  pass('conflicting policy data does not silently overwrite an existing domain');

  const { PersistentUploadService, inputRoot } = require('../app/services/persistent-upload.service');
  const BoundedUploadService = require('../app/services/bounded-upload.service');
  fs.mkdirSync(inputRoot, { recursive: true, mode: 0o700 });
  const inputPath = path.join(inputRoot, randomUUID() + '.csv');
  fs.writeFileSync(inputPath, `domain,ip_add,category\n${prefix}-upload.example,192.0.2.12,other\n${prefix}-upload.example,192.0.2.12,other\n,192.0.2.13,Other\n`);
  const [upload] = await new PersistentUploadService().enqueue([{ path: inputPath, originalname: 'outbox-input.csv' }]);
  await new BoundedUploadService().process(inputPath, upload.id);
  const staged = await service.stageCompletedUpload(upload.id);
  assert.equal(staged.acceptedRows, 2); assert.equal(staged.rejectedRows, 1);
  assert.equal(staged.stored, 1); assert.equal(staged.published, 0);
  assert.equal((await service.stageCompletedUpload(upload.id)).stored, 1);
  pass('retained completed upload maps to one idempotent pending policy despite duplicate/invalid rows');

  let messages = [];
  const unavailable = { send: async () => { throw Error('simulated broker outage'); } };
  await assert.rejects(service.dispatchOne(unavailable, topic, { policyId: policy.id }), /broker outage/);
  assert.equal((await service.status(prefix)).published, 0);
  pass('broker failure retains durable pending publication');
  const fake = { send: async request => { messages.push(request); } };
  await assert.rejects(service.dispatchOne(fake, 'dpdk-blocked-list'), /isolated integration-test/);
  pass('prototype refuses the live policy topic');
  await assert.rejects(service.dispatchOne(fake, topic, { policyId: policy.id, afterSend: async () => { throw Error('simulated crash after broker ack'); } }));
  assert.equal((await service.status(prefix)).published, 0);
  const published = await service.dispatchOne(fake, topic, { policyId: policy.id });
  assert.equal(messages[0].messages[0].headers['netpro-event-id'], messages[1].messages[0].headers['netpro-event-id']);
  assert.equal(published.state, 'published');
  const wire = JSON.parse(messages[1].messages[0].value);
  assert.equal(wire.createdBlockedList.id, policy.id); assert.equal(wire.type, 'create');
  assert.deepEqual(await service.status(prefix), { stored: 1, published: 1, applied: null, applicationVerified: false });
  pass('ack/commit interruption replays stable event IDs without claiming exactly-once or applied state');

  const real = await service.stage(prefix + '-real', { domain: prefix + '-real.example', ip_add: '192.0.2.11' });
  const { Kafka, logLevel } = require('/home/netpro/NetPro-Backend/node_modules/kafkajs');
  const kafka = new Kafka({ clientId: prefix, brokers: ['127.0.0.1:9092'], logLevel: logLevel.NOTHING });
  const admin = kafka.admin(), producer = kafka.producer(), consumer = kafka.consumer({ groupId: prefix });
  try {
    await admin.connect(); await admin.createTopics({ topics: [{ topic, numPartitions: 1, replicationFactor: 1 }] });
    await producer.connect();
    const delivered = await service.dispatchOne(producer, topic, { policyId: real.id });
    assert.equal(delivered.policyId, real.id);
    await consumer.connect(); await consumer.subscribe({ topic, fromBeginning: true });
    let resolveSeen;
    const seen = new Promise(resolve => { resolveSeen = resolve; });
    await consumer.run({ eachMessage: async ({ message }) => {
      const payload = JSON.parse(message.value.toString());
      if (payload.createdBlockedList.id === real.id) resolveSeen({ eventId: message.headers['netpro-event-id'].toString(), payload });
    }});
    let timer;
    const received = await Promise.race([seen, new Promise((_resolve, reject) => { timer = setTimeout(() => reject(Error('Kafka consume timeout')), 15000); })]).finally(() => clearTimeout(timer));
    assert.equal(received.eventId, delivered.eventId);
    assert.equal(received.payload.createdBlockedList.domain, prefix + '-real.example');
    assert.equal((await service.status(prefix + '-real')).published, 1);
    pass('real Kafka acknowledged event is consumed from isolated topic with matching policy/event IDs', { topic, policyId: real.id });
  } finally {
    await consumer.disconnect(); await producer.disconnect(); await admin.disconnect();
  }
}
main().catch(error => { results.push({ name: error.message, passed: false }); console.error(error.message); process.exitCode = 1; })
  .finally(async () => {
    await db.sequelize.close(); fs.mkdirSync('evidence', { recursive: true });
    fs.writeFileSync('evidence/stage3-outbox.json', JSON.stringify({ date: new Date().toISOString(),
      livePolicyTopicUsed: false, policyServerApplicationVerified: false, results }, null, 2), 'utf8');
  });
