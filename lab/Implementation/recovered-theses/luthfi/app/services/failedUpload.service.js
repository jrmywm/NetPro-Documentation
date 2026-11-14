const db = require("../config/db.config");
const { Op } = require("sequelize");
const { Parser } = require('json2csv');

class FailedUploadService {
  /**
   * Get failed records for a specific job
   * @param {number} jobId - The job ID
   * @returns {Promise<Object>} Failed records with total count
   */
  async getFailedRecordsByJob(jobId) {
    const failedRecords = await db.failedUpload.findAll({
      where: { job_id: jobId },
      attributes: [
        'id',
        'row_number',
        'domain',
        'category',
        'reason',
        'error_message',
        'name',
        'hit_count'
      ],
      order: [['row_number', 'ASC']]
    });

    return {
      total: failedRecords.length,
      records: failedRecords
    };
  }

  /**
   * Generate CSV data for failed records
   * @param {number} jobId - The job ID
   * @returns {Promise<string>} CSV data
   */
  async generateFailedRecordsCSV(jobId) {
    const failedRecords = await db.failedUpload.findAll({
      where: { job_id: jobId },
      attributes: [
        'row_number',
        'domain',
        'name',
        'category',
        'reason',
        'hit_count',
        'error_message'
      ],
      order: [['row_number', 'ASC']]
    });

    // Define CSV fields
    const fields = [
      'row_number',
      'domain',
      'name',
      'category',
      'reason',
      'hit_count',
      'error_message'
    ];

    // Create CSV parser with options to remove quotes
    const json2csvParser = new Parser({ 
      fields,
      quote: '',
      header: true,
      formatters: {
        string: (value) => value || '',
        number: (value) => value || 0
      }
    });

    // Convert records to CSV
    return json2csvParser.parse(failedRecords);
  }

  /**
   * Update a failed record
   * @param {number} jobId - The job ID
   * @param {number} recordId - The record ID
   * @param {Object} updateData - The data to update
   * @returns {Promise<Object>} Updated record
   */
  async updateFailedRecord(jobId, recordId, updateData) {
    const record = await db.failedUpload.findOne({
      where: {
        id: recordId,
        job_id: jobId
      }
    });

    if (!record) {
      throw new Error('Failed record not found');
    }

    // Update the record
    await record.update(updateData);

    return record;
  }

  /**
   * Process all failed records for a job
   * @param {number} jobId - The job ID
   * @param {Array} records - Array of records to process
   * @returns {Promise<Object>} Processed records and job status
   */
  async processAllFailedRecords(jobId, records) {
    const transaction = await db.sequelize.transaction();

    try {
      // Get the job
      const job = await db.uploadJob.findByPk(jobId);
      if (!job) {
        throw new Error(`Job with ID ${jobId} does not exist`);
      }

      const processedRecords = [];
      const failedRecords = [];

      // Process each record
      for (const record of records) {
        try {
          // Validate required fields
          if (!record.domain) {
            throw new Error('Domain is required');
          }

          // Find the failed record by row_number and job_id
          const existingRecord = await db.failedUpload.findOne({
            where: {
              row_number: record.row_number,
              job_id: jobId
            },
            transaction
          });

          if (!existingRecord) {
            throw new Error(`Failed record with row number ${record.row_number} not found`);
          }

          // Convert record to string for original_data
          const originalDataString = JSON.stringify(record);

          // Update the failed record
          await existingRecord.update({
            domain: record.domain,
            name: record.name,
            reason: record.reason,
            category: record.category,
            hit_count: record.hit_count,
            error_message: '', // Empty string instead of null
            original_data: originalDataString
          }, { transaction });

          // Add to blacklists table
          await db.blacklist.create({
            domain: record.domain,
            name: record.name,
            reason: record.reason,
            category: record.category,
            hit_count: record.hit_count
          }, { transaction });

          processedRecords.push(existingRecord);
        } catch (error) {
          failedRecords.push({
            row_number: record.row_number,
            error: error.message
          });
        }
      }

      // Update job status
      const successCount = processedRecords.length;
      const failedCount = failedRecords.length;

      // Calculate new job statistics
      const newProcessedRecords = job.processed_records + successCount;
      const newFailedRecords = job.failed_records - successCount;
      const newUniqueDomains = job.unique_domains + successCount; // Since these were failed records, they are unique

      await job.update({
        processed_records: newProcessedRecords,
        failed_records: newFailedRecords,
        unique_domains: newUniqueDomains,
        status: (newFailedRecords === 0) ? 'completed' : job.status,
        error_message: failedCount > 0 ? 
          `Processed ${successCount} records, ${failedCount} failed` : 
          'All records processed successfully'
      }, { transaction });

      // Delete processed records from failed_uploads
      if (processedRecords.length > 0) {
        await db.failedUpload.destroy({
          where: {
            id: {
              [Op.in]: processedRecords.map(r => r.id)
            }
          },
          transaction
        });
      }

      await transaction.commit();

      return {
        records: processedRecords,
        failedRecords,
        jobStatus: {
          processed_records: newProcessedRecords,
          failed_records: newFailedRecords,
          unique_domains: newUniqueDomains,
          status: (newFailedRecords === 0) ? 'completed' : job.status
        }
      };
    } catch (error) {
      await transaction.rollback();
      throw error;
    }
  }
}

module.exports = new FailedUploadService(); 