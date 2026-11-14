// Authoritative bulk-policy adapter. Dependencies are injected for isolated testing.
const { randomUUID, timingSafeEqual } = require('node:crypto');
const { toNetProPolicy } = require('./policy-contract');
function fail(message, status = 409) { const e = Error(message); e.status = status; throw e; }
function sourceKey(key) { if (!/^[a-zA-Z0-9:_-]{1,120}$/.test(key || '')) fail('Invalid import key', 400); return key; }
function validatePolicy(input) {
  const row = toNetProPolicy(input);
  const id = '00000000-0000-0000-0000-000000000000';
  const sql = `INSERT INTO policies (id, domain, ip_address) VALUES ('${id}', '${row.domain}', '${row.ip_add || ''}');`;
  if (Buffer.byteLength(sql) >= 256) fail('Domain exceeds the active Policy Server SQL-message capacity; consumer upgrade required', 400);
  return row;
}

class BulkPolicyService {
  constructor(db, producer) { this.db = db; this.producer = producer; this.stopping = false; this.timer = null; this.active = null; }
  async q(sql, bind = [], transaction) { const [rows] = await this.db.query(sql, { bind, transaction }); return rows; }
  async migrate() {
    await this.db.transaction(async t => {
      await this.q('SELECT pg_advisory_xact_lock(20261030, 40)', [], t);
      await this.q(`CREATE TABLE IF NOT EXISTS netpro_bulk_policy_keys (
        source_key VARCHAR(120) NOT NULL, domain VARCHAR(253) NOT NULL,
        policy_id UUID NOT NULL REFERENCES ps_blocked_list(id) ON DELETE CASCADE,
        request_payload JSONB NOT NULL, created_by_source BOOLEAN NOT NULL,
        PRIMARY KEY(source_key,domain))`, [], t);
      await this.q(`CREATE TABLE IF NOT EXISTS netpro_bulk_policy_events (
        event_id UUID PRIMARY KEY, policy_id UUID NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('create','delete')),
        payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), published_at TIMESTAMPTZ,
        attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, UNIQUE(policy_id,kind))`, [], t);
    });
  }
  async ready() {
    await this.q('SELECT source_key FROM netpro_bulk_policy_keys LIMIT 0');
    await this.q('SELECT event_id FROM netpro_bulk_policy_events LIMIT 0');
  }
  async event(policy, kind, t) {
    // Existing PS JSON parser requires an IP STRING. Empty string means domain-only,
    // not a fabricated address; PostgreSQL retains the semantic null.
    const wire = { ...policy, ip_add: policy.ip_add == null ? '' : policy.ip_add };
    const body = { [kind === 'create' ? 'createdBlockedList' : 'deletedBlockedList']: wire, type: kind };
    await this.q(`INSERT INTO netpro_bulk_policy_events(event_id,policy_id,kind,payload)
      VALUES($1,$2,$3,$4::jsonb) ON CONFLICT(policy_id,kind) DO NOTHING`, [randomUUID(), policy.id, kind, JSON.stringify(body)], t);
  }
  async store(key, input, { beforeCommit } = {}) {
    sourceKey(key);
    if (!Array.isArray(input) || input.length < 1 || input.length > 100) fail('Supply 1..100 rows per batch', 400);
    let mapped;
    try { mapped = input.map(validatePolicy); } catch (e) { fail(e.message, 400); }
    const unique = new Map();
    for (const row of mapped) {
      if (unique.has(row.domain) && JSON.stringify(unique.get(row.domain)) !== JSON.stringify(row)) fail('Conflicting duplicate domain in batch', 400);
      unique.set(row.domain, row);
    }
    return this.db.transaction(async t => {
      const results = [];
      for (const row of [...unique.values()].sort((a, b) => a.domain.localeCompare(b.domain))) {
        await this.q('SELECT pg_advisory_xact_lock(hashtext($1))', ['netpro-bulk:' + row.domain], t);
        const [receipt] = await this.q(`SELECT policy_id,created_by_source,request_payload=$3::jsonb AS same
          FROM netpro_bulk_policy_keys WHERE source_key=$1 AND domain=$2 FOR UPDATE`, [key, row.domain, JSON.stringify(row)], t);
        if (receipt) {
          if (!receipt.same) fail('Import key was already used with different policy fields');
          results.push({ id: receipt.policy_id, domain: row.domain, created: false, owned: receipt.created_by_source, replay: true }); continue;
        }
        const matches = await this.q('SELECT * FROM ps_blocked_list WHERE lower(domain)=$1 ORDER BY id FOR UPDATE', [row.domain], t);
        if (matches.length > 1) fail('Existing domain has ambiguous duplicate policies; reconcile explicitly');
        let policy = matches[0]; const created = !policy;
        if (policy && ((policy.ip_add || null) !== row.ip_add || policy.category !== row.category)) fail('Existing domain has different IP/category; explicit update required');
        if (!policy) {
          [policy] = await this.q(`INSERT INTO ps_blocked_list
            (id,name,domain,ip_add,category,hit_count,"createdAt","updatedAt")
            VALUES($1,$2,$3,$4,$5,0,NOW(),NOW()) RETURNING *`, [randomUUID(), row.name, row.domain, row.ip_add, row.category], t);
          await this.event(policy, 'create', t);
        }
        await this.q(`INSERT INTO netpro_bulk_policy_keys(source_key,domain,policy_id,request_payload,created_by_source)
          VALUES($1,$2,$3,$4::jsonb,$5)`, [key, row.domain, policy.id, JSON.stringify(row), created], t);
        results.push({ id: policy.id, domain: row.domain, created, owned: created, replay: false });
      }
      if (beforeCommit) await beforeCommit();
      return results;
    });
  }
  async removeOwned(key) {
    sourceKey(key);
    return this.db.transaction(async t => {
      const owned = await this.q(`SELECT p.*,k.request_payload FROM ps_blocked_list p JOIN netpro_bulk_policy_keys k ON k.policy_id=p.id
        WHERE k.source_key=$1 AND k.created_by_source=true ORDER BY p.id FOR UPDATE OF p`, [key], t);
      for (const row of owned) {
        const [links] = await this.q('SELECT count(*)::int AS n FROM netpro_bulk_policy_keys WHERE policy_id=$1', [row.id], t);
        if (links.n !== 1) fail('Policy is also referenced by another import; refusing automatic removal');
        const { request_payload: expected, ...policy } = row;
        if (policy.domain !== expected.domain || policy.name !== expected.name || (policy.ip_add || null) !== expected.ip_add || policy.category !== expected.category) {
          fail('Policy changed since import; review it explicitly in the blocked list before removal');
        }
        await this.event(policy, 'delete', t);
        await this.q('DELETE FROM ps_blocked_list WHERE id=$1', [row.id], t);
      }
      return owned.map(row => ({ id: row.id, domain: row.domain }));
    });
  }
  async status(key) {
    sourceKey(key);
    const [row] = await this.q(`SELECT count(*)::int AS stored,
      count(e.published_at)::int AS published,
      count(*) FILTER(WHERE e.event_id IS NULL)::int AS existing_unverified
      FROM netpro_bulk_policy_keys k LEFT JOIN netpro_bulk_policy_events e
      ON e.policy_id=k.policy_id AND e.kind='create' WHERE k.source_key=$1`, [key]);
    return { ...row, applied: null, applicationVerified: false };
  }
  async publishOne({ afterSend } = {}) {
    let eventId;
    try {
      return await this.db.transaction(async t => {
        const [event] = await this.q(`SELECT e.* FROM netpro_bulk_policy_events e
          WHERE e.published_at IS NULL AND NOT (e.kind='delete' AND EXISTS(
            SELECT 1 FROM netpro_bulk_policy_events c WHERE c.policy_id=e.policy_id AND c.kind='create' AND c.published_at IS NULL))
          ORDER BY e.created_at,e.event_id FOR UPDATE SKIP LOCKED LIMIT 1`, [], t);
        if (!event) return null;
        eventId = event.event_id;
        await this.producer.send({ topic: 'dpdk-blocked-list', acks: -1,
          messages: [{ key: 'List', value: JSON.stringify(event.payload), headers: { 'netpro-event-id': eventId } }] });
        if (afterSend) await afterSend(event);
        await this.q('UPDATE netpro_bulk_policy_events SET published_at=NOW(),attempts=attempts+1,last_error=NULL WHERE event_id=$1', [eventId], t);
        return { eventId, policyId: event.policy_id, kind: event.kind, state: 'published' };
      });
    } catch (e) {
      if (eventId) await this.q(`UPDATE netpro_bulk_policy_events SET attempts=attempts+1,last_error=$2 WHERE event_id=$1 AND published_at IS NULL`, [eventId, String(e.message).slice(0, 1000)]);
      throw e;
    }
  }
  start() {
    const poll = () => {
      if (this.stopping) return;
      this.timer = setTimeout(() => {
        this.active = this.publishBatch(100)
          .catch(e => console.error('Bulk policy publication pending:', e.message))
          .finally(() => { this.active = null; poll(); });
      }, 250);
    };
    poll();
  }
  async publishBatch(limit = 100) {
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) fail('Invalid publication batch limit', 400);
    let ids = [];
    try {
      return await this.db.transaction(async t => {
        const events = await this.q(`SELECT e.* FROM netpro_bulk_policy_events e
          WHERE e.published_at IS NULL AND NOT (e.kind='delete' AND EXISTS(
            SELECT 1 FROM netpro_bulk_policy_events c WHERE c.policy_id=e.policy_id AND c.kind='create' AND c.published_at IS NULL))
          ORDER BY e.created_at,e.event_id FOR UPDATE SKIP LOCKED LIMIT $1`, [limit], t);
        if (!events.length) return [];
        ids = events.map(e => e.event_id);
        await this.producer.send({ topic: 'dpdk-blocked-list', acks: -1,
          messages: events.map(e => ({ key: 'List', value: JSON.stringify(e.payload), headers: { 'netpro-event-id': e.event_id } })) });
        await this.q(`UPDATE netpro_bulk_policy_events SET published_at=NOW(),attempts=attempts+1,last_error=NULL WHERE event_id=ANY($1::uuid[])`, [ids], t);
        return events.map(e => ({ eventId: e.event_id, policyId: e.policy_id, kind: e.kind }));
      });
    } catch (e) {
      if (ids.length) await this.q(`UPDATE netpro_bulk_policy_events SET attempts=attempts+1,last_error=$2 WHERE event_id=ANY($1::uuid[]) AND published_at IS NULL`, [ids, String(e.message).slice(0, 1000)]);
      throw e;
    }
  }
  async stop() { this.stopping = true; clearTimeout(this.timer); if (this.active) await this.active; }
}

function createRouter(service, token) {
  const router = require('express').Router();
  router.use((req, res, next) => {
    const received = Buffer.from(req.get('Authorization') || '');
    const expected = Buffer.from('Bearer ' + token);
    if (!token || received.length !== expected.length || !timingSafeEqual(received, expected)) return res.status(401).json({ message: 'Import authorization required' });
    next();
  });
  router.post('/', async (req, res, next) => {
    try { const rows = await service.store(req.body.importKey, req.body.rows); res.status(202).json({ rows, ...await service.status(req.body.importKey) }); }
    catch (e) { next(e); }
  });
  router.get('/:key', async (req, res, next) => { try { res.json(await service.status(req.params.key)); } catch (e) { next(e); } });
  router.delete('/:key', async (req, res, next) => { try { res.status(202).json({ deleted: await service.removeOwned(req.params.key), state: 'deletion_pending_publication' }); } catch (e) { next(e); } });
  router.use((e, _req, res, _next) => res.status(e.status || 500).json({ message: e.status ? e.message : 'Bulk policy transaction failed' }));
  return router;
}
module.exports = { BulkPolicyService, createRouter, validatePolicy };
