const Review = require('../models/Review');
const Order = require('../models/Order');
const Notification = require('../models/Notification');
const User = require('../models/User');

// Create a review
exports.createReview = async (req, res) => {
  const { rating, title, review, orderId, companyName, profileImage } = req.body;
  const userId = req.user._id;

  // Validate rating
  if (!rating || rating < 1 || rating > 5) {
    return res.status(400).json({ message: 'Please provide a valid rating between 1 and 5' });
  }

  // Validate order
  if (!orderId) {
    return res.status(400).json({ message: 'Order ID is required to submit a review' });
  }

  // Check if order belongs to user and is delivered (completed)
  // Or at least just check if order exists for this user
  const order = await Order.findOne({ _id: orderId, buyer: userId, status: 'Delivered' });
  if (!order) {
    return res.status(400).json({ message: 'Review must be linked to a completed (Delivered) order.' });
  }

  // Check if user already reviewed this order
  const existingReview = await Review.findOne({ userId, orderId });
  if (existingReview) {
    return res.status(400).json({ message: 'You have already submitted a review for this order.' });
  }

  const newReview = await Review.create({
    userId,
    userName: req.user.name,
    userRole: req.user.role,
    companyName: companyName || req.user.company || '',
    profileImage: profileImage || req.user.avatar || '',
    rating,
    title,
    review,
    orderId,
    status: 'pending'
  });

  // Notify admins
  const admins = await User.find({ role: 'admin' });
  const adminNotifications = admins.map(admin => ({
    user: admin._id,
    title: 'New Review Submitted',
    message: `${req.user.name} submitted a new review.`,
    type: 'system'
  }));
  if (adminNotifications.length > 0) {
    await Notification.insertMany(adminNotifications);
  }

  res.status(201).json({ message: 'Review submitted successfully. Pending admin approval.', review: newReview });
};

// Get public reviews (approved only)
exports.getPublicReviews = async (req, res) => {
  const limit = parseInt(req.query.limit, 10) || 10;
  const page = parseInt(req.query.page, 10) || 1;

  const query = { status: 'approved' };
  
  const reviews = await Review.find(query)
    .sort({ featured: -1, createdAt: -1 })
    .skip((page - 1) * limit)
    .limit(limit);

  const total = await Review.countDocuments(query);

  res.json({
    reviews,
    page,
    pages: Math.ceil(total / limit),
    total
  });
};

// Get all reviews (Admin only)
exports.getAllReviews = async (req, res) => {
  const limit = parseInt(req.query.limit, 10) || 20;
  const page = parseInt(req.query.page, 10) || 1;
  const status = req.query.status;

  const query = {};
  if (status && status !== 'all') {
    query.status = status;
  }

  const reviews = await Review.find(query)
    .sort({ createdAt: -1 })
    .skip((page - 1) * limit)
    .limit(limit);

  const total = await Review.countDocuments(query);

  res.json({
    reviews,
    page,
    pages: Math.ceil(total / limit),
    total
  });
};

// Update review status (Admin only)
exports.updateReviewStatus = async (req, res) => {
  const { id } = req.params;
  const { status, featured } = req.body;

  const review = await Review.findById(id);
  if (!review) {
    return res.status(404).json({ message: 'Review not found' });
  }

  const oldStatus = review.status;

  if (status) review.status = status;
  if (featured !== undefined) review.featured = featured;

  await review.save();

  // Notify user if status changed to approved or rejected
  if (status && status !== oldStatus && (status === 'approved' || status === 'rejected')) {
    await Notification.create({
      user: review.userId,
      title: `Review ${status.charAt(0).toUpperCase() + status.slice(1)}`,
      message: `Your review "${review.title}" has been ${status}.`,
      type: 'system'
    });
  }

  res.json({ message: 'Review updated successfully', review });
};

// Delete review (Admin only)
exports.deleteReview = async (req, res) => {
  const { id } = req.params;
  const review = await Review.findByIdAndDelete(id);
  
  if (!review) {
    return res.status(404).json({ message: 'Review not found' });
  }

  res.json({ message: 'Review deleted successfully' });
};

// Get review statistics (Approved only)
exports.getReviewStats = async (req, res) => {
  const approvedReviews = await Review.find({ status: 'approved' });
  
  const totalReviews = approvedReviews.length;
  const averageRating = totalReviews > 0 
    ? (approvedReviews.reduce((acc, curr) => acc + curr.rating, 0) / totalReviews).toFixed(1)
    : 0;

  // Satisfaction rate: percentage of reviews 4 or 5 stars
  const highRatings = approvedReviews.filter(r => r.rating >= 4).length;
  const satisfactionRate = totalReviews > 0 
    ? Math.round((highRatings / totalReviews) * 100) 
    : 0;

  // Verified Customers (distinct users)
  const verifiedCustomers = new Set(approvedReviews.map(r => r.userId.toString())).size;

  res.json({
    totalReviews,
    averageRating: parseFloat(averageRating),
    satisfactionRate,
    verifiedCustomers
  });
};

// Get Admin review statistics
exports.getAdminReviewStats = async (req, res) => {
  const totalReviews = await Review.countDocuments();
  const pendingReviews = await Review.countDocuments({ status: 'pending' });
  const approvedReviews = await Review.countDocuments({ status: 'approved' });
  const rejectedReviews = await Review.countDocuments({ status: 'rejected' });
  
  const approvedDocs = await Review.find({ status: 'approved' });
  const averageRating = approvedDocs.length > 0 
    ? (approvedDocs.reduce((acc, curr) => acc + curr.rating, 0) / approvedDocs.length).toFixed(1)
    : 0;

  // Most active users
  const userAggregation = await Review.aggregate([
    { $group: { _id: '$userId', userName: { $first: '$userName' }, count: { $sum: 1 } } },
    { $sort: { count: -1 } },
    { $limit: 5 }
  ]);

  res.json({
    totalReviews,
    pendingReviews,
    approvedReviews,
    rejectedReviews,
    averageRating: parseFloat(averageRating),
    activeUsers: userAggregation
  });
};
