const nodemailer = require('nodemailer');
const jwt = require('jsonwebtoken');
const User = require('../models/User');

const transporter = nodemailer.createTransport({
  service: 'gmail',
  auth: {
    user: process.env.EMAIL_USER,
    pass: process.env.EMAIL_PASS,
  },
});

/**
 * Generate a cryptographically secure token for approval actions.
 */
const generateActionToken = (userId, action) => {
  return jwt.sign(
    { userId, action },
    process.env.JWT_SECRET,
    { expiresIn: '24h' }
  );
};

/**
 * Sends notification emails to all platform administrators when a new supplier registers.
 */
const sendSupplierRegistrationAdminEmail = async (supplier) => {
  const admins = await User.find({ role: 'admin' }).select('email');
  if (!admins || admins.length === 0) return;

  const clientUrl = process.env.CLIENT_URL || 'http://localhost:5173';
  const backendUrl = process.env.VITE_API_URL 
    ? process.env.VITE_API_URL 
    : 'http://localhost:5000/api';

  const approveToken = generateActionToken(supplier._id.toString(), 'approve');
  const rejectToken = generateActionToken(supplier._id.toString(), 'reject');

  const approveUrl = `${backendUrl}/auth/quick-action?token=${approveToken}`;
  const rejectUrl = `${backendUrl}/auth/quick-action?token=${rejectToken}`;
  const dashboardUrl = `${clientUrl}/admin/verification?supplierId=${supplier._id}`;

  const html = `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>New Supplier Registration</title>
    </head>
    <body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:30px 0;">
        <tr>
          <td align="center">
            <table width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,0.05);border:1px solid #e2e8f0;">
              
              <!-- Header -->
              <tr>
                <td style="background:linear-gradient(135deg,#047857,#065f46);padding:30px 40px;text-align:center;">
                  <div style="font-size:24px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">🥬 FreshLync</div>
                  <div style="font-size:12px;color:rgba(255,255,255,0.85);margin-top:4px;text-transform:uppercase;letter-spacing:0.05em;font-weight:700;">Admin Alerts Panel</div>
                </td>
              </tr>

              <!-- Body -->
              <tr>
                <td style="padding:40px;">
                  <span style="display:inline-block;background:#FEF3C7;color:#D97706;padding:4px 12px;border-radius:999px;font-size:11px;font-weight:700;text-transform:uppercase;margin-bottom:16px;letter-spacing:0.04em;">Pending Supplier Review</span>
                  <h1 style="font-size:20px;font-weight:800;color:#0f172a;margin:0 0 12px;letter-spacing:-0.3px;">New Supplier Account Created</h1>
                  <p style="font-size:14px;color:#475569;line-height:1.6;margin:0 0 24px;">
                    A new supplier has registered on the FreshLync platform and requires verification before they can post inventory.
                  </p>

                  <!-- Details Table -->
                  <div style="background:#f1f5f9;border-radius:12px;padding:20px;margin-bottom:30px;border:1px solid #e2e8f0;">
                    <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;color:#334155;line-height:1.5;">
                      <tr>
                        <td width="35%" style="font-weight:600;padding-bottom:10px;color:#64748b;">Supplier Name:</td>
                        <td style="padding-bottom:10px;font-weight:700;color:#0f172a;">${supplier.name}</td>
                      </tr>
                      <tr>
                        <td style="font-weight:600;padding-bottom:10px;color:#64748b;">Company Name:</td>
                        <td style="padding-bottom:10px;font-weight:700;color:#0f172a;">${supplier.company || '—'}</td>
                      </tr>
                      <tr>
                        <td style="font-weight:600;color:#64748b;">Email Address:</td>
                        <td style="font-weight:700;color:#0f172a;">${supplier.email}</td>
                      </tr>
                    </table>
                  </div>

                  <!-- Quick Action Buttons -->
                  <p style="font-size:13px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:0.03em;margin-bottom:12px;text-align:center;">Instant Phone Approval Actions:</p>
                  <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
                    <tr>
                      <td align="center" style="padding:10px 0;">
                        <a href="${approveUrl}" style="display:inline-block;background:#059669;color:#ffffff;text-decoration:none;font-weight:700;font-size:14px;padding:12px 30px;border-radius:8px;box-shadow:0 4px 12px rgba(5,150,105,0.2);margin-right:10px;">
                          Approve Supplier ✅
                        </a>
                        <a href="${rejectUrl}" style="display:inline-block;background:#dc2626;color:#ffffff;text-decoration:none;font-weight:700;font-size:14px;padding:12px 30px;border-radius:8px;box-shadow:0 4px 12px rgba(220,38,38,0.2);">
                          Reject Account ❌
                        </a>
                      </td>
                    </tr>
                  </table>

                  <hr style="border:none;border-top:1px solid #e2e8f0;margin:0 0 24px;" />
                  
                  <div style="text-align:center;">
                    <a href="${dashboardUrl}" style="color:#047857;font-size:13px;font-weight:700;text-decoration:underline;">
                      Open Full Admin Verification Panel →
                    </a>
                  </div>
                </td>
              </tr>

              <!-- Footer -->
              <tr>
                <td style="background:#f8fafc;padding:20px 40px;text-align:center;border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8;">
                  This is a secure system notification. Approval tokens expire in 24 hours. © ${new Date().getFullYear()} FreshLync.
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
  `;

  for (const admin of admins) {
    try {
      await transporter.sendMail({
        from: `"FreshLync" <${process.env.EMAIL_USER}>`,
        to: admin.email,
        subject: `[ALERT] New Supplier Registration: ${supplier.company || supplier.name}`,
        html,
      });
    } catch (err) {
      console.error(`Failed to send supplier registration email to ${admin.email}:`, err.message);
    }
  }
};

