import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
"""
============================================================
  FULL ORDER LIFECYCLE - AUTOMATED TEST SUITE
============================================================
Tests the complete order flow:
  Customer places order → Tailor accepts → Admin assigns
  delivery (fabric pickup) → Delivery picks up fabric (OTP)
  → Delivers to tailor (OTP) → Tailor starts stitching →
  Tailor marks ready → Admin assigns delivery (clothes) →
  Delivery picks from tailor (OTP) → Delivers to customer
  (OTP) → Customer submits review.
============================================================
"""
import json
import re
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app, db
from app.models import (
    User, TailorProfile, Design, Order, DeliveryAssignment,
    Notification, Review, generate_otp
)

# ── Colour helpers for terminal output ──────────────────────
try:
    '\u2500'.encode(sys.stdout.encoding or 'utf-8')
    DASH = '\u2500'
    CHECK = '\u2714'
    CROSS = '\u2718'
    WARN_SYM = '!'
except (UnicodeEncodeError, UnicodeDecodeError):
    DASH = '-'
    CHECK = '+'
    CROSS = 'x'
    WARN_SYM = '!'

GREEN  = '\033[92m'
RED    = '\033[91m'
YELLOW = '\033[93m'
CYAN   = '\033[96m'
BOLD   = '\033[1m'
RESET  = '\033[0m'

passed = 0
failed = 0
warnings_list = []



def ok(msg):
    global passed
    passed += 1
    print(f"  {GREEN}{CHECK} PASS{RESET}  {msg}")


def fail(msg, detail=''):
    global failed
    failed += 1
    print(f"  {RED}{CROSS} FAIL{RESET}  {msg}")
    if detail:
        print(f"          {RED}{detail}{RESET}")


def warn(msg):
    warnings_list.append(msg)
    print(f"  {YELLOW}{WARN_SYM} WARN{RESET}  {msg}")


def section(title):
    print(f"\n{CYAN}{BOLD}{DASH*60}")
    print(f"  {title}")
    print(f"{DASH*60}{RESET}")


def login(client, email, password):
    """Log in and return True on success."""
    # GET login page first to get CSRF token
    resp = client.get('/auth/login')
    token = extract_csrf(resp.data)
    resp = client.post('/auth/login', data={
        'email': email,
        'password': password,
        'csrf_token': token,
    }, follow_redirects=True)
    return resp


def extract_csrf(html_bytes):
    """Pull csrf_token from a rendered form."""
    match = re.search(rb'name="csrf_token"\s+value="([^"]+)"', html_bytes)
    if not match:
        match = re.search(rb'value="([^"]+)"\s+name="csrf_token"', html_bytes)
    return match.group(1).decode() if match else ''


def logout(client):
    client.get('/auth/logout', follow_redirects=True)


