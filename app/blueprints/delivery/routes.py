import json
from datetime import datetime
from functools import wraps
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.blueprints.delivery import delivery_bp
from app.extensions import db
from app.models import (DeliveryAssignment, Order, CustomerMeasurement,
                        TailorMeasurementTemplate, generate_otp,
                        StyleAgentAppointment, Notification)


def delivery_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'delivery':
            flash('Delivery agent access required.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@delivery_bp.route('/')
@login_required
@delivery_required
def dashboard():
    active = (DeliveryAssignment.query
              .filter_by(delivery_agent_id=current_user.id)
              .filter(DeliveryAssignment.status.in_(['assigned', 'picked_up']))
              .order_by(DeliveryAssignment.assigned_at.desc())
              .all())
    completed_count = (DeliveryAssignment.query
                       .filter_by(delivery_agent_id=current_user.id, status='delivered')
                       .count())
    return render_template('delivery/dashboard.html',
                           active=active, completed_count=completed_count)


@delivery_bp.route('/notifications')
@login_required
@delivery_required
def notifications():
    count = (DeliveryAssignment.query
             .filter_by(delivery_agent_id=current_user.id, status='assigned')
             .count())
    return jsonify({'new_assignments': count})


@delivery_bp.route('/assignments')
@login_required
@delivery_required
def assignments():
    status_filter = request.args.get('status', '')
    q = (DeliveryAssignment.query
         .filter_by(delivery_agent_id=current_user.id)
         .order_by(DeliveryAssignment.assigned_at.desc()))
    if status_filter:
        q = q.filter_by(status=status_filter)
    return render_template('delivery/assignments.html',
                           assignments=q.all(), status_filter=status_filter)


@delivery_bp.route('/assignments/<int:assignment_id>')
@login_required
@delivery_required
def assignment_detail(assignment_id):
    assignment = DeliveryAssignment.query.filter_by(
        id=assignment_id, delivery_agent_id=current_user.id
    ).first_or_404()

    order = assignment.order
    existing_measurements = order.get_measurements()

    # Use tailor's custom measurement fields if available
    tmpl = order.tailor.get_measurement_template(order.design_id)
    design_fields = tmpl.get_measurement_fields() if tmpl else order.design.get_measurement_fields()

    return render_template('delivery/assignment_detail.html',
                           assignment=assignment,
                           design_fields=design_fields,
                           existing_measurements=existing_measurements)


@delivery_bp.route('/assignments/<int:assignment_id>/verify-otp', methods=['POST'])
@login_required
@delivery_required
def verify_otp(assignment_id):
    assignment = DeliveryAssignment.query.filter_by(
        id=assignment_id, delivery_agent_id=current_user.id
    ).first_or_404()

    otp_entered = request.form.get('otp', '').strip()
    action = request.form.get('action', '')  # 'pickup' or 'deliver'

    if action == 'pickup':
        if otp_entered == assignment.pickup_otp:
            assignment.pickup_otp_verified = True
            assignment.status = 'picked_up'
            order = assignment.order
            if assignment.assignment_type == 'pickup_fabric':
                # Generate tailor receipt OTP — tailor verifies when agent drops fabric
                order.tailor_receipt_otp = generate_otp()
                order.add_status('fabric_collected',
                                 note='Fabric collected — OTP verified.',
                                 changed_by_id=current_user.id)
            db.session.commit()
            flash('OTP verified! Pickup confirmed.', 'success')
        else:
            flash('Incorrect OTP. Please ask the customer/tailor for the correct code.', 'danger')

    elif action == 'tailor_handover':
        # Delivery agent picks up finished garment from tailor — verifies tailor's handover OTP
        order = assignment.order
        if otp_entered == order.tailor_handover_otp and order.tailor_handover_otp:
            order.tailor_handover_verified = True
            assignment.pickup_otp_verified = True
            assignment.status = 'picked_up'
            order.add_status('out_for_delivery',
                             note='Garment picked up from tailor — out for delivery.',
                             changed_by_id=current_user.id)
            db.session.commit()
            flash('Tailor handover OTP verified! Now deliver to customer.', 'success')
        else:
            flash('Incorrect handover OTP. Ask the tailor for the correct code.', 'danger')

    elif action == 'deliver':
        if otp_entered == assignment.delivery_otp:
            assignment.delivery_otp_verified = True
            assignment.status = 'delivered'
            assignment.completed_at = datetime.utcnow()
            order = assignment.order
            if assignment.assignment_type == 'deliver_clothes':
                order.add_status('delivered',
                                 note='Clothes delivered — OTP verified.',
                                 changed_by_id=current_user.id)
            db.session.commit()
            flash('OTP verified! Delivery confirmed.', 'success')
        else:
            flash('Incorrect OTP. Please ask the customer for the correct code.', 'danger')

    return redirect(url_for('delivery.assignment_detail', assignment_id=assignment_id))


@delivery_bp.route('/assignments/<int:assignment_id>/save-measurements', methods=['POST'])
@login_required
@delivery_required
def save_measurements(assignment_id):
    assignment = DeliveryAssignment.query.filter_by(
        id=assignment_id, delivery_agent_id=current_user.id
    ).first_or_404()

    if assignment.assignment_type != 'pickup_fabric':
        flash('Measurements only apply to fabric pickup assignments.', 'warning')
        return redirect(url_for('delivery.assignment_detail', assignment_id=assignment_id))

    order = assignment.order
    # Use tailor-specific fields if defined
    tmpl = order.tailor.get_measurement_template(order.design_id)
    design_fields = tmpl.get_measurement_fields() if tmpl else order.design.get_measurement_fields()

    measurements = {}
    for field in design_fields:
        val = request.form.get(f'measurement_{field["key"]}', '').strip()
        measurements[field['key']] = val

    order.measurements = json.dumps(measurements)

    record = CustomerMeasurement.query.filter_by(
        customer_id=order.customer_id, design_id=order.design_id
    ).first()
    if record:
        record.measurements = json.dumps(measurements)
        record.taken_by_id = current_user.id
    else:
        record = CustomerMeasurement(
            customer_id=order.customer_id,
            design_id=order.design_id,
            measurements=json.dumps(measurements),
            taken_by_id=current_user.id,
        )
        db.session.add(record)

    db.session.commit()
    flash('Measurements saved and synced to customer profile.', 'success')
    return redirect(url_for('delivery.assignment_detail', assignment_id=assignment_id))


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — STYLE AGENT APPOINTMENTS
# ═══════════════════════════════════════════════════════════════════════════════

@delivery_bp.route('/my-appointments')
@login_required
@delivery_required
def my_appointments():
    status_filter = request.args.get('status', '')
    q = (StyleAgentAppointment.query
         .filter_by(style_agent_id=current_user.id)
         .order_by(StyleAgentAppointment.appointment_date.asc(),
                   StyleAgentAppointment.appointment_time.asc()))
    if status_filter:
        q = q.filter_by(status=status_filter)
    appts = q.all()
    return render_template('delivery/my_appointments.html',
                           appointments=appts, status_filter=status_filter)


@delivery_bp.route('/my-appointments/<int:appt_id>')
@login_required
@delivery_required
def appointment_detail(appt_id):
    appt = StyleAgentAppointment.query.filter_by(
        id=appt_id, style_agent_id=current_user.id
    ).first_or_404()
    return render_template('delivery/appointment_detail.html', appt=appt)


@delivery_bp.route('/my-appointments/<int:appt_id>/arrived', methods=['POST'])
@login_required
@delivery_required
def appointment_arrived(appt_id):
    appt = StyleAgentAppointment.query.filter_by(
        id=appt_id, style_agent_id=current_user.id
    ).first_or_404()
    appt.status = 'arrived'
    db.session.commit()
    flash('Marked as arrived. Proceed with the visit.', 'success')
    return redirect(url_for('delivery.appointment_detail', appt_id=appt_id))


@delivery_bp.route('/my-appointments/<int:appt_id>/complete', methods=['POST'])
@login_required
@delivery_required
def appointment_complete(appt_id):
    appt = StyleAgentAppointment.query.filter_by(
        id=appt_id, style_agent_id=current_user.id
    ).first_or_404()
    appt.status = 'completed'
    appt.completed_at = datetime.utcnow()
    appt.agent_notes = request.form.get('agent_notes', '').strip()

    # Notify customer
    Notification.create(
        user_id=appt.customer_id,
        title='Style Agent Visit Completed',
        body=f'Your Style Agent visit on {appt.display_datetime()} is complete. Your order will be processed shortly.',
        type='success',
    )
    db.session.commit()

    try:
        from app.services import email_service
        email_service.send_appointment_completed(appt)
    except Exception:
        pass

    flash('Appointment marked as completed.', 'success')
    return redirect(url_for('delivery.my_appointments'))


@delivery_bp.route('/my-appointments/<int:appt_id>/reschedule', methods=['POST'])
@login_required
@delivery_required
def appointment_reschedule(appt_id):
    appt = StyleAgentAppointment.query.filter_by(
        id=appt_id, style_agent_id=current_user.id
    ).first_or_404()
    appt.status = 'rescheduled'
    appt.agent_notes = request.form.get('agent_notes', '').strip()
    db.session.commit()
    flash('Appointment marked for rescheduling. Admin will follow up with customer.', 'info')
    return redirect(url_for('delivery.my_appointments'))
