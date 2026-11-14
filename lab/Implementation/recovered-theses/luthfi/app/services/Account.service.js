const bcrypt = require('bcrypt');
const db = require('../config/db.config');
const Account = db.account;

const register = async (name, email, password) => {
  try {
    // Check if email already exists
    const existingAccount = await Account.findOne({ where: { email } });
    if (existingAccount) {
      throw new Error('Email already registered');
    }

    // Hash password
    const hashedPassword = await bcrypt.hash(password, 10);

    // Create new account
    const account = await Account.create({
      name,
      email,
      password: hashedPassword
    });

    return {
      id: account.id,
      name: account.name,
      email: account.email
    };
  } catch (error) {
    throw error;
  }
};

const login = async (email, password) => {
  try {
    // Find account by email
    const account = await Account.findOne({ where: { email } });
    if (!account) {
      throw new Error('Account not found');
    }

    // Verify password
    const isValidPassword = await bcrypt.compare(password, account.password);
    if (!isValidPassword) {
      throw new Error('Invalid password');
    }

    return {
      id: account.id,
      name: account.name,
      email: account.email
    };
  } catch (error) {
    throw error;
  }
};

module.exports = {
  register,
  login
};
