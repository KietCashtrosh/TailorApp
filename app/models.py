import json
import random
import secrets
import string
from datetime import datetime, timedelta
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    password_hash = db.Column(db.Text)  # Text: hashes can exceed 256 chars on high iteration counts
    role = db.Column(db.String(20), nullable=False, index=True)  # admin | tailor | delivery | customer
    is_active = db.Column(db.Boolean, default=True)
    # approved | pending | rejected  (customers/admin auto-approved; tailors/delivery start pending)
    approval_status = db.Column(db.String(20), default='approved', index=True)
    default_pickup_address = db.Column(db.Text, default='')
    default_delivery_address = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tailor_profile = db.relationship('TailorProfile', backref='user', uselist=False)
    family_profiles = db.relationship('FamilyProfile', backref='user', lazy='dynamic',
                                      foreign_keys='FamilyProfile.user_id')
    customer_orders = db.relationship(
        'Order', foreign_keys='Order.customer_id', backref='customer', lazy='dynamic'
    )
    delivery_assignments = db.relationship(
        'DeliveryAssignment',
        foreign_keys='DeliveryAssignment.delivery_agent_id',
        backref='delivery_agent',
        lazy='dynamic',
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email} [{self.role}]>'


class FamilyProfile(db.Model):
    __tablename__ = 'family_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    relation = db.Column(db.String(50), default='')   # Self, Spouse, Child, Parent, etc.
    gender = db.Column(db.String(10), default='')
    date_of_birth = db.Column(db.String(20), default='')
    avatar_color = db.Column(db.String(20), default='#6f42c1')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def initials(self):
        parts = self.name.strip().split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return self.name[:2].upper() if self.name else '?'

    def __repr__(self):
        return f'<FamilyProfile {self.name} user={self.user_id}>'


class PasswordResetToken(db.Model):
    __tablename__ = 'password_reset_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='reset_tokens')

    @staticmethod
    def create_for_user(user):
        # Invalidate existing tokens
        PasswordResetToken.query.filter_by(user_id=user.id, used=False).update({'used': True})
        token = secrets.token_urlsafe(32)
        prt = PasswordResetToken(
            user_id=user.id,
            token=token,
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.session.add(prt)
        return prt

    @property
    def is_valid(self):
        return not self.used and datetime.utcnow() < self.expires_at

    def __repr__(self):
        return f'<PasswordResetToken user={self.user_id} used={self.used}>'


class TailorProfile(db.Model):
    __tablename__ = 'tailor_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    shop_name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.Text, nullable=False)
    latitude = db.Column(db.Float, default=0.0)
    longitude = db.Column(db.Float, default=0.0)
    specializations = db.Column(db.Text, default='[]')  # JSON list
    experience_years = db.Column(db.Integer, default=0)
    rating = db.Column(db.Float, default=0.0)
    rating_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    is_available = db.Column(db.Boolean, default=True)   # shop open/closed toggle
    bio = db.Column(db.Text, default='')
    shop_photo = db.Column(db.String(200), default='')   # uploaded shop/profile photo filename

    orders = db.relationship('Order', backref='tailor', lazy='dynamic')
    measurement_templates = db.relationship(
        'TailorMeasurementTemplate', backref='tailor', lazy='dynamic'
    )

    def get_specializations(self):
        try:
            return json.loads(self.specializations)
        except Exception:
            return []

    def set_specializations(self, spec_list):
        self.specializations = json.dumps(spec_list)

    def get_measurement_template(self, design_id):
        """Return tailor-specific measurement fields for a design, or None if not set."""
        tmpl = self.measurement_templates.filter_by(design_id=design_id).first()
        return tmpl

    def __repr__(self):
        return f'<TailorProfile {self.shop_name}>'


class Design(db.Model):
    __tablename__ = 'designs'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text, default='')
    base_price = db.Column(db.Float, nullable=False)
    icon = db.Column(db.String(50), default='bi-scissors')
    image_filename = db.Column(db.String(200), default='')
    measurement_fields = db.Column(db.Text, default='[]')  # JSON list of {key, label}
    design_options = db.Column(db.Text, default='[]')     # JSON list of {group, options[]}
    is_active = db.Column(db.Boolean, default=True)

    def get_measurement_fields(self):
        try:
            return json.loads(self.measurement_fields)
        except Exception:
            return []

    def get_design_options(self):
        """Return list of {group, options[]} dicts for the variant picker."""
        try:
            return json.loads(self.design_options or '[]')
        except Exception:
            return []

    def image_url(self):
        from flask import url_for
        if self.image_filename:
            return url_for('static', filename=f'uploads/{self.image_filename}')
        return None

    def __repr__(self):
        return f'<Design {self.name}>'


