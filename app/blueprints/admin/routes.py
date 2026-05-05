import os
import json
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
from flask import render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_required, current_user
from app.blueprints.admin import admin_bp
from app.extensions import db
from app.models import (User, TailorProfile, Order, DeliveryAssignment, Design,
                        Coupon, Review, generate_otp)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename):
    return ('.' in filename and
            filename.rsplit('.', 1)[1].lower() in
            current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'webp'}))


# ── Dashboard ──────────────────────────────────────────────
@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    stats = {
        'total_orders': Order.query.count(),
        'pending_orders': Order.query.filter(
            Order.status.in_(['placed', 'accepted', 'fabric_pickup',
                               'fabric_collected', 'stitching', 'ready', 'out_for_delivery'])
        ).count(),
        'delivered_orders': Order.query.filter_by(status='delivered').count(),
        'total_tailors': TailorProfile.query.filter_by(is_active=True).count(),
        'total_customers': User.query.filter_by(role='customer').count(),
        'total_delivery': User.query.filter_by(role='delivery').count(),
    }
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    return render_template('admin/dashboard.html', stats=stats, recent_orders=recent_orders)


@admin_bp.route('/notifications')
@login_required
@admin_required
def notifications():
    """HTMX polling endpoint — returns notification badge counts."""
    unassigned = Order.query.filter(
        Order.status.in_(['accepted', 'ready'])
    ).count()
    new_orders = Order.query.filter_by(status='placed').count()
    return jsonify({'unassigned': unassigned, 'new_orders': new_orders})


# ── Orders ─────────────────────────────────────────────────
@admin_bp.route('/orders')
@login_required
@admin_required
def orders():
    status_filter = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    q = Order.query.order_by(Order.created_at.desc())
    if status_filter:
        q = q.filter_by(status=status_filter)
    pagination = q.paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/orders.html', orders=pagination.items,
                           pagination=pagination, status_filter=status_filter)


@admin_bp.route('/orders/<int:order_id>')
@login_required
@admin_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    delivery_agents = User.query.filter_by(role='delivery', is_active=True).all()
    assignments = order.delivery_assignments.all()
    history = order.status_history.all()
    return render_template('admin/order_detail.html', order=order,
                           delivery_agents=delivery_agents,
                           assignments=assignments, history=history)


@admin_bp.route('/orders/<int:order_id>/assign-delivery', methods=['POST'])
@login_required
@admin_required
def assign_delivery(order_id):
    order = Order.query.get_or_404(order_id)
    agent_id = request.form.get('agent_id', type=int)
    assignment_type = request.form.get('assignment_type', '')
    notes = request.form.get('notes', '')

    if not agent_id or assignment_type not in ('pickup_fabric', 'deliver_clothes'):
        flash('Invalid assignment data.', 'danger')
        return redirect(url_for('admin.order_detail', order_id=order_id))

    agent = User.query.get(agent_id)
    if not agent or agent.role != 'delivery':
        flash('Invalid delivery agent.', 'danger')
        return redirect(url_for('admin.order_detail', order_id=order_id))

    if assignment_type == 'pickup_fabric':
        pickup, dropoff = order.pickup_address, order.tailor.address
        new_status = 'fabric_pickup'
    else:
        pickup, dropoff = order.tailor.address, order.delivery_address
        new_status = 'out_for_delivery'

    assignment = DeliveryAssignment(
        order_id=order.id,
        delivery_agent_id=agent_id,
        assignment_type=assignment_type,
        pickup_address=pickup,
        dropoff_address=dropoff,
        notes=notes,
        pickup_otp=generate_otp(),
        delivery_otp=generate_otp(),
    )
    db.session.add(assignment)
    order.add_status(new_status,
                     note=f'Delivery agent {agent.name} assigned.',
                     changed_by_id=current_user.id)
    db.session.commit()
    flash('Delivery agent assigned successfully.', 'success')
    return redirect(url_for('admin.order_detail', order_id=order_id))


# ── Designs ────────────────────────────────────────────────
@admin_bp.route('/designs')
@login_required
@admin_required
def designs():
    all_designs = Design.query.order_by(Design.name).all()
    return render_template('admin/designs.html', designs=all_designs)


