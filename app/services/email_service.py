"""
Email notification service.

All functions are fire-and-forget — they swallow send errors and log them
so a mail failure never breaks the core order flow.
"""
import traceback
from flask import current_app, render_template_string
from app.extensions import mail

try:
    from flask_mail import Message as MailMessage
except ImportError:
    MailMessage = None


def _send(subject, recipients, html_body):
    """Internal helper — sends a mail and swallows any exception."""
    if MailMessage is None:
        current_app.logger.warning('Flask-Mail not installed; skipping email.')
        return
    try:
        msg = MailMessage(
            subject=subject,
            recipients=recipients if isinstance(recipients, list) else [recipients],
            html=html_body,
            sender=current_app.config.get('MAIL_DEFAULT_SENDER', 'noreply@tailorapp.com'),
        )
        mail.send(msg)
    except Exception:
        current_app.logger.error('Email send failed:\n' + traceback.format_exc())


# ── Templates (inline for portability; move to files/app/templates/email/ later) ──

_BASE = """
<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:24px;border:1px solid #e0e0e0;border-radius:8px;">
  <div style="background:#6f42c1;padding:16px;border-radius:6px 6px 0 0;text-align:center;">
    <h2 style="color:#fff;margin:0;">✂️ TailorApp</h2>
  </div>
  <div style="padding:24px;">
    {body}
  </div>
  <div style="text-align:center;padding:12px;font-size:12px;color:#999;">
    © 2026 TailorApp · You received this because you have an account with us.
  </div>
</div>
"""


def _wrap(body_html):
    return _BASE.format(body=body_html)


# ── Order notifications ────────────────────────────────────────────────────────

def send_order_placed(order):
    html = _wrap(f"""
      <h3>Order Placed Successfully 🎉</h3>
      <p>Hi <strong>{order.customer.name}</strong>,</p>
      <p>Your order <strong>#{order.order_number}</strong> has been placed and is awaiting tailor confirmation.</p>
      <p><strong>Design:</strong> {order.display_design_name()}<br>
         <strong>Amount:</strong> ₹{order.payable_amount():,.0f}</p>
      <p>We'll notify you as soon as the tailor accepts your order.</p>
    """)
    _send(f'Order #{order.order_number} Placed — TailorApp', order.customer.email, html)


def send_order_accepted(order):
    eta = order.eta_date() or f'{order.estimated_days} days'
    html = _wrap(f"""
      <h3>Your Order Has Been Accepted ✅</h3>
      <p>Hi <strong>{order.customer.name}</strong>,</p>
      <p>Great news! <strong>{order.tailor.shop_name}</strong> has accepted your order
         <strong>#{order.order_number}</strong>.</p>
      <p><strong>Estimated Ready By:</strong> {eta}</p>
      <p>A Style Agent will be in touch to collect your fabric.</p>
    """)
    _send(f'Order #{order.order_number} Accepted — TailorApp', order.customer.email, html)


def send_order_ready(order):
    html = _wrap(f"""
      <h3>Your Order is Ready for Delivery 🚀</h3>
      <p>Hi <strong>{order.customer.name}</strong>,</p>
      <p>Your order <strong>#{order.order_number}</strong> has been stitched and is ready!</p>
      <p>A Style Agent will deliver it to you shortly.</p>
    """)
    _send(f'Order #{order.order_number} Ready — TailorApp', order.customer.email, html)


def send_order_delivered(order):
    html = _wrap(f"""
      <h3>Order Delivered! 🎊</h3>
      <p>Hi <strong>{order.customer.name}</strong>,</p>
      <p>Your order <strong>#{order.order_number}</strong> has been delivered.</p>
      <p>We'd love your feedback — please leave a review in the app.</p>
    """)
    _send(f'Order #{order.order_number} Delivered — TailorApp', order.customer.email, html)


# ── Appointment notifications ──────────────────────────────────────────────────

def send_appointment_confirmed(appointment):
    html = _wrap(f"""
      <h3>Appointment Confirmed 📅</h3>
      <p>Hi <strong>{appointment.customer.name}</strong>,</p>
      <p>Your Style Agent appointment is confirmed:</p>
      <p><strong>Date & Time:</strong> {appointment.display_datetime()}<br>
         <strong>Service:</strong> {appointment.service_label()}<br>
         <strong>Address:</strong> {appointment.customer_address}</p>
      <p>Our Style Agent will arrive within the selected time window.</p>
    """)
    _send('Appointment Confirmed — TailorApp', appointment.customer.email, html)


