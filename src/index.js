require('dotenv').config();
require('express-async-errors');
const express  = require('express');
const cors     = require('cors');
const path     = require('path');
const connectDB = require('./config/db');
const errorHandler = require('./middleware/error');

// Routes
const authRoutes      = require('./routes/auth');
const productRoutes   = require('./routes/products');
const orderRoutes     = require('./routes/orders');
const analyticsRoutes = require('./routes/analytics');
const adminRoutes     = require('./routes/admin');
const notificationRoutes = require('./routes/notifications');

// Connect to MongoDB Atlas
connectDB();

const app = express();

// CORS — allow frontend dev server
app.use(cors({
  origin: process.env.CLIENT_URL || 'http://localhost:5173',
  credentials: true,
}));

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Serve uploaded files
app.use('/uploads', express.static(path.join(__dirname, '../uploads')));

// API Routes
app.use('/api/auth',      authRoutes);
app.use('/api/products',  productRoutes);
app.use('/api/orders',    orderRoutes);
app.use('/api/analytics', analyticsRoutes);
app.use('/api/admin',     adminRoutes);
app.use('/api/notifications', notificationRoutes);

// Health check
app.get('/api/health', (req, res) => res.json({ status: 'ok', time: new Date() }));

// Global error handler
app.use(errorHandler);

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`🚀 FreshLync API running on http://localhost:${PORT}`);
});
