const User = require('../models/User');
const Order = require('../models/Order');
const Product = require('../models/Product');

// GET /api/admin/stats
exports.getPlatformStats = async (req, res) => {
  const [totalGMV, activeSuppliers, totalOrders, totalProducts] = await Promise.all([
    Order.aggregate([{ $group: { _id: null, gmv: { $sum: '$total' } } }]),
    User.countDocuments({ role: 'supplier' }),
    Order.countDocuments(),
    Product.countDocuments({ isActive: true }),
  ]);

  res.json({
    totalGMV: totalGMV[0]?.gmv || 0,
    activeSuppliers,
    totalOrders,
    totalProducts,
  });
};

// GET /api/admin/users
exports.getUsers = async (req, res) => {
  const { role, page = 1, limit = 20, search } = req.query;
  const query = {};
  if (role) query.role = role;
  if (search) query.$or = [
    { name: { $regex: search, $options: 'i' } },
    { email: { $regex: search, $options: 'i' } },
  ];

  const skip = (parseInt(page) - 1) * parseInt(limit);
  const [users, total] = await Promise.all([
    User.find(query).select('-password').sort({ createdAt: -1 }).skip(skip).limit(parseInt(limit)),
    User.countDocuments(query),
  ]);

  res.json({ users, total });
};

// PUT /api/admin/margin
exports.saveMargin = async (req, res) => {
  const { margin } = req.body;
  // In a real app this would persist to a Settings collection
  // For now we just return success
  res.json({ message: 'Margin saved', margin });
};

// PUT /api/admin/users/:id/verify
exports.verifySupplier = async (req, res) => {
  const { status = 'approved', notes = '' } = req.body || {};

  const allowed = ['approved', 'rejected', 'information_requested'];
  if (!allowed.includes(status)) {
    return res.status(400).json({ message: 'Invalid verification status' });
  }

  const user = await User.findById(req.params.id);
  if (!user) return res.status(404).json({ message: 'User not found' });

  user.verificationStatus = status;
  if (status === 'approved') {
    user.isVerified = true;
  } else {
    user.isVerified = false;
  }

  user.verificationHistory.push({
    status,
    notes,
    updatedBy: req.user._id,
    updatedByName: req.user.name,
    updatedAt: new Date()
  });

  await user.save();

  // Create persistent notification for the user in MongoDB
  const Notification = require('../models/Notification');
  let title = '';
  let message = '';
  if (status === 'approved') {
    title = 'Verification Approved';
    message = 'Your business verification has been approved. You can now publish products and receive orders.';
  } else if (status === 'rejected') {
    title = 'Verification Rejected';
    message = `Your business verification request was rejected. Reason: ${notes || 'No reason provided.'}`;
  } else if (status === 'information_requested') {
    title = 'Information Requested by Admin';
    message = `Additional business documentation requested: ${notes || 'Please review.'}`;
  }

  await Notification.create({
    user: user._id,
    title,
    message,
    type: 'system'
  });

  const userResponse = user.toObject();
  delete userResponse.password;

  res.json(userResponse);
};

// GET /api/admin/verification-logs
exports.getVerificationLogs = async (req, res) => {
  const users = await User.find({ 'verificationHistory.0': { $exists: true } })
    .select('name company email verificationHistory');

  const logs = [];
  users.forEach(u => {
    u.verificationHistory.forEach(h => {
      logs.push({
        _id: h._id,
        userId: u._id,
        userName: u.name,
        userCompany: u.company || u.name,
        userEmail: u.email,
        status: h.status,
        notes: h.notes,
        updatedBy: h.updatedBy,
        updatedByName: h.updatedByName,
        updatedAt: h.updatedAt
      });
    });
  });

  // Sort chronologically (newest first)
  logs.sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));

  res.json(logs);
};

