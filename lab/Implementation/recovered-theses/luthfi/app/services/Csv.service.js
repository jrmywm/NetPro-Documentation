const fs = require("fs");
const csv = require("fast-csv");
const { Parser } = require("json2csv");
const db = require("../config/db.config");
const Blacklist = db.blacklist;
const { allowedFileExtensions, maxSingleFileSize, maxTotalUploadSize } = require("../models/configuration.model");

const processSingleFile = async (file) => {
  const startTime = Date.now();
  const filePath = __basedir + "/uploads/" + file.filename;
  const blacklist = [];

  return new Promise((resolve, reject) => {
    fs.createReadStream(filePath)
      .pipe(csv.parse({ headers: true }))
      .on("error", (error) => {
        reject({ type: "ParseError", message: error.message });
      })
      .on("data", (row) => {
        blacklist.push(row);
      })
      .on("end", async () => {
        try {
          await Blacklist.bulkCreate(blacklist);
          const endTime = Date.now();
          const durationInSeconds = (endTime - startTime) / 1000;

          // Delete the CSV file after successful input to the database
          fs.unlink(filePath, (err) => {
            if (err) {
              console.error("Error deleting the file:", err);
            } else {
              console.log("CSV file deleted successfully.");
            }
          });

          resolve({
            filename: file.originalname,
            timeTaken: durationInSeconds.toFixed(2) + " seconds"
          });
        } catch (error) {
          // Delete the CSV file after error
          fs.unlink(filePath, (err) => {
            if (err) {
              console.error("Error deleting the file:", err);
            } else {
              console.log("CSV file deleted successfully.");
            }
          });
          reject({ 
            type: "DatabaseError", 
            message: error.errors ? error.errors.map((e) => e.message).join(", ") : error.message 
          });
        }
      });
  });
};

const processMultipleFiles = async (files) => {
  const results = [];

  for (const file of files) {
    try {
      const csvParserStream = fs
        .createReadStream(__basedir + "/uploads/" + file.filename)
        .pipe(csv.parse({ headers: true }));

      const blacklist = await new Promise((resolve, reject) => {
        let data = [];
        csvParserStream
          .on("error", (error) => {
            reject(error.message);
          })
          .on("data", (row) => {
            data.push(row);
          })
          .on("end", () => {
            resolve(data);
          });
      });

      await Blacklist.bulkCreate(blacklist);

      // Delete the CSV file after successful input to the database
      fs.unlink(__basedir + "/uploads/" + file.filename, (err) => {
        if (err) {
          console.error("Error deleting the file:", err);
        } else {
          console.log("CSV file deleted successfully:", file.originalname);
        }
      });

      results.push({
        status: "success",
        filename: file.originalname,
        message: "Uploaded the file successfully: " + file.originalname,
      });
    } catch (error) {
      console.error(error);
      results.push({
        status: "fail",
        filename: file.originalname,
        message: "Could not upload the file: " + file.originalname,
        error: error.message,
      });
    }
  }

  return results;
};

const generateCsvFile = async () => {
  const blacklist = await Blacklist.findAll({ 
    attributes: ["id", "name", "domain", "reason", "category", "hit_count"]
  });

  const jsonBlacklist = JSON.parse(JSON.stringify(blacklist));
  const csvFields = ["id", "name", "domain", "reason", "category", "hit_count"];
  const parser = new Parser({ fields: csvFields });
  const csvData = parser.parse(jsonBlacklist);

  return csvData;
};

const getAllowedFileExtensions = async () => {
  return allowedFileExtensions;
};

const getFileSizeLimits = async () => {
  return { singleFile: maxSingleFileSize, totalFiles: maxTotalUploadSize };
};

module.exports = {
  processSingleFile,
  processMultipleFiles,
  generateCsvFile,
  getAllowedFileExtensions, 
  getFileSizeLimits 
}; 