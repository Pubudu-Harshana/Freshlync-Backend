const mongoose = require('mongoose');

const notificationSchema = new mongoose.Schema({
  user:      { type: mongoose.Schema.Types.ObjectId, ref: 'User', required: true },
  title:     { type: String, required: true },
  message:   { type: String, required: true },
  type:      { type: String, enum: ['order', 'stock', 'system', 'payout'], default: 'system' },
  read:      { type: Boolean, default: false },
  supplierId: { type: mongoose.Schema.Types.ObjectId, ref: 'User' },
  verificationId: { type: String },
  readAt:    { type: Date }
}, { timestamps: true });

module.exports = mongoose.model('Notification', notificationSchema);