class TailorMeasurementTemplate(db.Model):
    """Per-tailor custom measurement fields for each design they support."""
    __tablename__ = 'tailor_measurement_templates'

    id = db.Column(db.Integer, primary_key=True)
    tailor_id = db.Column(db.Integer, db.ForeignKey('tailor_profiles.id'), nullable=False)
    design_id = db.Column(db.Integer, db.ForeignKey('designs.id'), nullable=False)
    measurement_fields = db.Column(db.Text, default='[]')  # JSON list of {key, label}
    custom_price = db.Column(db.Float, nullable=True)  # tailor's own price for this design
    admin_offer_price = db.Column(db.Float, nullable=True)  # admin-controlled promotional offer

    design = db.relationship('Design')

    __table_args__ = (
        db.UniqueConstraint('tailor_id', 'design_id', name='uq_tailor_design_tmpl'),
    )

    def get_measurement_fields(self):
        try:
            return json.loads(self.measurement_fields)
        except Exception:
            return []

    def set_measurement_fields(self, fields_list):
        self.measurement_fields = json.dumps(fields_list)

    def effective_price(self):
        if self.admin_offer_price is not None:
            return self.admin_offer_price
        return self.custom_price if self.custom_price else self.design.base_price

    def offer_original_price(self):
        """Returns the pre-offer price when admin_offer_price is active, else None."""
        if self.admin_offer_price is not None:
            return self.custom_price if self.custom_price else self.design.base_price
        return None

    def __repr__(self):
        return f'<TailorMeasurementTemplate tailor={self.tailor_id} design={self.design_id}>'


class Coupon(db.Model):
    __tablename__ = 'coupons'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    description = db.Column(db.String(200), default='')
    discount_type = db.Column(db.String(10), nullable=False)  # 'percent' | 'fixed'
    discount_value = db.Column(db.Float, nullable=False)
    min_order_amount = db.Column(db.Float, default=0)
    max_uses = db.Column(db.Integer, default=0)  # 0 = unlimited
    uses_count = db.Column(db.Integer, default=0)
    valid_from = db.Column(db.DateTime, default=datetime.utcnow)
    valid_to = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_valid(self):
        now = datetime.utcnow()
        if not self.is_active:
            return False, 'Coupon is inactive.'
        if self.valid_to and now > self.valid_to:
            return False, 'Coupon has expired.'
        if now < self.valid_from:
            return False, 'Coupon is not yet active.'
        if self.max_uses > 0 and self.uses_count >= self.max_uses:
            return False, 'Coupon usage limit reached.'
        return True, ''

    def compute_discount(self, order_amount):
        valid, msg = self.is_valid()
        if not valid:
            return 0, msg
        if order_amount < self.min_order_amount:
            return 0, f'Minimum order amount is Rs.{self.min_order_amount:.0f}.'
        if self.discount_type == 'percent':
            return round(order_amount * self.discount_value / 100, 2), ''
        return min(self.discount_value, order_amount), ''

    def __repr__(self):
        return f'<Coupon {self.code}>'


ORDER_STATUSES = [
    ('placed', 'Order Placed'),
    ('accepted', 'Accepted by Tailor'),
    ('fabric_pickup', 'Fabric Pickup Scheduled'),
    ('fabric_collected', 'Fabric Collected'),
    ('stitching', 'Stitching in Progress'),
    ('ready', 'Ready for Delivery'),
    ('out_for_delivery', 'Out for Delivery'),
    ('delivered', 'Delivered'),
    ('rejected', 'Rejected'),
    ('cancelled', 'Cancelled'),
]

STATUS_LABELS = dict(ORDER_STATUSES)

STATUS_BADGE = {
    'placed': 'primary',
    'accepted': 'info',
    'fabric_pickup': 'warning',
    'fabric_collected': 'warning',
    'stitching': 'secondary',
    'ready': 'success',
    'out_for_delivery': 'warning',
    'delivered': 'success',
    'rejected': 'danger',
    'cancelled': 'dark',
}


