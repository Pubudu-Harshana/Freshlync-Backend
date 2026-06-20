const { GoogleGenerativeAI } = require('@google/generative-ai');

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);

const SYSTEM_PROMPT = `You are FreshLync AI, a smart and friendly assistant for FreshLync — a B2B fresh food and seafood marketplace that connects verified suppliers with buyers.

Your role is to help buyers and suppliers with:
- Finding and comparing products (seafood, fresh produce, etc.)
- Understanding pricing and minimum order quantities
- Tracking and managing orders
- Learning about the verification process for suppliers
- Navigating the FreshLync marketplace platform
- General questions about food sourcing, quality, and certifications

Guidelines:
- Be concise, professional, and friendly
- Give specific, helpful answers — avoid generic filler responses
- If asked about a specific product or price you don't have live data for, guide the user to browse the marketplace or check their dashboard
- For order status, guide users to the "My Shipments" or "Orders" section in the dashboard
- Keep responses short (2-4 sentences) unless a detailed explanation is needed
- Use bullet points for lists
- Never make up specific prices or stock levels — say you don't have live data and direct users to the marketplace
- If asked something completely unrelated to FreshLync or food/business, politely redirect back to FreshLync topics`;

// POST /api/chat
exports.chat = async (req, res) => {
  const { message, history = [] } = req.body;

  if (!message || !message.trim()) {
    return res.status(400).json({ message: 'Message is required.' });
  }

  const model = genAI.getGenerativeModel({ model: 'gemini-2.0-flash' });

  // Build conversation history for Gemini (last 10 messages max for context)
  const recentHistory = history.slice(-10);

  const geminiHistory = [
    // Inject system prompt as the first user/model exchange
    {
      role: 'user',
      parts: [{ text: SYSTEM_PROMPT }],
    },
    {
      role: 'model',
      parts: [{ text: "Understood! I'm FreshLync AI, ready to help buyers and suppliers with products, orders, pricing, and everything related to the FreshLync marketplace. How can I assist you today?" }],
    },
    // Add actual conversation history
    ...recentHistory.map(msg => ({
      role: msg.role === 'user' ? 'user' : 'model',
      parts: [{ text: msg.text }],
    })),
  ];

  const chatSession = model.startChat({ history: geminiHistory });
  const result = await chatSession.sendMessage(message.trim());
  const reply = result.response.text();

  res.json({ reply });
};
