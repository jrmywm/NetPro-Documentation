const fs = require("fs");
const csv = require("fast-csv");
const db = require("../config/db.config");
const { Op, Transaction } = require("sequelize");
const readline = require('readline');

const CHUNK_SIZE = 10000;
const MAX_RETRIES = 3;
const RETRY_DELAY = 2000;
const BATCH_DELAY = 2000;

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

class UploadService {
  constructor() {
    // No need to pass io in constructor anymore
  }

  async findHeaderLine(filePath) {
    return new Promise((resolve, reject) => {
      const rl = readline.createInterface({
        input: fs.createReadStream(filePath),
        crlfDelay: Infinity
      });

      let lineNumber = 0;
      let headerLine = 0;
      let maxColumns = 0;
      let headerColumns = [];
      let allLines = [];

      rl.on('line', (line) => {
        lineNumber++;
        const columns = line.split(',').length;
        allLines.push({ lineNumber, line, columns });
        
        // Update max columns if this line has more columns
        if (columns > maxColumns) {
          maxColumns = columns;
        }
      });

      rl.on('close', () => {
        // Find the line with the most columns that contains header indicators
        const headerLineInfo = allLines.find(({ line, columns }) => 
          columns === maxColumns && (
            line.toLowerCase().includes('domain') || 
            line.toLowerCase().includes('url') || 
            line.toLowerCase().includes('website')
          )
        );

        if (headerLineInfo) {
          headerLine = headerLineInfo.lineNumber;
          headerColumns = headerLineInfo.line.split(',').map(col => col.trim());
        } else {
          // If no suitable header found, use the line with the most columns
          const maxLine = allLines.find(({ columns }) => columns === maxColumns);
          headerLine = maxLine ? maxLine.lineNumber : 1;
          headerColumns = Array.from({ length: maxColumns }, (_, i) => `column${i + 1}`);
        }

        console.log(`[INFO] Found header at line ${headerLine} with ${maxColumns} columns`);
        console.log(`[INFO] Headers:`, headerColumns);
        resolve({ headerLine, maxColumns, headerColumns });
      });

      rl.on('error', (error) => {
        reject(error);
      });
    });
  }

  async validateAndParseCSV(filePath) {
    return new Promise(async (resolve, reject) => {
      try {
        // Find the header line and column count
        const { headerLine, maxColumns, headerColumns } = await this.findHeaderLine(filePath);
        const records = [];
        const failedRecords = [];

        fs.createReadStream(filePath)
          .pipe(csv.parse({ 
            headers: headerColumns,
            skipRows: headerLine - 1,
            strictColumnHandling: false,
            trim: true,
            skipEmptyLines: true,
            ignoreEmpty: true,
            maxRows: 0, // No limit on rows
            transform: (row) => {
              // Ensure all rows have the same number of columns
              const columns = Object.keys(row).length;
              if (columns < maxColumns) {
                // Pad missing columns with empty values
                for (let i = columns; i < maxColumns; i++) {
                  row[`column${i + 1}`] = '';
                }
              } else if (columns > maxColumns) {
                // Truncate extra columns
                const newRow = {};
                headerColumns.forEach((header, index) => {
                  newRow[header] = row[header] || '';
                });
                return newRow;
              }

              // Convert hit_count to integer if it exists
              if (row.hit_count !== undefined) {
                row.hit_count = row.hit_count === '' ? 0 : parseInt(row.hit_count) || 0;
              }

              // Ensure other fields have default values if empty
              row.name = (row.name && row.name.trim() !== '') ? row.name : 'null';
              row.category = (row.category && row.category.trim() !== '') ? row.category : 'other';
              row.reason = (row.reason && row.reason.trim() !== '') ? row.reason : '';

              return row;
            }
          }))
          .on('headers', (headers) => {
            console.log("[INFO] Using headers:", headers);
          })
          .on('data', (data, rowNumber) => {
            // Skip if this is the header row
            if (Object.values(data).some(val => val === 'hit_count' || val === 'id' || val === 'name' || val === 'domain')) {
              return;
            }

            // Check for empty domain
            if (!data.domain || data.domain.trim() === '') {
              failedRecords.push({
                row_number: rowNumber,
                name: data.name,
                domain: data.domain || '',
                reason: data.reason,
                category: data.category,
                hit_count: data.hit_count,
                error_message: 'Domain is required',
                original_data: JSON.stringify(data)
              });
              return;
            }

            // If domain is not in the first column, try to find it
            if (!data.domain) {
              const domainKey = Object.keys(data).find(key => 
                key.toLowerCase().includes('domain') || 
                key.toLowerCase().includes('url') ||
                key.toLowerCase().includes('website')
              );
              if (domainKey) {
                data.domain = data[domainKey];
              } else {
                // If no domain column found, use the first non-empty column
                const firstValue = Object.values(data).find(val => val && val.trim() !== '');
                if (firstValue) {
                  data.domain = firstValue;
                }
              }
            }
            if (data.domain) {
              records.push(data);
            }
          })
          .on('end', async () => {
            console.log("[INFO] Successfully parsed CSV file");
            console.log(`[INFO] Found ${failedRecords.length} failed records`);
            resolve({ records, failedRecords });
          })
          .on('error', (error) => {
            console.error("[ERROR] CSV Parsing Error:", error);
            reject(new Error(`CSV parsing error: ${error.message}`));
          });
      } catch (error) {
        reject(error);
      }
    });
  }

