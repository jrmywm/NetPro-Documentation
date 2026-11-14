const dotenv = require("dotenv");
dotenv.config();
const { Sequelize } = require("sequelize");
const { getIsolationConfig } = require('./isolation');
const config = getIsolationConfig();

const sequelize = new Sequelize({
  dialect: "postgres",
  host: config.host,
  port: config.dbPort,
  username: config.username,
  password: config.password,
  database: config.database,
  logging: false,
  pool: { max: 3, min: 0, idle: 10000 }
});

const db = {};

db.Sequelize = Sequelize;
db.sequelize = sequelize;

// Import models
db.blacklist = require("../models/blacklist.model.js")(sequelize, Sequelize);
db.account = require("../models/account.model.js")(sequelize, Sequelize);
db.uploadJob = require("../models/uploadJob.model.js")(sequelize, Sequelize);
db.failedUpload = require("../models/failedUpload.model.js")(sequelize, Sequelize);

// Add associations
db.uploadJob.hasMany(db.failedUpload, { foreignKey: 'job_id' });
db.failedUpload.belongsTo(db.uploadJob, { foreignKey: 'job_id' });

module.exports = db;
