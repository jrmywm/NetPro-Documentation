const db = require("../config/db.config");
const UploadJob = db.uploadJob;
const sendResponse = require("../utils/Response.utilities");
const CsvService = require("../services/Csv.service");
const UploadService = require("../services/job.service");
const queueService = require('../services/queue.service');

// Initialize UploadService with Socket.IO instance
const uploadService = new UploadService();

exports.uploadFile = async (req, res) => {
  try {
    if (!req.file) {
      return sendResponse(
        res,
        "error",
        400,
        "No file uploaded",
        null,
        "ValidationError",
        "Please upload a file with key 'file'"
      );
    }

    // Create a new upload job
    const job = await UploadJob.create({
      filename: req.file.filename,
      status: 'queued'
    });

    // Send response immediately
    sendResponse(
      res,
      "success",
      200,
      "File upload queued successfully",
      {
        jobId: job.id,
        message: "File has been queued for processing"
      }
    );

    // Queue the job after sending response
    queueService.addToQueue({
      filePath: req.file.path,
      jobId: job.id,
      filename: req.file.filename,
      processFileInChunks: uploadService.processFileInChunks.bind(uploadService)
    }).catch(error => {
      console.error(`[ERROR] Failed to queue job ${job.id}:`, error);
      // Update job status to failed if queueing fails
      UploadJob.update(
        {
          status: 'failed',
          error_message: `Failed to queue job: ${error.message}`
        },
        { where: { id: job.id } }
      );
    });

  } catch (error) {
    console.error('Error in uploadFile:', error);
    sendResponse(
      res,
      "error",
      500,
      "Error processing file upload",
      null,
      error.name || "ServerError",
      error.message
    );
  }
};

exports.uploadMultipleFiles = async (req, res) => {
  try {
    if (!req.files || req.files.length === 0) {
      return sendResponse(
        res,
        "error",
        400,
        "No files uploaded",
        null,
        "ValidationError",
        "Please upload files with key 'files'"
      );
    }

    // Immediately respond to the client
    sendResponse(
      res,
      "success",
      200,
      "Multiple file upload started successfully",
      {
        message: "Files are being processed in the background"
      }
    );

    // Process the files in the background
    setImmediate(() => {
      uploadService.processMultipleFiles(req.files)
        .catch(error => {
          console.error('Error processing multiple files:', error);
        });
    });
  } catch (error) {
    console.error(error);
    sendResponse(
      res,
      "error",
      500,
      "Could not upload the files",
      null,
      "UploadError",
      error.message
    );
  }
};

exports.uploadMultipleFilesSafe = async (req, res) => {
  try {
    if (!req.files || req.files.length === 0) {
      return sendResponse(
        res,
        "error",
        400,
        "No files uploaded",
        null,
        "ValidationError",
        "Please upload files with key 'files'"
      );
    }

    // Create all jobs first
    const jobs = await Promise.all(req.files.map(async (file) => {
      const job = await UploadJob.create({
        filename: file.filename,
        status: 'pending'
      });
      return job;
    }));

    // Immediately respond to the client with all job IDs
    sendResponse(
      res,
      "success",
      200,
      "Multiple file upload started successfully",
      {
        jobs: jobs.map(job => ({
          id: job.id,
          filename: job.filename,
          status: job.status
        })),
        message: "Files are being processed sequentially with safe logging"
      }
    );

    // Process the files sequentially in the background
    setImmediate(() => {
      uploadService.processMultipleFilesSafe(req.files, jobs)
        .catch(error => {
          console.error('Error processing multiple files with safe logging:', error);
        });
    });
  } catch (error) {
    console.error(error);
    sendResponse(
      res,
      "error",
      500,
      "Could not upload the files",
      null,
      "UploadError",
      error.message
    );
  }
};

exports.downloadFile = async (req, res) => {
  try {
    const csvData = await CsvService.generateCsvFile();

    res.setHeader("Content-Type", "text/csv");
    res.setHeader(
      "Content-Disposition",
      "attachment; filename=blacklist.csv"
    );
    res.status(200).end(csvData);
  } catch (error) {
    console.error(error);
    sendResponse(
      res,
      "error",
      500,
      "Could not download the file",
      null,
      "DownloadError",
      error.message
    );
  }
};

exports.getAllowedFileExtensions = async (req, res) => {
  try {
    const allowedExtensions = await CsvService.getAllowedFileExtensions();
    sendResponse(
      res,
      "success",
      200,
      "Allowed file extensions",
      {
        allowedExtensions: allowedExtensions
      }
    );
  } catch (error) {
    console.error(error);
    sendResponse(
      res,
      "error",
      500,
      "Could not get allowed file extensions",
      null,
      "GetAllowedFileExtensionsError",
      error.message
    );
  }
};

exports.getFileSizeLimits = async (req, res) => {
  try {
    const limits = await CsvService.getFileSizeLimits();
    sendResponse(
      res,
      "success",
      200,
      "File size limits",
      {
        singleFile: limits.singleFile,
        totalFiles: limits.totalFiles
      }
    );
  } catch (error) {
    console.error(error);
    sendResponse(
      res,
      "error",
      500,
      "Could not get file size limits",
      null,
      "GetFileSizeLimitsError",
      error.message
    );
  }
};