/**
 * Sends notification emails to all platform administrators when a supplier submits verification documents.
 */
const sendSupplierVerificationAdminEmail = async (supplier) => {
  const admins = await User.find({ role: 'admin' }).select('email');
  if (!admins || admins.length === 0) return;

  const clientUrl = process.env.CLIENT_URL || 'http://localhost:5173';
  const backendUrl = process.env.VITE_API_URL 
    ? process.env.VITE_API_URL 
    : 'http://localhost:5000/api';

  const approveToken = generateActionToken(supplier._id.toString(), 'approve');
  const rejectToken = generateActionToken(supplier._id.toString(), 'reject');

  const approveUrl = `${backendUrl}/auth/quick-action?token=${approveToken}`;
  const rejectUrl = `${backendUrl}/auth/quick-action?token=${rejectToken}`;
  const dashboardUrl = `${clientUrl}/admin/verification?supplierId=${supplier._id}`;

  const html = `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>Supplier Business Documents Submitted</title>
    </head>
    <body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:30px 0;">
        <tr>
          <td align="center">
            <table width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,0.05);border:1px solid #e2e8f0;">
              
              <!-- Header -->
              <tr>
                <td style="background:linear-gradient(135deg,#047857,#065f46);padding:30px 40px;text-align:center;">
                  <div style="font-size:24px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">🥬 FreshLync</div>
                  <div style="font-size:12px;color:rgba(255,255,255,0.85);margin-top:4px;text-transform:uppercase;letter-spacing:0.05em;font-weight:700;">Admin Alerts Panel</div>
                </td>
              </tr>

              <!-- Body -->
              <tr>
                <td style="padding:40px;">
                  <span style="display:inline-block;background:#DBEAFE;color:#1E40AF;padding:4px 12px;border-radius:999px;font-size:11px;font-weight:700;text-transform:uppercase;margin-bottom:16px;letter-spacing:0.04em;">Verification Review Required</span>
                  <h1 style="font-size:20px;font-weight:800;color:#0f172a;margin:0 0 12px;letter-spacing:-0.3px;">Business Documents Uploaded</h1>
                  <p style="font-size:14px;color:#475569;line-height:1.6;margin:0 0 24px;">
                    <strong>${supplier.company || supplier.name}</strong> has submitted their corporate details and tax files for verification.
                  </p>

                  <!-- Details Table -->
                  <div style="background:#f1f5f9;border-radius:12px;padding:20px;margin-bottom:30px;border:1px solid #e2e8f0;">
                    <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;color:#334155;line-height:1.5;">
                      <tr>
                        <td width="35%" style="font-weight:600;padding-bottom:10px;color:#64748b;">Registered Name:</td>
                        <td style="padding-bottom:10px;font-weight:700;color:#0f172a;">${supplier.verificationDetails?.registeredBusinessName || supplier.company || '—'}</td>
                      </tr>
                      <tr>
                        <td style="font-weight:600;padding-bottom:10px;color:#64748b;">Reg. Number:</td>
                        <td style="padding-bottom:10px;font-weight:700;color:#0f172a;">${supplier.verificationDetails?.businessRegistrationNumber || '—'}</td>
                      </tr>
                      <tr>
                        <td style="font-weight:600;padding-bottom:10px;color:#64748b;">Tax ID:</td>
                        <td style="padding-bottom:10px;font-weight:700;color:#0f172a;">${supplier.verificationDetails?.taxId || '—'}</td>
                      </tr>
                      <tr>
                        <td style="font-weight:600;color:#64748b;">Documents:</td>
                        <td style="font-weight:700;color:#0f172a;">${supplier.verificationDetails?.documents?.length || 0} file(s) uploaded</td>
                      </tr>
                    </table>
                  </div>

                  <!-- Quick Action Buttons -->
                  <p style="font-size:13px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:0.03em;margin-bottom:12px;text-align:center;">Instant Phone Approval Actions:</p>
                  <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
                    <tr>
                      <td align="center" style="padding:10px 0;">
                        <a href="${approveUrl}" style="display:inline-block;background:#059669;color:#ffffff;text-decoration:none;font-weight:700;font-size:14px;padding:12px 30px;border-radius:8px;box-shadow:0 4px 12px rgba(5,150,105,0.2);margin-right:10px;">
                          Approve Verification ✅
                        </a>
                        <a href="${rejectUrl}" style="display:inline-block;background:#dc2626;color:#ffffff;text-decoration:none;font-weight:700;font-size:14px;padding:12px 30px;border-radius:8px;box-shadow:0 4px 12px rgba(220,38,38,0.2);">
                          Reject Request ❌
                        </a>
                      </td>
                    </tr>
                  </table>

                  <hr style="border:none;border-top:1px solid #e2e8f0;margin:0 0 24px;" />
                  
                  <div style="text-align:center;">
                    <a href="${dashboardUrl}" style="color:#047857;font-size:13px;font-weight:700;text-decoration:underline;">
                      Open Verification Panel to View Uploaded Files →
                    </a>
                  </div>
                </td>
              </tr>

              <!-- Footer -->
              <tr>
                <td style="background:#f8fafc;padding:20px 40px;text-align:center;border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8;">
                  This is a secure system notification. Approval tokens expire in 24 hours. © ${new Date().getFullYear()} FreshLync.
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
  `;

  for (const admin of admins) {
    try {
      await transporter.sendMail({
        from: `"FreshLync" <${process.env.EMAIL_USER}>`,
        to: admin.email,
        subject: `[ALERT] Verification Docs Submitted: ${supplier.company || supplier.name}`,
        html,
      });
    } catch (err) {
      console.error(`Failed to send supplier verification email to ${admin.email}:`, err.message);
    }
  }
};

module.exports = {
  sendSupplierRegistrationAdminEmail,
  sendSupplierVerificationAdminEmail,
};
