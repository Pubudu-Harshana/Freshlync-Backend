const fs = require('fs');
const path = require('path');
const Order = require('../models/Order');
const Product = require('../models/Product');
const User = require('../models/User');
const Invoice = require('../models/Invoice');

// GET /api/orders
exports.getOrders = async (req, res) => {
  const { status, page = 1, limit = 20 } = req.query;
  const query = {};

  // Role-based filtering
  if (req.user.role === 'buyer') {
    query.buyer = req.user._id;
  } else if (req.user.role === 'supplier') {
    query['items.supplier'] = req.user._id;
    query.status = { $ne: 'Pending Payment Verification' };
  }
  // admin sees all

  if (status && status !== 'All') {
    if (req.user.role === 'supplier') {
      query.supplierStatuses = {
        $elemMatch: {
          supplier: req.user._id,
          status: status
        }
      };
    } else {
      query.status = status;
    }
  }

  const skip = (parseInt(page) - 1) * parseInt(limit);
  const [rawOrders, total] = await Promise.all([
    Order.find(query)
      .populate('buyer', 'name email company')
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(parseInt(limit)),
    Order.countDocuments(query),
  ]);

  let orders = rawOrders;
  if (req.user.role === 'supplier') {
    const supplierIdStr = req.user._id.toString();
    orders = rawOrders.map(order => {
      const o = order.toObject ? order.toObject() : order;
      const supStatusEntry = o.supplierStatuses?.find(s => s.supplier?.toString() === supplierIdStr);
      o.status = supStatusEntry ? supStatusEntry.status : o.status;
      o.items = o.items.filter(item => item.supplier?.toString() === supplierIdStr);
      
      // Override price and total for supplier view, hide marketplacePrice
      o.items = o.items.map(item => {
        const base = item.supplierPrice !== undefined ? item.supplierPrice : item.price;
        item.price = base;
        delete item.marketplacePrice;
        return item;
      });
      o.total = o.items.reduce((sum, item) => sum + item.price * item.quantity, 0);
      return o;
    });
  } else if (req.user.role === 'buyer') {
    orders = rawOrders.map(order => {
      const o = order.toObject ? order.toObject() : order;
      
      // Hide supplierPrice from buyer
      o.items = o.items.map(item => {
        delete item.supplierPrice;
        return item;
      });
      return o;
    });
  }

  res.json({ orders, total });
};

// GET /api/orders/:id
exports.getOrder = async (req, res) => {
  const order = await Order.findById(req.params.id)
    .populate('buyer', 'name email')
    .populate('items.product', 'name image');

  if (!order) return res.status(404).json({ message: 'Order not found' });

  if (req.user.role === 'supplier') {
    const supplierIdStr = req.user._id.toString();
    const isSupplierInvolved = order.items.some(item => item.supplier?.toString() === supplierIdStr);
    if (!isSupplierInvolved) {
      return res.status(403).json({ message: 'Access denied' });
    }
    if (order.status === 'Pending Payment Verification') {
      return res.status(403).json({ message: 'Access denied. Order is awaiting payment verification.' });
    }

    const o = order.toObject();
    const supStatusEntry = o.supplierStatuses?.find(s => s.supplier?.toString() === supplierIdStr);
    o.status = supStatusEntry ? supStatusEntry.status : o.status;
    o.items = o.items.filter(item => item.supplier?.toString() === supplierIdStr);
    
    // Override price and total for supplier view, hide marketplacePrice
    o.items = o.items.map(item => {
      const base = item.supplierPrice !== undefined ? item.supplierPrice : item.price;
      item.price = base;
      delete item.marketplacePrice;
      return item;
    });
    o.total = o.items.reduce((sum, item) => sum + item.price * item.quantity, 0);

    return res.json(o);
  }

  if (req.user.role === 'buyer') {
    const o = order.toObject();
    // Hide supplierPrice from buyer
    o.items = o.items.map(item => {
      delete item.supplierPrice;
      return item;
    });
    return res.json(o);
  }

  res.json(order);
};

