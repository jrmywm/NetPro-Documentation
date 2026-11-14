// Startup must authenticate and check readiness, never synchronize/drop tables.
async function verifyDatabase(db) {
  await db.sequelize.authenticate();
  for (const name of ['blacklist', 'account', 'uploadJob', 'failedUpload']) {
    await db[name].findOne();
  }
}
async function startServer({ db, server, port, host }) {
  await verifyDatabase(db);
  await new Promise((resolve, reject) => {
    const onError = error => { server.removeListener('listening', onListen); reject(error); };
    const onListen = () => { server.removeListener('error', onError); resolve(); };
    server.once('error', onError);
    server.once('listening', onListen);
    server.listen(port, host);
  });
}
module.exports = { startServer, verifyDatabase };
