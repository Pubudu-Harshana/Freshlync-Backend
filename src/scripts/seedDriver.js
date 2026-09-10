/**
 * seedDriver.js – Run ONCE to create a default driver account in MongoDB.
 * Usage: node src/scripts/seedDriver.js
 */

require('dotenv').config();
const mongoose = require('mongoose');
const User = require('../models/User');

const DRIVER_EMAIL    = 'driver@freshlync.com';
const DRIVER_PASSWORD = 'Driver@1234';
const DRIVER_NAME     = 'Logistics Delivery Driver';

(async () => {
  try {
    await mongoose.connect(process.env.MONGO_URI);
    console.log('✅ Connected to MongoDB Atlas');

    // Check if driver already exists
    const existing = await User.findOne({ email: DRIVER_EMAIL });
    if (existing) {
      existing.role = 'driver';
      existing.isVerified = true;
      if (!existing.phone) existing.phone = '+1 (555) 890-1234';
      await existing.save();
      console.log(`ℹ️  Driver user already exists: ${DRIVER_EMAIL} (Updated role to driver)`);
      process.exit(0);
    }

    // Create driver user (password hashed automatically by pre-save hook)
    const driver = await User.create({
      name:       DRIVER_NAME,
      email:      DRIVER_EMAIL,
      password:   DRIVER_PASSWORD,
      role:       'driver',
      phone:      '+1 (555) 890-1234',
      isVerified: true,
      verificationStatus: 'approved'
    });

    console.log('🎉 Driver user created successfully!');
    console.log('─────────────────────────────────');
    console.log(`   Email    : ${DRIVER_EMAIL}`);
    console.log(`   Password : ${DRIVER_PASSWORD}`);
    console.log(`   Role     : ${driver.role}`);
    console.log('─────────────────────────────────');
    console.log('You can now log in with these credentials.');
    process.exit(0);
  } catch (err) {
    console.error('❌ Error creating driver:', err.message);
    process.exit(1);
  }
})();
