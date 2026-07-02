const { GoogleGenerativeAI } = require('@google/generative-ai');
const intentService = require('../services/intentService');
const productService = require('../services/productService');
const orderService = require('../services/orderService');
const notificationService = require('../services/notificationService');
const reviewService = require('../services/reviewService');
const { formatResponse } = require('../formatters/responseFormatter');

let model = null;
if (process.env.GEMINI_API_KEY) {
  const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
  model = genAI.getGenerativeModel({ model: 'gemini-2.5-flash' });
}

/**
 * Generates conversational response text from Gemini based on database context.
 */
async function generateGeminiResponse(userMessage, intent, dbData, user) {
  if (!model) {
    return null;
  }

  const role = user ? user.role : 'guest';
  const name = user ? (user.name || 'User') : 'Guest';

  try {
    const prompt = `
You are the FreshLync B2B Assistant, an intelligent chatbot for FreshLync, a food distribution and logistics platform.
The user role is: ${role}.
The user name is: ${name}.
The user's message is: "${userMessage}"
We detected intent: "${intent}"

We retrieved the following data from the database matching this query:
${JSON.stringify(dbData, null, 2)}

Please generate a natural, helpful, friendly, and professional conversational response in English summarizing or discussing this data.
Keep your response relatively concise (2-4 sentences is best).
Do not repeat raw database IDs unless specifically relevant.
Format your response as a simple text message. Do not include markdown tables or code blocks.
`;

    const result = await model.generateContent(prompt);
    return result.response.text().trim();
  } catch (err) {
    console.error('Failed to generate Gemini response:', err.message);
    return null;
  }
}

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
        if (!user) {
          responseType = 'order_status';
          responseData = {
            orderFound: false,
            error: 'Please log in to track your orders.',
            text: 'To track your orders, please sign in to your FreshLync account.'
          };
          break;
        }
        if (params.orderId) {
          try {
            const orderDetails = await orderService.getOrderDetails(params.orderId, user._id, user.role);
            responseType = 'order_status';
            responseData = {
              orderFound: true,
              order: orderDetails
            };
            const geminiText = await generateGeminiResponse(message, intent, { order: orderDetails }, user);
            if (geminiText) responseData.text = geminiText;
          } catch (err) {
            // Handle order not found (404) or unauthorized (403) specifically
            if (err.status === 403 || err.status === 404) {
              responseType = 'order_status';
              responseData = {
                orderFound: false,
                error: err.message,
                status: err.status
              };
              const geminiText = await generateGeminiResponse(message, intent, { error: err.message }, user);
              if (geminiText) responseData.text = geminiText;
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
          const geminiText = await generateGeminiResponse(message, intent, { recentOrders, error: 'No order ID provided' }, user);
          if (geminiText) responseData.text = geminiText;
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
          const geminiText = await generateGeminiResponse(message, intent, priceInfo, user);
          if (geminiText) responseData.text = geminiText;
        } else {
          // Fallback if no specific product was extracted
          const fallbackProducts = await productService.searchFallback(message);
          responseType = 'fallback';
          responseData = {
            message: "I couldn't identify the product you're asking about. Here are some of our available products:",
            products: fallbackProducts
          };
          const geminiText = await generateGeminiResponse(message, intent, { fallbackProducts, error: 'Product name not specified' }, user);
          if (geminiText) responseData.text = geminiText;
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
          const geminiText = await generateGeminiResponse(message, intent, stockInfo, user);
          if (geminiText) responseData.text = geminiText;
        } else {
          // Fallback if no specific product was extracted
          const fallbackProducts = await productService.searchFallback(message);
          responseType = 'fallback';
          responseData = {
            message: "I couldn't identify the product you're asking about. Here are some of our available products:",
            products: fallbackProducts
          };
          const geminiText = await generateGeminiResponse(message, intent, { fallbackProducts, error: 'Product name not specified' }, user);
          if (geminiText) responseData.text = geminiText;
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
          const geminiText = await generateGeminiResponse(message, intent, { category: params.category, products: categoryProducts }, user);
          if (geminiText) responseData.text = geminiText;
        } else {
          // Fallback if no category extracted
          const fallbackProducts = await productService.searchFallback(message);
          responseType = 'fallback';
          responseData = {
            message: "Here are some of our available products:",
            products: fallbackProducts
          };
          const geminiText = await generateGeminiResponse(message, intent, { fallbackProducts, error: 'Category not specified' }, user);
          if (geminiText) responseData.text = geminiText;
        }
        break;

      case intentService.INTENTS.NOTIFICATIONS:
        if (!user) {
          responseType = 'notifications';
          responseData = {
            unreadCount: 0,
            notifications: [],
            text: 'Please log in to view your recent notifications.'
          };
          break;
        }
        const notificationsData = await notificationService.getRecentNotifications(user._id);
        responseType = 'notifications';
        responseData = notificationsData;
        const geminiTextNotif = await generateGeminiResponse(message, intent, notificationsData, user);
        if (geminiTextNotif) responseData.text = geminiTextNotif;
        break;

      case intentService.INTENTS.REVIEWS:
        const reviewsData = await reviewService.getPlatformReviews();
        responseType = 'reviews';
        responseData = reviewsData;
        const geminiTextRev = await generateGeminiResponse(message, intent, reviewsData, user);
        if (geminiTextRev) responseData.text = geminiTextRev;
        break;

      case intentService.INTENTS.GENERAL_HELP:
        responseType = 'general_help';
        responseData = {
          userName: user ? (user.name || 'Trader') : 'Guest'
        };
        const geminiTextHelp = await generateGeminiResponse(message, intent, { userName: responseData.userName }, user);
        if (geminiTextHelp) responseData.text = geminiTextHelp;
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
        const geminiTextFallback = await generateGeminiResponse(message, intent, { fallbackProducts }, user);
        if (geminiTextFallback) {
          responseData.text = geminiTextFallback;
          responseData.message = geminiTextFallback;
        }
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
