import json
import math
from functools import wraps
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.blueprints.customer import customer_bp
from app.extensions import db
from app.models import (TailorProfile, Design, Order, CustomerMeasurement,
                        Coupon, Review, generate_order_number)


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

    q = TailorProfile.query.filter_by(is_active=True)
    if design_filter:
        q = q.filter(TailorProfile.specializations.contains(design_filter))
    if search:
        q = q.filter(TailorProfile.shop_name.ilike(f'%{search}%') |
                     TailorProfile.address.ilike(f'%{search}%'))

    tailors_list = q.all()
    if user_lat and user_lng:
        for t in tailors_list:
            if t.latitude and t.longitude:
                t.distance = round(haversine(user_lat, user_lng, t.latitude, t.longitude), 1)
            else:
                t.distance = None
        tailors_list.sort(key=lambda t: (t.distance is None, t.distance or 9999))

    designs = Design.query.filter_by(is_active=True).all()
    return render_template('customer/tailors.html', tailors=tailors_list,
                           designs=designs, design_filter=design_filter,
                           search=search, user_lat=user_lat, user_lng=user_lng)


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
                           saved_measurements=saved_measurements)


@customer_bp.route('/orders')
@login_required
@customer_required
def my_orders():
    orders = current_user.customer_orders.order_by(Order.created_at.desc()).all()
    return render_template('customer/my_orders.html', orders=orders)


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
