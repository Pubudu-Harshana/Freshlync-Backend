const Ticket = require('../models/Ticket');

// Seed default tickets if DB is empty
const seedDefaultTickets = async () => {
  const count = await Ticket.countDocuments();
  if (count === 0) {
    const defaultTickets = [
      {
        ticketId: 'TKT-101',
        title: 'Route scanner error',
        description: 'Driver cannot load map coordinates for London route.',
        creatorName: 'John Doe',
        creatorRole: 'supplier',
        status: 'Open',
        priority: 'High',
        category: 'Logistics',
        assignee: 'Jane Smith',
      },
      {
        ticketId: 'TKT-102',
        title: 'Payment payout delayed',
        description: 'Wholesale order payout not received for order ORD-A23B.',
        creatorName: 'GreenEarth Organics',
        creatorRole: 'supplier',
        status: 'In Progress',
        priority: 'Critical',
        category: 'Billing',
        assignee: 'Bob Johnson',
      },
      {
        ticketId: 'TKT-103',
        title: 'Incorrect invoice pricing',
        description: 'Platform margin markup applied incorrectly on fresh vegetables.',
        creatorName: 'SuperMart',
        creatorRole: 'buyer',
        status: 'Resolved',
        priority: 'Medium',
        category: 'Billing',
        assignee: 'Jane Smith',
      },
      {
        ticketId: 'TKT-104',
        title: 'Spoiled dairy packaging',
        description: 'Cold chain alert during transit of organic milk.',
        creatorName: 'DirectFoods',
        creatorRole: 'buyer',
        status: 'Closed',
        priority: 'High',
        category: 'Quality Assurance',
        assignee: 'Jane Smith',
      },
    ];
    await Ticket.insertMany(defaultTickets);
  }
};

// GET /api/tickets
exports.getTickets = async (req, res) => {
  await seedDefaultTickets();

  const { status, category } = req.query;
  const query = {};

  // If not admin, restrict to tickets created by user
  if (req.user && req.user.role !== 'admin') {
    query.creator = req.user._id;
  }

  if (status && status !== 'All') {
    query.status = status;
  }
  if (category && category !== 'All') {
    query.category = category;
  }

  const tickets = await Ticket.find(query).sort({ createdAt: -1 });

  // Map to frontend expected shape
  const formatted = tickets.map(t => ({
    id: t.ticketId,
    mongoId: t._id,
    title: t.title,
    desc: t.description,
    creator: t.creatorName,
    role: t.creatorRole,
    status: t.status,
    priority: t.priority,
    date: new Date(t.createdAt).toISOString().split('T')[0],
    category: t.category,
    assignee: t.assignee,
  }));

  res.json(formatted);
};

// POST /api/tickets
exports.createTicket = async (req, res) => {
  const { title, description, category, priority } = req.body;

  if (!title || !description) {
    return res.status(400).json({ message: 'Title and description are required' });
  }

  const count = await Ticket.countDocuments();
  const nextNum = 101 + count;
  const ticketId = `TKT-${nextNum}`;

  const ticket = await Ticket.create({
    ticketId,
    title,
    description,
    creatorName: req.user ? req.user.name : 'System User',
    creatorRole: req.user ? req.user.role : 'supplier',
    creator: req.user ? req.user._id : undefined,
    category: category || 'General',
    priority: priority || 'Medium',
    status: 'Open',
    assignee: 'Unassigned',
  });

  res.status(201).json({
    id: ticket.ticketId,
    mongoId: ticket._id,
    title: ticket.title,
    desc: ticket.description,
    creator: ticket.creatorName,
    role: ticket.creatorRole,
    status: ticket.status,
    priority: ticket.priority,
    date: new Date(ticket.createdAt).toISOString().split('T')[0],
    category: ticket.category,
    assignee: ticket.assignee,
  });
};

// PUT /api/tickets/:id
exports.updateTicket = async (req, res) => {
  const { id } = req.params; // ticketId e.g. TKT-101 or _id
  const { status, assignee, priority, category } = req.body;

  let ticket = await Ticket.findOne({ $or: [{ ticketId: id }, { _id: id }] });
  if (!ticket) {
    return res.status(404).json({ message: 'Ticket not found' });
  }

  if (status !== undefined) ticket.status = status;
  if (assignee !== undefined) ticket.assignee = assignee;
  if (priority !== undefined) ticket.priority = priority;
  if (category !== undefined) ticket.category = category;

  await ticket.save();

  res.json({
    id: ticket.ticketId,
    mongoId: ticket._id,
    title: ticket.title,
    desc: ticket.description,
    creator: ticket.creatorName,
    role: ticket.creatorRole,
    status: ticket.status,
    priority: ticket.priority,
    date: new Date(ticket.createdAt).toISOString().split('T')[0],
    category: ticket.category,
    assignee: ticket.assignee,
  });
};
