const express = require('express');
const router  = express.Router();
const { protect, requireRole } = require('../middleware/auth');
const { 
  getPlatformStats, 
  getUsers, 
  saveMargin, 
  verifySupplier, 
  getVerificationLogs,
  getMarketPredictions,
  getDemandForecast,
  getRegionalInsights,
  getSupplierForecasts,
  getAIRecommendations
} = require('../controllers/adminController');

router.get('/stats',       protect, requireRole('admin'), getPlatformStats);
router.get('/users',       protect, requireRole('admin'), getUsers);
router.put('/margin',      protect, requireRole('admin'), saveMargin);
router.put('/users/:id/verify', protect, requireRole('admin'), verifySupplier);
router.get('/verification-logs', protect, requireRole('admin'), getVerificationLogs);

// AI Predictions Endpoints
router.get('/predictions/market', protect, requireRole('admin'), getMarketPredictions);
router.get('/predictions/forecast', protect, requireRole('admin'), getDemandForecast);
router.get('/predictions/regions', protect, requireRole('admin'), getRegionalInsights);
router.get('/predictions/suppliers', protect, requireRole('admin'), getSupplierForecasts);
router.get('/predictions/recommendations', protect, requireRole('admin'), getAIRecommendations);

module.exports = router;
