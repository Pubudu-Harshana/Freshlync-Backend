const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');

const userSchema = new mongoose.Schema({
  name:     { type: String, required: true, trim: true },
  email:    { type: String, required: true, unique: true, lowercase: true, trim: true },
  password: { type: String, required: true, minlength: 6 },
  role:     { type: String, enum: ['buyer', 'supplier', 'admin'], default: 'buyer' },
  company:  { type: String, default: '' },
  phone:    { type: String, default: '' },
  avatar:   { type: String, default: '' },
  address:  { type: String, default: '' },
  website:  { type: String, default: '' },
  description: { type: String, default: '' },
  bankName:    { type: String, default: '' },
  accountNumber: { type: String, default: '' },
  sortCode:    { type: String, default: '' },
  isVerified: { type: Boolean, default: false },
  
  // Supplier Business Verification fields
  verificationStatus: {
    type: String,
    enum: ['unverified', 'pending', 'approved', 'rejected', 'information_requested', 'expired'],
    default: 'unverified'
  },
  verificationDetails: {
    registeredBusinessName: { type: String, default: '' },
    businessRegistrationNumber: { type: String, default: '' },
    businessType: { type: String, default: '' },
    taxId: { type: String, default: '' },
    businessAddress: { type: String, default: '' },
    businessPhone: { type: String, default: '' },
    businessEmail: { type: String, default: '' },
    contactName: { type: String, default: '' },
    contactJobTitle: { type: String, default: '' },
    contactEmail: { type: String, default: '' },
    contactPhone: { type: String, default: '' },
    documents: [{
      name: String,
      fieldName: String,
      url: String,
      uploadedAt: { type: Date, default: Date.now }
    }],
  },
  verificationHistory: [{
    status: String,
    notes: String,
    updatedBy: { type: mongoose.Schema.Types.ObjectId, ref: 'User' },
    updatedByName: String,
    updatedAt: { type: Date, default: Date.now }
  }]
}, { timestamps: true });

// Hash password before save
userSchema.pre('save', async function (next) {
  if (!this.isModified('password')) return next();
  this.password = await bcrypt.hash(this.password, 12);
  next();
});

// Compare password
userSchema.methods.matchPassword = async function (entered) {
  return bcrypt.compare(entered, this.password);
};

module.exports = mongoose.model('User', userSchema);
