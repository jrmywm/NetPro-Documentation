const express = require("express");
const bodyParser = require("body-parser");
const db = require("./config/dpdkDatabase");
const npbRoutes = require("./routes/npbRoutes"); // Updated route import
const psRoutes = require("./routes/psRoutes");
const configRoutes = require("./routes/configRoutes");
const userRoutes = require("./routes/userRoutes");
const cors = require("cors");
const npbController = require("./controllers/npbController");
const psContoller = require("./controllers/psController");
const cron = require("node-cron");
const { producer } = require("./config/kafkaConfig");
const psUtils = require('./utils/psUtils');

const app = express();

// Use bodyParser to parse JSON bodies
app.use(bodyParser.urlencoded({ extended: true, limit: '50mb' }));
app.use(bodyParser.json({ limit: '50mb' }));

const corsOptions = {
  origin: "*",
  Credentials: true,
  optionsSuccessStatus: 200,
};

app.use(cors(corsOptions));

// Connect to the database
db.authenticate()
  .then(async() => {
    console.log("Database connected");
    await psUtils.getAllBlockedPs();
  })
  .catch((err) => {
    console.error("Unable to connect to the database:", err);
  });

async function disconnect(){
  await producer.disconnect();
}

// Use the npb routes with /npb prefix
app.use("/npb", npbRoutes); // Updated route usage with /npb prefix
app.use("/ps", psRoutes);
app.use("/config", configRoutes);
app.use("/user", userRoutes);

app.locals.bulkPolicyReady = require('./integration/bootstrap')(app, db, producer)
  .catch(error => { console.error('Bulk policy adapter disabled:', error.message); app.locals.bulkPolicyError = error.message; });

// Cron job to run every 15 seconds
cron.schedule("*/15 * * * * *", async () => {
  try {
    // Call the controller function to perform heartbeat check
    await npbController.performHeartbeatCheck();
    await psContoller.performHeartbeatCheck();
  } catch (error) {
    console.error("Error in cron job:", error);
  }
});

module.exports = app;
