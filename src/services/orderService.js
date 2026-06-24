/**
 * Order database service for the FreshLync Chatbot.
 * Handles order lookup, security checks, and tracking timeline construction.
 */

const Order = require('../models/Order');
const mongoose = require('mongoose');

/**
 * Retrieves specific order details with strict security ownership checks.
 * @param {string} orderId - 24-char ObjectId or 8-char suffix of ObjectId
 * @param {string} userId - ID of the authenticated user
 * @param {string} userRole - Role of the authenticated user ('buyer', 'supplier', 'admin')
 * @returns {object} The structured order details
 * @throws {Error} If unauthorized (403) or order not found (404)
 */
async function getOrderDetails(orderId, userId, userRole) {
  if (!orderId) {
    throw new Error('Order ID is required.');
  }

  let order = null;

  // Case 1: Full 24-character ObjectId
  if (orderId.length === 24 && mongoose.Types.ObjectId.isValid(orderId)) {
    order = await Order.findById(orderId).lean();
  } else {
    // Case 2: Suffix search (e.g. 8-char display ID)
    // Since _id is an ObjectId, we can't run $regex on it directly.
    // Instead, we query the user's recent orders and match the suffix in memory.
    const query = userRole === 'supplier'
      ? { 'items.supplier': userId }
      : userRole === 'admin' ? {} : { buyer: userId };

    const recentOrders = await Order.find(query)
      .sort({ createdAt: -1 })
      .limit(50)
      .lean();

    order = recentOrders.find(o => 
      o._id.toString().toUpperCase().endsWith(orderId.toUpperCase()) ||
      o._id.toString().toUpperCase().startsWith(orderId.toUpperCase())
    );
  }

  if (!order) {
    const err = new Error('Order not found.');
    err.status = 404;
    throw err;
  }

  // ── STRICT SECURITY OWNERSHIP CHECK ──
  let isAuthorized = false;

  if (userRole === 'admin') {
    isAuthorized = true;
  } else if (userRole === 'buyer') {
    // Buyer must own the order
    isAuthorized = order.buyer.toString() === userId.toString();
  } else if (userRole === 'supplier') {
    // Supplier must be the supplier of at least one item in the order
    isAuthorized = order.items.some(item => 
      item.supplier && item.supplier.toString() === userId.toString()
    );
  }

  if (!isAuthorized) {
    const err = new Error('You are not authorised to view this order.');
    err.status = 403;
    throw err;
  }

  // ── CONSTRUCT TIMELINE ──
  // A standard B2B timeline based on paymentStatus and order status
  const timeline = [
    { status: 'Pending', label: 'Order Placed', completed: true, time: order.createdAt }
  ];

  if (order.paymentMethod === 'bank') {
    const isVerified = order.paymentStatus === 'Approved';
    const isRejected = order.paymentStatus === 'Rejected';
    timeline.push({
      status: 'Pending Payment Verification',
      label: isRejected ? 'Payment Rejected' : isVerified ? 'Payment Verified' : 'Awaiting Payment Verification',
      completed: isVerified,
      time: isVerified ? order.updatedAt : null,
      error: isRejected
    });
  }

  const inTransit = ['In Transit', 'Delivered'].includes(order.status);
  timeline.push({
    status: 'In Transit',
    label: 'In Transit',
    completed: inTransit,
    time: inTransit && order.status === 'In Transit' ? order.updatedAt : null
  });

  const delivered = order.status === 'Delivered';
  timeline.push({
    status: 'Delivered',
    label: 'Delivered',
    completed: delivered,
    time: delivered ? order.updatedAt : null
  });

  if (order.status === 'Cancelled') {
    timeline.push({
      status: 'Cancelled',
      label: 'Order Cancelled',
      completed: true,
      time: order.updatedAt,
      error: true
    });
  }

  // Return structured data mapping the schema perfectly
  return {
    orderId: order._id.toString(),
    status: order.status,
    paymentMethod: order.paymentMethod,
    paymentStatus: order.paymentStatus,
    total: order.total,
    createdAt: order.createdAt,
    items: order.items.map(item => ({
      name: item.name,
      price: item.price,
      quantity: item.quantity,
      unit: item.unit || 'kg',
      supplierName: item.supplierName || ''
    })),
    delivery: {
      firstName: order.delivery?.firstName || '',
      lastName: order.delivery?.lastName || '',
      company: order.delivery?.company || '',
      address: order.delivery?.address || '',
      city: order.delivery?.city || '',
      postcode: order.delivery?.postcode || '',
      country: order.delivery?.country || ''
    },
    timeline
  };
}

/**
 * Retrieves recent orders for a user.
 * @param {string} userId 
 * @param {string} userRole 
 * @returns {array} list of recent orders
 */
async function getRecentOrders(userId, userRole) {
  const query = userRole === 'supplier'
    ? { 'items.supplier': userId }
    : userRole === 'admin' ? {} : { buyer: userId };

  const orders = await Order.find(query)
    .sort({ createdAt: -1 })
    .limit(5)
    .select('_id status total createdAt paymentStatus items')
    .lean();

  return orders.map(o => ({
    orderId: o._id.toString(),
    status: o.status,
    total: o.total,
    createdAt: o.createdAt,
    paymentStatus: o.paymentStatus,
    itemCount: o.items ? o.items.length : 0
  }));
}

module.exports = {
  getOrderDetails,
  getRecentOrders
};
