const jwt    = require('jsonwebtoken');
const crypto = require('crypto');
const User   = require('../models/User');

const signToken = (id) =>
  jwt.sign({ id }, process.env.JWT_SECRET, { expiresIn: process.env.JWT_EXPIRES_IN });

// POST /api/auth/register
exports.register = async (req, res) => {
  const { name, email, password, role, company } = req.body;

  const exists = await User.findOne({ email });
  if (exists) return res.status(400).json({ message: 'Email already registered' });

  // Security: Only allow buyer or supplier on self-registration — admin cannot be self-assigned
  const allowedRoles = ['buyer', 'supplier'];
  const assignedRole = allowedRoles.includes(role) ? role : 'buyer';

  const user = await User.create({
    name,
    email,
    password,
    role: assignedRole,
    company,
    verificationStatus: assignedRole === 'supplier' ? 'pending' : 'unverified'
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

// Helper: mask sensitive bank details — show only last 4 chars
const maskBankDetails = (userObj) => {
  if (userObj.accountNumber && userObj.accountNumber.length > 4) {
    userObj.accountNumber = '****' + userObj.accountNumber.slice(-4);
  }
  if (userObj.sortCode && userObj.sortCode.length > 4) {
    userObj.sortCode = '**-**-' + userObj.sortCode.slice(-2);
  }
  return userObj;
};

// GET /api/auth/me
exports.getMe = async (req, res) => {
  const user = await User.findById(req.user._id).select('-password');
  const userObj = user.toObject();
  res.json(maskBankDetails(userObj));
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
    // Cloudinary storage: req.file.path is the full HTTPS URL
    updateFields.avatar = req.file.path;
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

  const userObj = user.toObject();
  res.json(maskBankDetails(userObj));
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
      // Cloudinary storage: file.path is the full HTTPS URL
      url: file.path,
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

// POST /api/auth/forgot-password
exports.forgotPassword = async (req, res) => {
  const { email } = req.body;
  if (!email) return res.status(400).json({ message: 'Email is required.' });

  // Always return the same response to prevent email enumeration
  const SAFE_MSG = { message: 'If an account with that email exists, a password reset link has been sent.' };

  const user = await User.findOne({ email: email.toLowerCase().trim() });
  if (!user) return res.json(SAFE_MSG);

  // Generate cryptographically secure random token
  const rawToken   = crypto.randomBytes(32).toString('hex');
  const hashedToken = crypto.createHash('sha256').update(rawToken).digest('hex');

  user.resetPasswordToken   = hashedToken;
  user.resetPasswordExpires = new Date(Date.now() + 60 * 60 * 1000); // 1 hour
  await user.save({ validateBeforeSave: false });

  const resetUrl = `${process.env.CLIENT_URL}/reset-password?token=${rawToken}`;

  try {
    const { sendPasswordResetEmail } = require('../utils/sendEmail');
    await sendPasswordResetEmail(user.email, resetUrl);
    res.json(SAFE_MSG);
  } catch (err) {
    // Clear token on email failure
    user.resetPasswordToken   = undefined;
    user.resetPasswordExpires = undefined;
    await user.save({ validateBeforeSave: false });
    console.error('Email send error:', err.message);
    res.status(500).json({ message: 'Failed to send reset email. Please try again later.' });
  }
};

// POST /api/auth/reset-password
exports.resetPassword = async (req, res) => {
  const { token, password } = req.body;
  if (!token || !password) return res.status(400).json({ message: 'Token and new password are required.' });
  if (password.length < 6) return res.status(400).json({ message: 'Password must be at least 6 characters.' });

  // Hash the raw token from the URL to compare with stored hash
  const hashedToken = crypto.createHash('sha256').update(token).digest('hex');

  const user = await User.findOne({
    resetPasswordToken:   hashedToken,
    resetPasswordExpires: { $gt: Date.now() }, // must not be expired
  });

  if (!user) {
    return res.status(400).json({ message: 'Invalid or expired reset link. Please request a new one.' });
  }

  // Update password and clear reset fields
  user.password             = password;
  user.resetPasswordToken   = undefined;
  user.resetPasswordExpires = undefined;
  await user.save();

  res.json({ message: 'Password reset successful. You can now log in with your new password.' });
};

// POST /api/auth/google
exports.googleLogin = async (req, res) => {
  const { accessToken, role } = req.body;

  if (!accessToken) {
    return res.status(400).json({ message: 'Access token is required.' });
  }

  try {
    const response = await fetch(`https://www.googleapis.com/oauth2/v3/userinfo?access_token=${accessToken}`);
    if (!response.ok) {
      return res.status(401).json({ message: 'Invalid Google access token.' });
    }
    const payload = await response.json();
    const { email, name, picture } = payload;

    if (!email) {
      return res.status(400).json({ message: 'Google account does not provide email access.' });
    }

    let user = await User.findOne({ email });

    if (!user) {
      const randomPassword = crypto.randomBytes(16).toString('hex');
      const assignedRole = ['buyer', 'supplier'].includes(role) ? role : 'buyer';
      user = await User.create({
        name,
        email,
        password: randomPassword,
        role: assignedRole,
        avatar: picture || '',
        verificationStatus: assignedRole === 'supplier' ? 'pending' : 'unverified',
        isVerified: false
      });
    }

    const token = signToken(user._id);
    const userResponse = user.toObject();
    delete userResponse.password;

    res.json({
      token,
      user: userResponse,
    });
  } catch (error) {
    console.error('Google login error:', error);
    res.status(500).json({ message: 'Internal server error during Google login.' });
  }
};

