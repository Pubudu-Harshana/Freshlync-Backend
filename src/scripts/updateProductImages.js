require('dotenv').config();
const mongoose = require('mongoose');
const Product = require('../models/Product');

const MONGO_URI = process.env.MONGO_URI || 'mongodb+srv://pubzH:Pubz1234@cluster0.wtwpktk.mongodb.net/?appName=Cluster0';

const UNSPLASH_IMAGES = {
  'salmon': 'https://images.unsplash.com/photo-1599084993091-1cb5c0721cc6?auto=format&fit=crop&q=80&w=600',
  'broccoli': 'https://images.unsplash.com/photo-1583663848850-46af132dc08e?auto=format&fit=crop&q=80&w=600',
  'beef': 'https://images.unsplash.com/photo-1603048297172-c92544798d5e?auto=format&fit=crop&q=80&w=600',
  'tomato': 'https://images.unsplash.com/photo-1592924357228-91a4daadcfea?auto=format&fit=crop&q=80&w=600',
  'seabass': 'https://images.unsplash.com/photo-1519708227418-c8fd9a32b7a2?auto=format&fit=crop&q=80&w=600',
  'carrot': 'https://images.unsplash.com/photo-1447175008436-054170c2e979?auto=format&fit=crop&q=80&w=600',
};

async function run() {
  console.log('Connecting to MongoDB Atlas...');
  try {
    await mongoose.connect(MONGO_URI);
    console.log('✅ Connected to database.');

    const products = await Product.find({});
    console.log(`Found ${products.length} products in database.`);

    let updatedCount = 0;
    for (const product of products) {
      const nameLower = product.name.toLowerCase();
      let matchedUrl = null;

      // Find matching Unsplash image by keyword
      for (const [keyword, url] of Object.entries(UNSPLASH_IMAGES)) {
        if (nameLower.includes(keyword)) {
          matchedUrl = url;
          break;
        }
      }

      // If matched and it currently points to a local upload or empty, update it
      if (matchedUrl && (!product.image || product.image.startsWith('/uploads/'))) {
        console.log(`Updating "${product.name}" image to: ${matchedUrl}`);
        product.image = matchedUrl;
        await product.save();
        updatedCount++;
      }
    }

    console.log(`Migration finished. Successfully updated ${updatedCount} product images in the database.`);
  } catch (error) {
    console.error('❌ Migration failed:', error);
  } finally {
    await mongoose.disconnect();
    console.log('Disconnected from database.');
  }
}

run();