@admin_bp.route('/designs/new', methods=['GET', 'POST'])
@admin_bp.route('/designs/<int:design_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def design_form(design_id=None):
    design = Design.query.get_or_404(design_id) if design_id else Design()

    if request.method == 'POST':
        design.name = request.form.get('name', '').strip()
        design.description = request.form.get('description', '').strip()
        design.base_price = request.form.get('base_price', 0, type=float)
        design.icon = request.form.get('icon', 'bi-scissors').strip()
        design.is_active = bool(request.form.get('is_active'))

        # Build measurement fields from dynamic rows
        keys = request.form.getlist('field_key')
        labels = request.form.getlist('field_label')
        fields = [{'key': k.strip(), 'label': l.strip()}
                  for k, l in zip(keys, labels) if k.strip() and l.strip()]
        design.measurement_fields = json.dumps(fields)

        # Image upload
        file = request.files.get('image')
        if file and file.filename and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = secure_filename(f'design_{design.name.lower().replace(" ", "_")}.{ext}')
            upload_path = current_app.config['UPLOAD_FOLDER']
            os.makedirs(upload_path, exist_ok=True)
            file.save(os.path.join(upload_path, filename))
            design.image_filename = filename

        if not design_id:
            db.session.add(design)
        db.session.commit()
        flash(f'Design "{design.name}" saved.', 'success')
        return redirect(url_for('admin.designs'))

    return render_template('admin/design_form.html', design=design)


@admin_bp.route('/designs/<int:design_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_design(design_id):
    design = Design.query.get_or_404(design_id)
    design.is_active = not design.is_active
    db.session.commit()
    flash(f'Design "{design.name}" {"activated" if design.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin.designs'))


# ── Coupons ────────────────────────────────────────────────
@admin_bp.route('/coupons')
@login_required
@admin_required
def coupons():
    all_coupons = Coupon.query.order_by(Coupon.created_at.desc()).all()
    return render_template('admin/coupons.html', coupons=all_coupons)


@admin_bp.route('/coupons/new', methods=['GET', 'POST'])
@admin_bp.route('/coupons/<int:coupon_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def coupon_form(coupon_id=None):
    coupon = Coupon.query.get_or_404(coupon_id) if coupon_id else Coupon()

    if request.method == 'POST':
        coupon.code = request.form.get('code', '').strip().upper()
        coupon.description = request.form.get('description', '').strip()
        coupon.discount_type = request.form.get('discount_type', 'percent')
        coupon.discount_value = request.form.get('discount_value', 0, type=float)
        coupon.min_order_amount = request.form.get('min_order_amount', 0, type=float)
        coupon.max_uses = request.form.get('max_uses', 0, type=int)
        coupon.is_active = bool(request.form.get('is_active'))
        vf = request.form.get('valid_from', '')
        vt = request.form.get('valid_to', '')
        coupon.valid_from = datetime.strptime(vf, '%Y-%m-%d') if vf else datetime.utcnow()
        coupon.valid_to = datetime.strptime(vt, '%Y-%m-%d') if vt else None

        if not coupon_id:
            if Coupon.query.filter_by(code=coupon.code).first():
                flash('Coupon code already exists.', 'danger')
                return render_template('admin/coupon_form.html', coupon=coupon)
            db.session.add(coupon)

        db.session.commit()
        flash(f'Coupon "{coupon.code}" saved.', 'success')
        return redirect(url_for('admin.coupons'))

    return render_template('admin/coupon_form.html', coupon=coupon)


@admin_bp.route('/coupons/<int:coupon_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_coupon(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    coupon.is_active = not coupon.is_active
    db.session.commit()
    flash(f'Coupon {coupon.code} {"activated" if coupon.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin.coupons'))


# ── Tailors ────────────────────────────────────────────────
@admin_bp.route('/tailors')
@login_required
@admin_required
def tailors():
    tailors_list = TailorProfile.query.join(User).order_by(User.name).all()
    return render_template('admin/tailors.html', tailors=tailors_list)


@admin_bp.route('/tailors/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_tailor():
    designs = Design.query.filter_by(is_active=True).all()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        shop_name = request.form.get('shop_name', '').strip()
        address = request.form.get('address', '').strip()

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('admin/add_tailor.html', designs=designs)

        user = User(name=name, email=email, phone=phone, role='tailor')
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        try:
            lat = float(request.form.get('latitude', 0) or 0)
            lng = float(request.form.get('longitude', 0) or 0)
        except ValueError:
            lat = lng = 0.0

        specs = request.form.getlist('specializations')
        profile = TailorProfile(
            user_id=user.id,
            shop_name=shop_name or f"{name}'s Tailor Shop",
            address=address,
            latitude=lat,
            longitude=lng,
        )
        profile.set_specializations(specs)
        db.session.add(profile)
        db.session.commit()
        flash(f'Tailor {name} added successfully.', 'success')
        return redirect(url_for('admin.tailors'))

    return render_template('admin/add_tailor.html', designs=designs)


@admin_bp.route('/tailors/<int:tailor_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_tailor(tailor_id):
    tailor = TailorProfile.query.get_or_404(tailor_id)
    tailor.is_active = not tailor.is_active
    db.session.commit()
    state = 'activated' if tailor.is_active else 'deactivated'
    flash(f'Tailor {tailor.shop_name} {state}.', 'success')
    return redirect(url_for('admin.tailors'))


# ── Users ──────────────────────────────────────────────────
@admin_bp.route('/users')
@login_required
@admin_required
def users():
    role_filter = request.args.get('role', '')
    q = User.query.order_by(User.created_at.desc())
    if role_filter:
        q = q.filter_by(role=role_filter)
    return render_template('admin/users.html', users=q.all(), role_filter=role_filter)


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'warning')
        return redirect(url_for('admin.users'))
    user.is_active = not user.is_active
    db.session.commit()
    flash(f'User {user.name} {"activated" if user.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/delivery-agents/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_delivery_agent():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('admin/add_delivery_agent.html')
        agent = User(name=name, email=email, phone=phone, role='delivery')
        agent.set_password(password)
        db.session.add(agent)
        db.session.commit()
        flash(f'Delivery agent {name} created.', 'success')
        return redirect(url_for('admin.users', role='delivery'))
    return render_template('admin/add_delivery_agent.html')


# ── Reviews ────────────────────────────────────────────────
@admin_bp.route('/reviews')
@login_required
@admin_required
def reviews():
    all_reviews = Review.query.order_by(Review.created_at.desc()).all()
    return render_template('admin/reviews.html', reviews=all_reviews)


# ── API: validate coupon ───────────────────────────────────
@admin_bp.route('/api/coupon/validate')
@login_required
def validate_coupon_api():
    code = request.args.get('code', '').strip().upper()
    amount = request.args.get('amount', 0, type=float)
    coupon = Coupon.query.filter_by(code=code).first()
    if not coupon:
        return jsonify({'valid': False, 'message': 'Coupon not found.'})
    discount, msg = coupon.compute_discount(amount)
    if discount == 0:
        return jsonify({'valid': False, 'message': msg or 'Invalid coupon.'})
    return jsonify({'valid': True, 'discount': discount,
                    'type': coupon.discount_type, 'value': coupon.discount_value,
                    'message': f'Coupon applied! You save Rs.{discount:.0f}.'})