  async processChunkWithRetry(chunk, jobId, filename, startTime, totalRecords, processedRecords, initialCount) {
    let retries = 0;
    while (retries < MAX_RETRIES) {
      const transaction = await db.sequelize.transaction({
        isolationLevel: Transaction.ISOLATION_LEVELS.READ_COMMITTED
      });

      try {
        // Transform data before processing
        const transformedChunk = chunk.map((record, index) => {
          const originalData = { ...record };
          let errorMessage = null;

          // Validate domain (required field)
          if (!record.domain || record.domain.trim() === '') {
            errorMessage = 'Domain is required';
          }

          // Convert hit_count to integer if it exists
          if (record.hit_count !== undefined) {
            if (record.hit_count === '' || record.hit_count === null || record.hit_count === undefined) {
              record.hit_count = 0;
            } else {
              const parsed = parseInt(record.hit_count);
              record.hit_count = isNaN(parsed) ? 0 : parsed;
            }
          }

          // Ensure other fields have default values if empty
          record.name = (record.name && record.name.trim() !== '') ? record.name : 'null';
          record.category = (record.category && record.category.trim() !== '') ? record.category : 'other';
          record.reason = (record.reason && record.reason.trim() !== '') ? record.reason : '';

          return {
            record,
            originalData,
            errorMessage,
            rowNumber: processedRecords + index + 1
          };
        });

        // Separate valid and invalid records
        const validRecords = [];
        const failedRecords = [];

        transformedChunk.forEach(({ record, originalData, errorMessage, rowNumber }) => {
          if (errorMessage) {
            failedRecords.push({
              job_id: jobId,
              row_number: rowNumber,
              name: record.name,
              domain: record.domain,
              reason: record.reason,
              category: record.category,
              hit_count: record.hit_count,
              error_message: errorMessage,
              original_data: JSON.stringify(originalData)
            });
          } else {
            validRecords.push(record);
          }
        });

        // Save failed records if any
        if (failedRecords.length > 0) {
          await db.failedUpload.bulkCreate(
            failedRecords.map((record, index) => ({
              ...record,
              job_id: jobId,
              row_number: index + 1
            })),
            { transaction }
          );
        }

        // Get ALL existing domains within transaction
        const domains = validRecords.map(record => record.domain).filter(Boolean);
        if (domains.length === 0) {
          console.log("[WARN] No valid domains found in chunk");
          await transaction.commit();
          return { 
            processedRecords, 
            uniqueDomains: 0, 
            duplicateDomains: 0,
            failedRecords: failedRecords.length 
          };
        }

        const existingRecords = await db.blacklist.findAll({
          where: { domain: { [Op.in]: domains } },
          transaction,
          lock: transaction.LOCK.UPDATE
        });
        const existingDomains = new Set(existingRecords.map(r => r.domain));

        // Filter out duplicates and remove id column
        const newRecords = validRecords
          .filter(record => record.domain && !existingDomains.has(record.domain))
          .map(({ id, ...record }) => record);
        
        // Calculate duplicates in this chunk
        const duplicateCount = validRecords.length - newRecords.length;
        
        if (newRecords.length > 0) {
          // Insert new records with transaction
          await db.blacklist.bulkCreate(newRecords, {
            transaction,
            ignoreDuplicates: true
          });
        }

        // Commit transaction
        await transaction.commit();

        // Update processed records
        processedRecords += chunk.length;

        // Get current database state
        const currentCount = await db.blacklist.count();
        const uniqueDomains = currentCount - initialCount;
        const duplicateDomains = duplicateCount; // Use the actual duplicate count from this chunk

        // Update job status
        const progress = (processedRecords / totalRecords) * 100;
        const processingTime = (Date.now() - startTime) / 1000;
        
        await db.uploadJob.update(
          {
            processed_records: processedRecords,
            unique_domains: uniqueDomains,
            duplicate_domains: duplicateDomains,
            processing_time: processingTime,
            status: processedRecords === totalRecords ? 'completed' : 'processing',
            error_message: failedRecords.length > 0 ? 
              `Processed with ${failedRecords.length} failed records. Check failed_uploads table for details.` : 
              null
          },
          { where: { id: jobId } }
        );

        // Emit progress update using global io
        if (global.io && progress < 100) {
          console.log("[INFO] Emitting progress update:", progress);
          console.log("[INFO] Failed records:", failedRecords.length);
          global.io.emit('uploadProgress', {
            jobId,
            filename,
            progress,
            processedRecords,
            totalRecords,
            uniqueDomains,
            duplicateDomains,
            failedRecords: failedRecords.length,
            processingTime,
            status: processedRecords === totalRecords ? 'completed' : 'processing'
          });
        }

        return { 
          processedRecords, 
          uniqueDomains, 
          duplicateDomains,
          failedRecords: failedRecords.length 
        };

      } catch (error) {
        await transaction.rollback();
        
        if (error.name === 'SequelizeDatabaseError' && error.parent?.code === '40P01') {
          retries++;
          console.log(`[WARN] Deadlock detected, retrying chunk (attempt ${retries}/${MAX_RETRIES})`);
          await sleep(RETRY_DELAY * retries); // Exponential backoff
          continue;
        }
        
        throw error;
      }
    }
    
    throw new Error(`Failed to process chunk after ${MAX_RETRIES} retries due to deadlocks`);
  }

