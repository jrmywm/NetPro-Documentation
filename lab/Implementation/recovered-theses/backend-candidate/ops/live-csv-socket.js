// Real user JWT + nginx WebSocket proxy checks; optional restart during 100k-row validation.
const fs = require('node:fs');
const { X509Certificate } = require('node:crypto');
const { spawn } = require('node:child_process');
const { io } = require('/home/netpro/recovered-theses-20261030/luthfi/node_modules/socket.io-client');
const data = JSON.parse(fs.readFileSync('/home/netpro/recovered-theses-20261030/csv-test-session.json', 'utf8'));
const restartMode = process.argv[2] === '--restart';
const ca = fs.readFileSync('/home/ubuntu/cert/server.crt'), pin = new X509Certificate(ca).fingerprint256;
const sockets = [], eventsA = [], eventsB = []; let restart, checkpoint;
const options = { path: '/api/import-socket', ca, rejectUnauthorized: true, transports: ['websocket'],
  checkServerIdentity: (_host, cert) => cert.fingerprint256 === pin ? undefined : Error('Certificate pin mismatch') };
function connect(token, events) {
  const socket = io('https://127.0.0.1:3005', { ...options, auth: { token } }); sockets.push(socket);
  socket.on('importProgress', event => {
    events.push({ id: event.id, filename: event.filename, status: event.status, processed: event.processed_records });
    if (restartMode && !restart && event.filename.startsWith('netpro-csv-restart-') && event.status === 'validating' && event.processed_records >= 1000 && event.processed_records < event.total_records) {
      checkpoint = event.processed_records;
      restart = new Promise((resolve, reject) => {
        const child = spawn('systemctl', ['restart','netpro-backend'], { stdio: 'ignore' });
        child.on('exit', rc => rc === 0 ? resolve() : reject(Error('Backend restart failed')));
      });
    }
  });
  return new Promise((resolve,reject) => { socket.once('connect', () => resolve(socket)); socket.once('connect_error',reject); });
}
async function main() {
  await Promise.all([connect(data.users.A.token, eventsA), connect(data.users.B.token, eventsB)]);
  const denied = io('https://127.0.0.1:3005', { ...options, auth: {}, reconnection: false }); sockets.push(denied);
  await new Promise((resolve,reject) => { denied.once('connect',()=>reject(Error('Unauthenticated socket connected'))); denied.once('connect_error', resolve); });
  const fixture = await new Promise((resolve,reject) => {
    const child = spawn('python3',['/home/netpro/recovered-theses-20261030/csv-live-api.py','upload',restartMode?'restart':'socket']);
    let out='',err=''; child.stdout.on('data', b => { out+=b; }); child.stderr.on('data',b=>{err+=b;});
    child.on('exit',rc=>{ if(rc!==0)reject(Error(err)); else {try{resolve(JSON.parse(out));}catch(e){reject(e);}} });
  });
  if (!eventsA.some(e => e.id === fixture.id)) throw Error('Owner did not receive actual upload progress');
  if (eventsB.length) throw Error('Progress leaked to another owner');
  if (restartMode) {
    if (!restart) throw Error('No intermediate checkpoint was observed before validation completed');
    await restart;
    if (fixture.valid !== 100000 || fixture.duplicate || fixture.invalid) throw Error('Restart recovery counters are incorrect');
  }
  const result = { passed: true, mode: restartMode?'restart':'websocket', fixture,
    ownerEvents: eventsA.filter(e=>e.id===fixture.id).length, otherOwnerEvents: eventsB.length,
    unauthenticatedRejected: true, restartCheckpoint: checkpoint, credentialsPrinted: false };
  fs.writeFileSync('/home/netpro/recovered-theses-20261030/luthfi/evidence/live-csv-'+(restartMode?'restart':'socket')+'.json',JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
}
main().catch(e=>{console.error(e.message);process.exitCode=1;}).finally(()=>{for(const s of sockets)s.close();});
