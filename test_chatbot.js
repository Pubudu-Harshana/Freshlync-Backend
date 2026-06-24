require('dotenv').config();
const mongoose = require('mongoose');
const connectDB = require('./src/config/db');
const intentService = require('./src/services/intentService');
const productService = require('./src/services/productService');
const orderService = require('./src/services/orderService');
const notificationService = require('./src/services/notificationService');
const reviewService = require('./src/services/reviewService');
const User = require('./src/models/User');
const Order = require('./src/models/Order');

async function runTests() {
  console.log('🧪 Starting Chatbot Automated Verification Tests...\n');
  
  await connectDB();

  // 1. Test Intent Classification
  console.log('1️⃣ Testing Intent Detection Scoring...');
  const testCases = [
    { text: 'Hello bot', expected: intentService.INTENTS.GENERAL_HELP },
    { text: 'help me please', expected: intentService.INTENTS.GENERAL_HELP },
    { text: 'price of salmon', expected: intentService.INTENTS.PRODUCT_PRICE },
    { text: 'is carrot in stock?', expected: intentService.INTENTS.PRODUCT_STOCK },
    { text: 'show me fish products', expected: intentService.INTENTS.CATEGORY_SEARCH },
    { text: 'do I have notifications?', expected: intentService.INTENTS.NOTIFICATIONS },
    { text: 'what do clients say?', expected: intentService.INTENTS.REVIEWS },
    { text: 'status of order 6a2da135692b83529ff7e74c', expected: intentService.INTENTS.ORDER_STATUS },
    { text: 'xyz123random', expected: intentService.INTENTS.FALLBACK_SEARCH }
  ];

  for (const tc of testCases) {
    const res = intentService.detectIntent(tc.text);
    const passed = res.intent === tc.expected;
    console.log(`   - "${tc.text}" -> Classified as [${res.intent}] (Confidence: ${res.confidence}) | ${passed ? '✅ PASSED' : '❌ FAILED'}`);
    if (!passed) {
      throw new Error(`Intent mismatch: expected ${tc.expected}, got ${res.intent}`);
    }
  }

  // Find a buyer and a supplier for DB queries
  const buyer = await User.findOne({ role: 'buyer' });
  const supplier = await User.findOne({ role: 'supplier' });
  
  if (!buyer || !supplier) {
    console.error('⚠️ Buyer or Supplier not found in DB! Please seed users first.');
    await mongoose.connection.close();
    process.exit(1);
  }
  
  console.log(`\nUsing Buyer: ${buyer.name} (${buyer._id})`);
  console.log(`Using Supplier: ${supplier.name} (${supplier._id})`);

  // 2. Test Product Info & Stock
  console.log('\n2️⃣ Testing Product Service...');
  const productInfo = await productService.getProductInfo('Carrot');
  if (productInfo) {
    console.log('   - getProductInfo("Carrot") -> ✅ SUCCESS');
    console.log(`     Found Product: ${productInfo.product?.name || 'None'} (Price: £${productInfo.product?.price || 0}, In Stock: ${productInfo.inStock})`);
  } else {
    console.log('   - getProductInfo("Carrot") -> ❌ FAILED');
    throw new Error('Product service returned empty result');
  }

  // 3. Test Out-of-Stock Fallback
  console.log('   - Testing non-existent product fallback...');
  const missingProduct = await productService.getProductInfo('Dragonfruit');
  console.log(`     getProductInfo("Dragonfruit") -> In Stock: ${missingProduct.inStock}, Alternatives count: ${missingProduct.alternatives.length}`);
  if (missingProduct.inStock === false && missingProduct.alternatives.length > 0) {
    console.log('     ✅ Alternatives fallback successfully resolved.');
  } else {
    throw new Error('Out of stock alternatives fallback failed');
  }

  // 4. Test Order Security & Access Control
  console.log('\n3️⃣ Testing Order Service Security & Tracking...');
  
  // Find an order placed by this buyer
  const buyerOrder = await Order.findOne({ buyer: buyer._id });
  
  if (buyerOrder) {
    console.log(`   - Testing authorized order access for Order #${buyerOrder._id}...`);
    const orderDetails = await orderService.getOrderDetails(buyerOrder._id.toString(), buyer._id, buyer.role);
    console.log(`     ✅ Access Granted. Order status: ${orderDetails.status}, Total: £${orderDetails.total}`);
    
    console.log('   - Testing unauthorized order access...');
    try {
      // Supplier should not be authorized to view the buyer's order if they are not in the items list
      const isSupplierInvolved = buyerOrder.items.some(item => item.supplier?.toString() === supplier._id.toString());
      if (!isSupplierInvolved) {
        await orderService.getOrderDetails(buyerOrder._id.toString(), supplier._id, supplier.role);
        throw new Error('Security vulnerability: unauthorized supplier was able to view buyer order!');
      } else {
        console.log('     (Supplier is involved in this order, skipping unauthorized check)');
      }
    } catch (err) {
      if (err.status === 403) {
        console.log('     ✅ Access Blocked correctly with 403 Forbidden.');
      } else {
        throw err;
      }
    }
  } else {
    console.log('   - (No orders found for this buyer in DB to test access control)');
  }

  // 5. Test Notifications Retrieval
  console.log('\n4️⃣ Testing Notification Service...');
  const notifications = await notificationService.getRecentNotifications(buyer._id);
  console.log(`   - Found ${notifications.notifications.length} alerts (Unread: ${notifications.unreadCount}) | ✅ SUCCESS`);

  // 6. Test Reviews Retrieval
  console.log('\n5️⃣ Testing Review Service...');
  const reviews = await reviewService.getPlatformReviews();
  console.log(`   - Platform Average Rating: ${reviews.averageRating} (Testimonials count: ${reviews.reviews.length}) | ✅ SUCCESS`);

  await mongoose.connection.close();
  console.log('\n🎉 All Chatbot Verification Tests Completed successfully!');
}

runTests().catch(err => {
  console.error('\n❌ Chatbot Test Suit FAILED:', err);
  if (mongoose.connection.readyState !== 0) {
    mongoose.connection.close();
  }
  process.exit(1);
});