// POST /api/orders  (buyer places order)
exports.placeOrder = async (req, res) => {
  const { items, delivery, paymentMethod, notes, paymentSlip } = req.body;

  if (!items || items.length === 0) {
    return res.status(400).json({ message: 'No items in order' });
  }

  if (paymentMethod === 'bank' && !paymentSlip) {
    return res.status(400).json({ message: 'Payment slip is required for bank transfers.' });
  }

  // Load margin setting
  let marginSetting = 15;
  const settingsPath = path.join(__dirname, '../../freshlync/ml_service/outputs/settings.json');
  if (fs.existsSync(settingsPath)) {
    try {
      const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
      if (settings.margin !== undefined) {
        marginSetting = parseFloat(settings.margin);
      }
    } catch (err) {
      console.error("Error reading settings.json during order checkout:", err);
    }
  }

  // Enrich items with supplier info and freeze/snapshot pricing
  const enrichedItems = [];
  const uniqueSuppliersSet = new Set();
  let calculatedTotal = 0;

  for (const item of items) {
    if (item.product) {
      const prod = await Product.findById(item.product).populate('supplier');
      if (prod) {
        const supIdStr = prod.supplier?._id?.toString() || prod.supplier?.toString();
        const basePrice = prod.basePrice !== undefined ? prod.basePrice : prod.price;
        const sellingPrice = prod.sellingPrice !== undefined ? prod.sellingPrice : parseFloat((basePrice * (1 + marginSetting / 100)).toFixed(2));

        enrichedItems.push({
          product: item.product,
          name: prod.name,
          quantity: item.quantity,
          unit: item.unit || prod.unit || 'kg',
          price: sellingPrice, // Legacy field contains sellingPrice
          supplierPrice: basePrice,
          marketplacePrice: sellingPrice,
          supplier: prod.supplier?._id || prod.supplier,
          supplierName: prod.supplierName || prod.supplier?.company || prod.supplier?.name || 'Unknown Supplier'
        });

        calculatedTotal += sellingPrice * item.quantity;

        if (supIdStr) {
          uniqueSuppliersSet.add(supIdStr);
        }
      } else {
        // Fallback
        enrichedItems.push({
          ...item,
          supplierPrice: item.price,
          marketplacePrice: item.price
        });
        calculatedTotal += item.price * item.quantity;
      }
    } else {
      // Fallback
      enrichedItems.push({
        ...item,
        supplierPrice: item.price,
        marketplacePrice: item.price
      });
      calculatedTotal += item.price * item.quantity;
    }
  }

  const total = parseFloat(calculatedTotal.toFixed(2));

  // B2B Net 30 Credit Limit Check
  if (paymentMethod === 'net30') {
    const userInvoices = await Invoice.find({ buyer: req.user._id });
    let outstanding = 0;
    userInvoices.forEach(inv => {
      if (inv.status === 'Unpaid' || inv.status === 'Overdue') {
        outstanding += inv.amount;
      }
    });
    const creditLimit = req.user.creditLimit || 100000;
    const availableCredit = creditLimit - outstanding;

    if (availableCredit < total) {
      return res.status(400).json({
        message: `Insufficient B2B credit limit. (Required: £${total.toFixed(2)}, Available: £${availableCredit.toFixed(2)}). Please request a credit limit increase on your Billing Dashboard.`
      });
    }
  }

  const firstSupplierId = uniqueSuppliersSet.size > 0 ? Array.from(uniqueSuppliersSet)[0] : null;
  const supplierStatuses = Array.from(uniqueSuppliersSet).map(supId => ({
    supplier: supId,
    status: 'Pending'
  }));

  const order = await Order.create({
    buyer: req.user._id,
    supplier: firstSupplierId,
    items: enrichedItems,
    total,
    delivery,
    paymentMethod,
    notes,
    paymentSlip: paymentSlip || '',
    paymentStatus: paymentMethod === 'bank' ? 'Pending Verification' : 'Approved',
    status: paymentMethod === 'bank' ? 'Pending Payment Verification' : 'Pending',
    supplierStatuses
  });

  // B2B Net 30 Invoice Creation
  if (paymentMethod === 'net30') {
    try {
      await Invoice.create({
        buyer: req.user._id,
        order: order._id,
        invoiceNumber: `INV-2026-${Math.floor(100000 + Math.random() * 900000)}`,
        amount: total,
        status: 'Unpaid',
        issueDate: new Date(),
        dueDate: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000) // Net 30
      });
    } catch (err) {
      console.error("Error creating B2B invoice document during checkout:", err);
    }
  }

  // Admin notification for new Bank Transfer verification request
  if (paymentMethod === 'bank') {
    try {
      const Notification = require('../models/Notification');
      const admin = await User.findOne({ role: 'admin' });
      if (admin) {
        await Notification.create({
          user: admin._id,
          title: 'Payment Verification Request',
          message: `New payment verification request received from ${req.user.name || req.user.email}`,
          type: 'system'
        });
      }
    } catch (err) {
      console.error("Error creating payment notification for admin:", err);
    }
  }

  res.status(201).json(order);
};

