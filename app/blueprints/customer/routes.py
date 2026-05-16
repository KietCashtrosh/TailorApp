import json
import math
from functools import wraps
from flask import render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from app.blueprints.customer import customer_bp
from app.extensions import db
from app.models import (TailorProfile, Design, Order, CustomerMeasurement,
                        Coupon, Review, CartItem, Notification, notify,
                        FamilyProfile, Message, generate_order_number,
                        ProductDesign, TailorProductService,
                        TailorMeasurementTemplate,
                        StyleAgentConfig, StyleAgentAppointment, AdminConfig)
from app.services.email_service import send_order_placed, send_order_delivered


def customer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'customer':
            flash('Please log in as a customer to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_active_profile():
    """Return the currently active FamilyProfile for the logged-in customer, or None."""
    profile_id = session.get('active_profile_id')
    if profile_id and current_user.is_authenticated:
        return FamilyProfile.query.filter_by(id=profile_id, user_id=current_user.id).first()
    return None


# ── Family Profiles ──────────────────────────────────────────

@customer_bp.route('/profiles')
@login_required
@customer_required
def profiles():
    all_profiles = FamilyProfile.query.filter_by(user_id=current_user.id).order_by(FamilyProfile.created_at).all()
    active = get_active_profile()
    return render_template('customer/profiles.html', profiles=all_profiles, active_profile=active)


@customer_bp.route('/profiles/select')
@login_required
@customer_required
def select_profile():
    all_profiles = FamilyProfile.query.filter_by(user_id=current_user.id).order_by(FamilyProfile.created_at).all()
    active = get_active_profile()
    return render_template('customer/select_profile.html', profiles=all_profiles, active_profile=active)


@customer_bp.route('/profiles/new', methods=['GET', 'POST'])
@login_required
@customer_required
def profile_new():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        relation = request.form.get('relation', '').strip()
        gender = request.form.get('gender', '').strip()
        date_of_birth = request.form.get('date_of_birth', '').strip()
        avatar_color = request.form.get('avatar_color', '#6f42c1').strip()
        if not name:
            flash('Name is required.', 'danger')
            return render_template('customer/profile_form.html', profile=None)
        fp = FamilyProfile(user_id=current_user.id, name=name, relation=relation,
                           gender=gender, date_of_birth=date_of_birth, avatar_color=avatar_color)
        db.session.add(fp)
        db.session.commit()
        flash(f'Profile for {name} created.', 'success')
        return redirect(url_for('customer.profiles'))
    return render_template('customer/profile_form.html', profile=None)


@customer_bp.route('/profiles/<int:profile_id>/edit', methods=['GET', 'POST'])
@login_required
@customer_required
def profile_edit(profile_id):
    fp = FamilyProfile.query.filter_by(id=profile_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        fp.name = request.form.get('name', fp.name).strip()
        fp.relation = request.form.get('relation', fp.relation).strip()
        fp.gender = request.form.get('gender', fp.gender).strip()
        fp.date_of_birth = request.form.get('date_of_birth', fp.date_of_birth).strip()
        fp.avatar_color = request.form.get('avatar_color', fp.avatar_color).strip()
        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('customer.profiles'))
    return render_template('customer/profile_form.html', profile=fp)


@customer_bp.route('/profiles/<int:profile_id>/delete', methods=['POST'])
@login_required
@customer_required
def profile_delete(profile_id):
    fp = FamilyProfile.query.filter_by(id=profile_id, user_id=current_user.id).first_or_404()
    if session.get('active_profile_id') == profile_id:
        session.pop('active_profile_id', None)
    db.session.delete(fp)
    db.session.commit()
    flash('Profile deleted.', 'info')
    return redirect(url_for('customer.profiles'))


@customer_bp.route('/profiles/<int:profile_id>/activate', methods=['POST'])
@login_required
@customer_required
def profile_activate(profile_id):
    fp = FamilyProfile.query.filter_by(id=profile_id, user_id=current_user.id).first_or_404()
    session['active_profile_id'] = fp.id
    flash(f'Ordering as {fp.name}.', 'success')
    next_url = request.form.get('next') or url_for('customer.home')
    return redirect(next_url)


@customer_bp.route('/profiles/clear', methods=['POST'])
@login_required
@customer_required
def profile_clear():
    # Set to None (not pop) so the key EXISTS in session.
    # home() checks 'key not in session' → None means "myself, don't redirect again"
    session['active_profile_id'] = None
    flash('Switched to ordering for yourself.', 'info')
    next_url = request.form.get('next') or request.referrer or url_for('customer.home')
    return redirect(next_url)


@customer_bp.route('/')
def home():
    # Remember-me / persistent-session guard:
    # 'active_profile_id' key absent  → user hasn't chosen yet → show selector
    # 'active_profile_id' = None      → user chose "myself" / skipped → OK
    # 'active_profile_id' = <id>      → user chose a family profile → OK
    if current_user.is_authenticated and current_user.role == 'customer':
        if 'active_profile_id' not in session:
            has_profiles = FamilyProfile.query.filter_by(
                user_id=current_user.id).count() > 0
            if has_profiles:
                return redirect(url_for('customer.select_profile'))

    designs = Design.query.filter_by(is_active=True).all()
    featured_tailors = TailorProfile.query.filter_by(is_active=True).limit(6).all()
    return render_template('customer/home.html', designs=designs,
                           featured_tailors=featured_tailors)


@customer_bp.route('/tailors')
def tailors():
    design_filter = request.args.get('design', '')
    search = request.args.get('search', '').strip()
    user_lat = request.args.get('lat', type=float)
    user_lng = request.args.get('lng', type=float)
    min_rating = request.args.get('min_rating', type=float)
    sort_by = request.args.get('sort', '')  # distance | rating | price_asc | price_desc

    from flask import current_app
    default_sort = current_app.config.get('DEFAULT_TAILOR_SORT', 'distance')
    if not sort_by:
        sort_by = default_sort

    q = TailorProfile.query.filter_by(is_active=True, is_available=True)
    selected_design = None
    if design_filter:
        q = q.filter(TailorProfile.specializations.contains(design_filter))
        selected_design = Design.query.filter_by(name=design_filter, is_active=True).first()
    if search:
        q = q.filter(TailorProfile.shop_name.ilike(f'%{search}%') |
                     TailorProfile.address.ilike(f'%{search}%'))
    if min_rating:
        q = q.filter(TailorProfile.rating >= min_rating)

    tailors_list = q.all()

    if user_lat and user_lng:
        for t in tailors_list:
            if t.latitude and t.longitude:
                t.distance = round(haversine(user_lat, user_lng, t.latitude, t.longitude), 1)
            else:
                t.distance = None
    else:
        for t in tailors_list:
            t.distance = None

    if sort_by == 'distance' and user_lat and user_lng:
        tailors_list.sort(key=lambda t: (t.distance is None, t.distance or 9999))
    elif sort_by == 'rating' or (sort_by == 'distance' and not user_lat):
        tailors_list.sort(key=lambda t: t.rating, reverse=True)
    elif sort_by == 'price_asc':
        tailors_list.sort(key=lambda t: min(
            (tmpl.effective_price() for tmpl in t.measurement_templates.all()), default=0))
    elif sort_by == 'price_desc':
        tailors_list.sort(key=lambda t: min(
            (tmpl.effective_price() for tmpl in t.measurement_templates.all()), default=0),
            reverse=True)

    designs = Design.query.filter_by(is_active=True).all()
    return render_template('customer/tailors.html', tailors=tailors_list,
                           designs=designs, design_filter=design_filter,
                           selected_design=selected_design,
                           search=search, user_lat=user_lat, user_lng=user_lng,
                           min_rating=min_rating, sort_by=sort_by)


@customer_bp.route('/tailors/<int:tailor_id>')
def tailor_detail(tailor_id):
    tailor = TailorProfile.query.filter_by(id=tailor_id, is_active=True).first_or_404()
    design_id = request.args.get('design_id', type=int)
    designs = Design.query.filter_by(is_active=True).all()
    specs = tailor.get_specializations()
    # Build per-design price (tailor custom or global base)
    design_prices = {}
    for d in designs:
        tmpl = tailor.get_measurement_template(d.id)
        design_prices[d.id] = tmpl.effective_price() if tmpl else d.base_price
    return render_template('customer/tailor_detail.html', tailor=tailor,
                           designs=designs, specs=specs, design_prices=design_prices,
                           selected_design_id=design_id)


@customer_bp.route('/design/<int:design_id>')
def design_showcase(design_id):
    """New design-first browse page: pick variants then choose tailor."""
    design = Design.query.filter_by(id=design_id, is_active=True).first_or_404()

    # Tailors with an explicit measurement template for this design
    templates = TailorMeasurementTemplate.query.filter_by(design_id=design_id).all()
    seen_ids = set()
    tailor_data = []
    for tmpl in templates:
        if tmpl.tailor_id in seen_ids:
            continue
        t = TailorProfile.query.filter_by(
            id=tmpl.tailor_id, is_active=True, is_available=True).first()
        if t:
            seen_ids.add(t.id)
            tailor_data.append({
                'tailor': t,
                'price': tmpl.effective_price(),
                'original_price': tmpl.offer_original_price(),
            })

    # Fallback: tailors with design in specialisations but no explicit template
    fallback = TailorProfile.query.filter_by(
        is_active=True, is_available=True
    ).filter(TailorProfile.specializations.contains(design.name)).all()
    for t in fallback:
        if t.id not in seen_ids:
            seen_ids.add(t.id)
            tailor_data.append({
                'tailor': t,
                'price': design.base_price,
                'original_price': None,
            })

    tailor_data.sort(key=lambda x: x['tailor'].rating, reverse=True)

    return render_template(
        'customer/design_showcase.html',
        design=design,
        tailor_data=tailor_data,
        design_options=design.get_design_options(),
    )


@customer_bp.route('/order/new', methods=['GET', 'POST'])
@login_required
@customer_required
def place_order():
    tailor_id = request.args.get('tailor_id', type=int)
    design_id = request.args.get('design_id', type=int)

    tailor = TailorProfile.query.filter_by(id=tailor_id, is_active=True).first() if tailor_id else None
    design = Design.query.get(design_id) if design_id else None
    all_tailors = TailorProfile.query.filter_by(is_active=True).all()
    all_designs = Design.query.filter_by(is_active=True).all()

    saved_measurements = None
    if design_id:
        saved_measurements = CustomerMeasurement.query.filter_by(
            customer_id=current_user.id, design_id=design_id
        ).first()

    if request.method == 'POST':
        tailor_id = request.form.get('tailor_id', type=int)
        design_id = request.form.get('design_id', type=int)
        pickup_address = request.form.get('pickup_address', '').strip()
        delivery_address = request.form.get('delivery_address', '').strip()
        fabric_description = request.form.get('fabric_description', '').strip()
        special_instructions = request.form.get('special_instructions', '').strip()
        measurement_preference = request.form.get('measurement_preference', 'delivery_will_measure')
        coupon_code = request.form.get('coupon_code', '').strip().upper()
        payment_method = request.form.get('payment_method', 'cod')

        tailor = TailorProfile.query.get(tailor_id)
        design = Design.query.get(design_id)

        if not tailor or not design or not pickup_address or not delivery_address:
            flash('Please fill in all required fields.', 'danger')
            return render_template('customer/place_order.html',
                                   tailor=tailor, design=design,
                                   all_tailors=all_tailors, all_designs=all_designs,
                                   saved_measurements=saved_measurements)

        # Effective base price (tailor custom or global)
        tmpl = tailor.get_measurement_template(design_id)
        base_price = tmpl.effective_price() if tmpl else design.base_price

        # Measurements
        measurements = {}
        if measurement_preference == 'use_saved':
            saved = CustomerMeasurement.query.filter_by(
                customer_id=current_user.id, design_id=design_id
            ).first()
            if saved:
                measurements = saved.get_measurements()
        elif measurement_preference == 'provided_by_customer':
            fields = tmpl.get_measurement_fields() if tmpl else design.get_measurement_fields()
            for field in fields:
                val = request.form.get(f'measurement_{field["key"]}', '').strip()
                measurements[field['key']] = val
            _save_measurements(current_user.id, design_id, measurements, taken_by_id=None)

        # Coupon
        discount_amount = 0
        applied_code = ''
        if coupon_code:
            coupon = Coupon.query.filter_by(code=coupon_code).first()
            if coupon:
                discount, msg = coupon.compute_discount(base_price)
                if discount > 0:
                    discount_amount = discount
                    applied_code = coupon_code
                    coupon.uses_count += 1
                else:
                    flash(f'Coupon not applied: {msg}', 'warning')
            else:
                flash('Coupon code not found.', 'warning')

        # Collect selected design variants from the form (e.g. Neckline, Sleeve Style)
        design_options = design.get_design_options()
        selected_variants = {}
        for group in design_options:
            key = f"variant_{group['group'].replace(' ', '_')}"
            val = request.form.get(key, '').strip()
            if val:
                selected_variants[group['group']] = val

        order = Order(
            order_number=generate_order_number(),
            customer_id=current_user.id,
            tailor_id=tailor.id,
            design_id=design.id,
            measurements=json.dumps(measurements),
            measurement_preference=measurement_preference,
            special_instructions=special_instructions,
            fabric_description=fabric_description,
            pickup_address=pickup_address,
            delivery_address=delivery_address,
            estimated_price=base_price,
            discount_amount=discount_amount,
            coupon_code=applied_code,
            payment_method=payment_method,
            payment_status='cod_pending' if payment_method == 'cod' else 'unpaid',
            selected_variants=json.dumps(selected_variants),
        )
        db.session.add(order)
        db.session.flush()
        order.add_status('placed', note='Order placed by customer.',
                         changed_by_id=current_user.id)
        notify(tailor.user_id,
               f'New order {order.order_number} for {design.name} from {current_user.name}.',
               url_for('tailor.order_detail', order_id=order.id))
        db.session.commit()
        send_order_placed(order)   # email the customer
        flash(f'Order {order.order_number} placed successfully!', 'success')
        return redirect(url_for('customer.order_detail', order_id=order.id))

    return render_template('customer/place_order.html', tailor=tailor, design=design,
                           all_tailors=all_tailors, all_designs=all_designs,
                           saved_measurements=saved_measurements,
                           default_pickup=current_user.default_pickup_address or '',
                           default_delivery=current_user.default_delivery_address or '')


@customer_bp.route('/orders')
@login_required
@customer_required
def my_orders():
    page = request.args.get('page', 1, type=int)
    pagination = (current_user.customer_orders
                  .order_by(Order.created_at.desc())
                  .paginate(page=page, per_page=10, error_out=False))
    return render_template('customer/my_orders.html',
                           orders=pagination.items, pagination=pagination)


@customer_bp.route('/orders/<int:order_id>/cancel', methods=['POST'])
@login_required
@customer_required
def cancel_order(order_id):
    order = Order.query.filter_by(id=order_id, customer_id=current_user.id).first_or_404()
    if order.status != 'placed':
        flash('This order can no longer be cancelled.', 'warning')
        return redirect(url_for('customer.order_detail', order_id=order_id))
    reason = request.form.get('reason', '').strip() or 'Cancelled by customer.'
    order.add_status('cancelled', note=reason, changed_by_id=current_user.id)
    notify(order.tailor.user_id,
           f'Order {order.order_number} was cancelled by the customer.',
           url_for('tailor.order_detail', order_id=order.id))
    db.session.commit()
    flash('Order cancelled successfully.', 'success')
    return redirect(url_for('customer.my_orders'))


@customer_bp.route('/orders/<int:order_id>')
@login_required
@customer_required
def order_detail(order_id):
    order = Order.query.filter_by(id=order_id, customer_id=current_user.id).first_or_404()
    history = order.status_history.all()
    measurements = order.get_measurements()
    primary_design = order.get_primary_design()
    tmpl = order.tailor.get_measurement_template(order.design_id) if order.design_id else None
    if tmpl:
        design_fields = tmpl.get_measurement_fields()
    elif primary_design:
        design_fields = primary_design.get_measurement_fields()
    else:
        design_fields = []
    assignments = order.delivery_assignments.all()
    messages = order.messages.all()
    return render_template('customer/order_detail.html', order=order,
                           history=history, measurements=measurements,
                           design_fields=design_fields, assignments=assignments,
                           messages=messages)


@customer_bp.route('/orders/<int:order_id>/review', methods=['GET', 'POST'])
@login_required
@customer_required
def submit_review(order_id):
    order = Order.query.filter_by(id=order_id, customer_id=current_user.id).first_or_404()
    if order.status != 'delivered':
        flash('You can only review after delivery is complete.', 'warning')
        return redirect(url_for('customer.order_detail', order_id=order_id))
    if order.review:
        flash('You have already submitted a review for this order.', 'info')
        return redirect(url_for('customer.order_detail', order_id=order_id))

    if request.method == 'POST':
        tailor_rating = request.form.get('tailor_rating', type=int)
        tailor_comment = request.form.get('tailor_comment', '').strip()
        delivery_rating = request.form.get('delivery_rating', type=int)
        delivery_comment = request.form.get('delivery_comment', '').strip()

        if not tailor_rating or tailor_rating not in range(1, 6):
            flash('Please provide a valid tailor rating (1-5).', 'danger')
            return render_template('customer/review.html', order=order)

        review = Review(
            order_id=order.id,
            customer_id=current_user.id,
            tailor_rating=tailor_rating,
            tailor_comment=tailor_comment,
            delivery_rating=delivery_rating,
            delivery_comment=delivery_comment,
        )
        db.session.add(review)

        # Recompute tailor rating average
        tailor = order.tailor
        all_reviews = [r for o in tailor.orders.all()
                       if o.review and o.review.tailor_rating]
        all_reviews_ratings = [o.review.tailor_rating for o in tailor.orders.all()
                                if o.review and o.review.tailor_rating]
        # Include current new rating
        all_reviews_ratings.append(tailor_rating)
        tailor.rating = round(sum(all_reviews_ratings) / len(all_reviews_ratings), 2)
        tailor.rating_count = len(all_reviews_ratings)

        db.session.commit()
        flash('Thank you for your review!', 'success')
        return redirect(url_for('customer.order_detail', order_id=order_id))

    return render_template('customer/review.html', order=order)


@customer_bp.route('/api/designs/<int:design_id>/fields')
def design_fields_api(design_id):
    tailor_id = request.args.get('tailor_id', type=int)
    design = Design.query.get_or_404(design_id)
    fields = design.get_measurement_fields()
    base_price = design.base_price

    if tailor_id:
        tailor = TailorProfile.query.get(tailor_id)
        if tailor:
            tmpl = tailor.get_measurement_template(design_id)
            if tmpl:
                fields = tmpl.get_measurement_fields()
                base_price = tmpl.effective_price()

    saved = None
    if current_user.is_authenticated:
        saved_rec = CustomerMeasurement.query.filter_by(
            customer_id=current_user.id, design_id=design_id
        ).first()
        if saved_rec:
            saved = saved_rec.get_measurements()

    return jsonify({'fields': fields, 'base_price': base_price, 'saved_measurements': saved})


@customer_bp.route('/api/coupon/validate')
@login_required
@customer_required
def validate_coupon():
    code = request.args.get('code', '').strip().upper()
    amount = request.args.get('amount', 0, type=float)
    coupon = Coupon.query.filter_by(code=code).first()
    if not coupon:
        return jsonify({'valid': False, 'message': 'Coupon not found.'})
    discount, msg = coupon.compute_discount(amount)
    if discount == 0:
        return jsonify({'valid': False, 'message': msg or 'Invalid coupon.'})
    return jsonify({'valid': True, 'discount': discount,
                    'message': f'Coupon applied! You save Rs.{discount:.0f}.'})


@customer_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@customer_required
def profile():
    if request.method == 'POST':
        current_user.name = request.form.get('name', current_user.name).strip()
        current_user.phone = request.form.get('phone', current_user.phone).strip()
        current_user.default_pickup_address = request.form.get('default_pickup_address', '').strip()
        current_user.default_delivery_address = request.form.get('default_delivery_address', '').strip()
        db.session.commit()
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('customer.profile'))
    return render_template('customer/profile.html')


