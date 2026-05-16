import os
import csv
import io
import json
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
from flask import render_template, redirect, url_for, flash, request, current_app, jsonify, Response
from flask_login import login_required, current_user
from app.blueprints.admin import admin_bp
from app.extensions import db
from app.models import (User, TailorProfile, Order, DeliveryAssignment, Design,
                        Coupon, Review, TailorMeasurementTemplate, Notification, notify,
                        generate_otp, ORDER_STATUSES,
                        ProductDesign, DesignVariant, DesignImage, TailorProductService,
                        StyleAgentConfig, StyleAgentAppointment, AdminConfig,
                        PaymentTransaction, PaymentAllocation)
from app.services.email_service import send_account_approved, send_account_rejected


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
        'pending_approvals': User.query.filter_by(approval_status='pending').count(),
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
    pending_approvals = User.query.filter_by(approval_status='pending').count()
    return jsonify({'unassigned': unassigned, 'new_orders': new_orders,
                    'pending_approvals': pending_approvals})


@admin_bp.route('/my-notifications')
@login_required
@admin_required
def my_notifications():
    notifs = (Notification.query
              .filter_by(user_id=current_user.id)
              .order_by(Notification.created_at.desc())
              .limit(60).all())
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return render_template('shared/notifications.html', notifications=notifs)


# ── Approvals ──────────────────────────────────────────────
@admin_bp.route('/approvals')
@login_required
@admin_required
def approvals():
    pending = User.query.filter_by(approval_status='pending').order_by(User.created_at.desc()).all()
    rejected = User.query.filter_by(approval_status='rejected').order_by(User.created_at.desc()).limit(20).all()
    return render_template('admin/approvals.html', pending=pending, rejected=rejected)


@admin_bp.route('/approvals/<int:user_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    user.approval_status = 'approved'
    user.is_active = True
    notify(user.id, 'Your registration has been approved. You can now log in.')
    db.session.commit()
    send_account_approved(user)   # fire-and-forget, won't crash if mail fails
    flash(f'{user.name} ({user.role}) has been approved and can now log in.', 'success')
    return redirect(url_for('admin.approvals'))


@admin_bp.route('/approvals/<int:user_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject_user(user_id):
    user = User.query.get_or_404(user_id)
    user.approval_status = 'rejected'
    user.is_active = False
    notify(user.id, 'Your registration was not approved. Please contact support for more details.')
    db.session.commit()
    send_account_rejected(user)   # fire-and-forget
    flash(f'{user.name}\'s registration has been rejected.', 'warning')
    return redirect(url_for('admin.approvals'))


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


@admin_bp.route('/orders/export')
@login_required
@admin_required
def export_orders():
    status_filter = request.args.get('status', '')
    q = Order.query.order_by(Order.created_at.desc())
    if status_filter:
        q = q.filter_by(status=status_filter)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Order #', 'Date', 'Customer', 'Customer Phone', 'Customer Email',
        'Tailor', 'Design', 'Status', 'Est. Price (Rs)', 'Final Price (Rs)',
        'Discount (Rs)', 'Coupon', 'Payable (Rs)',
        'Payment Method', 'Payment Status',
        'Pickup Address', 'Delivery Address',
        'Est. Days', 'ETA Date', 'Fabric', 'Special Instructions',
    ])
    for o in q.all():
        writer.writerow([
            o.order_number,
            o.created_at.strftime('%d-%m-%Y %H:%M'),
            o.customer.name, o.customer.phone, o.customer.email,
            o.tailor.shop_name, o.design.name, o.status_label(),
            o.estimated_price or '', o.final_price or '',
            o.discount_amount or 0, o.coupon_code or '', o.payable_amount(),
            o.payment_method_label(), o.payment_status_label(),
            o.pickup_address, o.delivery_address,
            o.estimated_days or '', o.eta_date() or '',
            o.fabric_description, o.special_instructions,
        ])

    filename = f"orders_{status_filter or 'all'}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv"
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


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
                           assignments=assignments, history=history,
                           order_statuses=ORDER_STATUSES)


