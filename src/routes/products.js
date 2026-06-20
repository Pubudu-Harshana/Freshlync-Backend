const express = require('express');
const router  = express.Router();
const multer  = require('multer');
const path    = require('path');
const { protect, requireRole } = require('../middleware/auth');
const {
  getProducts, getProduct, createProduct,
  updateProduct, deleteProduct, updateStock, submitAppeal,
} = require('../controllers/productController');

// Multer — save uploads to /uploads folder
const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, path.join(__dirname, '../../uploads')),
  filename:    (req, file, cb) => cb(null, `${Date.now()}-${file.originalname.replace(/\s/g, '_')}`),
});
// Security: Only allow image file types for product images
const imageFilter = (req, file, cb) => {
  const allowedExts = ['.jpg', '.jpeg', '.png', '.webp'];
  const ext = path.extname(file.originalname).toLowerCase();
  if (allowedExts.includes(ext)) {
    cb(null, true);
  } else {
    cb(new Error('Only JPG, JPEG, PNG, and WebP image files are allowed.'), false);
  }
};
const upload = multer({ storage, fileFilter: imageFilter, limits: { fileSize: 5 * 1024 * 1024 } });

router.get('/',      getProducts);                                      // public
router.get('/:id',   getProduct);                                       // public
router.post('/',     protect, requireRole('supplier', 'admin'), upload.single('image'), createProduct);
router.put('/:id',   protect, requireRole('supplier', 'admin'), updateProduct);
router.delete('/:id',protect, requireRole('supplier', 'admin'), deleteProduct);
router.patch('/:id/stock', protect, requireRole('supplier', 'admin'), updateStock);
router.post('/:id/appeal', protect, requireRole('supplier'), submitAppeal);

module.exports = router;
