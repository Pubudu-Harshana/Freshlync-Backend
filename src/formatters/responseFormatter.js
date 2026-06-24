/**
 * Response Formatter for the FreshLync Chatbot.
 * Ensures the backend ONLY returns structured, standardized JSON responses.
 * Contains no HTML or markdown formatting logic.
 */

/**
 * Formats a chatbot response into a standard structured JSON payload.
 * @param {string} type - Response type ('order_status', 'product_info', 'category_search', 'notifications', 'reviews', 'fallback', 'general_help')
 * @param {object} data - Structured database results
 * @returns {object} Standardized JSON response
 */
function formatResponse(type, data = {}) {
  const validTypes = [
    'order_status',
    'product_info',
    'category_search',
    'notifications',
    'reviews',
    'fallback',
    'general_help'
  ];

  const resolvedType = validTypes.includes(type) ? type : 'fallback';

  return {
    success: true,
    type: resolvedType,
    data
  };
}

module.exports = {
  formatResponse
};
