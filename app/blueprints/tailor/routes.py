import json
from datetime import datetime
from functools import wraps
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.blueprints.tailor import tailor_bp
from app.extensions import db
from app.models import (Order, TailorProfile, Design, TailorMeasurementTemplate,
                        Notification, notify, Message, generate_otp)


def tailor_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'tailor':
            flash('Tailor access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def get_tailor_profile():
    return TailorProfile.query.filter_by(user_id=current_user.id).first_or_404()


@tailor_bp.route('/')
@login_required
@tailor_required
def dashboard():
    profile = get_tailor_profile()
    stats = {
        'new': profile.orders.filter_by(status='placed').count(),
        'active': profile.orders.filter(
            Order.status.in_(['accepted', 'fabric_pickup', 'fabric_collected', 'stitching'])
        ).count(),
        'ready': profile.orders.filter_by(status='ready').count(),
        'completed': profile.orders.filter_by(status='delivered').count(),
    }
    recent = profile.orders.order_by(Order.created_at.desc()).limit(8).all()
    return render_template('tailor/dashboard.html', profile=profile, stats=stats, recent=recent)


@tailor_bp.route('/api/notifications/count')
@login_required
@tailor_required
def notifications_count():
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({'count': count})


@tailor_bp.route('/my-notifications')
@login_required
@tailor_required
def my_notifications():
    notifs = (Notification.query
              .filter_by(user_id=current_user.id)
              .order_by(Notification.created_at.desc())
              .limit(60).all())
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return render_template('tailor/notifications.html', notifications=notifs)


@tailor_bp.route('/orders/<int:order_id>/verify-receipt', methods=['POST'])
@login_required
@tailor_required
def verify_receipt_otp(order_id):
    profile = get_tailor_profile()
    order = Order.query.filter_by(id=order_id, tailor_id=profile.id).first_or_404()
    otp_entered = request.form.get('otp', '').strip()
    if order.tailor_receipt_otp and otp_entered == order.tailor_receipt_otp:
        order.tailor_receipt_verified = True
        order.add_status('stitching',
                         note='Fabric receipt OTP verified by tailor. Stitching started.',
                         changed_by_id=current_user.id)
        Notification.create(
            user_id=order.customer_id,
            title='Stitching started!',
            body=f'{profile.shop_name} confirmed fabric receipt — your order is now being stitched.',
            type='info',
            order_id=order.id,
            link=url_for('customer.order_detail', order_id=order.id),
        )
        db.session.commit()
        flash('OTP verified! Stitching has started.', 'success')
    else:
        flash('Incorrect OTP. Ask the delivery agent for the correct code.', 'danger')
    return redirect(url_for('tailor.order_detail', order_id=order_id))


@tailor_bp.route('/orders/<int:order_id>/messages/send', methods=['POST'])
@login_required
@tailor_required
def send_message(order_id):
    profile = get_tailor_profile()
    order = Order.query.filter_by(id=order_id, tailor_id=profile.id).first_or_404()
    content = request.form.get('content', '').strip()
    if not content:
        flash('Message cannot be empty.', 'warning')
        return redirect(url_for('tailor.order_detail', order_id=order_id))
    msg = Message(order_id=order.id, sender_id=current_user.id, content=content)
    db.session.add(msg)
    notify(order.customer_id,
           f'New message from {profile.shop_name} on order {order.order_number}.',
           url_for('customer.order_detail', order_id=order.id))
    db.session.commit()
    return redirect(url_for('tailor.order_detail', order_id=order_id))


@tailor_bp.route('/api/orders/<int:order_id>/messages')
@login_required
@tailor_required
def messages_api(order_id):
    profile = get_tailor_profile()
    order = Order.query.filter_by(id=order_id, tailor_id=profile.id).first_or_404()
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


@tailor_bp.route('/availability/toggle', methods=['POST'])
@login_required
@tailor_required
def toggle_availability():
    profile = get_tailor_profile()
    profile.is_available = not profile.is_available
    db.session.commit()
    state = 'Open' if profile.is_available else 'Closed'
    flash(f'Your shop is now marked as {state}.', 'success')
    return redirect(url_for('tailor.dashboard'))


@tailor_bp.route('/orders')
@login_required
@tailor_required
def orders():
    profile = get_tailor_profile()
    status_filter = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    q = profile.orders.order_by(Order.created_at.desc())
    if status_filter:
        q = q.filter_by(status=status_filter)
    pagination = q.paginate(page=page, per_page=15, error_out=False)
    return render_template('tailor/orders.html', orders=pagination.items,
                           pagination=pagination,
                           status_filter=status_filter, profile=profile)


@tailor_bp.route('/orders/<int:order_id>')
@login_required
@tailor_required
def order_detail(order_id):
    profile = get_tailor_profile()
    order = Order.query.filter_by(id=order_id, tailor_id=profile.id).first_or_404()
    history = order.status_history.all()
    measurements = order.get_measurements()

    tmpl = profile.get_measurement_template(order.design_id) if order.design_id else None
    primary_design = order.get_primary_design()
    if tmpl:
        design_fields = tmpl.get_measurement_fields()
    elif primary_design:
        design_fields = primary_design.get_measurement_fields()
    else:
        design_fields = []

    messages = order.messages.all()
    return render_template('tailor/order_detail.html', order=order,
                           history=history, measurements=measurements,
                           design_fields=design_fields, messages=messages)


@tailor_bp.route('/orders/<int:order_id>/update-status', methods=['POST'])
@login_required
@tailor_required
def update_order_status(order_id):
    profile = get_tailor_profile()
    order = Order.query.filter_by(id=order_id, tailor_id=profile.id).first_or_404()
    new_status = request.form.get('status', '')
    note = request.form.get('note', '')
    estimated_days = request.form.get('estimated_days', type=int)
    final_price = request.form.get('final_price', type=float)

    allowed = {
        'placed': ['accepted', 'rejected'],
        'fabric_collected': ['stitching'],
        'stitching': ['ready'],
    }

    if new_status not in allowed.get(order.status, []):
        flash('Invalid status transition.', 'danger')
        return redirect(url_for('tailor.order_detail', order_id=order_id))

    if new_status == 'accepted':
        order.accepted_at = datetime.utcnow()
        if estimated_days:
            order.estimated_days = estimated_days
        if final_price:
            order.final_price = final_price
        elif order.design:
            tmpl = profile.get_measurement_template(order.design_id)
            order.estimated_price = tmpl.effective_price() if tmpl else order.design.base_price
        Notification.create(
            user_id=order.customer_id,
            title=f'Order {order.order_number} accepted!',
            body=f'{profile.shop_name} has accepted your order.',
            type='success',
            order_id=order.id,
            link=url_for('customer.order_detail', order_id=order.id),
        )
    elif new_status == 'rejected':
        Notification.create(
            user_id=order.customer_id,
            title=f'Order {order.order_number} rejected.',
            body=f'{profile.shop_name} could not take this order. {note}',
            type='danger',
            order_id=order.id,
            link=url_for('customer.order_detail', order_id=order.id),
        )
    elif new_status == 'ready':
        order.tailor_handover_otp = generate_otp()
        Notification.create(
            user_id=order.customer_id,
            title=f'Order {order.order_number} is ready!',
            body=f'Your garment is stitched and ready for delivery.',
            type='success',
            order_id=order.id,
            link=url_for('customer.order_detail', order_id=order.id),
        )
    else:
        notify(order.customer_id,
               f'Order {order.order_number}: status updated to "{order.status_label()}".',
               url_for('customer.order_detail', order_id=order.id))

    order.add_status(new_status, note=note, changed_by_id=current_user.id)
    db.session.commit()
    flash(f'Order status updated to "{order.status_label()}".', 'success')
    return redirect(url_for('tailor.order_detail', order_id=order_id))


@tailor_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@tailor_required
def profile():
    tailor_profile = get_tailor_profile()
    all_designs = Design.query.filter_by(is_active=True).all()

    if request.method == 'POST':
        tailor_profile.shop_name = request.form.get('shop_name', '').strip()
        tailor_profile.address = request.form.get('address', '').strip()
        tailor_profile.bio = request.form.get('bio', '').strip()
        tailor_profile.experience_years = request.form.get('experience_years', 0, type=int)
        try:
            tailor_profile.latitude = float(request.form.get('latitude', 0) or 0)
            tailor_profile.longitude = float(request.form.get('longitude', 0) or 0)
        except (ValueError, TypeError):
            pass
        tailor_profile.set_specializations(request.form.getlist('specializations'))
        current_user.name = request.form.get('name', current_user.name).strip()
        current_user.phone = request.form.get('phone', current_user.phone).strip()
        db.session.commit()
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('tailor.profile'))

    return render_template('tailor/profile.html',
                           tailor_profile=tailor_profile, all_designs=all_designs)


