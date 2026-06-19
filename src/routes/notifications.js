const express = require('express');
const router  = express.Router();
const { protect } = require('../middleware/auth');
const Notification = require('../models/Notification');

// GET /api/notifications
router.get('/', protect, async (req, res) => {
  const list = await Notification.find({ user: req.user._id }).sort({ createdAt: -1 });
  res.json(list);
});

// PUT /api/notifications/read-all
router.put('/read-all', protect, async (req, res) => {
  await Notification.updateMany({ user: req.user._id, read: false }, { read: true, readAt: new Date() });
  res.json({ message: 'All marked as read' });
});

// PUT /api/notifications/:id/read
router.put('/:id/read', protect, async (req, res) => {
  const notif = await Notification.findOneAndUpdate(
    { _id: req.params.id, user: req.user._id },
    { read: true, readAt: new Date() },
    { new: true }
  );
  if (!notif) return res.status(404).json({ message: 'Notification not found' });
  res.json(notif);
});

// DELETE /api/notifications/:id
router.delete('/:id', protect, async (req, res) => {
  const notif = await Notification.findOneAndDelete({ _id: req.params.id, user: req.user._id });
  if (!notif) return res.status(404).json({ message: 'Notification not found' });
  res.json({ message: 'Notification deleted' });
});

module.exports = router;