@admin_bp.route('/orders/<int:order_id>/dispute', methods=['POST'])
@login_required
@admin_required
def order_dispute(order_id):
    order = Order.query.get_or_404(order_id)
    admin_note = request.form.get('admin_note', '').strip()
    force_status = request.form.get('force_status', '').strip()
    valid_statuses = [s for s, _ in ORDER_STATUSES]

    if admin_note:
        order.admin_note = admin_note

    if force_status and force_status in valid_statuses and force_status != order.status:
        note = f'[Admin Override] {admin_note}' if admin_note else '[Admin Override]'
        order.add_status(force_status, note=note, changed_by_id=current_user.id)
        notify(order.customer_id,
               f'Order {order.order_number} was updated by admin: "{order.status_label()}".',
               url_for('customer.order_detail', order_id=order.id))
        flash(f'Order status forced to "{order.status_label()}".', 'warning')
    elif admin_note:
        flash('Admin note saved.', 'success')

    db.session.commit()
    return redirect(url_for('admin.order_detail', order_id=order_id))


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


@admin_bp.route('/tailors/<int:tailor_id>/offers', methods=['GET', 'POST'])
@login_required
@admin_required
def tailor_offers(tailor_id):
    tailor = TailorProfile.query.get_or_404(tailor_id)
    designs = Design.query.filter_by(is_active=True).all()
    specs = tailor.get_specializations()

    if request.method == 'POST':
        for design in designs:
            if design.name not in specs:
                continue
            offer_val = request.form.get(f'offer_{design.id}', '').strip()
            tmpl = tailor.get_measurement_template(design.id)
            if not tmpl:
                tmpl = TailorMeasurementTemplate(tailor_id=tailor.id, design_id=design.id)
                db.session.add(tmpl)
                db.session.flush()
            tmpl.admin_offer_price = float(offer_val) if offer_val else None
        db.session.commit()
        flash('Offer prices updated successfully.', 'success')
        return redirect(url_for('admin.tailor_offers', tailor_id=tailor_id))

    templates = {t.design_id: t for t in tailor.measurement_templates.all()}
    return render_template('admin/tailor_offers.html',
                           tailor=tailor, designs=designs,
                           specs=specs, templates=templates)


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


# ── Analytics ─────────────────────────────────────────────
@admin_bp.route('/analytics')
@login_required
@admin_required
def analytics():
    # Revenue & order count by week (last 8 weeks)
    weekly = []
    for i in range(7, -1, -1):
        week_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        week_start -= timedelta(days=week_start.weekday() + i * 7)
        week_end = week_start + timedelta(days=7)
        orders_in_week = Order.query.filter(
            Order.created_at >= week_start,
            Order.created_at < week_end,
            Order.status.notin_(['rejected', 'cancelled'])
        ).all()
        revenue = sum((o.final_price or o.estimated_price or 0) for o in orders_in_week)
        weekly.append({
            'label': week_start.strftime('%d %b'),
            'orders': len(orders_in_week),
            'revenue': round(revenue, 2),
        })

    # Orders by design
    designs = Design.query.filter_by(is_active=True).all()
    design_stats = []
    for d in designs:
        count = Order.query.filter_by(design_id=d.id).filter(
            Order.status.notin_(['rejected', 'cancelled'])
        ).count()
        design_stats.append({'name': d.name, 'count': count})
    design_stats.sort(key=lambda x: x['count'], reverse=True)

    # Orders by status
    status_stats = []
    for val, label in ORDER_STATUSES:
        count = Order.query.filter_by(status=val).count()
        if count:
            status_stats.append({'status': label, 'count': count})

    # Top 5 tailors by completed orders
    tailors_all = TailorProfile.query.filter_by(is_active=True).all()
    tailor_stats = []
    for t in tailors_all:
        completed = t.orders.filter_by(status='delivered').count()
        revenue = sum(
            (o.final_price or o.estimated_price or 0)
            for o in t.orders.filter_by(status='delivered').all()
        )
        tailor_stats.append({
            'name': t.shop_name,
            'completed': completed,
            'revenue': round(revenue, 2),
            'rating': t.rating,
        })
    tailor_stats.sort(key=lambda x: x['completed'], reverse=True)
    top_tailors = tailor_stats[:5]

    # Summary cards
    total_revenue = sum(
        (o.final_price or o.estimated_price or 0)
        for o in Order.query.filter_by(status='delivered').all()
    )
    summary = {
        'total_revenue': round(total_revenue, 2),
        'total_orders': Order.query.count(),
        'delivered': Order.query.filter_by(status='delivered').count(),
        'active': Order.query.filter(
            Order.status.notin_(['placed', 'delivered', 'rejected', 'cancelled'])
        ).count(),
    }

    return render_template('admin/analytics.html',
                           weekly=weekly, design_stats=design_stats,
                           status_stats=status_stats, top_tailors=top_tailors,
                           summary=summary)


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


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — CATALOGUE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def _save_catalogue_image(file, subfolder='catalogue'):
    """Save uploaded image to uploads/catalogue/ and return filename."""
    if not file or not allowed_file(file.filename):
        return None
    filename = secure_filename(file.filename)
    import time
    filename = f"{int(time.time())}_{filename}"
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], subfolder)
    os.makedirs(upload_dir, exist_ok=True)
    file.save(os.path.join(upload_dir, filename))
    return filename


