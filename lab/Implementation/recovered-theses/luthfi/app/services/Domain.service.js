const db = require("../config/db.config");
const Blacklist = db.blacklist;
const { Op } = require('sequelize');

const getDomains = async (page = 1, limit = 50, search = '') => {
  try {
    const offset = (page - 1) * limit;
    
    // Build search condition
    const searchCondition = search ? {
      [Op.or]: [
        { domain: { [Op.iLike]: `%${search}%` } },
        { name: { [Op.iLike]: `%${search}%` } }
      ]
    } : {};

    // Get total count for pagination
    const total = await Blacklist.count({ where: searchCondition });

    // Get paginated data
    const domains = await Blacklist.findAll({
      where: searchCondition,
      attributes: ['id', 'name', 'domain', 'reason', 'category', 'hit_count'],
      order: [['domain', 'ASC']], // Sort by domain name alphabetically
      limit,
      offset
    });

    return {
      domains,
      pagination: {
        total,
        page,
        limit,
        totalPages: Math.ceil(total / limit)
      }
    };
  } catch (error) {
    throw error;
  }
};

const getDomainById = async (id) => {
  try {
    const domain = await Blacklist.findOne({
      where: { id },
      attributes: ['id', 'name', 'domain', 'reason', 'category', 'hit_count']
    });
    return domain;
  } catch (error) {
    throw error;
  }
};

module.exports = {
  getDomains,
  getDomainById
}; 