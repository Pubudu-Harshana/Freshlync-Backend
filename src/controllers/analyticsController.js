const Order = require('../models/Order');
const Product = require('../models/Product');

// GET /api/analytics/summary  (supplier)
exports.getSummary = async (req, res) => {
  const supplierId = req.user._id;
  const supplierIdStr = supplierId.toString();

  // Find all orders that have items belonging to this supplier
  const orders = await Order.find({ 'items.supplier': supplierId });

  let totalRevenue = 0;
  let totalOrders = orders.length;
  let deliveredOrders = 0;
  let orderValuesSum = 0;

  orders.forEach(order => {
    // filter items belonging to this supplier
    const supItems = order.items.filter(item => item.supplier?.toString() === supplierIdStr);
    const itemSubtotal = supItems.reduce((sum, item) => sum + item.price * item.quantity, 0);
    
    // get supplier specific status
    const supStatusEntry = order.supplierStatuses?.find(s => s.supplier?.toString() === supplierIdStr);
    const status = supStatusEntry ? supStatusEntry.status : order.status;

    if (status === 'Delivered') {
      totalRevenue += itemSubtotal;
      deliveredOrders++;
    }
    orderValuesSum += itemSubtotal;
  });

  const lowStockCount = await Product.countDocuments({
    supplier: supplierId,
    stock: { $gt: 0, $lt: 50 },
  });

  res.json({
    totalRevenue,
    totalOrders,
    deliveredOrders,
    fulfillmentRate: totalOrders > 0 ? ((deliveredOrders / totalOrders) * 100).toFixed(1) : 0,
    avgOrderValue: totalOrders > 0 ? (orderValuesSum / totalOrders).toFixed(2) : 0,
    lowStockCount,
  });
};

// GET /api/analytics/chart  (supplier — monthly revenue last 6 months)
exports.getChartData = async (req, res) => {
  const sixMonthsAgo = new Date();
  sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 5);
  sixMonthsAgo.setDate(1);

  const supplierIdStr = req.user._id.toString();

  const orders = await Order.find({
    'items.supplier': req.user._id,
    createdAt: { $gte: sixMonthsAgo }
  });

  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  
  // Group by year and month
  const grouped = {};
  orders.forEach(order => {
    const supStatusEntry = order.supplierStatuses?.find(s => s.supplier?.toString() === supplierIdStr);
    const status = supStatusEntry ? supStatusEntry.status : order.status;

    if (status === 'Delivered') {
      const date = new Date(order.createdAt);
      const year = date.getFullYear();
      const month = date.getMonth(); // 0-indexed
      const key = `${year}-${month}`;
      
      const supItems = order.items.filter(item => item.supplier?.toString() === supplierIdStr);
      const revenue = supItems.reduce((sum, item) => sum + item.price * item.quantity, 0);

      if (!grouped[key]) {
        grouped[key] = { year, month, revenue: 0, orders: 0 };
      }
      grouped[key].revenue += revenue;
      grouped[key].orders += 1;
    }
  });

  // Sort and format
  const chart = Object.values(grouped)
    .sort((a, b) => a.year - b.year || a.month - b.month)
    .map(d => ({
      month: months[d.month],
      revenue: d.revenue,
      orders: d.orders,
    }));

  res.json(chart);
};
