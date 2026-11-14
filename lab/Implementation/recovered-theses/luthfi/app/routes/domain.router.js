const express = require('express');
const router = express.Router();
const DomainController = require('../controllers/Domain.controller');

// Get domains with pagination and search
router.get('/', DomainController.getDomains);

// Get domain by ID
router.get('/:id', DomainController.getDomainById);

module.exports = router; 
