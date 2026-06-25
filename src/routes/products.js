const express = require('express');
const router  = express.Router();
const { protect, requireRole } = require('../middleware/auth');
const { uploadProduct } = require('../config/cloudinary');
const {
  getProducts, getProduct, createProduct,
  updateProduct, deleteProduct, updateStock, submitAppeal,
} = require('../controllers/productController');

router.get('/',      getProducts);                                                                          // public
router.get('/:id',   getProduct);                                                                           // public
router.post('/',     protect, requireRole('supplier', 'admin'), uploadProduct.single('image'), createProduct);
router.put('/:id',   protect, requireRole('supplier', 'admin'), uploadProduct.single('image'), updateProduct);
router.delete('/:id',protect, requireRole('supplier', 'admin'), deleteProduct);
router.patch('/:id/stock', protect, requireRole('supplier', 'admin'), updateStock);
router.post('/:id/appeal', protect, requireRole('supplier'), submitAppeal);

module.exports = router;
