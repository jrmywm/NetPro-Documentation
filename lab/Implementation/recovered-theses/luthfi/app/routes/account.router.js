const express = require('express');
const router = express.Router();
const AccountController = require('../controllers/Account.controller');

// Register route
router.post('/register', AccountController.register);

// Login route
router.post('/login', AccountController.login);

module.exports = router; 