@customer_bp.route('/measurements')
@login_required
@customer_required
def my_measurements():
    records = CustomerMeasurement.query.filter_by(
        customer_id=current_user.id
    ).order_by(CustomerMeasurement.updated_at.desc()).all()
    return render_template('customer/measurements.html', records=records)


# ── Cart ────────────────────────────────────────────────────

@customer_bp.route('/cart')
@login_required
@customer_required
def cart():
    from datetime import date, timedelta
    from flask import current_app

    items = CartItem.query.filter_by(customer_id=current_user.id).order_by(CartItem.created_at).all()
    # Attach effective price to each item
    for item in items:
        tmpl = item.tailor.get_measurement_template(item.design_id)
        item.effective_price = tmpl.effective_price() if tmpl else item.design.base_price
    total = sum(i.effective_price * i.quantity for i in items)

    # Load style agent slot config if enabled
    admin_config = AdminConfig.get()
    slot_config = None
    slots = []
    min_date = ''
    max_date = ''

    if admin_config.enable_style_agent_slot_booking:
        slot_config = (StyleAgentConfig.query
                       .filter_by(is_active=True)
                       .order_by(StyleAgentConfig.start_hour)
                       .first())
        if not slot_config:
            class _Default:
                start_hour, end_hour, slot_duration_minutes = 10, 18, 30
                def generate_slots(self):
                    s, cur, end = [], self.start_hour * 60, self.end_hour * 60
                    while cur < end:
                        h, m = divmod(cur, 60)
                        s.append(f'{h:02d}:{m:02d}')
                        cur += self.slot_duration_minutes
                    return s
            slot_config = _Default()
        slots = slot_config.generate_slots()
        advance_days = current_app.config.get('BOOKING_ADVANCE_DAYS', 30)
        today = date.today()
        min_date = (today + timedelta(days=1)).isoformat()
        max_date = (today + timedelta(days=advance_days)).isoformat()

    return render_template('customer/cart.html', items=items, total=total,
                           default_pickup=current_user.default_pickup_address or '',
                           default_delivery=current_user.default_delivery_address or '',
                           admin_config=admin_config, slots=slots, min_date=min_date, max_date=max_date)


