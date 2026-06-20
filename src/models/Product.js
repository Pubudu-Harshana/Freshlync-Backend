const mongoose = require('mongoose');

const productSchema = new mongoose.Schema({
  name:        { type: String, required: true, trim: true },
  category:    { type: String, required: true, enum: ['Fish', 'Meat', 'Vegetables', 'Dairy', 'Grains', 'Other'] },
  price:       { type: Number, required: true, min: 0 },
  basePrice:    { type: Number, required: true },
  sellingPrice: { type: Number, required: true },
  unit:        { type: String, required: true, default: 'kg' },
  stock:       { type: Number, required: true, default: 0 },
  minOrder:    { type: Number, default: 1 },
  description: { type: String, default: '' },
  sku:         { type: String, default: '' },
  image:       { type: String, default: '' },
  supplier:    { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
  supplierName:{ type: String, default: '' },
  rating:      { type: Number, default: 0 },
  reviews:     { type: Number, default: 0 },
  isActive:    { type: Boolean, default: true },
}, { timestamps: true });

// Virtual: status
productSchema.virtual('status').get(function () {
  if (this.stock === 0) return 'Out of Stock';
  if (this.stock < 50) return 'Low Stock';
  return 'In Stock';
});

productSchema.set('toJSON', { virtuals: true });

module.exports = mongoose.model('Product', productSchema);
