// Phase-three contract only: no network calls, writes or policy activation.
const { isIP } = require('node:net');
const categories = ['Social Media', 'News', 'Education', 'Entertainment', 'Shopping',
  'Finance', 'Health', 'Sports', 'Technology', 'Other'];
function toNetProPolicy(row) {
  const domain = String(row.domain || '').trim().toLowerCase();
  if (!/^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(domain) || isIP(domain)) {
    throw Error('Policy domain must be a DNS hostname');
  }
  const inputCategory = String(row.category || 'Other').trim();
  const category = categories.find(item => item.toLowerCase() === inputCategory.toLowerCase());
  if (!category) throw Error('Category is not supported by NetPro: ' + inputCategory);
  const ip = row.ip_add == null || String(row.ip_add).trim() === '' ? null : String(row.ip_add).trim();
  if (ip !== null && isIP(ip) !== 4) throw Error('Explicit ip_add must be an IPv4 address');
  const name = row.name && row.name !== 'null' ? String(row.name).trim() : domain;
  if (!name || name.length > 255) throw Error('Invalid policy name');
  // Do not invent/resolve an IP, reuse standalone IDs or import historical hit counters.
  return { name, domain, ip_add: ip, category };
}
module.exports = { toNetProPolicy, categories };
