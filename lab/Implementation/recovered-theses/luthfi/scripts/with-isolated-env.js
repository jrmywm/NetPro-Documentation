// Convenience runner: read VM-private test credentials, never print or export them.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const target = path.resolve(root, process.argv[2] || '');
if (!target.startsWith(root + path.sep) || !['scripts', 'tests'].includes(path.relative(root, target).split(path.sep)[0])) {
  throw Error('Only a candidate scripts/ or tests/ entry point may be selected');
}
Object.assign(process.env, JSON.parse(fs.readFileSync(path.join(root, '.stage1-env.json'), 'utf8')));
process.argv = [process.execPath, target, ...process.argv.slice(3)];
require(target);
