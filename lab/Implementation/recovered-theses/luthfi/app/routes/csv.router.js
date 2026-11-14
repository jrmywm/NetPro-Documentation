let express = require("express");
let router = express.Router();
let CsvController = require("../controllers/csv.controller.js");
let { upload, handleMulterError, checkTotalSize } = require("../middlewares/multer.middlewares.js");

let path = __basedir + "/views/";

// router.get("/", (req, res) => {
//   console.log("_basedir" + __basedir);
//   res.sendFile(path + "index.html");
// });

// Upload single file
router.post("/csv-upload", upload.single("file"), CsvController.uploadFile);

// Upload multiple files
router.post(
  "/csv-multiple-upload",
  upload.array("files", 10),
  checkTotalSize,
  CsvController.uploadMultipleFiles
);

// Upload multiple files with safe logging
router.post(
  "/csv-multiple-upload/safe",
  upload.array("files", 10),
  checkTotalSize,
  CsvController.uploadMultipleFilesSafe
);

// Download file
router.get("/csv-file", CsvController.downloadFile);

// Get allowed file extensions
router.get("/allowed-file-extensions", CsvController.getAllowedFileExtensions);

// Get file size limits
router.get("/file-size-limits", CsvController.getFileSizeLimits);

// Add error handling middleware
router.use(handleMulterError);

module.exports = router;
