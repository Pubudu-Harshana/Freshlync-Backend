/**
 * Billing Controller for FreshLync.
 * Manages B2B credit line configuration, real-time invoice calculations,
 * invoice payments, and credit limit increase requests using real MongoDB data.
 */

const Invoice = require('../models/Invoice');
const User = require('../models/User');

/**
 * Retrieves B2B credit line summary and invoices.
 * Automatically seeds initial B2B demo data for new users to guarantee an active experience.
 * GET /api/billing
 */
exports.getBillingData = async (req, res) => {
  const userId = req.user._id;

  try {
    // 1. Fetch user's creditLimit (default: 100000 if not set)
    const user = await User.findById(userId);
    const creditLimit = user.creditLimit || 100000;

    // 2. Fetch user's invoices
    let invoices = await Invoice.find({ buyer: userId })
      .sort({ issueDate: -1 })
      .lean();

    // 3. Auto-seed 4 standard B2B invoices if the user has 0 invoices.
    // This maintains the expected demo layout but makes it 100% real and interactive in MongoDB!
    if (invoices.length === 0) {
      const suffix = userId.toString().slice(-4).toUpperCase();
      const seedInvoices = [
        {
          buyer: userId,
          invoiceNumber: `INV-2026-001-${suffix}`,
          amount: 8450.00,
          status: 'Unpaid',
          issueDate: new Date('2026-06-10'),
          dueDate: new Date('2026-07-10')
        },
        {
          buyer: userId,
          invoiceNumber: `INV-2026-002-${suffix}`,
          amount: 12100.00,
          status: 'Paid',
          issueDate: new Date('2026-06-05'),
          dueDate: new Date('2026-07-05')
        },
        {
          buyer: userId,
          invoiceNumber: `INV-2026-003-${suffix}`,
          amount: 7000.00,
          status: 'Overdue',
          issueDate: new Date('2026-05-18'),
          dueDate: new Date('2026-06-15')
        },
        {
          buyer: userId,
          invoiceNumber: `INV-2026-004-${suffix}`,
          amount: 5900.00,
          status: 'Paid',
          issueDate: new Date('2026-05-01'),
          dueDate: new Date('2026-06-01')
        }
      ];

      await Invoice.insertMany(seedInvoices);
      
      // Re-fetch newly seeded invoices
      invoices = await Invoice.find({ buyer: userId })
        .sort({ issueDate: -1 })
        .lean();
    }

    // 4. Calculate outstanding balance dynamically (sum of Unpaid & Overdue)
    let outstanding = 0;
    invoices.forEach(inv => {
      if (inv.status === 'Unpaid' || inv.status === 'Overdue') {
        outstanding += inv.amount;
      }
    });

    // 5. Calculate available credit
    const availableCredit = Math.max(0, creditLimit - outstanding);

    // 6. Find the due date of the oldest unpaid invoice
    let nextPaymentDate = 'July 10, 2026'; // fallback/default
    const unpaidInvoices = invoices
      .filter(inv => inv.status === 'Unpaid' || inv.status === 'Overdue')
      .sort((a, b) => new Date(a.dueDate) - new Date(b.dueDate)); // oldest first

    if (unpaidInvoices.length > 0) {
      nextPaymentDate = new Date(unpaidInvoices[0].dueDate).toLocaleDateString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric'
      });
    }

    res.json({
      success: true,
      creditLimit,
      outstanding,
      availableCredit,
      nextPaymentDate,
      invoices: invoices.map(inv => ({
        id: inv._id.toString(),
        invoiceNumber: inv.invoiceNumber,
        date: inv.issueDate,
        dueDate: inv.dueDate,
        amount: inv.amount,
        status: inv.status
      }))
    });

  } catch (err) {
    console.error('Error fetching billing data:', err.message);
    res.status(500).json({ success: false, message: 'Failed to retrieve billing dashboard.' });
  }
};

/**
 * Pays a B2B invoice.
 * POST /api/billing/invoices/:id/pay
 */
exports.payInvoice = async (req, res) => {
  const invoiceId = req.params.id;
  const userId = req.user._id;

  try {
    const invoice = await Invoice.findById(invoiceId);
    if (!invoice) {
      return res.status(404).json({ success: false, message: 'Invoice not found.' });
    }

    // Security: ensure the invoice belongs to the logged-in buyer
    if (invoice.buyer.toString() !== userId.toString()) {
      return res.status(403).json({ success: false, message: 'Not authorised to pay this invoice.' });
    }

    if (invoice.status === 'Paid') {
      return res.status(400).json({ success: false, message: 'Invoice is already paid.' });
    }

    // Update status
    invoice.status = 'Paid';
    await invoice.save();

    res.json({
      success: true,
      message: `Invoice ${invoice.invoiceNumber} paid successfully!`,
      invoice: {
        id: invoice._id.toString(),
        invoiceNumber: invoice.invoiceNumber,
        amount: invoice.amount,
        status: invoice.status
      }
    });

  } catch (err) {
    console.error('Error paying invoice:', err.message);
    res.status(500).json({ success: false, message: 'Payment processing failed.' });
  }
};

/**
 * Requests an increase in the B2B credit limit.
 * POST /api/billing/credit-request
 */
exports.requestCreditIncrease = async (req, res) => {
  const userId = req.user._id;
  const { requestAmount } = req.body;

  if (!requestAmount || isNaN(requestAmount) || parseFloat(requestAmount) <= 0) {
    return res.status(400).json({ success: false, message: 'Please enter a valid target credit limit.' });
  }

  try {
    const user = await User.findById(userId);
    const targetAmount = parseFloat(requestAmount);

    if (targetAmount <= user.creditLimit) {
      return res.status(400).json({
        success: false,
        message: 'Please enter an amount higher than your current credit limit.'
      });
    }

    // Platform logic automatically approves credit line upgrades
    user.creditLimit = targetAmount;
    await user.save();

    res.json({
      success: true,
      message: `Credit limit increase approved! New limit: £${targetAmount.toLocaleString()}`,
      creditLimit: user.creditLimit
    });

  } catch (err) {
    console.error('Error upgrading credit limit:', err.message);
    res.status(500).json({ success: false, message: 'Credit request processing failed.' });
  }
};
