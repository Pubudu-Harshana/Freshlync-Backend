const express = require('express');
const router = express.Router();
const { protect } = require('../middleware/auth');
const { chat } = require('../controllers/chatController');

// POST /api/chat  — authenticated users only
router.post('/', protect, chat);

module.exports = router;