@admin_bp.route('/catalogue')
@login_required
@admin_required
def catalogue():
    """List all product designs grouped by category."""
    categories = Design.query.filter_by(is_active=True).order_by(Design.name).all()
    all_designs = ProductDesign.query.order_by(
        ProductDesign.design_id, ProductDesign.display_order
    ).all()
    return render_template('admin/catalogue.html',
                           categories=categories, all_designs=all_designs)


@admin_bp.route('/catalogue/new', methods=['GET', 'POST'])
@login_required
@admin_required
def catalogue_new():
    categories = Design.query.filter_by(is_active=True).order_by(Design.name).all()
    if request.method == 'POST':
        design_id = request.form.get('design_id', type=int)
        name = request.form.get('name', '').strip()
        if not design_id or not name:
            flash('Category and name are required.', 'danger')
            return render_template('admin/catalogue_form.html', categories=categories,
                                   product_design=None)

        fabric_list = [f.strip() for f in request.form.get('fabric_suggestions', '').split(',') if f.strip()]
        pd = ProductDesign(
            design_id=design_id,
            name=name,
            description=request.form.get('description', '').strip(),
            base_price_modifier=float(request.form.get('base_price_modifier') or 0),
            fabric_suggestions=json.dumps(fabric_list),
            display_order=int(request.form.get('display_order') or 0),
        )
        db.session.add(pd)
        db.session.flush()

        # Handle main image upload
        img_file = request.files.get('main_image')
        if img_file and img_file.filename:
            fn = _save_catalogue_image(img_file)
            if fn:
                db.session.add(DesignImage(product_design_id=pd.id,
                                           image_filename=fn, image_type='main', display_order=0))

        db.session.commit()
        flash(f'"{pd.name}" added to catalogue.', 'success')
        return redirect(url_for('admin.catalogue_detail', design_id=pd.id))

    return render_template('admin/catalogue_form.html', categories=categories, product_design=None)


@admin_bp.route('/catalogue/<int:design_id>')
@login_required
@admin_required
def catalogue_detail(design_id):
    pd = ProductDesign.query.get_or_404(design_id)
    tailors = TailorProfile.query.filter_by(is_active=True).all()
    services = {s.tailor_id: s for s in pd.tailor_services.all()}
    return render_template('admin/catalogue_detail.html', pd=pd,
                           tailors=tailors, services=services)


@admin_bp.route('/catalogue/<int:design_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def catalogue_edit(design_id):
    pd = ProductDesign.query.get_or_404(design_id)
    categories = Design.query.filter_by(is_active=True).order_by(Design.name).all()
    if request.method == 'POST':
        pd.design_id = request.form.get('design_id', type=int) or pd.design_id
        pd.name = request.form.get('name', pd.name).strip()
        pd.description = request.form.get('description', '').strip()
        pd.base_price_modifier = float(request.form.get('base_price_modifier') or 0)
        fabric_list = [f.strip() for f in request.form.get('fabric_suggestions', '').split(',') if f.strip()]
        pd.fabric_suggestions = json.dumps(fabric_list)
        pd.display_order = int(request.form.get('display_order') or 0)

        img_file = request.files.get('main_image')
        if img_file and img_file.filename:
            fn = _save_catalogue_image(img_file)
            if fn:
                existing = pd.images.filter_by(image_type='main').first()
                if existing:
                    existing.image_filename = fn
                else:
                    db.session.add(DesignImage(product_design_id=pd.id,
                                               image_filename=fn, image_type='main', display_order=0))

        db.session.commit()
        flash('Catalogue design updated.', 'success')
        return redirect(url_for('admin.catalogue_detail', design_id=pd.id))

    return render_template('admin/catalogue_form.html', categories=categories, product_design=pd)


@admin_bp.route('/catalogue/<int:design_id>/toggle', methods=['POST'])
@login_required
@admin_required
def catalogue_toggle(design_id):
    pd = ProductDesign.query.get_or_404(design_id)
    pd.is_active = not pd.is_active
    db.session.commit()
    flash(f'"{pd.name}" {"activated" if pd.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin.catalogue'))


