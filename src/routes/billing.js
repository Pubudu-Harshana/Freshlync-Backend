const express = require('express');
const router = express.Router();
const { protect } = require('../middleware/auth');
const {
  getBillingData,
  payInvoice,
  requestCreditIncrease
} = require('../controllers/billingController');

// All billing routes are protected (authenticated buyers only)
router.get('/', protect, getBillingData);
router.post('/credit-request', protect, requestCreditIncrease);
router.post('/invoices/:id/pay', protect, payInvoice);

module.exports = router;
