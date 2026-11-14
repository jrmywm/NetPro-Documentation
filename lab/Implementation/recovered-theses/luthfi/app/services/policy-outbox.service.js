// Phase-three prototype. Candidate policies and outbox share ONE guarded test database.
// Not a live-backend replacement; Kafka output is restricted to integration-test topics.
const { randomUUID } = require('node:crypto');
const db = require('../config/db.config');
const { toNetProPolicy } = require('./netpro-policy-contract');

class PolicyOutboxService {
  async stageCompletedUpload(jobId) {
    const job = await db.uploadJob.findByPk(jobId);
    if (!job || job.status !== 'completed' || !job.input_path) throw Error('A completed retained upload is required');
    const { digest } = require('./persistent-upload.service');
    const { csvBatches } = require('./csv-batches');
    if (await digest(job.input_path) !== job.input_sha256) throw Error('Retained input checksum changed');
    const importKey = 'upload:' + job.id;
    let accepted = 0, rejected = 0;
    const errors = [];
    for await (const batch of csvBatches(job.input_path, job.input_batch_size)) for (const row of batch) {
      // Validate mapping separately: persistence failures must abort, not be called bad CSV.
      let mapped;
      try {
        if (row.error) throw Error(row.error);
        mapped = toNetProPolicy({ ...row.record, ip_add: row.original.ip_add });
      } catch (error) {
        rejected++; if (errors.length < 10) errors.push({ record: row.rowNumber, error: error.message });
        continue;
      }
      await this.stage(importKey, mapped); accepted++;
    }
    if (await digest(job.input_path) !== job.input_sha256) throw Error('Input changed during staging; do not publish partial candidates');
    return { importKey, acceptedRows: accepted, rejectedRows: rejected, errors,
      ...await this.status(importKey), state: 'staged_not_applied' };
  }
  async stage(importKey, input, { beforeCommit } = {}) {
    if (typeof importKey !== 'string' || !importKey || importKey.length > 200) throw Error('Invalid import key');
    const payload = { ...toNetProPolicy(input), hit_count: 0 };
    return db.sequelize.transaction(async transaction => {
      const options = { transaction, type: db.Sequelize.QueryTypes.SELECT };
      let rows = await db.sequelize.query(`INSERT INTO netpro_policy_candidates(id,domain,payload)
        VALUES($1,$2,$3::jsonb) ON CONFLICT(domain) DO NOTHING RETURNING *`, {
        ...options, bind: [randomUUID(), payload.domain, JSON.stringify(payload)]
      });
      const created = rows.length > 0;
      if (!created) rows = await db.sequelize.query(`SELECT * FROM netpro_policy_candidates WHERE domain=$1 FOR UPDATE`, {
        ...options, bind: [payload.domain]
      });
      const policy = rows[0];
      const [same] = await db.sequelize.query(`SELECT payload=$1::jsonb AS same FROM netpro_policy_candidates WHERE id=$2`, {
        ...options, bind: [JSON.stringify(payload), policy.id]
      });
      if (!same.same) throw Error('Existing domain has different policy fields; explicit update required');
      const timestamp = new Date(policy.created_at).toISOString();
      const message = { createdBlockedList: { id: policy.id, ...payload, createdAt: timestamp, updatedAt: timestamp }, type: 'create' };
      await db.sequelize.query(`INSERT INTO netpro_policy_outbox(event_id,policy_id,payload)
        VALUES($1,$2,$3::jsonb) ON CONFLICT(policy_id) DO NOTHING`, {
        ...options, bind: [randomUUID(), policy.id, JSON.stringify(message)]
      });
      await db.sequelize.query(`INSERT INTO netpro_import_policy_links(import_key,domain,policy_id)
        VALUES($1,$2,$3) ON CONFLICT(import_key,domain) DO NOTHING`, {
        ...options, bind: [importKey, payload.domain, policy.id]
      });
      if (beforeCommit) await beforeCommit();
      return { id: policy.id, created, state: 'stored' };
    });
  }
  async dispatchOne(producer, topic, { afterSend, policyId = null } = {}) {
    if (!/^netpro-integration-test-[a-z0-9-]+$/.test(topic)) throw Error('Only isolated integration-test Kafka topics are allowed');
    let eventId;
    try {
      return await db.sequelize.transaction(async transaction => {
        const [event] = await db.sequelize.query(`SELECT * FROM netpro_policy_outbox
          WHERE published_at IS NULL AND ($1::uuid IS NULL OR policy_id=$1::uuid)
          ORDER BY created_at,event_id FOR UPDATE SKIP LOCKED LIMIT 1`, {
          transaction, bind: [policyId], type: db.Sequelize.QueryTypes.SELECT
        });
        if (!event) return null;
        eventId = event.event_id;
        await producer.send({ topic, acks: -1, messages: [{ key: 'List', value: JSON.stringify(event.payload),
          headers: { 'netpro-event-id': event.event_id } }] });
        // A crash here causes a replay with the SAME IDs: at-least-once, not exactly-once.
        if (afterSend) await afterSend(event);
        await db.sequelize.query(`UPDATE netpro_policy_outbox SET published_at=NOW(),attempts=attempts+1,last_error=NULL WHERE event_id=$1`, {
          transaction, bind: [event.event_id]
        });
        return { eventId, policyId: event.policy_id, state: 'published' };
      });
    } catch (error) {
      if (eventId) await db.sequelize.query(`UPDATE netpro_policy_outbox SET attempts=attempts+1,last_error=$2
        WHERE event_id=$1 AND published_at IS NULL`, { bind: [eventId, String(error.message).slice(0, 1000)] });
      throw error;
    }
  }
  async status(importKey) {
    const [row] = await db.sequelize.query(`SELECT count(*)::int AS stored,
      count(o.published_at)::int AS published FROM netpro_import_policy_links l
      JOIN netpro_policy_outbox o ON o.policy_id=l.policy_id WHERE l.import_key=$1`, {
      bind: [importKey], type: db.Sequelize.QueryTypes.SELECT
    });
    return { ...row, applied: null, applicationVerified: false };
  }
}
module.exports = PolicyOutboxService;