def generate_order_number():
    # Use secrets for cryptographically random suffix — order numbers should be unguessable
    alphabet = string.ascii_uppercase + string.digits
    suffix = ''.join(secrets.choice(alphabet) for _ in range(6))
    return f'ORD{datetime.utcnow().strftime("%y%m%d")}{suffix}'


def generate_otp():
    # 6-digit OTP — cryptographically random
    return str(secrets.randbelow(900000) + 100000)


class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False,
                             default=generate_order_number)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    tailor_id = db.Column(db.Integer, db.ForeignKey('tailor_profiles.id'), nullable=False, index=True)
    design_id = db.Column(db.Integer, db.ForeignKey('designs.id'), nullable=True)
    family_profile_id = db.Column(db.Integer, db.ForeignKey('family_profiles.id'), nullable=True)
    tailor_receipt_otp = db.Column(db.String(6), default='')
    tailor_receipt_verified = db.Column(db.Boolean, default=False)
    tailor_handover_otp = db.Column(db.String(6), default='')
    tailor_handover_verified = db.Column(db.Boolean, default=False)
    measurements = db.Column(db.Text, default='{}')
    measurement_preference = db.Column(db.String(20), default='delivery_will_measure')
    special_instructions = db.Column(db.Text, default='')
    fabric_description = db.Column(db.Text, default='')
    status = db.Column(db.String(30), default='placed', index=True)
    pickup_address = db.Column(db.Text, nullable=False)
    delivery_address = db.Column(db.Text, nullable=False)
    estimated_price = db.Column(db.Float)
    final_price = db.Column(db.Float)
    discount_amount = db.Column(db.Float, default=0)
    coupon_code = db.Column(db.String(30), default='')
    estimated_days = db.Column(db.Integer)
    payment_method = db.Column(db.String(20), default='cod')   # cod | online | cash
    payment_status = db.Column(db.String(20), default='unpaid') # unpaid | paid | cod_pending
    accepted_at = db.Column(db.DateTime)
    admin_note = db.Column(db.Text, default='')
    work_images = db.Column(db.Text, default='[]')       # JSON list of filenames (tailor work-proof photos)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        # Composite index: tailor dashboard filters by tailor + status constantly
        db.Index('ix_orders_tailor_status', 'tailor_id', 'status'),
        # Composite index: customer order list filters by customer + status
        db.Index('ix_orders_customer_status', 'customer_id', 'status'),
    )

    design = db.relationship('Design')
    family_profile = db.relationship('FamilyProfile', foreign_keys=[family_profile_id])
    coupon = db.relationship('Coupon', foreign_keys=[coupon_code],
                             primaryjoin='Order.coupon_code == Coupon.code',
                             backref='orders', uselist=False)
    status_history = db.relationship(
        'OrderStatusHistory', backref='order',
        lazy='dynamic', order_by='OrderStatusHistory.created_at'
    )
    delivery_assignments = db.relationship(
        'DeliveryAssignment', backref='order', lazy='dynamic'
    )
    order_items = db.relationship('OrderItem', backref='order', lazy='dynamic')
    messages = db.relationship('Message', backref='order', lazy='dynamic',
                               order_by='Message.created_at')
    review = db.relationship('Review', backref='order', uselist=False)

    # Phase 1: Style Agent booking fields
    style_agent_appointment_date = db.Column(db.String(10), default='')  # YYYY-MM-DD (when style agent slot booking enabled)
    style_agent_appointment_time = db.Column(db.String(5), default='')   # HH:MM
    auto_assigned_style_agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # When admin manually assigns
    admin_assigned_at = db.Column(db.DateTime, nullable=True)  # Timestamp when admin assigned agent
    customer_confirmed_slot = db.Column(db.Boolean, default=False)  # Customer confirmed admin-assigned slot
    style_agent = db.relationship('User', foreign_keys=[auto_assigned_style_agent_id], backref='orders_as_assigned_agent')

    def get_measurements(self):
        try:
            return json.loads(self.measurements)
        except Exception:
            return {}

    def get_work_images(self):
        try:
            return json.loads(self.work_images or '[]')
        except Exception:
            return []

    def add_work_image(self, filename):
        imgs = self.get_work_images()
        imgs.append(filename)
        self.work_images = json.dumps(imgs)

    def remove_work_image(self, filename):
        imgs = self.get_work_images()
        if filename in imgs:
            imgs.remove(filename)
        self.work_images = json.dumps(imgs)

    def is_multi_item(self):
        return self.design_id is None and self.order_items.count() > 0

    def display_design_name(self):
        if self.is_multi_item():
            count = self.order_items.count()
            return f'{count} item order'
        return self.design.name if self.design else 'Custom Order'

    def get_primary_design(self):
        if self.design:
            return self.design
        first = self.order_items.first()
        return first.design if first else None

    def items_subtotal(self):
        if self.is_multi_item():
            return sum(item.subtotal for item in self.order_items.all())
        return self.final_price or self.estimated_price or 0

    def payable_amount(self):
        base = self.items_subtotal()
        return max(0, base - (self.discount_amount or 0))

    def eta_date(self):
        from datetime import timedelta
        if self.accepted_at and self.estimated_days:
            return (self.accepted_at + timedelta(days=self.estimated_days)).strftime('%d %B %Y')
        return None

    def payment_status_label(self):
        return {'unpaid': 'Unpaid', 'paid': 'Paid', 'cod_pending': 'Cash on Delivery'}.get(
            self.payment_status, self.payment_status
        )

    def payment_method_label(self):
        return {'cod': 'Cash on Delivery', 'online': 'Online Payment', 'cash': 'Cash'}.get(
            self.payment_method, self.payment_method
        )

    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)

    def status_badge(self):
        return STATUS_BADGE.get(self.status, 'secondary')

    def add_status(self, status, note='', changed_by_id=None):
        self.status = status
        self.updated_at = datetime.utcnow()
        history = OrderStatusHistory(
            order_id=self.id,
            status=status,
            note=note,
            changed_by_id=changed_by_id,
        )
        db.session.add(history)

    def __repr__(self):
        return f'<Order {self.order_number}>'


