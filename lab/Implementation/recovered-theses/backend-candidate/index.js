const app = require("./src/app")
const https = require("https");
const fs = require("fs");
const { producer, admin } = require("./src/config/kafkaConfig"); // Destructure producer and admin from the exported object

const PORT = process.env.PORT || 443;

const options = {
  key: fs.readFileSync("/home/ubuntu/cert/server.key"), // replace it with your key path
  cert: fs.readFileSync("/home/ubuntu/cert/server.crt"), // replace it with your certificate path
};

const server = https.createServer(options, app);
Promise.resolve(app.locals.bulkPolicyReady).then(() => {
  if (app.locals.bulkPolicyError) throw Error(app.locals.bulkPolicyError);
  if (app.locals.csvImportService) app.locals.csvImportService.attach(server, require('./src/middleware/authMiddleware').authMiddleware);
  server.listen(PORT, () => console.log(`HTTPS Server running on port ${PORT}; import routes ready`));
}).catch(async error => {
  console.error('Backend initialization failed:', error.message);
  try {
    if (app.locals.csvImportService) await app.locals.csvImportService.stop();
    if (app.locals.bulkPolicyService) await app.locals.bulkPolicyService.stop();
    await producer.disconnect(); await admin.disconnect();
  } finally { process.exit(1); }
});

// app.listen(PORT, () => {
//   console.log(`Server running on port ${PORT}`);
// });

let shuttingDown = false;
const shutdown = async () => { // Preserve topics and pending publication records on shutdown.
  if (shuttingDown) return;
  shuttingDown = true;
  console.log("Received shutdown signal; preserving Kafka topics.");

  // Perform cleanup operations or graceful shutdown here
  // For example, closing database connections, closing files, etc.

  // Then exit the process
  if (app.locals.csvImportService) await app.locals.csvImportService.stop();
  if (app.locals.bulkPolicyService) await app.locals.bulkPolicyService.stop();
  await producer.disconnect();

  // Kafka topics are durable infrastructure; never delete them during app cleanup.

  await admin.disconnect(); // Disconnect admin
  process.exit(0);
};
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