# ── Variants ────────────────────────────────────────────────────────────────

@admin_bp.route('/catalogue/<int:design_id>/variants/add', methods=['POST'])
@login_required
@admin_required
def variant_add(design_id):
    pd = ProductDesign.query.get_or_404(design_id)
    group = request.form.get('variant_group', '').strip()
    options_raw = request.form.get('variant_options', '').strip()
    if not group or not options_raw:
        flash('Variant group and at least one option are required.', 'danger')
        return redirect(url_for('admin.catalogue_detail', design_id=design_id))

    opts = [o.strip() for o in options_raw.split(',') if o.strip()]
    v = DesignVariant(
        product_design_id=pd.id,
        variant_group=group,
        variant_options=json.dumps(opts),
        price_modifier=float(request.form.get('price_modifier') or 0),
        display_order=int(request.form.get('display_order') or 0),
    )
    db.session.add(v)
    db.session.commit()
    flash(f'Variant "{group}" added.', 'success')
    return redirect(url_for('admin.catalogue_detail', design_id=design_id))


@admin_bp.route('/variants/<int:variant_id>/delete', methods=['POST'])
@login_required
@admin_required
def variant_delete(variant_id):
    v = DesignVariant.query.get_or_404(variant_id)
    design_id = v.product_design_id
    db.session.delete(v)
    db.session.commit()
    flash('Variant removed.', 'success')
    return redirect(url_for('admin.catalogue_detail', design_id=design_id))


# ── Tailor Service Mapping ──────────────────────────────────────────────────

@admin_bp.route('/catalogue/<int:design_id>/services/save', methods=['POST'])
@login_required
@admin_required
def tailor_service_save(design_id):
    pd = ProductDesign.query.get_or_404(design_id)
    tailor_id = request.form.get('tailor_id', type=int)
    if not tailor_id:
        flash('Select a tailor.', 'danger')
        return redirect(url_for('admin.catalogue_detail', design_id=design_id))

    svc = TailorProductService.query.filter_by(
        tailor_id=tailor_id, product_design_id=pd.id).first()
    if not svc:
        svc = TailorProductService(tailor_id=tailor_id, product_design_id=pd.id)
        db.session.add(svc)

    price_val = request.form.get('custom_price', '').strip()
    svc.custom_price = float(price_val) if price_val else None
    svc.estimated_days = int(request.form.get('estimated_days') or 7)
    svc.expertise_level = request.form.get('expertise_level', 'intermediate')
    svc.is_available = 'is_available' in request.form

    db.session.commit()
    flash('Tailor service saved.', 'success')
    return redirect(url_for('admin.catalogue_detail', design_id=design_id))


@admin_bp.route('/catalogue/services/<int:service_id>/delete', methods=['POST'])
@login_required
@admin_required
def tailor_service_delete(service_id):
    svc = TailorProductService.query.get_or_404(service_id)
    design_id = svc.product_design_id
    db.session.delete(svc)
    db.session.commit()
    flash('Tailor removed from this design.', 'success')
    return redirect(url_for('admin.catalogue_detail', design_id=design_id))


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — STYLE AGENT APPOINTMENTS
# ═══════════════════════════════════════════════════════════════════════════════

