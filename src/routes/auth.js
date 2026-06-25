const express = require('express');
const router = express.Router();
const { register, login, getMe, updateProfile, changePassword, submitBusinessVerification, forgotPassword, resetPassword } = require('../controllers/authController');
const { protect } = require('../middleware/auth');
const { uploadAvatar, uploadDoc } = require('../config/cloudinary');

router.post('/register',       register);
router.post('/login',          login);
router.get('/me',              protect, getMe);
router.put('/profile',         protect, uploadAvatar.single('avatar'), updateProfile);
router.put('/password',        protect, changePassword);
router.put('/verify-details',  protect, uploadDoc.any(), submitBusinessVerification);

// Password reset (public routes — no auth required)
router.post('/forgot-password', forgotPassword);
router.post('/reset-password',  resetPassword);

module.exports = router;
