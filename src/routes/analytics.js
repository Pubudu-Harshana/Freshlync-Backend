const express = require('express');
const router  = express.Router();
const { protect, requireRole } = require('../middleware/auth');
const { getSummary, getChartData, predictSales } = require('../controllers/analyticsController');

router.get('/summary',   protect, requireRole('supplier', 'admin'), getSummary);
router.get('/chart',     protect, requireRole('supplier', 'admin'), getChartData);
router.post('/predict',  protect, requireRole('supplier', 'admin'), predictSales);

module.exports = router;
