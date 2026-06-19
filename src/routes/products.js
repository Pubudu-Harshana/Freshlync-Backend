const express = require('express');
const router  = express.Router();
const multer  = require('multer');
const path    = require('path');
const { protect, requireRole } = require('../middleware/auth');
const {
  getProducts, getProduct, createProduct,
  updateProduct, deleteProduct, updateStock,
} = require('../controllers/productController');

// Multer — save uploads to /uploads folder
const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, path.join(__dirname, '../../uploads')),
  filename:    (req, file, cb) => cb(null, `${Date.now()}-${file.originalname.replace(/\s/g, '_')}`),
});
const upload = multer({ storage, limits: { fileSize: 10 * 1024 * 1024 } });

router.get('/',      getProducts);                                      // public
router.get('/:id',   getProduct);                                       // public
router.post('/',     protect, requireRole('supplier', 'admin'), upload.single('image'), createProduct);
router.put('/:id',   protect, requireRole('supplier', 'admin'), updateProduct);
router.delete('/:id',protect, requireRole('supplier', 'admin'), deleteProduct);
router.patch('/:id/stock', protect, requireRole('supplier', 'admin'), updateStock);

module.exports = router;
