const jwt = require('jsonwebtoken');
const User = require('../models/User');

const signToken = (id) =>
  jwt.sign({ id }, process.env.JWT_SECRET, { expiresIn: process.env.JWT_EXPIRES_IN });

// POST /api/auth/register
exports.register = async (req, res) => {
  const { name, email, password, role, company } = req.body;

  const exists = await User.findOne({ email });
  if (exists) return res.status(400).json({ message: 'Email already registered' });

  const user = await User.create({
    name,
    email,
    password,
    role: role || 'buyer',
    company,
    verificationStatus: role === 'supplier' ? 'pending' : 'unverified'
  });
  const token = signToken(user._id);

  const userResponse = user.toObject();
  delete userResponse.password;

  res.status(201).json({
    token,
    user: userResponse,
  });
};

// POST /api/auth/login
exports.login = async (req, res) => {
  const { email, password } = req.body;

  if (!email || !password) return res.status(400).json({ message: 'Email and password required' });

  const user = await User.findOne({ email });
  if (!user || !(await user.matchPassword(password))) {
    return res.status(401).json({ message: 'Invalid email or password' });
  }

  const token = signToken(user._id);
  const userResponse = user.toObject();
  delete userResponse.password;

  res.json({
    token,
    user: userResponse,
  });
};

// GET /api/auth/me
exports.getMe = async (req, res) => {
  const user = await User.findById(req.user._id).select('-password');
  res.json(user);
};

// PUT /api/auth/profile
exports.updateProfile = async (req, res) => {
  const { name, email, company, phone, address, bankName, accountNumber, sortCode, website, description } = req.body;

  if (email) {
    const emailExists = await User.findOne({ email, _id: { $ne: req.user._id } });
    if (emailExists) {
      return res.status(400).json({ message: 'Email is already in use by another account' });
    }
  }

  const updateFields = {
    name,
    email,
    company,
    phone,
    address,
    bankName,
    accountNumber,
    sortCode,
    website,
    description
  };

  if (req.file) {
    updateFields.avatar = `/uploads/${req.file.filename}`;
  }

  // Remove undefined fields
  Object.keys(updateFields).forEach(key => {
    if (updateFields[key] === undefined) {
      delete updateFields[key];
    }
  });

  const user = await User.findByIdAndUpdate(
    req.user._id,
    updateFields,
    { new: true, runValidators: true }
  ).select('-password');

  res.json(user);
};

// PUT /api/auth/password
exports.changePassword = async (req, res) => {
  const { currentPassword, newPassword } = req.body;
  const user = await User.findById(req.user._id);
  if (!(await user.matchPassword(currentPassword))) {
    return res.status(400).json({ message: 'Current password is incorrect' });
  }
  user.password = newPassword;
  await user.save();
  res.json({ message: 'Password updated successfully' });
};

// PUT /api/auth/verify-details
exports.submitBusinessVerification = async (req, res) => {
  const {
    registeredBusinessName,
    businessRegistrationNumber,
    businessType,
    taxId,
    businessAddress,
    businessPhone,
    businessEmail,
    contactName,
    contactJobTitle,
    contactEmail,
    contactPhone
  } = req.body;

  const user = await User.findById(req.user._id);
  if (!user) return res.status(404).json({ message: 'User not found' });

  // Map text fields
  user.verificationDetails = {
    registeredBusinessName: registeredBusinessName || '',
    businessRegistrationNumber: businessRegistrationNumber || '',
    businessType: businessType || '',
    taxId: taxId || '',
    businessAddress: businessAddress || '',
    businessPhone: businessPhone || '',
    businessEmail: businessEmail || '',
    contactName: contactName || '',
    contactJobTitle: contactJobTitle || '',
    contactEmail: contactEmail || '',
    contactPhone: contactPhone || '',
    documents: user.verificationDetails?.documents || []
  };

  // Add files
  if (req.files && req.files.length > 0) {
    const docs = req.files.map(file => ({
      name: file.originalname,
      fieldName: file.fieldname,
      url: `/uploads/${file.filename}`,
      uploadedAt: new Date()
    }));
    user.verificationDetails.documents.push(...docs);
  }

  const previousStatus = user.verificationStatus;

  // Update status to pending
  user.verificationStatus = 'pending';
  user.isVerified = false;

  // Add to history
  user.verificationHistory.push({
    status: 'pending',
    notes: 'Business verification details submitted.',
    updatedBy: req.user._id,
    updatedByName: req.user.name,
    updatedAt: new Date()
  });

  await user.save();

  // Create user notification
  const Notification = require('../models/Notification');
  let supplierNotifTitle = 'Verification Submitted';
  let supplierNotifMessage = 'Your business verification request has been successfully submitted and is pending admin review.';
  if (previousStatus === 'rejected') {
    supplierNotifTitle = 'Verification Documents Updated';
    supplierNotifMessage = 'Your business verification documents have been resubmitted and are pending admin review.';
  } else if (previousStatus === 'approved' || previousStatus === 'pending' || previousStatus === 'information_requested') {
    supplierNotifTitle = 'Verification Documents Updated';
    supplierNotifMessage = 'Your business verification documents have been updated and are pending admin review.';
  }

  await Notification.create({
    user: user._id,
    title: supplierNotifTitle,
    message: supplierNotifMessage,
    type: 'system'
  });

  // Create Admin notifications automatically for all administrators
  let adminTitle = 'New Supplier Verification Request Submitted';
  if (previousStatus === 'rejected') {
    adminTitle = 'Supplier Verification Resubmitted';
  } else if (previousStatus === 'approved' || previousStatus === 'pending' || previousStatus === 'information_requested') {
    adminTitle = 'Verification Documents Updated';
  }

  const admins = await User.find({ role: 'admin' }).select('_id');
  if (admins.length > 0) {
    const adminNotifs = admins.map(admin => ({
      user: admin._id,
      title: adminTitle,
      message: `"${user.company || user.name}" has submitted business verification documents and requires review.`,
      type: 'system',
      supplierId: user._id,
      verificationId: user.verificationHistory[user.verificationHistory.length - 1]?._id?.toString()
    }));
    await Notification.insertMany(adminNotifs);
  }

  res.json(user);
};

