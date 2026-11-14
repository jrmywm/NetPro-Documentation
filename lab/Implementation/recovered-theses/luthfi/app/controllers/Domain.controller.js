const sendResponse = require("../utils/Response.utilities");
const DomainService = require("../services/Domain.service");

exports.getDomains = async (req, res) => {
  try {
    // Handle both 'page' and 'pages' query parameters
    const page = parseInt(req.query.page || req.query.pages) || 1;
    const limit = parseInt(req.query.limit) || 50;
    const search = req.query.search || '';

    // Validate page and limit
    if (page < 1 || limit < 1) {
      return sendResponse(
        res,
        "error",
        400,
        "Invalid pagination parameters",
        null,
        "ValidationError",
        "Page and limit must be positive numbers"
      );
    }

    const result = await DomainService.getDomains(page, limit, search);
    
    sendResponse(
      res,
      "success",
      200,
      "Domains retrieved successfully",
      result
    );
  } catch (error) {
    console.error(error);
    sendResponse(
      res,
      "error",
      500,
      "Failed to retrieve domains",
      null,
      "ServerError",
      error.message
    );
  }
};

exports.getDomainById = async (req, res) => {
  try {
    const { id } = req.params;
    
    const domain = await DomainService.getDomainById(id);
    
    if (!domain) {
      return sendResponse(
        res,
        "error",
        404,
        "Domain not found",
        null,
        "NotFoundError",
        "The requested domain does not exist"
      );
    }

    sendResponse(
      res,
      "success",
      200,
      "Domain retrieved successfully",
      domain
    );
  } catch (error) {
    console.error(error);
    sendResponse(
      res,
      "error",
      500,
      "Failed to retrieve domain",
      null,
      "ServerError",
      error.message
    );
  }
}; 