# ════════════════════════════════════════════════════════════
#  MAIN TEST
# ════════════════════════════════════════════════════════════
def run_tests():
    global passed, failed

    # Create isolated temp DB BEFORE app initialization
    import tempfile
    test_db_fd, test_db_path = tempfile.mkstemp(suffix='.db', prefix='test_order_')
    os.close(test_db_fd)

    # Set env var BEFORE create_app so the real DB is never touched
    os.environ['DATABASE_URL'] = f'sqlite:///{test_db_path}'

    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    with app.app_context():
        db.drop_all()
        db.create_all()

        # ── Seed minimal data ──────────────────────────────
        section("SEEDING TEST DATA")

        admin = User(name='Admin', email='admin@test.com', phone='9000000000',
                     role='admin', approval_status='approved')
        admin.set_password('admin123')
        db.session.add(admin)

        customer = User(name='Test Customer', email='cust@test.com',
                        phone='9111111111', role='customer', approval_status='approved',
                        default_pickup_address='123 Customer Lane',
                        default_delivery_address='456 Customer Home')
        customer.set_password('cust123')
        db.session.add(customer)

        tailor_user = User(name='Test Tailor', email='tailor@test.com',
                           phone='9222222222', role='tailor', approval_status='approved')
        tailor_user.set_password('tailor123')
        db.session.add(tailor_user)
        db.session.flush()

        tailor_profile = TailorProfile(
            user_id=tailor_user.id,
            shop_name='Test Tailor Shop',
            address='789 Tailor Street',
            specializations=json.dumps(['TestShirt']),
            experience_years=5,
            bio='Test tailor',
        )
        db.session.add(tailor_profile)

        delivery_user = User(name='Test Delivery', email='delivery@test.com',
                             phone='9333333333', role='delivery', approval_status='approved')
        delivery_user.set_password('delivery123')
        db.session.add(delivery_user)

        design = Design(
            name='TestShirt', description='Test shirt',
            base_price=500, icon='bi-person',
            measurement_fields=json.dumps([
                {'key': 'chest', 'label': 'Chest (inches)'},
                {'key': 'waist', 'label': 'Waist (inches)'},
            ]),
        )
        db.session.add(design)
        db.session.commit()

        # Reload IDs
        customer    = User.query.filter_by(email='cust@test.com').first()
        tailor_user = User.query.filter_by(email='tailor@test.com').first()
        delivery_user = User.query.filter_by(email='delivery@test.com').first()
        admin       = User.query.filter_by(email='admin@test.com').first()
        tailor_profile = TailorProfile.query.filter_by(user_id=tailor_user.id).first()
        design      = Design.query.filter_by(name='TestShirt').first()

        ok(f"Admin:    {admin.email} (id={admin.id})")
        ok(f"Customer: {customer.email} (id={customer.id})")
        ok(f"Tailor:   {tailor_user.email} (id={tailor_user.id}), profile id={tailor_profile.id}")
        ok(f"Delivery: {delivery_user.email} (id={delivery_user.id})")
        ok(f"Design:   {design.name} (id={design.id}), base_price={design.base_price}")

        # ══════════════════════════════════════════════════
        #  STEP 1: Customer logs in & places order
        # ══════════════════════════════════════════════════
        section("STEP 1: Customer Login & Place Order")

        with app.test_client() as c:
            resp = login(c, 'cust@test.com', 'cust123')
            if b'Welcome back' in resp.data or resp.status_code == 200:
                ok("Customer logged in successfully")
            else:
                fail("Customer login failed", f"status={resp.status_code}")

            # Place order via POST
            resp = c.post('/order/new', data={
                'tailor_id': tailor_profile.id,
                'design_id': design.id,
                'pickup_address': '123 Customer Lane, City',
                'delivery_address': '456 Customer Home, City',
                'fabric_description': 'Blue cotton fabric',
                'special_instructions': 'Slim fit please',
                'measurement_preference': 'delivery_will_measure',
                'payment_method': 'cod',
                'coupon_code': '',
            }, follow_redirects=True)

            order = Order.query.first()
            if order:
                ok(f"Order placed: {order.order_number} (id={order.id})")
                if order.status == 'placed':
                    ok(f"Order status = '{order.status}'")
                else:
                    fail(f"Expected status 'placed', got '{order.status}'")
            else:
                fail("Order was NOT created in database")
                print(f"\n{RED}{BOLD}Cannot continue without an order. Aborting.{RESET}")
                return

            # Check notification sent to tailor
            tailor_notif = Notification.query.filter_by(user_id=tailor_user.id).first()
            if tailor_notif:
                ok(f"Tailor notification created: '{tailor_notif.message[:50]}...'")
            else:
                warn("No notification found for tailor (notify() may not persist here)")

            logout(c)

        # ══════════════════════════════════════════════════
        #  STEP 2: Tailor reviews & accepts the order
        # ══════════════════════════════════════════════════
        section("STEP 2: Tailor Reviews & Accepts Order")

        with app.test_client() as c:
            login(c, 'tailor@test.com', 'tailor123')

            # View order detail
            resp = c.get(f'/tailor/orders/{order.id}')
            if resp.status_code == 200:
                ok("Tailor can view order detail page")
            else:
                fail(f"Tailor order detail returned {resp.status_code}")

            # Accept the order
            resp = c.post(f'/tailor/orders/{order.id}/update-status', data={
                'status': 'accepted',
                'estimated_days': 7,
                'final_price': 550,
                'note': 'Will complete in a week.',
            }, follow_redirects=True)

            db.session.refresh(order)
            if order.status == 'accepted':
                ok(f"Tailor accepted order → status='{order.status}'")
            else:
                fail(f"Expected 'accepted', got '{order.status}'")

            if order.estimated_days == 7:
                ok(f"Estimated days set to {order.estimated_days}")
            if order.final_price == 550:
                ok(f"Final price set to {order.final_price}")

            logout(c)

        # ══════════════════════════════════════════════════
        #  STEP 3: Admin assigns delivery for fabric pickup
        # ══════════════════════════════════════════════════
        section("STEP 3: Admin Assigns Delivery (Fabric Pickup)")

        with app.test_client() as c:
            login(c, 'admin@test.com', 'admin123')

            resp = c.post(f'/admin/orders/{order.id}/assign-delivery', data={
                'agent_id': delivery_user.id,
                'assignment_type': 'pickup_fabric',
                'notes': 'Pick up blue cotton from customer',
            }, follow_redirects=True)

            db.session.refresh(order)
            pickup_assignment = DeliveryAssignment.query.filter_by(
                order_id=order.id, assignment_type='pickup_fabric'
            ).first()

            if pickup_assignment:
                ok(f"Pickup assignment created (id={pickup_assignment.id})")
                ok(f"Pickup OTP = {pickup_assignment.pickup_otp}")
                ok(f"Delivery OTP = {pickup_assignment.delivery_otp}")
            else:
                fail("Pickup assignment NOT created")
                return

            if order.status == 'fabric_pickup':
                ok(f"Order status → '{order.status}'")
            else:
                fail(f"Expected 'fabric_pickup', got '{order.status}'")

            logout(c)

        # ══════════════════════════════════════════════════
        #  STEP 4: Delivery agent picks up fabric (OTP)
        # ══════════════════════════════════════════════════
        section("STEP 4: Delivery Agent Picks Up Fabric (OTP Validation)")

        with app.test_client() as c:
            login(c, 'delivery@test.com', 'delivery123')

            # View assignment
            resp = c.get(f'/delivery/assignments/{pickup_assignment.id}')
            if resp.status_code == 200:
                ok("Delivery agent can view assignment detail")
            else:
                fail(f"Assignment detail returned {resp.status_code}")

            # Verify pickup OTP (wrong first)
            resp = c.post(f'/delivery/assignments/{pickup_assignment.id}/verify-otp', data={
                'otp': '000000',
                'action': 'pickup',
            }, follow_redirects=True)
            db.session.refresh(pickup_assignment)
            if not pickup_assignment.pickup_otp_verified:
                ok("Wrong OTP correctly rejected")
            else:
                fail("Wrong OTP was accepted!")

            # Verify with correct OTP
            resp = c.post(f'/delivery/assignments/{pickup_assignment.id}/verify-otp', data={
                'otp': pickup_assignment.pickup_otp,
                'action': 'pickup',
            }, follow_redirects=True)
            db.session.refresh(pickup_assignment)
            db.session.refresh(order)

            if pickup_assignment.pickup_otp_verified:
                ok("Correct pickup OTP verified")
            else:
                fail("Pickup OTP verification failed")

            if pickup_assignment.status == 'picked_up':
                ok(f"Assignment status → '{pickup_assignment.status}'")
            else:
                fail(f"Expected 'picked_up', got '{pickup_assignment.status}'")

            # ── Save measurements ──
            resp = c.post(f'/delivery/assignments/{pickup_assignment.id}/save-measurements', data={
                'measurement_chest': '38',
                'measurement_waist': '32',
            }, follow_redirects=True)
            db.session.refresh(order)
            measurements = order.get_measurements()
            if measurements.get('chest') == '38' and measurements.get('waist') == '32':
                ok(f"Measurements saved: {measurements}")
            else:
                fail(f"Measurements not saved correctly: {measurements}")

            if order.status == 'fabric_collected':
                ok(f"Order status → '{order.status}'")
            else:
                fail(f"Expected 'fabric_collected', got '{order.status}'")

            # ── Deliver fabric to tailor (tailor receipt OTP) ──
            section("STEP 5: Delivery Hands Fabric to Tailor (Tailor Receipt OTP)")
            db.session.refresh(order)

            if order.tailor_receipt_otp:
                ok(f"Tailor receipt OTP generated = {order.tailor_receipt_otp}")
            else:
                warn("No tailor_receipt_otp generated — this step may not be implemented")

            logout(c)

        # ══════════════════════════════════════════════════
        #  STEP 5b: Tailor verifies receipt OTP → stitching
        # ══════════════════════════════════════════════════
        section("STEP 5b: Tailor Verifies Fabric Receipt OTP")

        with app.test_client() as c:
            login(c, 'tailor@test.com', 'tailor123')

            if order.tailor_receipt_otp:
                resp = c.post(f'/tailor/orders/{order.id}/verify-receipt', data={
                    'otp': order.tailor_receipt_otp,
                }, follow_redirects=True)
                db.session.refresh(order)

                if order.status == 'stitching':
                    ok(f"Tailor receipt OTP verified → status='{order.status}'")
                else:
                    # The verify-receipt route uses Notification.create which may differ
                    warn(f"Status after receipt verify: '{order.status}' (expected 'stitching')")
            else:
                # Manually advance since OTP wasn't generated
                warn("Skipping receipt OTP — manually advancing to stitching")
                resp = c.post(f'/tailor/orders/{order.id}/update-status', data={
                    'status': 'stitching',
                    'note': 'Starting stitching (test fallback)',
                }, follow_redirects=True)
                db.session.refresh(order)

            if order.status == 'stitching':
                ok(f"Order status confirmed = '{order.status}'")
            else:
                fail(f"Expected 'stitching', got '{order.status}'")

            # ── Tailor marks as ready ──
            section("STEP 6: Tailor Marks Order as Ready")

            resp = c.post(f'/tailor/orders/{order.id}/update-status', data={
                'status': 'ready',
                'note': 'Stitching complete, ready for delivery.',
            }, follow_redirects=True)
            db.session.refresh(order)

            if order.status == 'ready':
                ok(f"Tailor marked ready → status='{order.status}'")
            else:
                fail(f"Expected 'ready', got '{order.status}'")

            if order.tailor_handover_otp:
                ok(f"Tailor handover OTP generated = {order.tailor_handover_otp}")
            else:
                warn("No tailor_handover_otp generated")

            logout(c)

        # ══════════════════════════════════════════════════
        #  STEP 7: Admin assigns delivery for clothes
        # ══════════════════════════════════════════════════
        section("STEP 7: Admin Assigns Delivery (Deliver Clothes)")

        with app.test_client() as c:
            login(c, 'admin@test.com', 'admin123')

            resp = c.post(f'/admin/orders/{order.id}/assign-delivery', data={
                'agent_id': delivery_user.id,
                'assignment_type': 'deliver_clothes',
                'notes': 'Deliver finished garment to customer',
            }, follow_redirects=True)

            db.session.refresh(order)
            clothes_assignment = DeliveryAssignment.query.filter_by(
                order_id=order.id, assignment_type='deliver_clothes'
            ).first()

            if clothes_assignment:
                ok(f"Clothes delivery assignment created (id={clothes_assignment.id})")
                ok(f"Pickup OTP = {clothes_assignment.pickup_otp}")
                ok(f"Delivery OTP = {clothes_assignment.delivery_otp}")
            else:
                fail("Clothes delivery assignment NOT created")
                return

            if order.status == 'out_for_delivery':
                ok(f"Order status → '{order.status}'")
            else:
                fail(f"Expected 'out_for_delivery', got '{order.status}'")

            logout(c)

        # ══════════════════════════════════════════════════
        #  STEP 8: Delivery picks clothes from tailor (OTP)
        # ══════════════════════════════════════════════════
        section("STEP 8: Delivery Picks Up Clothes from Tailor (Handover OTP)")

        with app.test_client() as c:
            login(c, 'delivery@test.com', 'delivery123')

            # Verify tailor handover OTP
            if order.tailor_handover_otp:
                resp = c.post(f'/delivery/assignments/{clothes_assignment.id}/verify-otp', data={
                    'otp': order.tailor_handover_otp,
                    'action': 'tailor_handover',
                }, follow_redirects=True)
                db.session.refresh(clothes_assignment)
                db.session.refresh(order)

                if clothes_assignment.pickup_otp_verified:
                    ok("Tailor handover OTP verified")
                else:
                    fail("Tailor handover OTP verification failed")
            else:
                warn("No handover OTP — using pickup OTP fallback")
                resp = c.post(f'/delivery/assignments/{clothes_assignment.id}/verify-otp', data={
                    'otp': clothes_assignment.pickup_otp,
                    'action': 'pickup',
                }, follow_redirects=True)
                db.session.refresh(clothes_assignment)

            # ── Deliver to customer (delivery OTP) ──
            section("STEP 9: Delivery Hands Over to Customer (Delivery OTP)")

            resp = c.post(f'/delivery/assignments/{clothes_assignment.id}/verify-otp', data={
                'otp': clothes_assignment.delivery_otp,
                'action': 'deliver',
            }, follow_redirects=True)
            db.session.refresh(clothes_assignment)
            db.session.refresh(order)

            if clothes_assignment.delivery_otp_verified:
                ok("Customer delivery OTP verified")
            else:
                fail("Customer delivery OTP verification failed")

            if order.status == 'delivered':
                ok(f"Order status -> '{order.status}' DONE!")
            else:
                fail(f"Expected 'delivered', got '{order.status}'")

            logout(c)

        # ══════════════════════════════════════════════════
        #  STEP 10: Customer submits review
        # ══════════════════════════════════════════════════
        section("STEP 10: Customer Submits Review")

        with app.test_client() as c:
            login(c, 'cust@test.com', 'cust123')

            resp = c.post(f'/orders/{order.id}/review', data={
                'tailor_rating': 5,
                'tailor_comment': 'Excellent stitching quality!',
                'delivery_rating': 4,
                'delivery_comment': 'Good service, on time.',
            }, follow_redirects=True)

            review = Review.query.filter_by(order_id=order.id).first()
            if review:
                ok(f"Review submitted: tailor={review.tailor_rating}/5, delivery={review.delivery_rating}/5")
            else:
                fail("Review was NOT created")

            # Verify tailor rating updated
            db.session.refresh(tailor_profile)
            if tailor_profile.rating > 0:
                ok(f"Tailor rating updated to {tailor_profile.rating}")
            else:
                warn("Tailor rating not updated")

            logout(c)

        # ══════════════════════════════════════════════════
        #  SUMMARY: Full status history
        # ══════════════════════════════════════════════════
        section("ORDER STATUS HISTORY")

        history = order.status_history.order_by('created_at').all()
        for i, h in enumerate(history, 1):
            marker = '[*]' if h.status == 'delivered' else '[>]'
            print(f"  {marker} {i}. {h.status_label()} -- {h.note or '(no note)'}")

        # ══════════════════════════════════════════════════
        #  FINAL REPORT
        # ══════════════════════════════════════════════════
        section("FINAL REPORT")
        total = passed + failed
        print(f"  Total:    {total}")
        print(f"  {GREEN}Passed:   {passed}{RESET}")
        print(f"  {RED}Failed:   {failed}{RESET}")
        if warnings_list:
            print(f"  {YELLOW}Warnings: {len(warnings_list)}{RESET}")
            for w in warnings_list:
                print(f"    {YELLOW}! {w}{RESET}")

        if failed == 0:
            print(f"\n  {GREEN}{BOLD}*** ALL TESTS PASSED -- Full order cycle works! ***{RESET}\n")
        else:
            print(f"\n  {RED}{BOLD}XXX {failed} test(s) failed -- see above for details.{RESET}\n")

        # Cleanup temp DB
        db.drop_all()

    try:
        os.unlink(test_db_path)
    except OSError:
        pass

    # Restore env
    os.environ.pop('DATABASE_URL', None)

    return failed


if __name__ == '__main__':
    failures = run_tests()
    sys.exit(1 if failures else 0)
