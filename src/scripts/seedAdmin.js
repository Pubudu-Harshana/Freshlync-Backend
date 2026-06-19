/**
 * seedAdmin.js – Run ONCE to create the admin account in MongoDB Atlas.
 * Usage: node src/scripts/seedAdmin.js
 */

require('dotenv').config();
const mongoose = require('mongoose');
const User = require('../models/User');

const ADMIN_EMAIL    = 'admin@freshlync.com';
const ADMIN_PASSWORD = 'Admin@1234';
const ADMIN_NAME     = 'FreshLync Admin';

(async () => {
  try {
    await mongoose.connect(process.env.MONGO_URI);
    console.log('✅ Connected to MongoDB Atlas');

    // Check if admin already exists
    const existing = await User.findOne({ email: ADMIN_EMAIL });
    if (existing) {
      console.log(`ℹ️  Admin user already exists: ${ADMIN_EMAIL}`);
      console.log(`   Role: ${existing.role}`);
      process.exit(0);
    }

    // Create admin user (password is hashed automatically by the pre-save hook)
    const admin = await User.create({
      name:       ADMIN_NAME,
      email:      ADMIN_EMAIL,
      password:   ADMIN_PASSWORD,
      role:       'admin',
      isVerified: true,
    });

    console.log('🎉 Admin user created successfully!');
    console.log('─────────────────────────────────');
    console.log(`   Email    : ${ADMIN_EMAIL}`);
    console.log(`   Password : ${ADMIN_PASSWORD}`);
    console.log(`   Role     : ${admin.role}`);
    console.log('─────────────────────────────────');
    console.log('You can now log in with these credentials.');
    process.exit(0);
  } catch (err) {
    console.error('❌ Error creating admin:', err.message);
    process.exit(1);
  }
})();
