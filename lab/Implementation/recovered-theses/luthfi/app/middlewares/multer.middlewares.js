const multer = require("multer");
const sendResponse = require("../utils/Response.utilities");
const path = require("path");
const { allowedFileExtensions, maxSingleFileSize, maxTotalUploadSize } = require("../models/configuration.model");

// File size limits (in bytes)
const FILE_SIZE_LIMITS = {
  SINGLE_FILE: maxSingleFileSize * 1024 * 1024, 
  TOTAL: maxTotalUploadSize * 1024 * 1024 
};

// Get allowed file extensions from environment variable
const getAllowedExtensions = () => {
  const allowedExts = allowedFileExtensions;
  return allowedExts.split(',').map(ext => ext.trim().toLowerCase());
};

// MIME types mapping
const MIME_TYPES = {
  '.csv': ['text/csv', 'application/vnd.ms-excel'],
  '.xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
  '.xls': ['application/vnd.ms-excel'],
  '.json': ['application/json'],
  '.xml': ['application/xml', 'text/xml'],
  '.txt': ['text/plain']
};

const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, __basedir + "/uploads/");
  },
  filename: (req, file, cb) => {
    const now = new Date();
    const date = now.toLocaleDateString('en-GB').replace(/\//g, '-'); // Format: DD-MM-YYYY
    const time = now.toLocaleTimeString('en-US', { hour12: false }).replace(/:/g, ':'); // Format: HH:MM:SS
    
    // Get file name without extension
    const fileNameWithoutExt = path.basename(file.originalname, path.extname(file.originalname));
    
    // Create new filename with date and time
    const newFileName = `${fileNameWithoutExt}_${date}_${time}${path.extname(file.originalname)}`;
    
    cb(null, newFileName);
  },
});
  
const fileFilter = (req, file, cb) => {
  // Check file extension
  const ext = path.extname(file.originalname).toLowerCase();
  const allowedExtensions = getAllowedExtensions();
  
  if (!allowedExtensions.includes(ext)) {
    return cb(new Error(`Invalid file type! Allowed types: ${allowedExtensions.join(', ')}`), false);
  }

  // Check MIME type if extension is allowed
  const validMimeTypes = MIME_TYPES[ext] || [];
  if (!validMimeTypes.includes(file.mimetype)) {
    return cb(new Error(`Invalid MIME type for ${ext} files!`), false);
  }

  // Check file size using single file limit
  if (file.size > FILE_SIZE_LIMITS.SINGLE_FILE) {
    return cb(new Error(`File size exceeds the limit of ${FILE_SIZE_LIMITS.SINGLE_FILE / (1024 * 1024)}MB`), false);
  }

  cb(null, true);
};

// Calculate total size of files in request
const calculateTotalSize = (files) => {
  return files.reduce((total, file) => total + file.size, 0);
};

const upload = multer({ 
  storage: storage,
  fileFilter: fileFilter,
  limits: {
    fileSize: FILE_SIZE_LIMITS.SINGLE_FILE, 
    files: 10 
  }
});

// Error handling middleware
const handleMulterError = (err, req, res, next) => {
  if (err instanceof multer.MulterError) {
    switch (err.code) {
      case 'LIMIT_UNEXPECTED_FILE':
        return sendResponse(
          res,
          "error",
          400,
          "Invalid file upload",
          null,
          "ValidationError",
          "Please upload a file with key 'file' for single upload or 'files' for multiple upload"
        );
      
      case 'LIMIT_FILE_SIZE':
        return sendResponse(
          res,
          "error",
          400,
          "File too large",
          null,
          "ValidationError",
          `File size should not exceed ${FILE_SIZE_LIMITS.SINGLE_FILE / (1024 * 1024)}MB`
        );
      
      case 'LIMIT_FILE_COUNT':
        return sendResponse(
          res,
          "error",
          400,
          "Too many files",
          null,
          "ValidationError",
          "Maximum 10 files can be uploaded at once"
        );
      
      default:
        return sendResponse(
          res,
          "error",
          400,
          "File upload error",
          null,
          "ValidationError",
          err.message
        );
    }
  }

  if (err.message.includes('Only CSV, Excel, JSON, XML, TXT files are allowed') || 
      err.message.includes('Invalid file type')) {
    return sendResponse(
      res,
      "error",
      400,
      "Invalid file type",
      null,
      "ValidationError",
      "Only CSV, Excel, JSON, XML, TXT files are allowed"
    );
  }

  next(err);
};

// Middleware to check total size of multiple files
const checkTotalSize = (req, res, next) => {
  if (!req.files) return next();

  const totalSize = calculateTotalSize(req.files);
  if (totalSize > FILE_SIZE_LIMITS.TOTAL) {
    return sendResponse(
      res,
      "error",
      400,
      "Total file size too large",
      null,
      "ValidationError",
      `Total size of all files should not exceed ${FILE_SIZE_LIMITS.TOTAL / (1024 * 1024)}MB`
    );
  }
  next();
};

module.exports = { 
  upload, 
  handleMulterError,
  checkTotalSize,
  FILE_SIZE_LIMITS 
};
