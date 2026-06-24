require('dotenv').config();
const mongoose = require('mongoose');
const connectDB = require('./src/config/db');
const User = require('./src/models/User');
const Order = require('./src/models/Order');
const Invoice = require('./src/models/Invoice');
const Product = require('./src/models/Product');
const billingController = require('./src/controllers/billingController');
const orderController = require('./src/controllers/orderController');

async function runTests() {
  console.log('🧪 Starting B2B Billing & Credit Automated Verification Tests...\n');
  
  await connectDB();

  // Find a buyer
  const buyer = await User.findOne({ role: 'buyer' });
  if (!buyer) {
    console.error('⚠️ Buyer not found in DB! Please seed users first.');
    await mongoose.connection.close();
    process.exit(1);
  }
  console.log(`Using Buyer: ${buyer.name} (${buyer._id})`);

  // Clear existing invoices for this buyer to ensure a clean state
  await Invoice.deleteMany({ buyer: buyer._id });
  console.log('🧹 Cleaned existing invoices for buyer.');

  // 1. Test Billing Data retrieval and seeding
  console.log('\n1️⃣ Testing Billing Data Retrieval & Autoseeding...');
  
  const reqMock = { user: buyer };
  let jsonRes = null;
  const resMock = {
    json: function(data) {
      jsonRes = data;
      return this;
    },
    status: function() { return this; }
  };

  await billingController.getBillingData(reqMock, resMock);

  if (jsonRes && jsonRes.success) {
    console.log('   - getBillingData -> ✅ SUCCESS');
    console.log(`     Seeded Invoice Count: ${jsonRes.invoices.length}`);
    console.log(`     Credit Limit: £${jsonRes.creditLimit}`);
    console.log(`     Outstanding Balance: £${jsonRes.outstanding}`);
    console.log(`     Available Credit: £${jsonRes.availableCredit}`);
    console.log(`     Next Payment Due: ${jsonRes.nextPaymentDate}`);
    
    if (jsonRes.invoices.length !== 4) {
      throw new Error('Autoseeding failed: expected 4 invoices, got ' + jsonRes.invoices.length);
    }
  } else {
    throw new Error('Failed to retrieve billing data');
  }

  // 2. Test Invoice Payment
  console.log('\n2️⃣ Testing Invoice Payment Flow...');
  
  // Find an unpaid invoice
  const unpaidInvoice = await Invoice.findOne({ buyer: buyer._id, status: 'Unpaid' });
  if (!unpaidInvoice) {
    throw new Error('No unpaid invoice found to test payment');
  }
  console.log(`   - Paying Invoice ${unpaidInvoice.invoiceNumber} (£${unpaidInvoice.amount})...`);

  const payReqMock = {
    user: buyer,
    params: { id: unpaidInvoice._id.toString() }
  };
  let payJsonRes = null;
  const payResMock = {
    json: function(data) {
      payJsonRes = data;
      return this;
    },
    status: function() { return this; }
  };

  await billingController.payInvoice(payReqMock, payResMock);

  if (payJsonRes && payJsonRes.success) {
    console.log('   - payInvoice -> ✅ SUCCESS');
    console.log(`     Status changed to: ${payJsonRes.invoice.status}`);
    
    // Verify in DB
    const updatedInv = await Invoice.findById(unpaidInvoice._id);
    if (updatedInv.status !== 'Paid') {
      throw new Error('Invoice status was not updated to Paid in MongoDB');
    }
    console.log('     Verified status in MongoDB: Paid');
  } else {
    throw new Error('Failed to pay invoice: ' + (payJsonRes ? payJsonRes.message : 'no response'));
  }

  // 3. Test Credit Line Limit Upgrades
  console.log('\n3️⃣ Testing Credit Limit Upgrade Request...');
  const newLimitRequest = buyer.creditLimit ? buyer.creditLimit + 50000 : 150000;
  console.log(`   - Requesting Credit Limit increase to £${newLimitRequest.toLocaleString()}...`);

  const limitReqMock = {
    user: buyer,
    body: { requestAmount: newLimitRequest }
  };
  let limitJsonRes = null;
  const limitResMock = {
    json: function(data) {
      limitJsonRes = data;
      return this;
    },
    status: function() { return this; }
  };

  await billingController.requestCreditIncrease(limitReqMock, limitResMock);

  if (limitJsonRes && limitJsonRes.success) {
    console.log('   - requestCreditIncrease -> ✅ SUCCESS');
    console.log(`     New limit returned: £${limitJsonRes.creditLimit}`);
    
    // Verify in DB
    const updatedUser = await User.findById(buyer._id);
    if (updatedUser.creditLimit !== newLimitRequest) {
      throw new Error('Credit limit was not updated in MongoDB User document');
    }
    console.log('     Verified credit limit in MongoDB: £' + updatedUser.creditLimit);
  } else {
    throw new Error('Failed to request credit limit increase');
  }

  // 4. Test Checkout Net 30 Flow & Invoice Generation
  console.log('\n4️⃣ Testing Checkout Net 30 Order placement...');
  
  // Find a product
  const product = await Product.findOne({ stock: { $gt: 10 } });
  if (!product) {
    console.error('⚠️ No products found with stock > 10 in DB, skipping Checkout integration test.');
    await mongoose.connection.close();
    return;
  }
  console.log(`   - Using product: ${product.name} (Price: £${product.price})`);

  // Place a Net 30 order
  const orderReqMock = {
    user: buyer,
    body: {
      items: [
        {
          product: product._id.toString(),
          quantity: 2,
          unit: product.unit || 'kg'
        }
      ],
      delivery: {
        firstName: 'B2B',
        lastName: 'Buyer',
        company: 'Wholesale Co',
        email: buyer.email,
        address: '100 Wholesale Lane',
        city: 'London',
        postcode: 'EC1A 1BB',
        country: 'United Kingdom'
      },
      paymentMethod: 'net30',
      notes: '{"shippingOption":"standard"}'
    }
  };

  let orderJsonRes = null;
  const orderResMock = {
    status: function(code) {
      this.statusCode = code;
      return this;
    },
    json: function(data) {
      orderJsonRes = data;
      return this;
    }
  };

  await orderController.placeOrder(orderReqMock, orderResMock);

  if (orderJsonRes && orderJsonRes._id) {
    console.log('   - placeOrder (Net 30) -> ✅ SUCCESS');
    console.log(`     Order ID: ${orderJsonRes._id} (Total: £${orderJsonRes.total}, Payment Method: ${orderJsonRes.paymentMethod})`);
    
    // Verify that a corresponding Invoice was created!
    const orderInvoice = await Invoice.findOne({ order: orderJsonRes._id });
    if (orderInvoice) {
      console.log(`     ✅ Corresponding Invoice Created: ${orderInvoice.invoiceNumber}`);
      console.log(`     Invoice Details: Amount: £${orderInvoice.amount}, Status: ${orderInvoice.status}, Due Date: ${orderInvoice.dueDate.toLocaleDateString()}`);
    } else {
      throw new Error('Invoice was NOT generated for Net 30 order!');
    }
  } else {
    throw new Error('Failed to place Net 30 order: ' + (orderJsonRes ? orderJsonRes.message : 'no response'));
  }

  await mongoose.connection.close();
  console.log('\n🎉 B2B Billing & Credit Verification Tests Completed successfully!');
}

runTests().catch(err => {
  console.error('\n❌ B2B Billing Test Suit FAILED:', err);
  if (mongoose.connection.readyState !== 0) {
    mongoose.connection.close();
  }
  process.exit(1);
});