// PUT /api/orders/:id/status  (supplier or admin)
exports.updateStatus = async (req, res) => {
  const { status } = req.body;
  const allowed = ['Pending', 'In Transit', 'Delivered', 'Cancelled'];
  if (!allowed.includes(status)) {
    return res.status(400).json({ message: 'Invalid status value' });
  }

  const order = await Order.findById(req.params.id);
  if (!order) return res.status(404).json({ message: 'Order not found' });

  if (req.user.role === 'supplier') {
    const supplierIdStr = req.user._id.toString();
    const isSupplierInvolved = order.items.some(item => item.supplier?.toString() === supplierIdStr);
    if (!isSupplierInvolved) {
      return res.status(403).json({ message: 'Access denied' });
    }

    let supStatusEntry = order.supplierStatuses?.find(s => s.supplier?.toString() === supplierIdStr);
    if (supStatusEntry) {
      supStatusEntry.status = status;
    } else {
      if (!order.supplierStatuses) order.supplierStatuses = [];
      order.supplierStatuses.push({ supplier: req.user._id, status });
    }

    // Recalculate overall status
    const activeStatuses = order.supplierStatuses.filter(s => s.status !== 'Cancelled').map(s => s.status);
    let overallStatus = 'Pending';
    if (activeStatuses.length === 0) {
      overallStatus = 'Cancelled';
    } else if (activeStatuses.every(s => s === 'Delivered')) {
      overallStatus = 'Delivered';
    } else if (activeStatuses.some(s => s === 'In Transit' || s === 'Delivered')) {
      overallStatus = 'In Transit';
    }
    order.status = overallStatus;

    await order.save();

    const o = order.toObject();
    const updatedStatusEntry = o.supplierStatuses?.find(s => s.supplier?.toString() === supplierIdStr);
    o.status = updatedStatusEntry ? updatedStatusEntry.status : o.status;
    o.items = o.items.filter(item => item.supplier?.toString() === supplierIdStr);
    o.total = o.items.reduce((sum, item) => sum + item.price * item.quantity, 0);

    return res.json(o);
  }

  if (req.user.role === 'admin') {
    order.status = status;
    order.supplierStatuses.forEach(s => {
      s.status = status;
    });

    if (order.supplierStatuses.length === 0) {
      const uniqueSuppliers = [...new Set(order.items.filter(item => item.supplier).map(item => item.supplier.toString()))];
      uniqueSuppliers.forEach(supId => {
        order.supplierStatuses.push({ supplier: supId, status });
      });
    }

    await order.save();
    return res.json(order);
  }

  res.status(403).json({ message: 'Access denied' });
};

// PUT /api/orders/:id/verify-payment  (admin verifies payment slip)
exports.verifyPayment = async (req, res) => {
  const { action } = req.body;
  if (!['approve', 'reject'].includes(action)) {
    return res.status(400).json({ message: 'Invalid action. Must be approve or reject.' });
  }

  const order = await Order.findById(req.params.id);
  if (!order) return res.status(404).json({ message: 'Order not found' });

  const Notification = require('../models/Notification');

  if (action === 'approve') {
    order.paymentStatus = 'Approved';
    order.status = 'Pending';
    // set supplierStatuses of order to Pending
    order.supplierStatuses.forEach(s => {
      s.status = 'Pending';
    });
    await order.save();

    // 1. Notify buyer
    try {
      await Notification.create({
        user: order.buyer,
        title: 'Order Payment Approved',
        message: `Your payment has been verified and your order has been confirmed.`,
        type: 'order'
      });
    } catch (err) {
      console.error(err);
    }

    // 2. Notify supplier(s) involved
    try {
      const suppliers = [...new Set(order.items.filter(item => item.supplier).map(item => item.supplier.toString()))];
      for (const supId of suppliers) {
        await Notification.create({
          user: supId,
          title: 'New Order Available',
          message: `A new verified order is available for processing.`,
          type: 'order'
        });
      }
    } catch (err) {
      console.error(err);
    }

  } else if (action === 'reject') {
    order.paymentStatus = 'Rejected';
    await order.save();

    // Notify buyer
    try {
      await Notification.create({
        user: order.buyer,
        title: 'Order Payment Rejected',
        message: `Your payment slip has been rejected. Please upload a new payment slip.`,
        type: 'order'
      });
    } catch (err) {
      console.error(err);
    }
  }

  res.json(order);
};

// PUT /api/orders/:id/reupload-slip  (customer uploads a replacement slip)
exports.reuploadSlip = async (req, res) => {
  const { paymentSlip } = req.body;
  if (!paymentSlip) {
    return res.status(400).json({ message: 'Payment slip is required.' });
  }

  const order = await Order.findOne({ _id: req.params.id, buyer: req.user._id });
  if (!order) return res.status(404).json({ message: 'Order not found' });

  order.paymentSlip = paymentSlip;
  order.paymentStatus = 'Pending Verification';
  order.status = 'Pending Payment Verification';
  await order.save();

  // Notify Admin
  try {
    const Notification = require('../models/Notification');
    const admin = await User.findOne({ role: 'admin' });
    if (admin) {
      await Notification.create({
        user: admin._id,
        title: 'Payment Slip Resubmitted',
        message: `Customer has resubmitted a payment slip for Order #${order._id.toString().slice(-6).toUpperCase()}`,
        type: 'system'
      });
    }
  } catch (err) {
    console.error(err);
  }

  res.json(order);
};
