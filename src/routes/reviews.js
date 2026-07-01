const express = require('express');
const router = express.Router();
const { protect, requireRole } = require('../middleware/auth');
const {
  createReview,
  getPublicReviews,
  getAllReviews,
  updateReviewStatus,
  deleteReview,
  getReviewStats,
  getAdminReviewStats,
  getProductReviews,
  getProductReviewStats
} = require('../controllers/reviewController');

// Public routes
router.get('/public', getPublicReviews);
router.get('/stats', getReviewStats);
router.get('/product/:productId', getProductReviews);
router.get('/product/:productId/stats', getProductReviewStats);

// Protected routes (User)
router.post('/create', protect, createReview);

// Admin routes
router.get('/admin/all', protect, requireRole('admin'), getAllReviews);
router.get('/admin/stats', protect, requireRole('admin'), getAdminReviewStats);
router.put('/admin/status/:id', protect, requireRole('admin'), updateReviewStatus);
router.delete('/admin/:id', protect, requireRole('admin'), deleteReview);

module.exports = router;

