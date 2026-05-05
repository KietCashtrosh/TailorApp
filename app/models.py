import json
import random
import string
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), nullable=False)  # admin | tailor | delivery | customer
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tailor_profile = db.relationship('TailorProfile', backref='user', uselist=False)
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
    is_active = db.Column(db.Boolean, default=True)

    def get_measurement_fields(self):
        try:
            return json.loads(self.measurement_fields)
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
    custom_price = db.Column(db.Float, nullable=True)  # override base price for this tailor+design

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
        return self.custom_price if self.custom_price else self.design.base_price

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
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f'ORD{datetime.utcnow().strftime("%y%m%d")}{suffix}'


def generate_otp():
    return str(random.randint(100000, 999999))


class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False,
                             default=generate_order_number)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tailor_id = db.Column(db.Integer, db.ForeignKey('tailor_profiles.id'), nullable=False)
    design_id = db.Column(db.Integer, db.ForeignKey('designs.id'), nullable=False)
    measurements = db.Column(db.Text, default='{}')
    measurement_preference = db.Column(db.String(20), default='delivery_will_measure')
    special_instructions = db.Column(db.Text, default='')
    fabric_description = db.Column(db.Text, default='')
    status = db.Column(db.String(30), default='placed')
    pickup_address = db.Column(db.Text, nullable=False)
    delivery_address = db.Column(db.Text, nullable=False)
    estimated_price = db.Column(db.Float)
    final_price = db.Column(db.Float)
    discount_amount = db.Column(db.Float, default=0)
    coupon_code = db.Column(db.String(30), default='')
    estimated_days = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    design = db.relationship('Design')
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
    review = db.relationship('Review', backref='order', uselist=False)

    def get_measurements(self):
        try:
            return json.loads(self.measurements)
        except Exception:
            return {}

    def payable_amount(self):
        base = self.final_price or self.estimated_price or 0
        return max(0, base - (self.discount_amount or 0))

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
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
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
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    delivery_agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assignment_type = db.Column(db.String(20), nullable=False)
    pickup_address = db.Column(db.Text)
    dropoff_address = db.Column(db.Text)
    status = db.Column(db.String(20), default='assigned')
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


class CustomerMeasurement(db.Model):
    __tablename__ = 'customer_measurements'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
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
