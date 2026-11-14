const Queue = require('better-queue');
const fs = require('fs').promises;

class QueueService {
  constructor() {
    this.processingQueue = new Queue(async (input, cb) => {
      const { filePath, jobId, filename, processFileInChunks } = input;
      
      try {
        // Check if file exists before processing
        await fs.access(filePath);
        
        // Process the file
        await processFileInChunks(filePath, jobId, filename);
        
        // Clean up file after successful processing
        try {
          await fs.unlink(filePath);
          console.log(`[INFO] Cleaned up file: ${filePath}`);
        } catch (cleanupError) {
          console.error(`[WARN] Error cleaning up file ${filePath}:`, cleanupError.message);
        }
        
        cb(null, { success: true });
      } catch (error) {
        // Handle file not found error
        if (error.code === 'ENOENT') {
          console.error(`[ERROR] File not found: ${filePath}`);
          cb(new Error(`File not found: ${filename}`));
        } else {
          console.error(`[ERROR] Processing error for ${filename}:`, error);
          cb(error);
        }
      }
    }, {
      concurrent: 1, // Process one file at a time
      maxRetries: 3,
      retryDelay: 5000,
      failTaskOnProcessException: true
    });

    // Queue event handlers
    this.processingQueue.on('failed', (taskId, error) => {
      console.error(`[ERROR] Task ${taskId} failed:`, error.message);
    });

    this.processingQueue.on('completed', (taskId, result) => {
      console.log(`[INFO] Task ${taskId} completed successfully`);
    });

    this.processingQueue.on('retrying', (taskId, error) => {
      console.log(`[INFO] Retrying task ${taskId} after error:`, error.message);
    });
  }

  addToQueue(task) {
    return new Promise((resolve, reject) => {
      this.processingQueue.push(task, (err, result) => {
        if (err) reject(err);
        else resolve(result);
      });
    });
  }

  getQueueStatus() {
    return {
      length: this.processingQueue.length,
      running: this.processingQueue.running
    };
  }
}

// Export singleton instance
module.exports = new QueueService(); 