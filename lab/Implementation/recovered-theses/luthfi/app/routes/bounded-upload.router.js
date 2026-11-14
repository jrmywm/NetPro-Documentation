const express = require('express');
const multer = require('multer');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const db = require('../config/db.config');
const { inputRoot } = require('../services/persistent-upload.service');

function publicJob(job) {
  const data = job.toJSON ? job.toJSON() : { ...job };
  delete data.input_path; delete data.input_sha256;
  return data;
}
function createUploadRouter(queue) {
  fs.mkdirSync(inputRoot, { recursive: true, mode: 0o700 });
  const upload = multer({ storage: multer.diskStorage({
    destination: inputRoot, filename: (_req, _file, cb) => cb(null, randomUUID() + '.csv')
  }), limits: { fileSize: 10 * 1024 * 1024, files: 5, fields: 10 },
    fileFilter: (_req, file, cb) => cb(path.extname(file.originalname).toLowerCase() === '.csv' ? null : Error('Only CSV files are accepted'), true) });
  const router = express.Router();
  const handle = single => async (req, res, next) => {
    const files = single ? (req.file ? [req.file] : []) : (req.files || []);
    if (!files.length) return res.status(400).json({ message: 'Upload at least one CSV file' });
    try {
      const jobs = await queue.enqueue(files);
      res.status(202).json({ status: 'success', message: 'Upload durably queued',
        data: single ? { jobId: jobs[0].id } : { jobs: jobs.map(publicJob) } });
    } catch (error) {
      // These are rejected, unreferenced request-owned temporary inputs, not retained jobs.
      for (const file of files) await fs.promises.unlink(file.path).catch(() => {});
      next(error);
    }
  };
  router.post('/csv-upload', upload.single('file'), handle(true));
  router.post('/csv-multiple-upload', upload.array('files', 5), handle(false));
  router.post('/csv-multiple-upload/safe', upload.array('files', 5), handle(false));
  router.use((error, _req, res, _next) => res.status(error.code === 'LIMIT_FILE_SIZE' ? 413 : 400).json({ message: error.message }));
  return router;
}
function createJobRouter(queue) {
  const router = express.Router();
  router.get('/', async (_req, res, next) => {
    try { res.json({ data: (await db.uploadJob.findAll({ order: [['id', 'DESC']], limit: 50 })).map(publicJob) }); } catch (e) { next(e); }
  });
  router.get('/:id', async (req, res, next) => {
    try {
      if (!/^\d+$/.test(req.params.id)) return res.status(400).json({ message: 'Invalid job ID' });
      const job = await db.uploadJob.findByPk(req.params.id);
      if (!job) return res.status(404).json({ message: 'Job not found' });
      res.json({ data: publicJob(job) });
    } catch (e) { next(e); }
  });
  router.post('/:id/retry', async (req, res) => {
    try { await queue.retry(req.params.id); res.status(202).json({ message: 'Retry queued' }); }
    catch (e) { res.status(409).json({ message: e.message }); }
  });
  return router;
}
module.exports = { createUploadRouter, createJobRouter };