def send_appointment_completed(appointment):
    html = _wrap(f"""
      <h3>Appointment Completed ✅</h3>
      <p>Hi <strong>{appointment.customer.name}</strong>,</p>
      <p>Your Style Agent visit on <strong>{appointment.display_datetime()}</strong> is complete.</p>
      <p>Measurements / fabric have been recorded. Your order will be processed shortly.</p>
    """)
    _send('Appointment Completed — TailorApp', appointment.customer.email, html)


# ── Payment notifications ──────────────────────────────────────────────────────

def send_payment_success(order, transaction):
    html = _wrap(f"""
      <h3>Payment Successful 💳</h3>
      <p>Hi <strong>{order.customer.name}</strong>,</p>
      <p>Payment of <strong>₹{transaction.amount:,.0f}</strong> for order
         <strong>#{order.order_number}</strong> was received successfully.</p>
      <p><strong>Transaction Ref:</strong> {transaction.transaction_ref}</p>
    """)
    _send(f'Payment Received for #{order.order_number} — TailorApp',
          order.customer.email, html)


def send_payment_failed(order, transaction):
    html = _wrap(f"""
      <h3>Payment Failed ❌</h3>
      <p>Hi <strong>{order.customer.name}</strong>,</p>
      <p>Unfortunately your payment of <strong>₹{transaction.amount:,.0f}</strong>
         for order <strong>#{order.order_number}</strong> could not be processed.</p>
      <p><strong>Reason:</strong> {transaction.failure_reason or 'Unknown error'}</p>
      <p>Please retry payment from the order detail page.</p>
    """)
    _send(f'Payment Failed for #{order.order_number} — TailorApp',
          order.customer.email, html)


def send_refund_initiated(order, amount):
    html = _wrap(f"""
      <h3>Refund Initiated 💸</h3>
      <p>Hi <strong>{order.customer.name}</strong>,</p>
      <p>A refund of <strong>₹{amount:,.0f}</strong> for order
         <strong>#{order.order_number}</strong> has been initiated.</p>
      <p>It will reflect in your account within 5-7 business days.</p>
    """)
    _send(f'Refund Initiated for #{order.order_number} — TailorApp',
          order.customer.email, html)


# ── Account approval notifications ────────────────────────────────────────────

def send_account_approved(user):
    role_label = {'tailor': 'Tailor', 'delivery': 'Delivery Agent'}.get(user.role, user.role.title())
    html = _wrap(f"""
      <h3>Your Account Has Been Approved ✅</h3>
      <p>Hi <strong>{user.name}</strong>,</p>
      <p>Great news! Your <strong>{role_label}</strong> registration on TailorApp has been approved.</p>
      <p>You can now log in and start using the platform.</p>
      <p style="text-align:center;margin-top:24px;">
        <a href="#" style="background:#6f42c1;color:#fff;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:bold;">
          Log In Now
        </a>
      </p>
    """)
    _send('Your TailorApp Account is Approved!', user.email, html)


def send_account_rejected(user):
    role_label = {'tailor': 'Tailor', 'delivery': 'Delivery Agent'}.get(user.role, user.role.title())
    html = _wrap(f"""
      <h3>Registration Update</h3>
      <p>Hi <strong>{user.name}</strong>,</p>
      <p>Thank you for applying to join TailorApp as a <strong>{role_label}</strong>.</p>
      <p>After reviewing your application, we are unable to approve your registration at this time.</p>
      <p>If you believe this is an error or would like more information, please contact our support team.</p>
    """)
    _send('TailorApp Registration Update', user.email, html)


def send_password_reset(user, reset_url):
    html = _wrap(f"""
      <h3>Reset Your Password 🔑</h3>
      <p>Hi <strong>{user.name}</strong>,</p>
      <p>We received a request to reset your TailorApp password.</p>
      <p style="text-align:center;margin:24px 0;">
        <a href="{reset_url}" style="background:#6f42c1;color:#fff;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:bold;">
          Reset Password
        </a>
      </p>
      <p style="font-size:13px;color:#666;">This link expires in <strong>1 hour</strong> and can only be used once.</p>
      <p style="font-size:13px;color:#666;">If you didn't request this, you can safely ignore this email.</p>
    """)
    _send('Reset Your TailorApp Password', user.email, html)


def send_style_agent_assigned(order, agent):
    """Notify customer when admin manually assigns a style agent to their order."""
    html = _wrap(f"""
      <h3>Style Agent Assigned 👔</h3>
      <p>Hi <strong>{order.customer.name}</strong>,</p>
      <p><strong>{agent.name}</strong> has been assigned as your Style Agent for order <strong>#{order.order_number}</strong>.</p>
      <p>You'll receive a separate notification in the TailorApp with the appointment details. Please confirm this assignment in your app.</p>
      <p><strong>Agent Contact:</strong> {agent.phone}</p>
    """)
    _send(f'Style Agent Assigned for #{order.order_number} — TailorApp',
          order.customer.email, html)
