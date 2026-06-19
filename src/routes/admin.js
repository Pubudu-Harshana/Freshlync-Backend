const express = require('express');
const router  = express.Router();
const { protect, requireRole } = require('../middleware/auth');
const { getPlatformStats, getUsers, saveMargin, verifySupplier, getVerificationLogs } = require('../controllers/adminController');

router.get('/stats',       protect, requireRole('admin'), getPlatformStats);
router.get('/users',       protect, requireRole('admin'), getUsers);
router.put('/margin',      protect, requireRole('admin'), saveMargin);
router.put('/users/:id/verify', protect, requireRole('admin'), verifySupplier);
router.get('/verification-logs', protect, requireRole('admin'), getVerificationLogs);


module.exports = router;
