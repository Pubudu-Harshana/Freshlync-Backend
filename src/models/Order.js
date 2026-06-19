const mongoose = require('mongoose');

const orderItemSchema = new mongoose.Schema({
  product:  { type: mongoose.Schema.Types.ObjectId, ref: 'Product' },
  name:     { type: String, required: true },
  price:    { type: Number, required: true },
  quantity: { type: Number, required: true },
  unit:     { type: String, default: 'kg' },
  supplier: { type: mongoose.Schema.Types.ObjectId, ref: 'User' },
  supplierName: { type: String, default: '' },
});

const supplierStatusSchema = new mongoose.Schema({
  supplier: { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
  status: {
    type: String,
    enum: ['Pending', 'In Transit', 'Delivered', 'Cancelled'],
    default: 'Pending',
  },
});

const orderSchema = new mongoose.Schema({
  buyer:    { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
  supplier: { type: mongoose.Schema.Types.ObjectId, ref: 'User' },

  items:    [orderItemSchema],

  total:    { type: Number, required: true },

  status: {
    type: String,
    enum: ['Pending', 'In Transit', 'Delivered', 'Cancelled'],
    default: 'Pending',
  },

  supplierStatuses: [supplierStatusSchema],

  delivery: {
    firstName: String,
    lastName:  String,
    company:   String,
    email:     String,
    address:   String,
    city:      String,
    postcode:  String,
    country:   String,
  },

  paymentMethod: { type: String, default: 'card' },
  notes:         { type: String, default: '' },
}, { timestamps: true });

module.exports = mongoose.model('Order', orderSchema);
