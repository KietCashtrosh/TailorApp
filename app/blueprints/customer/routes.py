import json
import math
from functools import wraps
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.blueprints.customer import customer_bp
from app.extensions import db
from app.models import (TailorProfile, Design, Order, CustomerMeasurement,
                        Coupon, Review, CartItem, generate_order_number)


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


@customer_bp.route('/')
def home():
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
    sort_by = request.args.get('sort', '')  # rating | price_asc | price_desc

    q = TailorProfile.query.filter_by(is_active=True, is_available=True)
    if design_filter:
        q = q.filter(TailorProfile.specializations.contains(design_filter))
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
        if not sort_by:
            tailors_list.sort(key=lambda t: (t.distance is None, t.distance or 9999))

    if sort_by == 'rating':
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
                           search=search, user_lat=user_lat, user_lng=user_lng,
                           min_rating=min_rating, sort_by=sort_by)


@customer_bp.route('/tailors/<int:tailor_id>')
def tailor_detail(tailor_id):
    tailor = TailorProfile.query.filter_by(id=tailor_id, is_active=True).first_or_404()
    designs = Design.query.filter_by(is_active=True).all()
    specs = tailor.get_specializations()
    # Build per-design price (tailor custom or global base)
    design_prices = {}
    for d in designs:
        tmpl = tailor.get_measurement_template(d.id)
        design_prices[d.id] = tmpl.effective_price() if tmpl else d.base_price
    return render_template('customer/tailor_detail.html', tailor=tailor,
                           designs=designs, specs=specs, design_prices=design_prices)


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
        )
        db.session.add(order)
        db.session.flush()
        order.add_status('placed', note='Order placed by customer.',
                         changed_by_id=current_user.id)
        db.session.commit()
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
    tmpl = order.tailor.get_measurement_template(order.design_id)
    design_fields = tmpl.get_measurement_fields() if tmpl else order.design.get_measurement_fields()
    # Get active assignments for OTP display
    assignments = order.delivery_assignments.all()
    return render_template('customer/order_detail.html', order=order,
                           history=history, measurements=measurements,
                           design_fields=design_fields, assignments=assignments)


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
    items = CartItem.query.filter_by(customer_id=current_user.id).order_by(CartItem.created_at).all()
    # Attach effective price to each item
    for item in items:
        tmpl = item.tailor.get_measurement_template(item.design_id)
        item.effective_price = tmpl.effective_price() if tmpl else item.design.base_price
    total = sum(i.effective_price for i in items)
    return render_template('customer/cart.html', items=items, total=total,
                           default_pickup=current_user.default_pickup_address or '',
                           default_delivery=current_user.default_delivery_address or '')


@customer_bp.route('/cart/add', methods=['POST'])
@login_required
@customer_required
def cart_add():
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

    # Prevent duplicate same design+tailor in cart
    existing = CartItem.query.filter_by(
        customer_id=current_user.id, tailor_id=tailor_id, design_id=design_id
    ).first()
    if existing:
        flash(f'{design.name} from {tailor.shop_name} is already in your cart.', 'info')
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

    # Save addresses to profile if changed
    if pickup_address != current_user.default_pickup_address:
        current_user.default_pickup_address = pickup_address
    if delivery_address != current_user.default_delivery_address:
        current_user.default_delivery_address = delivery_address

    coupon = Coupon.query.filter_by(code=coupon_code).first() if coupon_code else None
    placed_orders = []

    for item in items:
        tmpl = item.tailor.get_measurement_template(item.design_id)
        base_price = tmpl.effective_price() if tmpl else item.design.base_price

        discount_amount = 0
        applied_code = ''
        if coupon:
            discount, msg = coupon.compute_discount(base_price)
            if discount > 0:
                discount_amount = discount
                applied_code = coupon_code

        order = Order(
            order_number=generate_order_number(),
            customer_id=current_user.id,
            tailor_id=item.tailor_id,
            design_id=item.design_id,
            measurements=item.measurements,
            measurement_preference=item.measurement_preference,
            fabric_description=item.fabric_description,
            special_instructions=item.special_instructions,
            pickup_address=pickup_address,
            delivery_address=delivery_address,
            estimated_price=base_price,
            discount_amount=discount_amount,
            coupon_code=applied_code,
            payment_method=payment_method,
            payment_status='cod_pending' if payment_method == 'cod' else 'unpaid',
        )
        db.session.add(order)
        db.session.flush()
        order.add_status('placed', note='Order placed via cart.', changed_by_id=current_user.id)
        placed_orders.append(order)

    if coupon and applied_code:
        coupon.uses_count += len(placed_orders)

    # Clear the cart
    CartItem.query.filter_by(customer_id=current_user.id).delete()
    db.session.commit()

    flash(f'{len(placed_orders)} order(s) placed successfully!', 'success')
    return redirect(url_for('customer.my_orders'))


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