@customer_bp.route('/cart/add', methods=['GET', 'POST'])
@login_required
@customer_required
def cart_add():
    if request.method == 'GET':
        tailor_id = request.args.get('tailor_id', type=int)
        design_id = request.args.get('design_id', type=int)
        tailor = TailorProfile.query.filter_by(id=tailor_id, is_active=True).first_or_404()
        design = Design.query.filter_by(id=design_id, is_active=True).first_or_404()
        tmpl = tailor.get_measurement_template(design_id)
        fields = tmpl.get_measurement_fields() if tmpl else design.get_measurement_fields()
        price = tmpl.effective_price() if tmpl else design.base_price
        saved = CustomerMeasurement.query.filter_by(
            customer_id=current_user.id, design_id=design_id).first()
        design_options = design.get_design_options()
        # Pre-select variants passed from the design showcase page
        url_variants = {}
        for group in design_options:
            val = request.args.get(f'v_{group["group"]}', '').strip()
            if val:
                url_variants[group['group']] = val
        return render_template('customer/cart_add.html', tailor=tailor, design=design,
                               fields=fields, price=price, saved_measurements=saved,
                               design_options=design_options, url_variants=url_variants)
    tailor_id = request.form.get('tailor_id', type=int)
    design_id = request.form.get('design_id', type=int)
    fabric_description = request.form.get('fabric_description', '').strip()
    special_instructions = request.form.get('special_instructions', '').strip()
    measurement_preference = request.form.get('measurement_preference', 'delivery_will_measure')

    tailor = TailorProfile.query.filter_by(id=tailor_id, is_active=True).first()
    design = Design.query.filter_by(id=design_id, is_active=True).first()

    if not tailor or not design:
        flash('Invalid tailor or design.', 'danger')
        return redirect(request.referrer or url_for('customer.tailors'))

    # Collect selected design variant options
    selected_variants = {}
    for group in design.get_design_options():
        field_name = f'variant_{group["group"]}'
        val = request.form.get(field_name, '').strip()
        if val:
            selected_variants[group['group']] = val

    # Check if same design+tailor already in cart
    existing = CartItem.query.filter_by(
        customer_id=current_user.id, tailor_id=tailor_id, design_id=design_id
    ).first()
    if existing:
        existing.quantity += 1
        # Update variants if newly specified
        if selected_variants:
            existing.selected_variants = json.dumps(selected_variants)
        db.session.commit()
        flash(f'Increased quantity of {design.name} from {tailor.shop_name} in your cart.', 'success')
        return redirect(url_for('customer.cart'))

    measurements = {}
    if measurement_preference == 'provided_by_customer':
        fields = design.get_measurement_fields()
        tmpl = tailor.get_measurement_template(design_id)
        if tmpl:
            fields = tmpl.get_measurement_fields()
        for field in fields:
            val = request.form.get(f'measurement_{field["key"]}', '').strip()
            measurements[field['key']] = val

    item = CartItem(
        customer_id=current_user.id,
        tailor_id=tailor_id,
        design_id=design_id,
        fabric_description=fabric_description,
        special_instructions=special_instructions,
        measurement_preference=measurement_preference,
        measurements=json.dumps(measurements),
        selected_variants=json.dumps(selected_variants),
    )
    db.session.add(item)
    db.session.commit()
    flash(f'{design.name} added to your cart.', 'success')
    return redirect(url_for('customer.cart'))