@admin_bp.route('/appointments')
@login_required
@admin_required
def appointments():
    status_filter = request.args.get('status', '')
    q = StyleAgentAppointment.query.order_by(
        StyleAgentAppointment.appointment_date.desc(),
        StyleAgentAppointment.appointment_time.desc()
    )
    if status_filter:
        q = q.filter_by(status=status_filter)
    appts = q.all()
    agents = User.query.filter_by(role='delivery', is_active=True).all()
    return render_template('admin/appointments.html', appointments=appts,
                           agents=agents, status_filter=status_filter)


@admin_bp.route('/appointments/<int:appt_id>/assign', methods=['POST'])
@login_required
@admin_required
def appointment_assign(appt_id):
    appt = StyleAgentAppointment.query.get_or_404(appt_id)
    agent_id = request.form.get('agent_id', type=int)
    if not agent_id:
        flash('Select a Style Agent.', 'danger')
        return redirect(url_for('admin.appointments'))
    appt.style_agent_id = agent_id
    appt.status = 'agent_assigned'
    db.session.commit()
    flash('Style Agent assigned.', 'success')
    return redirect(url_for('admin.appointments'))


@admin_bp.route('/appointments/<int:appt_id>/confirm', methods=['POST'])
@login_required
@admin_required
def appointment_confirm(appt_id):
    appt = StyleAgentAppointment.query.get_or_404(appt_id)
    appt.status = 'confirmed'
    db.session.commit()
    try:
        from app.services import email_service
        email_service.send_appointment_confirmed(appt)
    except Exception:
        pass
    flash('Appointment confirmed and customer notified.', 'success')
    return redirect(url_for('admin.appointments'))


@admin_bp.route('/appointments/<int:appt_id>/cancel', methods=['POST'])
@login_required
@admin_required
def appointment_cancel(appt_id):
    appt = StyleAgentAppointment.query.get_or_404(appt_id)
    appt.status = 'cancelled'
    db.session.commit()
    flash('Appointment cancelled.', 'warning')
    return redirect(url_for('admin.appointments'))


# ── Style Agent Schedule Config ─────────────────────────────────────────────

@admin_bp.route('/schedule-config')
@login_required
@admin_required
def schedule_config():
    configs = StyleAgentConfig.query.order_by(StyleAgentConfig.created_at).all()
    return render_template('admin/schedule_config.html', configs=configs)


@admin_bp.route('/schedule-config/save', methods=['POST'])
@login_required
@admin_required
def schedule_config_save():
    config_id = request.form.get('config_id', type=int)
    cfg = StyleAgentConfig.query.get(config_id) if config_id else StyleAgentConfig()

    cfg.config_name = request.form.get('config_name', '').strip()
    cfg.start_hour = int(request.form.get('start_hour') or 10)
    cfg.end_hour = int(request.form.get('end_hour') or 18)
    cfg.slot_duration_minutes = int(request.form.get('slot_duration_minutes') or 30)
    cfg.is_active = 'is_active' in request.form

    if not cfg.id:
        db.session.add(cfg)
    db.session.commit()
    flash('Schedule configuration saved.', 'success')
    return redirect(url_for('admin.schedule_config'))


@admin_bp.route('/schedule-config/<int:cfg_id>/delete', methods=['POST'])
@login_required
@admin_required
def schedule_config_delete(cfg_id):
    cfg = StyleAgentConfig.query.get_or_404(cfg_id)
    db.session.delete(cfg)
    db.session.commit()
    flash('Config deleted.', 'success')
    return redirect(url_for('admin.schedule_config'))


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — FINANCIAL DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

@admin_bp.route('/financial')
@login_required
@admin_required
def financial():
    from sqlalchemy import func
    total_revenue = db.session.query(func.sum(PaymentTransaction.amount)).filter_by(
        status='success').scalar() or 0
    total_refunds = db.session.query(func.sum(PaymentTransaction.amount)).filter(
        PaymentTransaction.status.in_(['refunded', 'refund_initiated'])).scalar() or 0
    pending_payouts = db.session.query(func.sum(PaymentAllocation.amount)).filter_by(
        payout_status='pending').scalar() or 0

    recent_txns = (PaymentTransaction.query
                   .order_by(PaymentTransaction.created_at.desc())
                   .limit(50).all())
    tailor_earnings = (
        db.session.query(
            TailorProfile.shop_name,
            func.sum(PaymentAllocation.amount).label('total')
        )
        .join(PaymentAllocation, PaymentAllocation.recipient_id == TailorProfile.id)
        .filter(PaymentAllocation.recipient_type == 'tailor',
                PaymentAllocation.payout_status == 'pending')
        .group_by(TailorProfile.id)
        .all()
    )
    return render_template('admin/financial.html',
                           total_revenue=total_revenue,
                           total_refunds=total_refunds,
                           pending_payouts=pending_payouts,
                           recent_txns=recent_txns,
                           tailor_earnings=tailor_earnings)