# ── Measurement Templates ──────────────────────────────────
@tailor_bp.route('/measurement-templates')
@login_required
@tailor_required
def measurement_templates():
    profile = get_tailor_profile()
    designs = Design.query.filter_by(is_active=True).all()
    templates = {t.design_id: t for t in profile.measurement_templates.all()}
    return render_template('tailor/measurement_templates.html',
                           profile=profile, designs=designs, templates=templates)


@tailor_bp.route('/measurement-templates/<int:design_id>', methods=['GET', 'POST'])
@login_required
@tailor_required
def edit_measurement_template(design_id):
    profile = get_tailor_profile()
    design = Design.query.get_or_404(design_id)
    tmpl = profile.measurement_templates.filter_by(design_id=design_id).first()

    if request.method == 'POST':
        keys = request.form.getlist('field_key')
        labels = request.form.getlist('field_label')
        fields = [{'key': k.strip(), 'label': l.strip()}
                  for k, l in zip(keys, labels) if k.strip() and l.strip()]
        custom_price = request.form.get('custom_price', type=float)

        if tmpl:
            tmpl.set_measurement_fields(fields)
            tmpl.custom_price = custom_price
        else:
            tmpl = TailorMeasurementTemplate(
                tailor_id=profile.id,
                design_id=design_id,
                custom_price=custom_price,
            )
            tmpl.set_measurement_fields(fields)
            db.session.add(tmpl)

        db.session.commit()
        flash(f'Measurement template for {design.name} saved.', 'success')
        return redirect(url_for('tailor.measurement_templates'))

    # Pre-fill with global fields if no custom template yet
    default_fields = tmpl.get_measurement_fields() if tmpl else design.get_measurement_fields()
    return render_template('tailor/edit_measurement_template.html',
                           design=design, tmpl=tmpl, default_fields=default_fields)


@tailor_bp.route('/measurement-templates/<int:design_id>/reset', methods=['POST'])
@login_required
@tailor_required
def reset_measurement_template(design_id):
    profile = get_tailor_profile()
    tmpl = profile.measurement_templates.filter_by(design_id=design_id).first()
    if tmpl:
        db.session.delete(tmpl)
        db.session.commit()
        flash('Template reset to global defaults.', 'success')
    return redirect(url_for('tailor.measurement_templates'))