@customer_bp.route('/cart/remove/<int:item_id>', methods=['POST'])
@login_required
@customer_required
def cart_remove(item_id):
    item = CartItem.query.filter_by(id=item_id, customer_id=current_user.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash('Item removed from cart.', 'info')
    return redirect(url_for('customer.cart'))


@customer_bp.route('/cart/update/<int:item_id>', methods=['POST'])
@login_required
@customer_required
def cart_update(item_id):
    item = CartItem.query.filter_by(id=item_id, customer_id=current_user.id).first_or_404()
    action = request.form.get('action')
    if action == 'increase':
        item.quantity += 1
    elif action == 'decrease' and item.quantity > 1:
        item.quantity -= 1
    db.session.commit()
    return redirect(url_for('customer.cart'))


@customer_bp.route('/cart/checkout', methods=['POST'])
@login_required
@customer_required
def cart_checkout():
    items = CartItem.query.filter_by(customer_id=current_user.id).all()
    if not items:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('customer.tailors'))

    pickup_address = request.form.get('pickup_address', '').strip()
    delivery_address = request.form.get('delivery_address', '').strip()
    payment_method = request.form.get('payment_method', 'cod')
    coupon_code = request.form.get('coupon_code', '').strip().upper()

    if not pickup_address or not delivery_address:
        flash('Please fill in pickup and delivery addresses.', 'danger')
        return redirect(url_for('customer.cart'))

    # Check if style agent slot booking is enabled
    admin_config = AdminConfig.get()
    style_agent_date = ''
    style_agent_time = ''
    if admin_config.enable_style_agent_slot_booking:
        style_agent_date = request.form.get('style_agent_date', '').strip()
        style_agent_time = request.form.get('style_agent_time', '').strip()
        if not style_agent_date or not style_agent_time:
            flash('Please select a style agent visit slot.', 'danger')
            return redirect(url_for('customer.cart'))

    # Save addresses to profile if changed
    if pickup_address != current_user.default_pickup_address:
        current_user.default_pickup_address = pickup_address
    if delivery_address != current_user.default_delivery_address:
        current_user.default_delivery_address = delivery_address

    coupon = Coupon.query.filter_by(code=coupon_code).first() if coupon_code else None
    placed_orders = []

    # Group items by tailor
    tailor_items = {}
    for item in items:
        tailor_items.setdefault(item.tailor_id, []).append(item)

    from app.models import OrderItem

    for t_id, t_items in tailor_items.items():
        subtotal = 0
        for item in t_items:
            tmpl = item.tailor.get_measurement_template(item.design_id)
            price = tmpl.effective_price() if tmpl else item.design.base_price
            subtotal += price * item.quantity

        discount_amount = 0
        applied_code = ''
        if coupon:
            discount, msg = coupon.compute_discount(subtotal)
            if discount > 0:
                discount_amount = discount
                applied_code = coupon_code

        order = Order(
            order_number=generate_order_number(),
            customer_id=current_user.id,
            tailor_id=t_id,
            design_id=None, # None indicates multi-item order via OrderItem
            measurements='{}',
            measurement_preference='mixed',
            fabric_description='Multiple items',
            special_instructions='Multiple items',
            pickup_address=pickup_address,
            delivery_address=delivery_address,
            estimated_price=subtotal,
            discount_amount=discount_amount,
            coupon_code=applied_code,
            payment_method=payment_method,
            payment_status='cod_pending' if payment_method == 'cod' else 'unpaid',
            style_agent_appointment_date=style_agent_date if admin_config.enable_style_agent_slot_booking else '',
            style_agent_appointment_time=style_agent_time if admin_config.enable_style_agent_slot_booking else '',
        )
        db.session.add(order)
        db.session.flush()

        for item in t_items:
            tmpl = item.tailor.get_measurement_template(item.design_id)
            price = tmpl.effective_price() if tmpl else item.design.base_price
            order_item = OrderItem(
                order_id=order.id,
                design_id=item.design_id,
                quantity=item.quantity,
                fabric_description=item.fabric_description,
                measurements=item.measurements,
                special_instructions=item.special_instructions,
                selected_variants=item.selected_variants,
                unit_price=price,
            )
            db.session.add(order_item)

        order.add_status('placed', note='Order placed via cart.', changed_by_id=current_user.id)
        notify(t_id,
               f'New multi-item order {order.order_number} from {current_user.name}.',
               url_for('tailor.order_detail', order_id=order.id))
        placed_orders.append(order)

    if coupon and applied_code:
        coupon.uses_count += len(placed_orders)

    # Clear the cart
    CartItem.query.filter_by(customer_id=current_user.id).delete()
    db.session.commit()

    flash(f'{len(placed_orders)} order(s) placed successfully!', 'success')
    return redirect(url_for('customer.my_orders'))


