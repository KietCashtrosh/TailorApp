"""
Dummy payment gateway + money-split logic.

process_payment() simulates a card/UPI gateway:
  - 95% success rate
  - Creates PaymentTransaction + PaymentAllocation rows
  - Triggers email notifications
  - Returns (success: bool, transaction: PaymentTransaction)
"""
import random
from datetime import datetime
from flask import current_app
from app.extensions import db
from app.models import PaymentTransaction, PaymentAllocation


def process_payment(order, payment_method='dummy_card'):
    """
    Simulate a payment for an order.
    Returns (success, transaction).
    """
    amount = order.payable_amount()
    ref = PaymentTransaction.generate_ref()

    txn = PaymentTransaction(
        order_id=order.id,
        amount=amount,
        payment_method=payment_method,
        transaction_ref=ref,
        status='pending',
    )
    db.session.add(txn)
    db.session.flush()

    # Simulate gateway response (95% success)
    success = random.random() < 0.95

    if success:
        txn.status = 'success'
        txn.processed_at = datetime.utcnow()
        _create_allocations(txn, order, amount)
        order.payment_status = 'paid'
    else:
        reasons = [
            'Card declined by bank',
            'Insufficient funds',
            'Gateway timeout',
            'Invalid card details',
        ]
        txn.status = 'failed'
        txn.failure_reason = random.choice(reasons)

    db.session.commit()

    # Fire email notifications (non-blocking)
    try:
        from app.services import email_service
        if success:
            email_service.send_payment_success(order, txn)
        else:
            email_service.send_payment_failed(order, txn)
    except Exception:
        pass

    return success, txn


def _create_allocations(txn, order, amount):
    """Split the payment according to configured percentages."""
    cfg = current_app.config
    platform_pct = cfg.get('PLATFORM_FEE_PERCENT', 10)
    tailor_pct = cfg.get('TAILOR_SHARE_PERCENT', 80)
    agent_pct = cfg.get('AGENT_SHARE_PERCENT', 10)

    platform_amt = round(amount * platform_pct / 100, 2)
    tailor_amt = round(amount * tailor_pct / 100, 2)
    agent_amt = round(amount - platform_amt - tailor_amt, 2)  # remainder to avoid rounding drift

    allocs = [
        PaymentAllocation(
            transaction_id=txn.id,
            recipient_type='platform',
            recipient_id=None,
            amount=platform_amt,
        ),
        PaymentAllocation(
            transaction_id=txn.id,
            recipient_type='tailor',
            recipient_id=order.tailor_id,
            amount=tailor_amt,
        ),
        PaymentAllocation(
            transaction_id=txn.id,
            recipient_type='style_agent',
            recipient_id=None,  # assigned later when agent is known
            amount=agent_amt,
        ),
    ]
    for a in allocs:
        db.session.add(a)


def initiate_refund(order, amount=None):
    """
    Mark the latest successful transaction as refund_initiated.
    Returns the transaction or None if not found.
    """
    txn = (PaymentTransaction.query
           .filter_by(order_id=order.id, status='success')
           .order_by(PaymentTransaction.created_at.desc())
           .first())
    if not txn:
        return None

    refund_amount = amount or txn.amount
    txn.status = 'refund_initiated'
    order.payment_status = 'unpaid'

    # Mark all allocations as refunded
    for alloc in txn.allocations:
        alloc.payout_status = 'refunded'

    db.session.commit()

    try:
        from app.services import email_service
        email_service.send_refund_initiated(order, refund_amount)
    except Exception:
        pass

    return txn
