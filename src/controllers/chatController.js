/**
 * Chat Controller for the FreshLync Chatbot.
 * Lightweight request handler that orchestrates intent classification,
 * database query execution, and standard structured JSON formatting.
 */

const intentService = require('../services/intentService');
const productService = require('../services/productService');
const orderService = require('../services/orderService');
const notificationService = require('../services/notificationService');
const reviewService = require('../services/reviewService');
const { formatResponse } = require('../formatters/responseFormatter');

/**
 * Handles incoming chatbot queries.
 * POST /api/chat
 */
exports.chat = async (req, res) => {
  const { message } = req.body;
  const user = req.user;

  if (!message || !message.trim()) {
    return res.status(400).json({ success: false, message: 'Message is required.' });
  }

  try {
    // 1. Detect user intent and extract parameters
    const { intent, confidence, params } = intentService.detectIntent(message);

    let responseType = 'fallback';
    let responseData = {};

    // 2. Route to appropriate database service based on intent
    switch (intent) {
      case intentService.INTENTS.ORDER_STATUS:
        if (params.orderId) {
          try {
            const orderDetails = await orderService.getOrderDetails(params.orderId, user._id, user.role);
            responseType = 'order_status';
            responseData = {
              orderFound: true,
              order: orderDetails
            };
          } catch (err) {
            // Handle order not found (404) or unauthorized (403) specifically
            if (err.status === 403 || err.status === 404) {
              responseType = 'order_status';
              responseData = {
                orderFound: false,
                error: err.message,
                status: err.status
              };
            } else {
              throw err;
            }
          }
        } else {
          // If no order ID was provided, return their recent orders as a helpful context
          const recentOrders = await orderService.getRecentOrders(user._id, user.role);
          responseType = 'order_status';
          responseData = {
            orderFound: false,
            error: 'Please provide a specific Order ID to track.',
            recentOrders
          };
        }
        break;

      case intentService.INTENTS.PRODUCT_PRICE:
        if (params.productName) {
          const priceInfo = await productService.getProductInfo(params.productName);
          responseType = 'product_info';
          responseData = {
            queryType: 'price',
            productName: params.productName,
            ...priceInfo
          };
        } else {
          // Fallback if no specific product was extracted
          const fallbackProducts = await productService.searchFallback(message);
          responseType = 'fallback';
          responseData = {
            message: "I couldn't identify the product you're asking about. Here are some of our available products:",
            products: fallbackProducts
          };
        }
        break;

      case intentService.INTENTS.PRODUCT_STOCK:
        if (params.productName) {
          const stockInfo = await productService.getProductInfo(params.productName);
          responseType = 'product_info';
          responseData = {
            queryType: 'stock',
            productName: params.productName,
            ...stockInfo
          };
        } else {
          // Fallback if no specific product was extracted
          const fallbackProducts = await productService.searchFallback(message);
          responseType = 'fallback';
          responseData = {
            message: "I couldn't identify the product you're asking about. Here are some of our available products:",
            products: fallbackProducts
          };
        }
        break;

      case intentService.INTENTS.CATEGORY_SEARCH:
        if (params.category) {
          const categoryProducts = await productService.getCategoryProducts(params.category);
          responseType = 'category_search';
          responseData = {
            category: params.category,
            products: categoryProducts
          };
        } else {
          // Fallback if no category extracted
          const fallbackProducts = await productService.searchFallback(message);
          responseType = 'fallback';
          responseData = {
            message: "Here are some of our available products:",
            products: fallbackProducts
          };
        }
        break;

      case intentService.INTENTS.NOTIFICATIONS:
        const notificationsData = await notificationService.getRecentNotifications(user._id);
        responseType = 'notifications';
        responseData = notificationsData;
        break;

      case intentService.INTENTS.REVIEWS:
        const reviewsData = await reviewService.getPlatformReviews();
        responseType = 'reviews';
        responseData = reviewsData;
        break;

      case intentService.INTENTS.GENERAL_HELP:
        responseType = 'general_help';
        responseData = {
          userName: user.name || 'Trader'
        };
        break;

      case intentService.INTENTS.FALLBACK_SEARCH:
      default:
        // Smart fallback recovery: perform database text search over query terms
        const fallbackProducts = await productService.searchFallback(message);
        responseType = 'fallback';
        responseData = {
          message: "I couldn't find a direct match for your request. Here are some products you might be looking for:",
          products: fallbackProducts
        };
        break;
    }

    // 3. Format the response and send structured JSON
    const formattedResponse = formatResponse(responseType, responseData);
    res.json(formattedResponse);

  } catch (err) {
    console.error('[FreshLync Chat Controller Error]:', err.message);
    res.status(500).json({
      success: false,
      message: 'Chat service temporarily unavailable. Please try again.'
    });
  }
};
