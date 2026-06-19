const Product = require('../models/Product');
const User = require('../models/User');
const jwt = require('jsonwebtoken');

// GET /api/products  (public — marketplace browsing)
exports.getProducts = async (req, res) => {
  const { search, category, maxPrice, page = 1, limit = 20, supplierId } = req.query;

  // Find all approved suppliers
  const approvedSuppliers = await User.find({ role: 'supplier', verificationStatus: 'approved' }).select('_id');
  const approvedSupplierIds = approvedSuppliers.map(s => s._id);

  // Check if requestor is the supplier themselves (to let them see their own dashboard inventory)
  let isRequestorOwnSupplier = false;
  if (req.headers.authorization && req.headers.authorization.startsWith('Bearer ')) {
    try {
      const token = req.headers.authorization.split(' ')[1];
      const decoded = jwt.verify(token, process.env.JWT_SECRET);
      if (decoded && decoded.id && supplierId && decoded.id.toString() === supplierId.toString()) {
        isRequestorOwnSupplier = true;
      }
    } catch (err) {
      // Ignore
    }
  }

  const query = { isActive: true };
  if (category && category !== 'All') query.category = category;
  if (maxPrice) query.price = { $lte: parseFloat(maxPrice) };
  
  if (supplierId) {
    const isApproved = approvedSupplierIds.map(id => id.toString()).includes(supplierId.toString());
    if (isApproved || isRequestorOwnSupplier) {
      query.supplier = supplierId;
    } else {
      query.supplier = '000000000000000000000000'; // Return empty results
    }
  } else {
    query.supplier = { $in: approvedSupplierIds };
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

  res.json({ products, total, page: parseInt(page), pages: Math.ceil(total / limit) });
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

  res.json(product);
};

// POST /api/products  (supplier only)
exports.createProduct = async (req, res) => {
  if (req.user.role === 'supplier' && req.user.verificationStatus !== 'approved') {
    return res.status(403).json({ message: 'Verification approval is required to publish products.' });
  }

  const { name, category, price, unit, stock, minOrder, description, sku } = req.body;
  const image = req.file ? `/uploads/${req.file.filename}` : '';

  const product = await Product.create({
    name, category, price: parseFloat(price), unit,
    stock: parseInt(stock), minOrder: parseInt(minOrder) || 1,
    description, sku,
    image,
    supplier: req.user._id,
    supplierName: req.user.company || req.user.name,
  });

  res.status(201).json(product);
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
  const updated = await Product.findByIdAndUpdate(
    req.params.id,
    { name, category, price: parseFloat(price), unit, stock: parseInt(stock), minOrder: parseInt(minOrder), description, sku },
    { new: true, runValidators: true }
  );

  res.json(updated);
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

  res.json(product);
};
