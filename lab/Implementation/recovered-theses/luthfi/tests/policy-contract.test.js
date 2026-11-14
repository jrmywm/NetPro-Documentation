const { test } = require('node:test');
const assert = require('node:assert/strict');
const { toNetProPolicy } = require('../app/services/netpro-policy-contract');
test('maps standalone fields to exact backend creation contract', () => {
  assert.deepEqual(toNetProPolicy({ domain: ' EXAMPLE.COM ', category: 'other',
    ip_add: '192.0.2.10', name: 'CSV example', id: 123, hit_count: 999, reason: 'metadata' }),
  { domain: 'example.com', category: 'Other', ip_add: '192.0.2.10', name: 'CSV example' });
});
test('domain-only input remains domain-only; no DNS resolution or fabricated IP', () => {
  assert.deepEqual(toNetProPolicy({ domain: 'example.com' }),
    { name: 'example.com', domain: 'example.com', ip_add: null, category: 'Other' });
});
test('normalizes supported category spelling', () => assert.equal(toNetProPolicy({ domain: 'example.com', category: 'social media' }).category, 'Social Media'));
for (const [name, data] of [
  ['unknown category', { domain: 'example.com', category: 'unspecified category' }],
  ['full URL', { domain: 'https://example.com/' }],
  ['IP as domain', { domain: '192.0.2.1' }],
  ['invalid explicit IP', { domain: 'example.com', ip_add: 'GOOGLE_IP' }],
  ['unsupported IPv6', { domain: 'example.com', ip_add: '2001:db8::1' }]
]) test(`rejects ${name}`, () => assert.throws(() => toNetProPolicy(data)));
