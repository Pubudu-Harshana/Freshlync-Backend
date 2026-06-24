/**
 * Review database service for the FreshLync Chatbot.
 * Fetches platform feedback and ratings.
 */

const Review = require('../models/Review');

/**
 * Retrieves platform reviews summary and testimonials.
 * @returns {object} { averageRating, reviews }
 */
async function getPlatformReviews() {
  // Query all approved reviews
  const approvedReviews = await Review.find({ status: 'approved' }).lean();

  let averageRating = 5.0; // Default fallback if no reviews exist
  if (approvedReviews.length > 0) {
    const totalRating = approvedReviews.reduce((sum, r) => sum + r.rating, 0);
    averageRating = Number((totalRating / approvedReviews.length).toFixed(1));
  }

  // Fetch latest 3 approved reviews to display
  const latestReviews = await Review.find({ status: 'approved' })
    .sort({ createdAt: -1 })
    .limit(3)
    .lean();

  return {
    averageRating,
    reviews: latestReviews.map(r => ({
      id: r._id.toString(),
      userName: r.userName,
      userRole: r.userRole || 'buyer',
      companyName: r.companyName || '',
      rating: r.rating,
      title: r.title,
      review: r.review,
      createdAt: r.createdAt
    }))
  };
}

module.exports = {
  getPlatformReviews
};
