const failedUploadService = require("../services/failedUpload.service");
const sendResponse = require("../utils/Response.utilities");

// res,
// status,
// code,
// message,
// data,
// errorType = null,
// description = null

/**
 * Get failed records for a specific job
 * @param {Object} req - Express request object
 * @param {Object} res - Express response object
 */
exports.getFailedRecordsByJob = async (req, res) => {
  try {
    const { jobId } = req.params;
    const result = await failedUploadService.getFailedRecordsByJob(jobId);
    sendResponse(
        res, 
        "success", 
        200, 
        "Failed records retrieved successfully", 
        result
    );

  } catch (error) {
    console.error('Error getting failed records:', error);
    sendResponse(
        res, 
        "error", 
        500, 
        "Error getting failed records", 
        null,
        "InternalServerError",
        "Failed to get failed records"
    );
  }
};

/**
 * Download failed records as CSV
 * @param {Object} req - Express request object
 * @param {Object} res - Express response object
 */
exports.downloadFailedRecords = async (req, res) => {
  try {
    const { jobId } = req.params;
    const csvData = await failedUploadService.generateFailedRecordsCSV(jobId);

    // Set headers for CSV download
    res.setHeader('Content-Type', 'text/csv');
    res.setHeader('Content-Disposition', `attachment; filename=failed-records-${jobId}.csv`);

    res.send(csvData);
  } catch (error) {
    console.error('Error downloading failed records:', error);
    sendResponse(
        res, 
        "error", 
        500, 
        "Error downloading failed records", 
        null,
        "InternalServerError",
        "Failed to download failed records"
    );
  }
};

/**
 * Update a failed record
 * @param {Object} req - Express request object
 * @param {Object} res - Express response object
 */
exports.updateFailedRecord = async (req, res) => {
  try {
    const { jobId, recordId } = req.params;
    const updateData = req.body;

    const updatedRecord = await failedUploadService.updateFailedRecord(jobId, recordId, updateData);
    sendResponse(
        res, 
        "success", 
        200, 
        "Failed record updated successfully", 
        updatedRecord
    );
  } catch (error) {
    console.error('Error updating failed record:', error);
    sendResponse(
        res, 
        "error", 
        500, 
        "Error updating failed record", 
        null,
        "InternalServerError",
        "Failed to update failed record"
    );
  }
};

/**
 * Process all failed records for a job
 * @param {Object} req - Express request object
 * @param {Object} res - Express response object
 */
exports.processAllFailedRecords = async (req, res) => {
  try {
    const { jobId } = req.params;
    const { records } = req.body;

    if (!records || !Array.isArray(records)) {
      return sendResponse(
        res,
        "error",
        400,
        "Invalid request body",
        null,
        "ValidationError",
        "Records must be an array"
      );
    }

    // Validate each record has required fields
    for (const record of records) {
      if (!record.row_number || !record.domain || !record.name || !record.category || !record.reason || !record.hit_count) {
        return sendResponse(
          res,
          "error",
          400,
          "Invalid record format",
          null,
          "ValidationError",
          "Each record must have row_number, domain, name, category, reason, and hit_count"
        );
      }
    }

    const result = await failedUploadService.processAllFailedRecords(jobId, records);

    return sendResponse(
      res,
      "success",
      200,
      "Records processed successfully",
      result
    );
  } catch (error) {
    console.error('Error processing failed records:', error);
    
    if (error.message.includes('does not exist')) {
      return sendResponse(
        res,
        "error",
        404,
        "Job not found",
        null,
        "NotFoundError",
        error.message
      );
    }

    return sendResponse(
      res,
      "error",
      500,
      "Error processing failed records",
      null,
      "InternalServerError",
      error.message
    );
  }
}; 