@customer_bp.route('/my-notifications')
@login_required
@customer_required
def my_notifications():
    notifs = (Notification.query
              .filter_by(user_id=current_user.id)
              .order_by(Notification.created_at.desc())
              .limit(60).all())
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return render_template('customer/notifications.html', notifications=notifs)


@customer_bp.route('/api/notifications/count')
@login_required
@customer_required
def notifications_count():
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    cart_count = CartItem.query.filter_by(customer_id=current_user.id).count()
    return jsonify({'count': count, 'cart_count': cart_count})


@customer_bp.route('/orders/<int:order_id>/messages/send', methods=['POST'])
@login_required
@customer_required
def send_message(order_id):
    order = Order.query.filter_by(id=order_id, customer_id=current_user.id).first_or_404()
    content = request.form.get('content', '').strip()
    if not content:
        flash('Message cannot be empty.', 'warning')
        return redirect(url_for('customer.order_detail', order_id=order_id))
    msg = Message(order_id=order.id, sender_id=current_user.id, content=content)
    db.session.add(msg)
    # Notify tailor
    notify(order.tailor.user_id,
           f'New message from {current_user.name} on order {order.order_number}.',
           url_for('tailor.order_detail', order_id=order.id))
    db.session.commit()
    return redirect(url_for('customer.order_detail', order_id=order_id))


