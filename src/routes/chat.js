const express = require('express');
const router = express.Router();
const { optionalProtect } = require('../middleware/auth');
const { chat } = require('../controllers/chatController');

// POST /api/chat  — authenticated/guest users
router.post('/', optionalProtect, chat);

module.exports = router;
