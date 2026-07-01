require('dotenv').config();
const mongoose = require('mongoose');
const User = require('../models/User');

const MONGO_URI = process.env.MONGO_URI || 'mongodb+srv://pubzH:Pubz1234@cluster0.wtwpktk.mongodb.net/?appName=Cluster0';

async function run() {
  console.log('Connecting to MongoDB Atlas...');
  try {
    await mongoose.connect(MONGO_URI);
    console.log('✅ Connected to database.');

    // Find all users with local avatar uploads
    const users = await User.find({ avatar: { $regex: /^\/uploads\// } });
    console.log(`Found ${users.length} users with local avatar uploads in database.`);

    let updatedCount = 0;
    for (const user of users) {
      console.log(`Resetting avatar for user: ${user.name} (${user.email})`);
      user.avatar = '';
      await user.save();
      updatedCount++;
    }

    console.log(`Successfully reset ${updatedCount} user avatars in the database to empty (forcing default placeholder).`);
  } catch (error) {
    console.error('❌ Reset failed:', error);
  } finally {
    await mongoose.disconnect();
    console.log('Disconnected from database.');
  }
}

run();