@customer_bp.route('/api/orders/<int:order_id>/messages')
@login_required
@customer_required
def messages_api(order_id):
    order = Order.query.filter_by(id=order_id, customer_id=current_user.id).first_or_404()
    since = request.args.get('since', 0, type=int)
    msgs = order.messages.filter(Message.id > since).all()
    result = []
    for m in msgs:
        result.append({
            'id': m.id,
            'sender': m.sender.name,
            'content': m.content,
            'time': m.created_at.strftime('%I:%M %p'),
            'is_mine': m.sender_id == current_user.id,
        })
    return jsonify(result)


def _save_measurements(customer_id, design_id, measurements_dict, taken_by_id=None):
    record = CustomerMeasurement.query.filter_by(
        customer_id=customer_id, design_id=design_id
    ).first()
    if record:
        record.measurements = json.dumps(measurements_dict)
        record.taken_by_id = taken_by_id
    else:
        record = CustomerMeasurement(
            customer_id=customer_id,
            design_id=design_id,
            measurements=json.dumps(measurements_dict),
            taken_by_id=taken_by_id,
        )
        db.session.add(record)
    return record


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — PRODUCT CATALOGUE BROWSING
# ═══════════════════════════════════════════════════════════════════════════════

@customer_bp.route('/catalogue')
def catalogue():
    """Level-1 grid: all active categories."""
    categories = Design.query.filter_by(is_active=True).order_by(Design.name).all()
    # Attach sub-design counts
    for cat in categories:
        cat.sub_count = ProductDesign.query.filter_by(
            design_id=cat.id, is_active=True).count()
    return render_template('customer/catalogue.html', categories=categories)


