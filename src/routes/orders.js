const express = require('express');
const router  = express.Router();
const multer  = require('multer');
const path    = require('path');
const { protect, requireRole } = require('../middleware/auth');
const { getOrders, getOrder, placeOrder, updateStatus, verifyPayment, reuploadSlip } = require('../controllers/orderController');

// Multer – save uploads to /uploads folder
const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, path.join(__dirname, '../../uploads')),
  filename:    (req, file, cb) => cb(null, `${Date.now()}-${file.originalname.replace(/\s/g, '_')}`),
});

const fileFilter = (req, file, cb) => {
  const allowedExts = ['.jpg', '.jpeg', '.png', '.pdf'];
  const ext = path.extname(file.originalname).toLowerCase();
  if (allowedExts.includes(ext)) {
    cb(null, true);
  } else {
    cb(new Error('Only JPG, JPEG, PNG, and PDF files are allowed.'), false);
  }
};

const upload = multer({ 
  storage, 
  fileFilter,
  limits: { fileSize: 10 * 1024 * 1024 } // 10MB limit
});

router.get('/',        protect, getOrders);
router.get('/:id',     protect, getOrder);
router.post('/',       protect, requireRole('buyer'), placeOrder);
router.put('/:id/status', protect, requireRole('supplier', 'admin'), updateStatus);

// Payment Approval Routes
router.post('/upload-slip', protect, requireRole('buyer'), (req, res) => {
  upload.single('slip')(req, res, (err) => {
    if (err) {
      return res.status(400).json({ message: err.message });
    }
    if (!req.file) {
      return res.status(400).json({ message: 'No file uploaded.' });
    }
    const filePath = `/uploads/${req.file.filename}`;
    res.status(200).json({ filePath });
  });
});

router.put('/:id/verify-payment', protect, requireRole('admin'), verifyPayment);
router.put('/:id/reupload-slip', protect, requireRole('buyer'), reuploadSlip);

module.exports = router;
