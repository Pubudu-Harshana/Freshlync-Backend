const fs = require('fs');
const path = require('path');
const Product = require('../models/Product');
const User = require('../models/User');
const Notification = require('../models/Notification');
const jwt = require('jsonwebtoken');

const getMarginSetting = () => {
  let marginSetting = 15;
  const settingsPath = path.join(__dirname, '../../freshlync/ml_service/outputs/settings.json');
  if (fs.existsSync(settingsPath)) {
    try {
      const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
      if (settings.margin !== undefined) {
        marginSetting = parseFloat(settings.margin);
      }
    } catch (err) {
      console.error("Error reading settings.json:", err);
    }
  }
  return marginSetting;
};

const getRequestorRole = async (req) => {
  if (req.user && req.user.role) {
    return req.user.role;
  }
  if (req.headers.authorization && req.headers.authorization.startsWith('Bearer ')) {
    try {
      const token = req.headers.authorization.split(' ')[1];
      const decoded = jwt.verify(token, process.env.JWT_SECRET);
      if (decoded && decoded.id) {
        const user = await User.findById(decoded.id);
        if (user) return user.role;
      }
    } catch (err) {
      // Ignore
    }
  }
  return null;
};

const formatProductForRole = (product, requestorRole, marginSetting) => {
  if (!product) return product;
  const p = product.toObject ? product.toObject() : { ...product };
  const basePrice = p.basePrice !== undefined ? p.basePrice : p.price;
  const sellingPrice = p.sellingPrice !== undefined ? p.sellingPrice : parseFloat((basePrice * (1 + marginSetting / 100)).toFixed(2));

  p.basePrice = basePrice;
  p.sellingPrice = sellingPrice;
  p.supplierPrice = basePrice;
  p.marketplacePrice = sellingPrice;
  p.displayPrice = requestorRole === 'supplier' ? basePrice : sellingPrice;

  if (requestorRole === 'supplier') {
    delete p.sellingPrice;
    delete p.marketplacePrice;
  } else if (requestorRole === 'buyer' || !requestorRole) {
    delete p.price;
    delete p.basePrice;
    delete p.supplierPrice;
  }
  return p;
};

// GET /api/products  (public — marketplace browsing)
exports.getProducts = async (req, res) => {
  const { search, category, maxPrice, page = 1, supplierId } = req.query;
  // Security: Cap limit to prevent resource abuse
  const limit = Math.min(parseInt(req.query.limit) || 20, 100);

  // Find all approved suppliers
  const approvedSuppliers = await User.find({ role: 'supplier', verificationStatus: 'approved' }).select('_id');
  const approvedSupplierIds = approvedSuppliers.map(s => s._id);

  // Check requestor details from token
  let isRequestorAdmin = false;
  let isRequestorOwnSupplier = false;
  let requestorId = null;
  if (req.headers.authorization && req.headers.authorization.startsWith('Bearer ')) {
    try {
      const token = req.headers.authorization.split(' ')[1];
      const decoded = jwt.verify(token, process.env.JWT_SECRET);
      if (decoded && decoded.id) {
        requestorId = decoded.id;
        const user = await User.findById(decoded.id);
        if (user) {
          if (user.role === 'admin') {
            isRequestorAdmin = true;
          }
          if (user.role === 'supplier' && supplierId && user._id.toString() === supplierId.toString()) {
            isRequestorOwnSupplier = true;
          }
        }
      }
    } catch (err) {
      // Ignore
    }
  }

  const query = {};
  if (!isRequestorAdmin && !isRequestorOwnSupplier) {
    query.isActive = true;
  }

  if (category && category !== 'All') query.category = category;
  if (maxPrice) query.price = { $lte: parseFloat(maxPrice) };
  
  if (supplierId) {
    const isApproved = approvedSupplierIds.map(id => id.toString()).includes(supplierId.toString());
    if (isApproved || isRequestorOwnSupplier || isRequestorAdmin) {
      query.supplier = supplierId;
    } else {
      query.supplier = '000000000000000000000000'; // Return empty results
    }
  } else {
    if (!isRequestorAdmin) {
      query.supplier = { $in: approvedSupplierIds };
    }
  }

  if (search) {
    query.$or = [
      { name: { $regex: search, $options: 'i' } },
      { supplierName: { $regex: search, $options: 'i' } },
      { category: { $regex: search, $options: 'i' } },
    ];
  }

  const skip = (parseInt(page) - 1) * parseInt(limit);
  const [products, total] = await Promise.all([
    Product.find(query).sort({ createdAt: -1 }).skip(skip).limit(parseInt(limit)),
    Product.countDocuments(query),
  ]);

  const marginSetting = getMarginSetting();
  const requestorRole = await getRequestorRole(req);

  const productsWithMarkup = products.map(product => formatProductForRole(product, requestorRole, marginSetting));

  res.json({ products: productsWithMarkup, total, page: parseInt(page), pages: Math.ceil(total / limit) });
};