@customer_bp.route('/catalogue/<int:category_id>')
def catalogue_category(category_id):
    """Level-2 grid: all sub-designs under a category."""
    category = Design.query.get_or_404(category_id)
    sub_designs = (ProductDesign.query
                   .filter_by(design_id=category_id, is_active=True)
                   .order_by(ProductDesign.display_order, ProductDesign.name)
                   .all())
    return render_template('customer/catalogue_category.html',
                           category=category, sub_designs=sub_designs)


@customer_bp.route('/catalogue/design/<int:design_id>')
def catalogue_design(design_id):
    """Level-3 detail: sub-design info + variants + tailors who can stitch it."""
    pd = ProductDesign.query.filter_by(id=design_id, is_active=True).first_or_404()
    services = (TailorProductService.query
                .filter_by(product_design_id=design_id, is_available=True)
                .join(TailorProductService.tailor)
                .filter_by(is_active=True, is_available=True)
                .all())
    variants = pd.variants.order_by('display_order').all()
    images = pd.images.order_by('display_order').all()
    return render_template('customer/catalogue_design.html',
                           pd=pd, services=services, variants=variants, images=images)


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — STYLE AGENT APPOINTMENT BOOKING
# ═══════════════════════════════════════════════════════════════════════════════

@customer_bp.route('/appointments')
@login_required
@customer_required
def my_appointments():
    appts = (StyleAgentAppointment.query
             .filter_by(customer_id=current_user.id)
             .order_by(StyleAgentAppointment.appointment_date.desc())
             .all())
    return render_template('customer/my_appointments.html', appointments=appts)


