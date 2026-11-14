// Labelled adaptation: bounded row batches instead of collecting the entire file.
const fs = require('node:fs');
const csv = require('fast-csv');

async function* csvBatches(filePath, batchSize = 1000) {
  if (!Number.isInteger(batchSize) || batchSize < 1 || batchSize > 10000) throw Error('Invalid batch size');
  const input = fs.createReadStream(filePath);
  const parser = csv.parse({ headers: headers => headers.map(h => h.trim().toLowerCase()),
    trim: true, ignoreEmpty: true });
  // Forward filesystem errors to the iterator instead of emitting an unhandled error.
  input.on('error', error => parser.destroy(error));
  input.pipe(parser);
  let batch = [];
  let rowNumber = 1;
  try {
    for await (const data of parser) {
      rowNumber++;
      const domain = String(data.domain ?? data.url ?? data.website ?? '').trim().toLowerCase();
      const hitCount = data.hit_count === undefined || data.hit_count === '' ? 0 : Number(data.hit_count);
      let error = null;
      if (!domain) error = 'Domain is required';
      else if (domain.length > 253 || !/^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(domain)) error = 'Expected a DNS hostname, not a URL or IP address';
      else if (/^\d+\.\d+\.\d+\.\d+$/.test(domain)) error = 'IP-only input is not supported by this domain importer';
      else if (!Number.isInteger(hitCount) || hitCount < 0 || hitCount > 2147483647) error = 'Invalid hit_count';
      for (const field of ['name', 'category']) if (String(data[field] || '').length > 255) error = `${field} is too long`;
      batch.push({ rowNumber, error, original: data, record: {
        domain, name: data.name || 'null', category: data.category || 'other',
        reason: data.reason || '', hit_count: Number.isInteger(hitCount) && hitCount >= 0 && hitCount <= 2147483647 ? hitCount : 0
      }});
      if (batch.length === batchSize) { yield batch; batch = []; }
    }
    if (batch.length) yield batch;
  } finally {
    input.destroy(); parser.destroy();
  }
}
module.exports = { csvBatches };
