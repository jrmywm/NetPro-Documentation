// This model is used to get the environment configuration
const allowedFileExtensions = process.env.ALLOWED_FILE_EXTENSIONS || '.csv, .xlsx, .xls, .json, .xml, .txt';
const maxSingleFileSize = process.env.MAX_SINGLE_FILE_SIZE || 100;
const maxTotalUploadSize = process.env.MAX_TOTAL_UPLOAD_SIZE || 1000;

module.exports = {
  allowedFileExtensions,
  maxSingleFileSize,
  maxTotalUploadSize
};