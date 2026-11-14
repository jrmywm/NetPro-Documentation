const express = require("express");
const router = express.Router();
const jobController = require("../controllers/job.controller");
const failedUploadController = require('../controllers/failedUpload.controller');

// Get all jobs (specific route first)
router.get("/all", jobController.getAllJobs);

// Get job status by ID (parameterized route after specific routes)
router.get("/:jobId", jobController.getJobStatus);

// Retry failed job
router.post("/:jobId/retry", jobController.retryFailedJob);

// Get failed records for a specific job
router.get('/:jobId/failed-records', failedUploadController.getFailedRecordsByJob);

// Download failed records as CSV
router.get('/:jobId/failed-records/download', failedUploadController.downloadFailedRecords);

// Update a failed record
router.put('/:jobId/failed-records/:recordId', failedUploadController.updateFailedRecord);

// Process all failed records for a job
router.post('/:jobId/failed-records/process-all', failedUploadController.processAllFailedRecords);

module.exports = router;