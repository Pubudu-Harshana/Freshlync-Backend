/**
 * Intent detection service for FreshLync Chatbot.
 * Uses a robust, deterministic, weighted scoring system based on keywords,
 * phrase patterns, and regex extractions to classify user queries.
 */

const INTENTS = {
  ORDER_STATUS: 'ORDER_STATUS',
  PRODUCT_PRICE: 'PRODUCT_PRICE',
  PRODUCT_STOCK: 'PRODUCT_STOCK',
  CATEGORY_SEARCH: 'CATEGORY_SEARCH',
  NOTIFICATIONS: 'NOTIFICATIONS',
  REVIEWS: 'REVIEWS',
  GENERAL_HELP: 'GENERAL_HELP',
  FALLBACK_SEARCH: 'FALLBACK_SEARCH'
};

const CATEGORIES = ['fish', 'meat', 'vegetables', 'fruit', 'dairy', 'spices', 'seafood', 'poultry', 'greens', 'produce'];

/**
 * Detects intent and extracts parameters from a user message.
 * @param {string} message 
 * @returns {object} { intent, confidence, params }
 */
function detectIntent(message) {
  if (!message || typeof message !== 'string') {
    return { intent: INTENTS.FALLBACK_SEARCH, confidence: 0, params: {} };
  }

  const m = message.toLowerCase().trim();
  const scores = {};
  const params = {};

  // Initialize scores
  Object.keys(INTENTS).forEach(intent => {
    scores[intent] = 0.0;
  });

  // 1. ORDER_STATUS INTENT
  const orderIdRegex = /\b([a-f0-9]{24})\b/i;
  const shortOrderIdRegex = /\b([a-f0-9]{8})\b/i;
  const orderIdMatch = message.match(orderIdRegex);
  const shortOrderIdMatch = message.match(shortOrderIdRegex);

  let hasOrderId = false;
  if (orderIdMatch) {
    params.orderId = orderIdMatch[1];
    hasOrderId = true;
  } else if (shortOrderIdMatch && (m.includes('order') || m.includes('status') || m.includes('track'))) {
    params.orderId = shortOrderIdMatch[1];
    hasOrderId = true;
  }

  let orderScore = 0.0;
  if (hasOrderId) {
    orderScore = 0.95; // Direct match on ID
  } else if (m.includes('status of order') || m.includes('track order') || m.includes('where is my order') || m.includes('delivery status') || m.includes('order status')) {
    orderScore = 0.9;
  } else {
    const orderKeywords = ['order', 'orders', 'track', 'shipment', 'delivery', 'purchase', 'purchases', 'history', 'reorder'];
    if (orderKeywords.some(kw => m.includes(kw))) {
      orderScore = 0.8;
    }
  }
  scores[INTENTS.ORDER_STATUS] = orderScore;


  // Helper to extract product name candidates from phrases
  const extractProductName = (text, phrases) => {
    for (const phrase of phrases) {
      const idx = text.indexOf(phrase);
      if (idx !== -1) {
        let candidate = text.substring(idx + phrase.length).trim();
        // Remove trailing question marks or punctuation
        candidate = candidate.replace(/[?.!,]/g, '').trim();
        if (candidate.length > 1) {
          return candidate;
        }
      }
    }
    return null;
  };

  // 2. PRODUCT_PRICE INTENT
  let priceScore = 0.0;
  const pricePhrases = ['price of', 'how much is', 'how much for', 'cost of', 'price for', 'cost for', 'value of'];
  const extractedPriceProduct = extractProductName(m, pricePhrases);
  
  if (extractedPriceProduct) {
    params.productName = extractedPriceProduct;
    priceScore = 0.9;
  } else {
    const priceKeywords = ['price', 'prices', 'cost', 'costs', 'how much', 'value', 'cheapest', 'lowest price', 'affordable', 'deals', 'discount'];
    if (priceKeywords.some(kw => m.includes(kw))) {
      priceScore = 0.8;
    }
  }
  scores[INTENTS.PRODUCT_PRICE] = priceScore;


  // 3. PRODUCT_STOCK INTENT
  let stockScore = 0.0;
  const stockPhrases = ['stock of', 'is there any', 'do you have', 'is there', 'availability of', 'in stock'];
  const extractedStockProduct = extractProductName(m, stockPhrases);
  
  if (extractedStockProduct) {
    if (!CATEGORIES.includes(extractedStockProduct)) {
      params.productName = extractedStockProduct;
      stockScore = 0.9;
    }
  } else {
    const stockKeywords = ['stock', 'stocks', 'available', 'availability', 'in stock', 'in-stock', 'quantity', 'quantities', 'do you have', 'bulk', 'wholesale'];
    if (stockKeywords.some(kw => m.includes(kw))) {
      stockScore = 0.8;
    }
  }
  scores[INTENTS.PRODUCT_STOCK] = stockScore;


  // 4. CATEGORY_SEARCH INTENT
  let categoryScore = 0.0;
  let matchedCategory = null;
  for (const cat of CATEGORIES) {
    if (m.includes(cat) || (cat === 'vegetables' && (m.includes('veg') || m.includes('vegetable')))) {
      matchedCategory = cat;
      break;
    }
  }
  
  if (matchedCategory) {
    params.category = matchedCategory;
    const catBrowseKeywords = ['show', 'list', 'browse', 'all', 'what', 'category', 'categories'];
    if (catBrowseKeywords.some(kw => m.includes(kw))) {
      categoryScore = 0.9;
    } else {
      categoryScore = 0.7; // Moderate score, can be overridden by price/stock if they are present
    }
  }
  scores[INTENTS.CATEGORY_SEARCH] = categoryScore;


  // 5. NOTIFICATIONS INTENT
  let notifScore = 0.0;
  const notifKeywords = ['notification', 'notifications', 'alert', 'alerts', 'unread', 'messages', 'system updates', 'payouts'];
  if (notifKeywords.some(kw => m.includes(kw))) {
    notifScore = 0.9;
  }
  scores[INTENTS.NOTIFICATIONS] = notifScore;


  // 6. REVIEWS INTENT
  let reviewScore = 0.0;
  const reviewKeywords = ['review', 'reviews', 'feedback', 'testimonial', 'testimonials', 'rating', 'ratings', 'what do customers say', 'what do buyers say', 'what do clients say', 'client', 'clients', 'is it good', 'reputation'];
  if (reviewKeywords.some(kw => m.includes(kw))) {
    reviewScore = 0.9;
  }
  scores[INTENTS.REVIEWS] = reviewScore;


  // 7. GENERAL_HELP INTENT
  let helpScore = 0.0;
  const helpKeywords = ['help', 'what can you do', 'commands', 'options', 'menu', 'information', 'how to use', 'help me'];
  const greetingsKeywords = ['hello', 'hi', 'hey', 'good morning', 'good evening', 'howdy', 'greetings', 'thank', 'thanks', 'bye', 'goodbye', 'see you', 'great', 'awesome'];
  
  if (helpKeywords.some(kw => m.includes(kw)) || greetingsKeywords.some(kw => m.includes(kw))) {
    helpScore = 0.95;
  }
  scores[INTENTS.GENERAL_HELP] = helpScore;

  // ── RESOLUTION ──
  let bestIntent = INTENTS.FALLBACK_SEARCH;
  let bestScore = 0.0;

  Object.entries(scores).forEach(([intent, score]) => {
    if (score > bestScore) {
      bestScore = score;
      bestIntent = intent;
    }
  });

  // Threshold check: If highest confidence is below 0.5, default to FALLBACK_SEARCH
  if (bestScore < 0.5) {
    bestIntent = INTENTS.FALLBACK_SEARCH;
    bestScore = 0.5;
  }

  // Refine parameter extraction for price/stock fallback
  if ((bestIntent === INTENTS.PRODUCT_PRICE || bestIntent === INTENTS.PRODUCT_STOCK) && !params.productName) {
    const skipWords = [
      'price', 'prices', 'cost', 'costs', 'how', 'much', 'value', 'cheapest', 'lowest', 'affordable', 'deals', 'discount',
      'stock', 'stocks', 'available', 'availability', 'in', 'quantity', 'quantities', 'do', 'you', 'have', 'bulk', 'wholesale',
      'is', 'there', 'any', 'for', 'and', 'with', 'what', 'show', 'list', 'the', 'of'
    ];
    const cleanWords = m.split(/\s+/).filter(w => w.length > 2 && !skipWords.includes(w));
    if (cleanWords.length > 0) {
      params.productName = cleanWords.join(' ');
    }
  }

  return {
    intent: bestIntent,
    confidence: Number(bestScore.toFixed(2)),
    params
  };
}

module.exports = {
  INTENTS,
  detectIntent
};
