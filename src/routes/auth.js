const express = require('express');
const router = express.Router();
const multer = require('multer');
const path = require('path');
const { register, login, getMe, updateProfile, changePassword, submitBusinessVerification } = require('../controllers/authController');
const { protect } = require('../middleware/auth');

// Configure Multer for user profile pictures
const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, path.join(__dirname, '../../uploads')),
  filename:    (req, file, cb) => cb(null, `avatar-${Date.now()}-${file.originalname.replace(/\s/g, '_')}`),
});
const upload = multer({ storage, limits: { fileSize: 10 * 1024 * 1024 } });

router.post('/register', register);
router.post('/login',    login);
router.get('/me',        protect, getMe);
router.put('/profile',   protect, upload.single('avatar'), updateProfile);
router.put('/password',  protect, changePassword);
router.put('/verify-details', protect, upload.any(), submitBusinessVerification);

module.exports = router;