// GET /api/products/:id
exports.getProduct = async (req, res) => {
  const product = await Product.findById(req.params.id).populate('supplier', 'name company role verificationStatus');
  if (!product) return res.status(404).json({ message: 'Product not found' });

  // If supplier is not approved, restrict unless requestor is that supplier or admin
  if (product.supplier && product.supplier.role === 'supplier' && product.supplier.verificationStatus !== 'approved') {
    let isAuthorized = false;
    if (req.headers.authorization && req.headers.authorization.startsWith('Bearer ')) {
      try {
        const token = req.headers.authorization.split(' ')[1];
        const decoded = jwt.verify(token, process.env.JWT_SECRET);
        if (decoded) {
          if (decoded.id === product.supplier._id.toString()) {
            isAuthorized = true;
          } else {
            const reqUser = await User.findById(decoded.id);
            if (reqUser && reqUser.role === 'admin') {
              isAuthorized = true;
            }
          }
        }
      } catch (err) {
        // Ignore
      }
    }
    if (!isAuthorized) {
      return res.status(403).json({ message: 'Supplier is not verified' });
    }
  }

  const marginSetting = getMarginSetting();
  const requestorRole = await getRequestorRole(req);

  res.json(formatProductForRole(product, requestorRole, marginSetting));
};

// POST /api/products  (supplier only)
exports.createProduct = async (req, res) => {
  if (req.user.role === 'supplier' && req.user.verificationStatus !== 'approved') {
    return res.status(403).json({ message: 'Verification approval is required to publish products.' });
  }

  const { name, category, price, unit, stock, minOrder, description, sku } = req.body;
  // With Cloudinary storage, req.file.path is the full HTTPS URL
  const image = req.file ? req.file.path : '';

  const marginSetting = getMarginSetting();
  const basePrice = parseFloat(price);
  const sellingPrice = parseFloat((basePrice * (1 + marginSetting / 100)).toFixed(2));

  const product = await Product.create({
    name, category, price: basePrice,
    basePrice, sellingPrice,
    unit, stock: parseInt(stock), minOrder: parseInt(minOrder) || 1,
    description, sku,
    image,
    supplier: req.user._id,
    supplierName: req.user.company || req.user.name,
  });

  res.status(201).json(formatProductForRole(product, req.user.role, marginSetting));
};

