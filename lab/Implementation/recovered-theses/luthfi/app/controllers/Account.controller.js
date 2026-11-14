const sendResponse = require('../utils/Response.utilities');
const AccountService = require('../services/Account.service');

exports.register = async (req, res) => {
  try {
    const { name, email, password } = req.body;

    // Validate required fields
    if (!name || !email || !password) {
      return sendResponse(
        res,
        'error',
        400,
        'Missing required fields',
        null,
        'ValidationError',
        'Name, email, and password are required'
      );
    }

    const account = await AccountService.register(name, email, password);

    return sendResponse(
      res,
      'success',
      201,
      'Account created successfully',
      account
    );
  } catch (error) {
    if (error.message === 'Email already registered') {
      return sendResponse(
        res,
        'error',
        409,
        'Registration failed',
        null,
        'DuplicateError',
        'Email already registered'
      );
    }

    return sendResponse(
      res,
      'error',
      500,
      'Registration failed',
      null,
      'ServerError',
      error.message
    );
  }
};

exports.login = async (req, res) => {
  try {
    const { email, password } = req.body;

    // Validate required fields
    if (!email || !password) {
      return sendResponse(
        res,
        'error',
        400,
        'Missing required fields',
        null,
        'ValidationError',
        'Email and password are required'
      );
    }

    const account = await AccountService.login(email, password);

    return sendResponse(
      res,
      'success',
      200,
      'Login successful',
      account
    );
  } catch (error) {
    if (error.message === 'Account not found' || error.message === 'Invalid password') {
      return sendResponse(
        res,
        'error',
        401,
        'Login failed',
        null,
        'AuthenticationError',
        'Invalid email or password'
      );
    }

    return sendResponse(
      res,
      'error',
      500,
      'Login failed',
      null,
      'ServerError',
      error.message
    );
  }
};