  async processFileInChunks(filePath, jobId, filename) {
    console.log("[INFO] Starting file processing:", filePath);
    let totalRecords = 0;
    let processedRecords = 0;
    const startTime = Date.now();

    try {
      // Parse CSV file
      const { records, failedRecords } = await this.validateAndParseCSV(filePath);
      totalRecords = records.length + failedRecords.length;
      console.log("[INFO] Total records in file:", totalRecords);
      console.log("[INFO] Failed records:", failedRecords.length);

      // Get initial count for this job
      const initialCount = await db.blacklist.count();
      console.log("[INFO] Initial blacklist count:", initialCount);

      // Save failed records if any
      if (failedRecords.length > 0) {
        const transaction = await db.sequelize.transaction();
        try {
          await db.failedUpload.bulkCreate(
            failedRecords.map((record, index) => ({
              ...record,
              job_id: jobId,
              row_number: index + 1
            })),
            { transaction }
          );
          await transaction.commit();
        } catch (error) {
          await transaction.rollback();
          throw error;
        }
      }

      // Update job with total records
      await db.uploadJob.update(
        { 
          total_records: totalRecords,
          failed_records: failedRecords.length,
          error_message: failedRecords.length > 0 ? 
            `Found ${failedRecords.length} records with missing domains. Check failed_uploads table for details.` : 
            null
        },
        { where: { id: jobId } }
      );
      
      // Process in chunks
      for (let i = 0; i < records.length; i += CHUNK_SIZE) {
        const chunk = records.slice(i, i + CHUNK_SIZE);
        
        try {
          const result = await this.processChunkWithRetry(
            chunk,
            jobId,
            filename,
            startTime,
            totalRecords,
            processedRecords,
            initialCount
          );
          
          processedRecords = result.processedRecords;
          
          // Add delay between chunks
          await sleep(BATCH_DELAY);
          
        } catch (error) {
          console.error("[ERROR] Error processing chunk:", error.message);
          throw error;
        }
      }

      // Get final counts
      const finalCount = await db.blacklist.count();
      const uniqueDomains = finalCount - initialCount;
      const duplicateDomains = processedRecords - uniqueDomains; // Only count actual duplicates, not failed records

      console.log("[INFO] Processing complete:");
      console.log("[INFO] Initial blacklist count:", initialCount);
      console.log("[INFO] Final blacklist count:", finalCount);
      console.log("[INFO] Total records processed:", processedRecords);
      console.log("[INFO] Unique domains inserted:", uniqueDomains);
      console.log("[INFO] Duplicate domains skipped:", duplicateDomains);
      console.log("[INFO] Failed records:", failedRecords.length);
      console.log("[INFO] Actual new domains in database:", finalCount - initialCount);

      // Prepare completion message
      let completionMessage = `Successfully processed ${totalRecords} records | `;
      if (failedRecords.length > 0) {
        completionMessage += `${failedRecords.length} records failed validation | `;
      }
      if (duplicateDomains > 0) {
        completionMessage += `${duplicateDomains} duplicate domains were skipped | `;
      }
      completionMessage += `${uniqueDomains} new domains were added to the database`;

      // Final update
      const finalProcessingTime = (Date.now() - startTime) / 1000;
      await db.uploadJob.update(
        {
          status: 'completed',
          processing_time: finalProcessingTime,
          total_records: totalRecords,
          processed_records: processedRecords,
          unique_domains: uniqueDomains,
          duplicate_domains: duplicateDomains,
          failed_records: failedRecords.length,
          error_message: completionMessage
        },
        { where: { id: jobId } }
      );

      // emit completion data 
      if (global.io) {
        global.io.emit('uploadProgress', {
          jobId,
          filename,
          progress: 100,
          processedRecords,
          totalRecords,
          uniqueDomains,
          duplicateDomains,
          failedRecords: failedRecords.length,
          processingTime: (Date.now() - startTime) / 1000,
          status: 'completed'
        });
      }

      // Clean up file
      fs.unlink(filePath, (err) => {
        if (err) console.error("[ERROR] Error deleting file:", err);
        else console.log("[INFO] Cleaned up file:", filePath);
      });

    } catch (error) {
      console.error("[ERROR] Final Processing Error:", error.message);
      
      // Prepare error message
      let errorMessage = `Error processing file: ${error.message}. `;
      if (error.name === 'SequelizeUniqueConstraintError') {
        errorMessage += "This might be due to duplicate domains in the file.";
      } else if (error.name === 'SequelizeValidationError') {
        errorMessage += "Some records failed validation. Please check the data format.";
      } else if (error.name === 'SequelizeConnectionError') {
        errorMessage += "Database connection error. Please try again.";
      } else if (error.name === 'SequelizeDatabaseError' && error.parent?.code === '40P01') {
        errorMessage += "Database deadlock detected. Please try again.";
      }

      // Update job status to failed
      await db.uploadJob.update(
        {
          status: 'failed',
          error_message: errorMessage,
          processing_time: (Date.now() - startTime) / 1000
        },
        { where: { id: jobId } }
      );

      // Clean up file
      fs.unlink(filePath, (err) => {
        if (err) console.error("[ERROR] Error deleting file:", err);
        else console.log("[INFO] Cleaned up file:", filePath);
      });

      throw error;
    }
  }

