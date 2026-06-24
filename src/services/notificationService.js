/**
 * Notification database service for the FreshLync Chatbot.
 * Fetches recent alerts and unread counts for the user.
 */

const Notification = require('../models/Notification');

/**
 * Retrieves the latest 5 notifications and unread count for a user.
 * @param {string} userId 
 * @returns {object} { unreadCount, notifications }
 */
async function getRecentNotifications(userId) {
  if (!userId) {
    return { unreadCount: 0, notifications: [] };
  }

  // Count unread notifications
  const unreadCount = await Notification.countDocuments({
    user: userId,
    read: false
  });

  // Fetch latest 5 notifications
  const notifications = await Notification.find({ user: userId })
    .sort({ createdAt: -1 })
    .limit(5)
    .lean();

  return {
    unreadCount,
    notifications: notifications.map(n => ({
      id: n._id.toString(),
      title: n.title,
      message: n.message,
      type: n.type || 'system',
      read: n.read,
      createdAt: n.createdAt
    }))
  };
}

module.exports = {
  getRecentNotifications
};
