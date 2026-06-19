const Order = require('../models/Order');
const Product = require('../models/Product');

// GET /api/orders
exports.getOrders = async (req, res) => {
  const { status, page = 1, limit = 20 } = req.query;
  const query = {};

  // Role-based filtering
  if (req.user.role === 'buyer') {
    query.buyer = req.user._id;
  } else if (req.user.role === 'supplier') {
    query['items.supplier'] = req.user._id;
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
      o.total = o.items.reduce((sum, item) => sum + item.price * item.quantity, 0);
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

    const o = order.toObject();
    const supStatusEntry = o.supplierStatuses?.find(s => s.supplier?.toString() === supplierIdStr);
    o.status = supStatusEntry ? supStatusEntry.status : o.status;
    o.items = o.items.filter(item => item.supplier?.toString() === supplierIdStr);
    o.total = o.items.reduce((sum, item) => sum + item.price * item.quantity, 0);

    return res.json(o);
  }

  res.json(order);
};

// POST /api/orders  (buyer places order)
exports.placeOrder = async (req, res) => {
  const { items, delivery, paymentMethod, notes } = req.body;

  if (!items || items.length === 0) {
    return res.status(400).json({ message: 'No items in order' });
  }

  // Calculate total
  const total = items.reduce((sum, item) => sum + item.price * item.quantity, 0);

  // Enrich items with supplier info and find unique suppliers
  const enrichedItems = [];
  const uniqueSuppliersSet = new Set();

  for (const item of items) {
    if (item.product) {
      const prod = await Product.findById(item.product).populate('supplier');
      if (prod) {
        const supIdStr = prod.supplier?._id?.toString() || prod.supplier?.toString();
        enrichedItems.push({
          ...item,
          supplier: prod.supplier?._id || prod.supplier,
          supplierName: prod.supplierName || prod.supplier?.company || prod.supplier?.name || 'Unknown Supplier'
        });
        if (supIdStr) {
          uniqueSuppliersSet.add(supIdStr);
        }
      } else {
        enrichedItems.push(item);
      }
    } else {
      enrichedItems.push(item);
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
    supplierStatuses
  });

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
