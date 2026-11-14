// Isolated, labelled replacement processing core, used by the persistent queue.
const { csvBatches } = require('./csv-batches');
const db = require('../config/db.config');

class BoundedUploadService {
  constructor({ batchSize = 1000, afterBatch, beforeBatch } = {}) {
    this.batchSize = batchSize;
    this.afterBatch = afterBatch;
    this.beforeBatch = beforeBatch;
  }
  async process(filePath, jobId) {
    let total = 0;
    // First pass counts rows using the same bounded parser; no row collection.
    for await (const batch of csvBatches(filePath, this.batchSize)) total += batch.length;
    const job = await db.uploadJob.findByPk(jobId);
    if (!job) throw Error('Job not found');
    if (job.status === 'completed') return job;
    if (job.processed_records > total) throw Error('Checkpoint exceeds input size');
    // The persistent queue verifies retained input identity before calling this core.
    await job.update({ total_records: total, status: 'processing', error_message: null });
    let position = 0;
    try {
      for await (const batch of csvBatches(filePath, this.batchSize)) {
        if (this.beforeBatch) await this.beforeBatch();
        const batchStart = position;
        position += batch.length;
        const outcome = await db.sequelize.transaction(async transaction => {
          const current = await db.uploadJob.findByPk(jobId, { transaction, lock: transaction.LOCK.UPDATE });
          if (current.processed_records >= position) return null;
          if (current.processed_records !== batchStart) throw Error('Checkpoint does not match batch boundary');
          const failures = batch.filter(row => row.error);
          const valid = batch.filter(row => !row.error);
          let inserted = 0;
          if (valid.length) {
            // RETURNING counts this transaction's actual inserts, not global table growth.
            const rows = await db.sequelize.query(`INSERT INTO "blacklists"
              ("domain","name","category","reason","hit_count","createdAt","updatedAt")
              SELECT domain,name,category,reason,hit_count,NOW(),NOW()
              FROM jsonb_to_recordset($1::jsonb) AS x(domain text,name text,category text,reason text,hit_count integer)
              ON CONFLICT (domain) DO NOTHING RETURNING id`, {
                bind: [JSON.stringify(valid.map(row => row.record))],
                type: db.Sequelize.QueryTypes.SELECT, transaction
              });
            inserted = rows.length;
          }
          if (failures.length) await db.failedUpload.bulkCreate(failures.map(row => ({
            job_id: jobId, row_number: row.rowNumber, ...row.record,
            // Preserve bad values in original_data without violating failure-table varchar limits.
            domain: row.record.domain.slice(0, 255), name: row.record.name.slice(0, 255),
            category: row.record.category.slice(0, 255),
            error_message: row.error, original_data: JSON.stringify(row.original)
          })), { transaction });
          const values = {
            processed_records: position,
            unique_domains: current.unique_domains + inserted,
            duplicate_domains: current.duplicate_domains + valid.length - inserted,
            failed_records: current.failed_records + failures.length,
            status: position === total ? 'completed' : 'processing'
          };
          await current.update(values, { transaction });
          return values;
        });
        // Publish only after the transaction has committed.
        if (outcome && global.io) global.io.emit('uploadProgress', { jobId,
          filename: job.filename,
          processedRecords: outcome.processed_records, totalRecords: total,
          uniqueDomains: outcome.unique_domains, duplicateDomains: outcome.duplicate_domains,
          failedRecords: outcome.failed_records, status: outcome.status,
          progress: total ? 100 * outcome.processed_records / total : 100 });
        if (outcome && this.afterBatch) await this.afterBatch(outcome);
      }
      const final = await db.uploadJob.findByPk(jobId);
      if (final.processed_records !== total || total !== final.unique_domains + final.duplicate_domains + final.failed_records) {
        throw Error('Final upload accounting does not match committed checkpoint');
      }
      if (final.status !== 'completed') await final.update({ status: 'completed' });
      // Also cover zero-row files and resume after the final data commit.
      if (global.io) global.io.emit('uploadProgress', { jobId, filename: job.filename,
        processedRecords: total, totalRecords: total, uniqueDomains: final.unique_domains,
        duplicateDomains: final.duplicate_domains, failedRecords: final.failed_records,
        status: 'completed', progress: 100 });
      return final;
    } catch (error) {
      await db.uploadJob.update({ status: 'failed', error_message: error.message }, { where: { id: jobId } });
      throw error;
    }
  }
}
module.exports = BoundedUploadService;
