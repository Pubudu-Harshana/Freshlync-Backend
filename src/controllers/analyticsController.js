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
    const itemSubtotal = supItems.reduce((sum, item) => sum + (item.supplierPrice !== undefined ? item.supplierPrice : item.price) * item.quantity, 0);
    
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
      const revenue = supItems.reduce((sum, item) => sum + (item.supplierPrice !== undefined ? item.supplierPrice : item.price) * item.quantity, 0);

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

// POST /api/analytics/predict (supplier, admin)
exports.predictSales = async (req, res) => {
  const { spawn } = require('child_process');
  const path = require('path');
  const { product_name, category, day_of_week, is_holiday, weather_condition } = req.body;

  if (!product_name || !category || !day_of_week || !weather_condition) {
    return res.status(400).json({ message: 'Missing required fields for prediction' });
  }

  // Path to python script
  const scriptPath = path.join(__dirname, '../../freshlync/ml_service/predict.py');

  const child = spawn('python', [scriptPath]);

  let stdoutData = '';
  let stderrData = '';

  child.stdout.on('data', (data) => {
    stdoutData += data.toString();
  });

  child.stderr.on('data', (data) => {
    stderrData += data.toString();
  });

  child.on('close', (code) => {
    if (code !== 0) {
      console.error(`Python script exited with code ${code}. Error: ${stderrData}`);
      return res.status(500).json({ message: 'Prediction service failed', error: stderrData });
    }

    try {
      const result = JSON.parse(stdoutData.trim());
      if (result.error) {
        return res.status(400).json({ message: 'Prediction error', error: result.error });
      }
      res.json(result);
    } catch (e) {
      console.error('Failed to parse prediction output:', stdoutData);
      res.status(500).json({ message: 'Invalid prediction output format' });
    }
  });

  // Write inputs as JSON to stdin
  const inputPayload = JSON.stringify({
    product_name,
    category,
    day_of_week,
    is_holiday: !!is_holiday,
    weather_condition,
  });

  child.stdin.write(inputPayload);
  child.stdin.end();
};

// GET /api/analytics/earnings  (supplier)
exports.getEarnings = async (req, res) => {
  try {
    const supplierId = req.user._id;
    const supplierIdStr = supplierId.toString();
    const FEE_RATE = 0.10; // 10% platform commission

    const orders = await Order.find({ 'items.supplier': supplierId })
      .sort({ createdAt: -1 });

    let totalEarned = 0;
    let pendingPayout = 0;
    let availablePayout = 0;
    let completedPayout = 0;
    const breakdown = [];

    orders.forEach(order => {
      const supItems = order.items.filter(
        item => item.supplier?.toString() === supplierIdStr
      );
      if (supItems.length === 0) return;

      const gross = supItems.reduce(
        (sum, item) =>
          sum + (item.supplierPrice !== undefined ? item.supplierPrice : item.price) * item.quantity,
        0
      );
      const fee = parseFloat((gross * FEE_RATE).toFixed(2));
      const net = parseFloat((gross - fee).toFixed(2));

      const supStatusEntry = order.supplierStatuses?.find(
        s => s.supplier?.toString() === supplierIdStr
      );
      const supplierStatus = supStatusEntry ? supStatusEntry.status : order.status;
      const paymentApproved = order.paymentStatus === 'Approved';

      let earningsStatus;
      if (supplierStatus === 'Delivered' && paymentApproved) {
        earningsStatus = 'Paid';
        totalEarned += net;
        completedPayout += net;
      } else if (supplierStatus === 'Delivered' && !paymentApproved) {
        earningsStatus = 'Available';
        totalEarned += net;
        availablePayout += net;
      } else if (supplierStatus === 'Cancelled') {
        earningsStatus = 'Cancelled';
      } else {
        earningsStatus = 'Pending';
        pendingPayout += net;
      }

      const dateStr = new Date(order.createdAt).toLocaleDateString('en-GB', {
        day: '2-digit', month: 'short', year: 'numeric'
      });

      breakdown.push({
        orderId: order._id.toString().slice(-8).toUpperCase(),
        date: dateStr,
        amount: parseFloat(gross.toFixed(2)),
        fee,
        net,
        status: earningsStatus,
      });
    });

    // Group paid entries into monthly payout records
    const payoutMap = {};
    breakdown
      .filter(b => b.status === 'Paid')
      .forEach(b => {
        const d = new Date(b.date);
        const key = `${d.getFullYear()}-${d.getMonth()}`;
        if (!payoutMap[key]) {
          payoutMap[key] = {
            id: `PAY-${key}`,
            date: b.date,
            amount: 0,
            method: 'Direct Deposit',
            status: 'Completed',
          };
        }
        payoutMap[key].amount += b.net;
      });

    const payouts = Object.values(payoutMap)
      .map(p => ({ ...p, amount: parseFloat(p.amount.toFixed(2)) }))
      .sort((a, b) => new Date(b.date) - new Date(a.date));

    res.json({
      revenueSummary: {
        totalEarned: parseFloat(totalEarned.toFixed(2)),
        pendingPayout: parseFloat(pendingPayout.toFixed(2)),
        availablePayout: parseFloat(availablePayout.toFixed(2)),
        completedPayout: parseFloat(completedPayout.toFixed(2)),
      },
      payouts,
      breakdown: breakdown.filter(b => b.status !== 'Cancelled'),
    });
  } catch (err) {
    console.error('getEarnings error:', err);
    res.status(500).json({ message: 'Failed to load earnings data' });
  }
};

