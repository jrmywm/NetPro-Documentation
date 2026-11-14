const db = require("../config/db.config");
const UploadJob = db.uploadJob;
const sendResponse = require("../utils/Response.utilities");
const UploadService = require("../services/job.service");

// Initialize UploadService without io
const uploadService = new UploadService();

exports.getAllJobs = async (req, res) => {
  try {
    const jobs = await uploadService.getAllJobs();
    sendResponse(
      res,
      "success",
      200,
      "Successfully retrieved all jobs",
      jobs
    );
  } catch (error) {
    console.error("Error in getAllJobs:", error);
    sendResponse(
      res,
      "error",
      500,
      "Error retrieving jobs",
      null,
      "DatabaseError",
      error.message
    );
  }
};

exports.getJobStatus = async (req, res) => {
  try {
    const job = await uploadService.getJobStatus(req.params.jobId);
    if (!job) {
      return sendResponse(
        res,
        "error",
        404,
        "Job not found",
        null,
        "NotFoundError",
        `Job with id ${req.params.jobId} not found`
      );
    }
    sendResponse(
      res,
      "success",
      200,
      "Successfully retrieved job status",
      job
    );
  } catch (error) {
    console.error("Error in getJobStatus:", error);
    sendResponse(
      res,
      "error",
      500,
      "Error retrieving job status",
      null,
      "DatabaseError",
      error.message
    );
  }
};

exports.retryFailedJob = async (req, res) => {
  try {
    const job = await uploadService.retryFailedJob(req.params.jobId);
    sendResponse(
      res,
      "success",
      200,
      "Job retry started successfully",
      {
        jobId: job.id,
        message: "Job is being processed in the background"
      }
    );
  } catch (error) {
    console.error("Error in retryFailedJob:", error);
    sendResponse(
      res,
      "error",
      500,
      "Error retrying job",
      null,
      "JobError",
      error.message
    );
  }
};