  async processMultipleFiles(files) {
    const jobs = [];
    for (const file of files) {
      const job = await db.uploadJob.create({
        filename: file.filename,
        status: 'pending'
      });
      jobs.push(job);
      
      // Process each file in the background
      this.processFileInChunks(file.path, job.id, job.filename)
        .catch(error => {
          console.error('Error processing file:', error);
        });
    }
    return jobs;
  }

  async getJobStatus(jobId) {
    return await db.uploadJob.findByPk(jobId);
  }

  async getAllJobs() {
    return await db.uploadJob.findAll({
      order: [['createdAt', 'DESC']],
      attributes: [
        'id',
        'filename',
        'status',
        'failed_records',
        'total_records',
        'processed_records',
        'unique_domains',
        'duplicate_domains',
        'processing_time',
        'error_message',
        'createdAt',
        'updatedAt'
      ]
    });
  }

  async retryFailedJob(jobId) {
    const job = await db.uploadJob.findByPk(jobId);
    if (!job) {
      throw new Error('Job not found');
    }

    if (job.status !== 'failed') {
      throw new Error('Only failed jobs can be retried');
    }

    // Reset job status
    await job.update({
      status: 'pending',
      processed_records: 0,
      unique_domains: 0,
      duplicate_domains: 0,
      processing_time: 0,
      error_message: null
    });

    // Retry processing
    return this.processFileInChunks(job.filename, job.id);
  }

