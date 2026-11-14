// Set global __basedir first
global.__basedir = __dirname;
require('dotenv').config();
const { getIsolationConfig } = require('./app/config/isolation');
const isolatedConfig = getIsolationConfig();
const { startServer } = require('./app/services/startup.service');

// Import required modules
const express = require("express");
const dotenv = require("dotenv");
const cors = require("cors");
const app = express();
const http = require('http');
const { Server } = require("socket.io");

// Import database configuration
const db = require("./app/config/db.config.js");

// Create HTTP server
const server = http.createServer(app);

// Initialize Socket.IO
const io = new Server(server, {
  cors: {
    origin: process.env.CORS_ORIGIN,
    methods: ["GET", "POST"],
    credentials: true
  }
});

// Make io accessible globally
global.io = io;

// Socket.IO connection handling
io.on('connection', (socket) => {
  console.log('Client connected:', socket.id);

  socket.emit('test', 'Connected');

  socket.on('disconnect', () => {
    console.log('Client disconnected:', socket.id);
  });
});

// Import routes and other files here
const { getHomePage, getSocketTestPage } = require("./app/utils/LandingPage.js");
const { PersistentUploadService } = require('./app/services/persistent-upload.service');
const { createUploadRouter, createJobRouter } = require('./app/routes/bounded-upload.router');
const uploadQueue = new PersistentUploadService();
const accountRouter = require("./app/routes/account.router.js");
const domainRouter = require("./app/routes/domain.router.js");
// Serve static files from the public directory
app.use(express.static("public"));
app.use(express.static("resources"));

// Set up the server
dotenv.config();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(
  cors({
    origin: process.env.CORS_ORIGIN,
    methods: ["GET", "POST", "PUT", "DELETE"],
    credentials: true,
  })
);

// Schema creation is explicit and restricted to an empty isolated database.

// Routes used in the application
app.get("/", getHomePage);
app.get("/testSocket", getSocketTestPage);
app.use("/massive-data", createUploadRouter(uploadQueue));
app.use("/auth", accountRouter);
app.use("/domains", domainRouter);
app.use("/jobs", createJobRouter(uploadQueue));
app.use((error, _req, res, _next) => res.status(500).json({ message: 'Isolated application request failed' }));

const { verifyDatabase } = require('./app/services/startup.service');
verifyDatabase(db).then(() => uploadQueue.start())
.then(() => startServer({ db, server, port: isolatedConfig.port, host: isolatedConfig.bindHost }))
.then(() => console.log(`Isolated server ready on ${isolatedConfig.bindHost}:${isolatedConfig.port}`))
.catch(async error => {
  console.error('Startup failed:', error.message);
  await uploadQueue.stop();
  await io.close();
  await db.sequelize.close();
  process.exitCode = 1;
});

let shuttingDown = false;
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, async () => {
  if (shuttingDown) return;
  shuttingDown = true;
  try {
    await uploadQueue.stop();
    await new Promise(resolve => io.close(resolve));
    await db.sequelize.close();
  } catch (error) { console.error('Shutdown failed:', error.message); process.exitCode = 1; }
});
