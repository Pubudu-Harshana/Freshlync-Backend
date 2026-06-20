const nodemailer = require('nodemailer');

const transporter = nodemailer.createTransport({
  service: 'gmail',
  auth: {
    user: process.env.EMAIL_USER,
    pass: process.env.EMAIL_PASS,
  },
});

/**
 * Send a password reset email.
 * @param {string} to  - recipient email
 * @param {string} resetUrl - full reset URL with token
 */
const sendPasswordResetEmail = async (to, resetUrl) => {
  const html = `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>Reset Your Password</title>
    </head>
    <body style="margin:0;padding:0;background:#f1f5f9;font-family:'Segoe UI',Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:40px 0;">
        <tr>
          <td align="center">
            <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
              
              <!-- Header -->
              <tr>
                <td style="background:linear-gradient(135deg,#15803d,#1f9d55);padding:32px 40px;text-align:center;">
                  <div style="font-size:28px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">🥬 FreshLync</div>
                  <div style="font-size:13px;color:rgba(255,255,255,0.8);margin-top:4px;">B2B Fresh Food Marketplace</div>
                </td>
              </tr>

              <!-- Body -->
              <tr>
                <td style="padding:40px;">
                  <h1 style="font-size:22px;font-weight:700;color:#0f172a;margin:0 0 12px;">Reset Your Password</h1>
                  <p style="font-size:15px;color:#475569;line-height:1.6;margin:0 0 28px;">
                    We received a request to reset your FreshLync password. Click the button below to choose a new password. This link is valid for <strong>1 hour</strong>.
                  </p>

                  <!-- Button -->
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td align="center" style="padding:0 0 32px;">
                        <a href="${resetUrl}" style="display:inline-block;background:linear-gradient(135deg,#15803d,#1f9d55);color:#ffffff;text-decoration:none;font-weight:600;font-size:15px;padding:14px 36px;border-radius:8px;letter-spacing:0.2px;">
                          Reset My Password
                        </a>
                      </td>
                    </tr>
                  </table>

                  <p style="font-size:13px;color:#94a3b8;line-height:1.6;margin:0 0 12px;">
                    If the button doesn't work, copy and paste this link into your browser:
                  </p>
                  <p style="font-size:12px;word-break:break-all;color:#64748b;background:#f8fafc;padding:12px;border-radius:6px;border:1px solid #e2e8f0;margin:0 0 28px;">
                    ${resetUrl}
                  </p>

                  <hr style="border:none;border-top:1px solid #e2e8f0;margin:0 0 24px;" />
                  <p style="font-size:13px;color:#94a3b8;line-height:1.6;margin:0;">
                    If you didn't request a password reset, you can safely ignore this email. Your password will remain unchanged.<br/><br/>
                    — The FreshLync Team
                  </p>
                </td>
              </tr>

              <!-- Footer -->
              <tr>
                <td style="background:#f8fafc;padding:20px 40px;text-align:center;border-top:1px solid #e2e8f0;">
                  <p style="font-size:12px;color:#94a3b8;margin:0;">
                    © ${new Date().getFullYear()} FreshLync. All rights reserved.
                  </p>
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
  `;

  await transporter.sendMail({
    from: `"FreshLync" <${process.env.EMAIL_USER}>`,
    to,
    subject: 'Reset Your FreshLync Password',
    html,
  });
};

module.exports = { sendPasswordResetEmail };
