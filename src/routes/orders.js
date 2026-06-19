const express = require('express');
const router  = express.Router();
const { protect, requireRole } = require('../middleware/auth');
const { getOrders, getOrder, placeOrder, updateStatus } = require('../controllers/orderController');

router.get('/',        protect, getOrders);
router.get('/:id',     protect, getOrder);
router.post('/',       protect, requireRole('buyer'), placeOrder);
router.put('/:id/status', protect, requireRole('supplier', 'admin'), updateStatus);

module.exports = router;
