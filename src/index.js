require('dotenv').config();
require('express-async-errors');
const express       = require('express');
const cors          = require('cors');
const path          = require('path');
const helmet        = require('helmet');
const rateLimit     = require('express-rate-limit');
const mongoSanitize = require('express-mongo-sanitize');
const connectDB     = require('./config/db');
const errorHandler  = require('./middleware/error');

// Routes
const authRoutes      = require('./routes/auth');
const productRoutes   = require('./routes/products');
const orderRoutes     = require('./routes/orders');
const analyticsRoutes = require('./routes/analytics');
const adminRoutes     = require('./routes/admin');
const notificationRoutes = require('./routes/notifications');
const reviewRoutes    = require('./routes/reviews');
const chatRoutes      = require('./routes/chat');

// Connect to MongoDB Atlas
connectDB();

const app = express();

// Security: HTTP headers
app.use(helmet());

// CORS — allow frontend dev server
app.use(cors({
  origin: process.env.CLIENT_URL || 'http://localhost:5173',
  credentials: true,
}));

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Security: Strip MongoDB operators from user input (NoSQL injection prevention)
app.use(mongoSanitize());

// Security: Rate limiting on auth routes (50 requests per 15 minutes)
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 50,
  message: { message: 'Too many requests from this IP, please try again after 15 minutes.' },
  standardHeaders: true,
  legacyHeaders: false,
});
app.use('/api/auth/login',    authLimiter);
app.use('/api/auth/register', authLimiter);

// Serve uploaded files — override helmet's CORP header so the frontend (different port) can load images
app.use('/uploads', (req, res, next) => {
  res.setHeader('Cross-Origin-Resource-Policy', 'cross-origin');
  next();
}, express.static(path.join(__dirname, '../uploads')));

// API Routes
app.use('/api/auth',      authRoutes);
app.use('/api/products',  productRoutes);
app.use('/api/orders',    orderRoutes);
app.use('/api/analytics', analyticsRoutes);
app.use('/api/admin',     adminRoutes);
app.use('/api/notifications', notificationRoutes);
app.use('/api/reviews',   reviewRoutes);
app.use('/api/chat',      chatRoutes);

// Health check
app.get('/api/health', (req, res) => res.json({ status: 'ok', time: new Date() }));

// Global error handler
app.use(errorHandler);

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`🚀 FreshLync API running on http://localhost:${PORT}`);
});