// PUT /api/products/:id
exports.updateProduct = async (req, res) => {
  if (req.user.role === 'supplier' && req.user.verificationStatus !== 'approved') {
    return res.status(403).json({ message: 'Verification approval is required to manage inventory.' });
  }

  const product = await Product.findById(req.params.id);
  if (!product) return res.status(404).json({ message: 'Product not found' });

  // Ensure supplier owns product or admin
  if (product.supplier.toString() !== req.user._id.toString() && req.user.role !== 'admin') {
    return res.status(403).json({ message: 'Not authorised' });
  }

  const { name, category, price, unit, stock, minOrder, description, sku } = req.body;
  const updateData = {};
  if (name !== undefined) updateData.name = name;
  if (category !== undefined) updateData.category = category;
  if (price !== undefined) {
    const marginSetting = getMarginSetting();
    const basePrice = parseFloat(price);
    const sellingPrice = parseFloat((basePrice * (1 + marginSetting / 100)).toFixed(2));
    updateData.price = basePrice;
    updateData.basePrice = basePrice;
    updateData.sellingPrice = sellingPrice;
  }
  if (unit !== undefined) updateData.unit = unit;
  if (stock !== undefined) updateData.stock = parseInt(stock);
  if (minOrder !== undefined) updateData.minOrder = parseInt(minOrder);
  if (description !== undefined) updateData.description = description;
  if (sku !== undefined) updateData.sku = sku;
  // Handle image update via Cloudinary
  if (req.file) updateData.image = req.file.path;
  if (req.body.isActive !== undefined) {
    const isApproved = req.body.isActive === true || req.body.isActive === 'true';
    if (product.isActive !== isApproved) {
      updateData.isActive = isApproved;
      try {
        await Notification.create({
          user: product.supplier,
          title: isApproved ? 'Product Listing Approved' : 'Product Listing Flagged/Rejected',
          message: isApproved 
            ? `Your product listing "${product.name}" has been approved and is now active in the marketplace.` 
            : `Your product listing "${product.name}" has been flagged and temporarily deactivated by administrators.`,
          type: 'system'
        });
      } catch (err) {
        console.error("Error creating product status notification:", err);
      }
    }
  }

  const updated = await Product.findByIdAndUpdate(
    req.params.id,
    { $set: updateData },
    { new: true, runValidators: true }
  );

  const marginSetting = getMarginSetting();
  res.json(formatProductForRole(updated, req.user.role, marginSetting));
};

// DELETE /api/products/:id
exports.deleteProduct = async (req, res) => {
  if (req.user.role === 'supplier' && req.user.verificationStatus !== 'approved') {
    return res.status(403).json({ message: 'Verification approval is required to manage inventory.' });
  }

  const product = await Product.findById(req.params.id);
  if (!product) return res.status(404).json({ message: 'Product not found' });

  if (product.supplier.toString() !== req.user._id.toString() && req.user.role !== 'admin') {
    return res.status(403).json({ message: 'Not authorised' });
  }

  await product.deleteOne();
  res.json({ message: 'Product deleted' });
};

// PATCH /api/products/:id/stock
exports.updateStock = async (req, res) => {
  if (req.user.role === 'supplier' && req.user.verificationStatus !== 'approved') {
    return res.status(403).json({ message: 'Verification approval is required to manage inventory.' });
  }

  const product = await Product.findById(req.params.id);
  if (!product) return res.status(404).json({ message: 'Product not found' });

  // Ensure supplier owns product or admin
  if (product.supplier.toString() !== req.user._id.toString() && req.user.role !== 'admin') {
    return res.status(403).json({ message: 'Not authorised' });
  }

  const { stock } = req.body;
  product.stock = parseInt(stock);
  await product.save();

  const marginSetting = getMarginSetting();
  res.json(formatProductForRole(product, req.user.role, marginSetting));
};

// POST /api/products/:id/appeal
exports.submitAppeal = async (req, res) => {
  const product = await Product.findById(req.params.id);
  if (!product) return res.status(404).json({ message: 'Product not found' });

  // Ensure requestor is the supplier who owns the product
  if (product.supplier.toString() !== req.user._id.toString()) {
    return res.status(403).json({ message: 'Not authorised to appeal for this product' });
  }

  const { reason } = req.body;
  if (!reason || reason.trim() === '') {
    return res.status(400).json({ message: 'Appeal reason is required' });
  }

  // Find admin user to direct notification to
  const admin = await User.findOne({ role: 'admin' });
  if (!admin) return res.status(500).json({ message: 'No admin user found to receive the appeal' });

  // Create appeal notification targeting the admin
  await Notification.create({
    user: admin._id,
    title: 'Product Listing Appeal',
    message: `Supplier "${req.user.company || req.user.name}" appealed rejection of "${product.name}": ${reason}`,
    type: 'system'
  });

  res.json({ message: 'Appeal submitted successfully.' });
};