class OrderStatusHistory(db.Model):
    __tablename__ = 'order_status_history'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False)
    note = db.Column(db.Text, default='')
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    changed_by = db.relationship('User', foreign_keys=[changed_by_id])

    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)


class DeliveryAssignment(db.Model):
    __tablename__ = 'delivery_assignments'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    delivery_agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    assignment_type = db.Column(db.String(20), nullable=False)
    pickup_address = db.Column(db.Text)
    dropoff_address = db.Column(db.Text)
    status = db.Column(db.String(20), default='assigned', index=True)
    # assigned | otp_pending | picked_up | delivered
    pickup_otp = db.Column(db.String(6), default='')
    delivery_otp = db.Column(db.String(6), default='')
    pickup_otp_verified = db.Column(db.Boolean, default=False)
    delivery_otp_verified = db.Column(db.Boolean, default=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    notes = db.Column(db.Text, default='')

    def type_label(self):
        return {
            'pickup_fabric': 'Pickup Fabric from Customer',
            'deliver_clothes': 'Deliver Clothes to Customer',
        }.get(self.assignment_type, self.assignment_type)

    def __repr__(self):
        return f'<DeliveryAssignment order={self.order_id} type={self.assignment_type}>'


class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    design_id = db.Column(db.Integer, db.ForeignKey('designs.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    fabric_description = db.Column(db.Text, default='')
    measurements = db.Column(db.Text, default='{}')
    special_instructions = db.Column(db.Text, default='')
    selected_variants = db.Column(db.Text, default='{}')  # JSON {group: chosen_option}
    unit_price = db.Column(db.Float, default=0)

    design = db.relationship('Design')

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def get_measurements(self):
        try:
            return json.loads(self.measurements)
        except Exception:
            return {}

    def get_selected_variants(self):
        try:
            return json.loads(self.selected_variants or '{}')
        except Exception:
            return {}

    def format_variants_display(self):
        """Return a human-readable string of selected variants."""
        v = self.get_selected_variants()
        if not v:
            return ''
        return ' · '.join(f'{g}: {o}' for g, o in v.items())

    def __repr__(self):
        return f'<OrderItem order={self.order_id} design={self.design_id}>'


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id])

    def __repr__(self):
        return f'<Message order={self.order_id} sender={self.sender_id}>'


class CustomerMeasurement(db.Model):
    __tablename__ = 'customer_measurements'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    design_id = db.Column(db.Integer, db.ForeignKey('designs.id'), nullable=False)
    measurements = db.Column(db.Text, default='{}')
    taken_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = db.relationship('User', foreign_keys=[customer_id], backref='saved_measurements')
    design = db.relationship('Design')
    taken_by = db.relationship('User', foreign_keys=[taken_by_id])

    __table_args__ = (
        db.UniqueConstraint('customer_id', 'design_id', name='uq_customer_design'),
    )

    def get_measurements(self):
        try:
            return json.loads(self.measurements)
        except Exception:
            return {}

    def __repr__(self):
        return f'<CustomerMeasurement customer={self.customer_id} design={self.design_id}>'


class CartItem(db.Model):
    __tablename__ = 'cart_items'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    tailor_id = db.Column(db.Integer, db.ForeignKey('tailor_profiles.id'), nullable=False)
    design_id = db.Column(db.Integer, db.ForeignKey('designs.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    fabric_description = db.Column(db.Text, default='')
    special_instructions = db.Column(db.Text, default='')
    measurement_preference = db.Column(db.String(20), default='delivery_will_measure')
    measurements = db.Column(db.Text, default='{}')
    selected_variants = db.Column(db.Text, default='{}')  # JSON {group: chosen_option}
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship('User', foreign_keys=[customer_id])
    tailor = db.relationship('TailorProfile')
    design = db.relationship('Design')

    def get_measurements(self):
        try:
            return json.loads(self.measurements)
        except Exception:
            return {}

    def get_selected_variants(self):
        try:
            return json.loads(self.selected_variants or '{}')
        except Exception:
            return {}

    def __repr__(self):
        return f'<CartItem customer={self.customer_id} design={self.design_id}>'


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(300), default='')
    # Extended fields for richer notifications
    title = db.Column(db.String(200), default='')
    body = db.Column(db.Text, default='')
    type = db.Column(db.String(20), default='info')   # info | success | warning | danger
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    is_read = db.Column(db.Boolean, default=False, index=True)  # filtered constantly for unread badge
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='notifications')

    def display_title(self):
        return self.title or self.message

    def display_body(self):
        return self.body or ''

    @staticmethod
    def create(user_id, title, body='', type='info', order_id=None, link=''):
        """Create a rich notification with title + body."""
        n = Notification(
            user_id=user_id,
            message=title,
            link=link,
            title=title,
            body=body,
            type=type,
            order_id=order_id,
        )
        db.session.add(n)
        return n

    def __repr__(self):
        return f'<Notification user={self.user_id} read={self.is_read}>'


def notify(user_id, message, link=''):
    """Add an unread notification for a user. Caller must commit the session."""
    n = Notification(user_id=user_id, message=message, link=link, title=message)
    db.session.add(n)


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 — Multi-Level Product Catalogue
# ─────────────────────────────────────────────────────────────────────────────

class ProductDesign(db.Model):
    """Level-2: Named sub-design under a Design category (e.g. Round Neck under Blouse)."""
    __tablename__ = 'product_designs'

    id = db.Column(db.Integer, primary_key=True)
    design_id = db.Column(db.Integer, db.ForeignKey('designs.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, default='')
    base_price_modifier = db.Column(db.Float, default=0.0)
    fabric_suggestions = db.Column(db.Text, default='[]')  # JSON list of strings
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    category = db.relationship('Design', backref='product_designs')
    variants = db.relationship('DesignVariant', backref='product_design',
                               lazy='dynamic', cascade='all, delete-orphan')
    images = db.relationship('DesignImage', backref='product_design',
                             lazy='dynamic', cascade='all, delete-orphan',
                             order_by='DesignImage.display_order')
    tailor_services = db.relationship('TailorProductService', backref='product_design',
                                      lazy='dynamic', cascade='all, delete-orphan')

    def get_fabric_suggestions(self):
        try:
            return json.loads(self.fabric_suggestions)
        except Exception:
            return []

    def effective_base_price(self):
        return (self.category.base_price or 0) + self.base_price_modifier

    def main_image(self):
        img = self.images.filter_by(image_type='main').first()
        if not img:
            img = self.images.first()
        return img

    def __repr__(self):
        return f'<ProductDesign {self.name}>'


class DesignVariant(db.Model):
    """Level-3: Customization group with options for a ProductDesign."""
    __tablename__ = 'design_variants'

    id = db.Column(db.Integer, primary_key=True)
    product_design_id = db.Column(db.Integer, db.ForeignKey('product_designs.id'), nullable=False)
    variant_group = db.Column(db.String(100), nullable=False)  # e.g. "Sleeve Style"
    variant_options = db.Column(db.Text, default='[]')  # JSON list e.g. ["Half", "Full", "None"]
    price_modifier = db.Column(db.Float, default=0.0)
    display_order = db.Column(db.Integer, default=0)

    def get_options(self):
        try:
            return json.loads(self.variant_options)
        except Exception:
            return []

    def set_options(self, opts):
        self.variant_options = json.dumps(opts)

    def __repr__(self):
        return f'<DesignVariant {self.variant_group}>'


class DesignImage(db.Model):
    """Images attached to a ProductDesign (main, gallery, size_chart, fabric_swatch)."""
    __tablename__ = 'design_images'

    id = db.Column(db.Integer, primary_key=True)
    product_design_id = db.Column(db.Integer, db.ForeignKey('product_designs.id'), nullable=False)
    image_filename = db.Column(db.String(200), nullable=False)
    image_type = db.Column(db.String(30), default='main')  # main | gallery | size_chart | fabric_swatch
    caption = db.Column(db.String(200), default='')
    display_order = db.Column(db.Integer, default=0)

    def url(self):
        from flask import url_for
        return url_for('static', filename=f'uploads/catalogue/{self.image_filename}')

    def __repr__(self):
        return f'<DesignImage {self.image_filename}>'


class TailorProductService(db.Model):
    """Tailor-specific availability, pricing, and timeline for a ProductDesign."""
    __tablename__ = 'tailor_product_services'

    id = db.Column(db.Integer, primary_key=True)
    tailor_id = db.Column(db.Integer, db.ForeignKey('tailor_profiles.id'), nullable=False)
    product_design_id = db.Column(db.Integer, db.ForeignKey('product_designs.id'), nullable=False)
    custom_price = db.Column(db.Float, nullable=True)
    estimated_days = db.Column(db.Integer, default=7)
    expertise_level = db.Column(db.String(20), default='intermediate')  # basic | intermediate | expert
    is_available = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tailor = db.relationship('TailorProfile', backref='product_services')

    __table_args__ = (
        db.UniqueConstraint('tailor_id', 'product_design_id', name='uq_tailor_product_service'),
    )

    def effective_price(self):
        if self.custom_price is not None:
            return self.custom_price
        return self.product_design.effective_base_price()

    def expertise_badge(self):
        return {'basic': 'secondary', 'intermediate': 'info', 'expert': 'warning'}.get(
            self.expertise_level, 'secondary')

    def __repr__(self):
        return f'<TailorProductService tailor={self.tailor_id} design={self.product_design_id}>'


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 — Style Agent Appointment Booking
# ─────────────────────────────────────────────────────────────────────────────

class StyleAgentConfig(db.Model):
    """Admin-configurable working-hours profile for Style Agents."""
    __tablename__ = 'style_agent_configs'

    id = db.Column(db.Integer, primary_key=True)
    config_name = db.Column(db.String(100), nullable=False)
    start_hour = db.Column(db.Integer, default=10)   # 10 = 10:00 AM
    end_hour = db.Column(db.Integer, default=18)     # 18 = 6:00 PM
    slot_duration_minutes = db.Column(db.Integer, default=30)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def generate_slots(self):
        """Return list of 'HH:MM' strings for this config."""
        slots = []
        total_minutes = self.start_hour * 60
        end_minutes = self.end_hour * 60
        while total_minutes < end_minutes:
            h, m = divmod(total_minutes, 60)
            slots.append(f'{h:02d}:{m:02d}')
            total_minutes += self.slot_duration_minutes
        return slots

    def __repr__(self):
        return f'<StyleAgentConfig {self.config_name}>'


APPOINTMENT_STATUSES = [
    ('pending', 'Pending Confirmation'),
    ('confirmed', 'Confirmed'),
    ('agent_assigned', 'Agent Assigned'),
    ('arrived', 'Agent Arrived'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
    ('rescheduled', 'Rescheduled'),
]

APPOINTMENT_STATUS_LABELS = dict(APPOINTMENT_STATUSES)

APPOINTMENT_STATUS_BADGE = {
    'pending': 'warning',
    'confirmed': 'info',
    'agent_assigned': 'primary',
    'arrived': 'secondary',
    'completed': 'success',
    'cancelled': 'danger',
    'rescheduled': 'warning',
}

SERVICE_TYPE_LABELS = {
    'measurement_only': 'Measurement Only',
    'fabric_pickup_only': 'Fabric Pickup Only',
    'both': 'Measurement + Fabric Pickup',
}


class StyleAgentAppointment(db.Model):
    """Customer-booked appointment for a Style Agent visit."""
    __tablename__ = 'style_agent_appointments'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    style_agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)
    product_design_id = db.Column(db.Integer, db.ForeignKey('product_designs.id'), nullable=True)
    appointment_date = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD
    appointment_time = db.Column(db.String(5), nullable=False)   # HH:MM
    service_type = db.Column(db.String(30), nullable=False, default='both')
    status = db.Column(db.String(20), default='pending')
    customer_address = db.Column(db.Text, nullable=False)
    notes = db.Column(db.Text, default='')
    agent_notes = db.Column(db.Text, default='')
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship('User', foreign_keys=[customer_id],
                               backref='appointments_as_customer')
    style_agent = db.relationship('User', foreign_keys=[style_agent_id],
                                  backref='appointments_as_agent')
    order = db.relationship('Order', foreign_keys=[order_id], backref='appointment')
    product_design = db.relationship('ProductDesign')

    def status_label(self):
        return APPOINTMENT_STATUS_LABELS.get(self.status, self.status)

    def status_badge(self):
        return APPOINTMENT_STATUS_BADGE.get(self.status, 'secondary')

    def service_label(self):
        return SERVICE_TYPE_LABELS.get(self.service_type, self.service_type)

    def display_datetime(self):
        try:
            from datetime import datetime as dt
            d = dt.strptime(self.appointment_date, '%Y-%m-%d')
            return f"{d.strftime('%d %b %Y')} at {self.appointment_time}"
        except Exception:
            return f"{self.appointment_date} {self.appointment_time}"

    def __repr__(self):
        return f'<StyleAgentAppointment customer={self.customer_id} date={self.appointment_date}>'


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 — Dummy Payment Gateway + Money Tracking
# ─────────────────────────────────────────────────────────────────────────────

PAYMENT_STATUSES = ['pending', 'success', 'failed', 'refunded', 'refund_initiated']

PAYOUT_STATUSES = ['pending', 'processed', 'failed', 'refunded']


class PaymentTransaction(db.Model):
    """Records each payment attempt against an order."""
    __tablename__ = 'payment_transactions'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    payment_method = db.Column(db.String(30), default='dummy_card')
    transaction_ref = db.Column(db.String(40), unique=True, nullable=False)
    failure_reason = db.Column(db.String(200), default='')
    processed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    order = db.relationship('Order', backref='payment_transactions')
    allocations = db.relationship('PaymentAllocation', backref='transaction',
                                  lazy='dynamic', cascade='all, delete-orphan')

    @staticmethod
    def generate_ref():
        return 'TXN' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

    def __repr__(self):
        return f'<PaymentTransaction {self.transaction_ref} {self.status}>'


class PaymentAllocation(db.Model):
    """How a successful payment is split between platform, tailor, and style agent."""
    __tablename__ = 'payment_allocations'

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('payment_transactions.id'), nullable=False)
    recipient_type = db.Column(db.String(20), nullable=False)  # platform | tailor | style_agent
    recipient_id = db.Column(db.Integer, nullable=True)        # user_id or tailor_profile_id
    amount = db.Column(db.Float, nullable=False)
    payout_status = db.Column(db.String(20), default='pending')
    payout_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<PaymentAllocation {self.recipient_type} ₹{self.amount}>'


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN CONFIG — Toggleable system-wide settings
# ─────────────────────────────────────────────────────────────────────────────

class AdminConfig(db.Model):
    """System-wide admin-configurable settings."""
    __tablename__ = 'admin_configs'

    id = db.Column(db.Integer, primary_key=True, default=1)
    tailor_acceptance_window_hours = db.Column(db.Integer, default=2)
    enable_style_agent_slot_booking = db.Column(db.Boolean, default=True)
    auto_confirm_orders_if_no_response = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get():
        config = AdminConfig.query.first()
        if not config:
            config = AdminConfig(id=1)
            db.session.add(config)
            db.session.commit()
        return config

    def __repr__(self):
        return f'<AdminConfig tailor_window={self.tailor_acceptance_window_hours}h slot_booking={self.enable_style_agent_slot_booking}>'


class Review(db.Model):
    __tablename__ = 'reviews'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tailor_rating = db.Column(db.Integer)       # 1-5
    tailor_comment = db.Column(db.Text, default='')
    delivery_rating = db.Column(db.Integer)     # 1-5
    delivery_comment = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship('User', foreign_keys=[customer_id])

    def __repr__(self):
        return f'<Review order={self.order_id}>'