@admin_bp.route('/financial/payout/<int:alloc_id>', methods=['POST'])
@login_required
@admin_required
def mark_payout(alloc_id):
    alloc = PaymentAllocation.query.get_or_404(alloc_id)
    alloc.payout_status = 'processed'
    alloc.payout_date = datetime.utcnow()
    db.session.commit()
    flash('Payout marked as processed.', 'success')
    return redirect(url_for('admin.financial'))


@admin_bp.route('/financial/refund/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def initiate_refund(order_id):
    order = Order.query.get_or_404(order_id)
    from app.services import payment_service
    txn = payment_service.initiate_refund(order)
    if txn:
        flash(f'Refund initiated for order #{order.order_number}.', 'success')
    else:
        flash('No successful payment found for this order.', 'warning')
    return redirect(url_for('admin.financial'))


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN SETTINGS — System Configuration
# ═══════════════════════════════════════════════════════════════════════════════

@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    from app.models import AdminConfig
    config = AdminConfig.get()

    if request.method == 'POST':
        config.tailor_acceptance_window_hours = request.form.get('tailor_window', 2, type=int)
        enable_slot = request.form.get('enable_slot_booking')
        config.enable_style_agent_slot_booking = enable_slot == 'on'
        auto_confirm = request.form.get('auto_confirm')
        config.auto_confirm_orders_if_no_response = auto_confirm == 'on'
        db.session.commit()
        flash('Settings updated successfully.', 'success')
        return redirect(url_for('admin.settings'))

    return render_template('admin/settings.html', config=config)


# ═══════════════════════════════════════════════════════════════════════════════
# STYLE AGENT ASSIGNMENT — Manual assignment when slot booking disabled
# ═══════════════════════════════════════════════════════════════════════════════

@admin_bp.route('/orders/<int:order_id>/assign-style-agent', methods=['GET', 'POST'])
@login_required
@admin_required
def assign_style_agent(order_id):
    order = Order.query.get_or_404(order_id)

    # Guard: style agent assignment only makes sense after tailor has accepted
    if order.status != 'accepted':
        flash('Style agent can only be assigned after the tailor has accepted the order.', 'warning')
        return redirect(url_for('admin.order_detail', order_id=order_id))

    if request.method == 'POST':
        agent_id = request.form.get('style_agent_id', type=int)
        agent = User.query.filter_by(id=agent_id, role='delivery').first_or_404()

        # Allow admin to override the slot date/time if needed
        new_date = request.form.get('visit_date', '').strip()
        new_time = request.form.get('visit_time', '').strip()
        if new_date:
            order.style_agent_appointment_date = new_date
        if new_time:
            order.style_agent_appointment_time = new_time

        order.auto_assigned_style_agent_id = agent.id
        order.admin_assigned_at = datetime.utcnow()
        order.customer_confirmed_slot = False
        db.session.commit()

        slot_info = ''
        if order.style_agent_appointment_date:
            slot_info = f' for {order.style_agent_appointment_date} @ {order.style_agent_appointment_time}'

        # Notify customer to confirm the assigned slot
        Notification.create(
            user_id=order.customer_id,
            title='Style Agent Assigned',
            body=f'{agent.name} has been assigned as your Style Agent for order #{order.order_number}{slot_info}. Please confirm this assignment.',
            type='info',
            order_id=order.id,
        )
        db.session.commit()

        try:
            from app.services import email_service
            email_service.send_style_agent_assigned(order, agent)
        except Exception:
            pass

        flash(f'Style Agent {agent.name} assigned to order #{order.order_number}.', 'success')
        return redirect(url_for('admin.order_detail', order_id=order_id))

    # Get all available delivery agents
    agents = User.query.filter_by(role='delivery', is_active=True).all()
    return render_template('admin/assign_style_agent.html', order=order, agents=agents)