@customer_bp.route('/appointments/book', methods=['GET', 'POST'])
@login_required
@customer_required
def book_appointment():
    from datetime import date, timedelta
    from flask import current_app

    # Load active slot config (widest hours wins)
    config = (StyleAgentConfig.query
              .filter_by(is_active=True)
              .order_by(StyleAgentConfig.start_hour)
              .first())
    if not config:
        # Fallback default: 10–18
        class _Default:
            start_hour, end_hour, slot_duration_minutes = 10, 18, 30
            def generate_slots(self):
                slots, cur, end = [], self.start_hour * 60, self.end_hour * 60
                while cur < end:
                    h, m = divmod(cur, 60)
                    slots.append(f'{h:02d}:{m:02d}')
                    cur += self.slot_duration_minutes
                return slots
        config = _Default()

    slots = config.generate_slots()
    advance_days = current_app.config.get('BOOKING_ADVANCE_DAYS', 30)
    today = date.today()
    min_date = (today + timedelta(days=1)).isoformat()
    max_date = (today + timedelta(days=advance_days)).isoformat()

    # Pre-select product design if coming from catalogue
    design_id = request.args.get('design_id', type=int)
    pd = ProductDesign.query.get(design_id) if design_id else None

    if request.method == 'POST':
        appt_date = request.form.get('appointment_date', '').strip()
        appt_time = request.form.get('appointment_time', '').strip()
        service_type = request.form.get('service_type', 'both')
        address = request.form.get('customer_address', '').strip()
        notes = request.form.get('notes', '').strip()
        prod_design_id = request.form.get('product_design_id', type=int)

        if not appt_date or not appt_time or not address:
            flash('Please fill in date, time slot, and address.', 'danger')
            return render_template('customer/book_appointment.html',
                                   slots=slots, min_date=min_date, max_date=max_date,
                                   config=config, pd=pd)

        appt = StyleAgentAppointment(
            customer_id=current_user.id,
            appointment_date=appt_date,
            appointment_time=appt_time,
            service_type=service_type,
            customer_address=address,
            notes=notes,
            product_design_id=prod_design_id or None,
            status='pending',
        )
        db.session.add(appt)
        db.session.commit()

        Notification.create(
            user_id=current_user.id,
            title='Appointment Booked',
            body=f'Your Style Agent visit is booked for {appt.display_datetime()}. We\'ll confirm shortly.',
            type='success',
        )
        db.session.commit()

        flash('Appointment booked! We\'ll confirm and assign a Style Agent shortly.', 'success')
        return redirect(url_for('customer.my_appointments'))

    return render_template('customer/book_appointment.html',
                           slots=slots, min_date=min_date, max_date=max_date,
                           config=config, pd=pd)


@customer_bp.route('/appointments/<int:appt_id>/cancel', methods=['POST'])
@login_required
@customer_required
def cancel_appointment(appt_id):
    appt = StyleAgentAppointment.query.filter_by(
        id=appt_id, customer_id=current_user.id).first_or_404()
    if appt.status in ('completed', 'cancelled'):
        flash('This appointment cannot be cancelled.', 'warning')
        return redirect(url_for('customer.my_appointments'))
    appt.status = 'cancelled'
    db.session.commit()
    flash('Appointment cancelled.', 'info')
    return redirect(url_for('customer.my_appointments'))


@customer_bp.route('/orders/<int:order_id>/confirm-style-agent', methods=['POST'])
@login_required
@customer_required
def confirm_style_agent(order_id):
    """Customer confirms the admin-assigned style agent slot."""
    order = Order.query.filter_by(id=order_id, customer_id=current_user.id).first_or_404()

    if not order.auto_assigned_style_agent_id:
        flash('No style agent has been assigned to this order.', 'warning')
        return redirect(url_for('customer.order_detail', order_id=order_id))

    if order.customer_confirmed_slot:
        flash('You have already confirmed this assignment.', 'info')
        return redirect(url_for('customer.order_detail', order_id=order_id))

    order.customer_confirmed_slot = True
    db.session.commit()

    Notification.create(
        user_id=order.customer_id,
        title='Style Agent Confirmed',
        body=f'You have confirmed {order.style_agent.name} as your Style Agent.',
        type='success',
        order_id=order.id,
    )
    db.session.commit()

    flash(f'Style Agent {order.style_agent.name} confirmed!', 'success')
    return redirect(url_for('customer.order_detail', order_id=order_id))


# ── Dummy payment endpoint ───────────────────────────────────────────────────

@customer_bp.route('/orders/<int:order_id>/pay', methods=['POST'])
@login_required
@customer_required
def pay_order(order_id):
    order = Order.query.filter_by(id=order_id, customer_id=current_user.id).first_or_404()
    if order.payment_status == 'paid':
        flash('This order is already paid.', 'info')
        return redirect(url_for('customer.order_detail', order_id=order_id))

    from app.services import payment_service
    method = request.form.get('payment_method', 'dummy_card')
    success, txn = payment_service.process_payment(order, payment_method=method)

    if success:
        flash(f'Payment of ₹{txn.amount:,.0f} successful! Ref: {txn.transaction_ref}', 'success')
    else:
        flash(f'Payment failed: {txn.failure_reason}. Please try again.', 'danger')

    return redirect(url_for('customer.order_detail', order_id=order_id))
