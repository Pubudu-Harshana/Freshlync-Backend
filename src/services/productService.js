/**
 * Product database service for the FreshLync Chatbot.
 * Handles product search, stock checks, category filtering, and smart recommendations.
 */

const Product = require('../models/Product');

/**
 * Retrieves product information and handles out-of-stock or not-found alternatives.
 * @param {string} name - Product name to query
 * @returns {object} { product, inStock, alternatives }
 */
async function getProductInfo(name) {
  if (!name || typeof name !== 'string') {
    return { product: null, inStock: false, alternatives: [] };
  }

  // Try to find exact or partial matches
  let product = await Product.findOne({
    name: { $regex: name.trim(), $options: 'i' }
  }).lean();

  // If not found, try to split words and match any word (fallback partial match)
  if (!product) {
    const words = name.split(/\s+/).filter(w => w.length > 2);
    if (words.length > 0) {
      const regex = words.join('|');
      product = await Product.findOne({
        name: { $regex: regex, $options: 'i' }
      }).lean();
    }
  }

  // If product is found and in stock
  if (product && product.stock > 0) {
    return {
      product: {
        name: product.name,
        price: product.price,
        stock: product.stock,
        unit: product.unit || 'kg',
        category: product.category
      },
      inStock: true,
      alternatives: []
    };
  }

  // If product is found but out of stock, OR not found at all, fetch alternatives!
  const alternatives = [];
  
  if (product) {
    // Fetch products in the same category
    const sameCategory = await Product.find({
      category: product.category,
      stock: { $gt: 0 },
      _id: { $ne: product._id }
    })
      .select('name price unit stock category')
      .limit(3)
      .lean();
    alternatives.push(...sameCategory);
  }

  // If we still need more alternatives, or product wasn't found at all,
  // grab the cheapest/most available overall products as fallback recommendations
  if (alternatives.length < 3) {
    const limit = 5 - alternatives.length;
    const excludeIds = product ? [product._id, ...alternatives.map(a => a._id)] : alternatives.map(a => a._id);
    const overallFallbacks = await Product.find({
      stock: { $gt: 0 },
      _id: { $not: { $in: excludeIds } }
    })
      .select('name price unit stock category')
      .sort({ price: 1 }) // cheapest first
      .limit(limit)
      .lean();
    alternatives.push(...overallFallbacks);
  }

  return {
    product: product ? {
      name: product.name,
      price: product.price,
      stock: 0,
      unit: product.unit || 'kg',
      category: product.category
    } : null,
    inStock: false,
    alternatives: alternatives.map(p => ({
      name: p.name,
      price: p.price,
      stock: p.stock,
      unit: p.unit || 'kg',
      category: p.category
    }))
  };
}

/**
 * Retrieves in-stock products under a specific category.
 * @param {string} categoryName 
 * @returns {array} list of products
 */
async function getCategoryProducts(categoryName) {
  if (!categoryName) return [];

  // Map keywords to official categories in DB if needed
  // (e.g. "veg" -> "Vegetables", "seafood" -> "Fish")
  let catRegex = categoryName;
  if (categoryName.toLowerCase() === 'veg' || categoryName.toLowerCase() === 'vegetable') {
    catRegex = 'Vegetables';
  } else if (categoryName.toLowerCase() === 'seafood' || categoryName.toLowerCase() === 'fish') {
    catRegex = 'Fish|Seafood';
  }

  const products = await Product.find({
    $or: [
      { category: { $regex: catRegex, $options: 'i' } },
      { name: { $regex: categoryName, $options: 'i' } }
    ],
    stock: { $gt: 0 }
  })
    .select('name price unit stock category')
    .sort({ price: 1 })
    .limit(10)
    .lean();

  return products.map(p => ({
    name: p.name,
    price: p.price,
    stock: p.stock,
    unit: p.unit || 'kg',
    category: p.category
  }));
}

/**
 * Smart fallback search for products matching search terms.
 * @param {string} query 
 * @returns {array} list of 5 products
 */
async function searchFallback(query) {
  const words = query ? query.split(/\s+/).filter(w => w.length > 2) : [];
  let filter = { stock: { $gt: 0 } };

  if (words.length > 0) {
    const regex = words.join('|');
    filter = {
      stock: { $gt: 0 },
      $or: [
        { name: { $regex: regex, $options: 'i' } },
        { category: { $regex: regex, $options: 'i' } }
      ]
    };
  }

  const products = await Product.find(filter)
    .select('name price unit stock category')
    .limit(5)
    .lean();

  // If we found nothing, return any top 5 in-stock products
  if (products.length === 0) {
    const defaultProducts = await Product.find({ stock: { $gt: 0 } })
      .select('name price unit stock category')
      .limit(5)
      .lean();
    return defaultProducts.map(p => ({
      name: p.name,
      price: p.price,
      stock: p.stock,
      unit: p.unit || 'kg',
      category: p.category
    }));
  }

  return products.map(p => ({
    name: p.name,
    price: p.price,
    stock: p.stock,
    unit: p.unit || 'kg',
    category: p.category
  }));
}

module.exports = {
  getProductInfo,
  getCategoryProducts,
  searchFallback
};