  async processMultipleFilesSafe(files, jobs) {
    console.log("[INFO] Starting safe sequential file processing");
    const startTime = Date.now();
    let processedFiles = 0;
    let totalRecords = 0;
    let totalUniqueDomains = 0;
    let totalDuplicateDomains = 0;

    try {
      // Emit initial state for all jobs
      if (global.io) {
        for (const job of jobs) {
          global.io.emit('uploadProgress', {
            jobId: job.id,
            filename: job.filename,
            progress: 0,
            processedFiles: 0,
            totalFiles: files.length,
            totalRecords: 0,
            totalUniqueDomains: 0,
            totalDuplicateDomains: 0,
            processingTime: 0,
            status: 'pending'
          });
        }
      }

      // Process each file sequentially
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const fileJob = jobs[i];
        
        console.log(`[INFO] Processing file ${i + 1}/${files.length}: ${file.filename}`);
        
        try {
          // Update file job status to processing
          await db.uploadJob.update(
            {
              status: 'processing'
            },
            { where: { id: fileJob.id } }
          );

          // Get initial count for this file
          const initialCount = await db.blacklist.count();
          console.log(`[INFO] Initial blacklist count for ${file.filename}: ${initialCount}`);

          // Process the file
          await this.processFileInChunks(file.path, fileJob.id, file.filename);
          
          // Get the final stats for this file
          const fileStats = await db.uploadJob.findByPk(fileJob.id);
          const finalCount = await db.blacklist.count();
          const failedRecords = await db.failedUpload.findAll({
            where: { job_id: fileJob.id }
          });   
          
          // Calculate unique and duplicate domains for this file
          const uniqueDomains = finalCount - initialCount;
          const duplicateDomains = fileStats.total_records - uniqueDomains - failedRecords.length;
          
          // Update file job with accurate stats
          await db.uploadJob.update(
            {
              unique_domains: uniqueDomains,
              duplicate_domains: duplicateDomains,
              status: 'completed'
            },
            { where: { id: fileJob.id } }
          );
          
          // Update totals
          totalRecords += fileStats.total_records;
          totalUniqueDomains += uniqueDomains;
          totalDuplicateDomains += duplicateDomains;
          processedFiles++;

        } catch (error) {
          console.error(`[ERROR] Error processing file ${file.filename}:`, error);
          
          // Update file job status
          await db.uploadJob.update(
            {
              status: 'failed',
              error_message: `Error processing file: ${error.message}`
            },
            { where: { id: fileJob.id } }
          );

          // Emit error update
          if (global.io) {
            global.io.emit('uploadProgress', {
              jobId: fileJob.id,
              filename: file.filename,
              status: 'failed',
              error: error.message
            });
          }

          throw error;
        }
      }

    } catch (error) {
      console.error("[ERROR] Safe Sequential Processing Error:", error);
      throw error;
    }
  }
}

module.exports = UploadService; 