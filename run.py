import json
import os
from app import create_app, db
from app.models import (
    User, TailorProfile, Design,
    ProductDesign, DesignVariant, DesignImage, TailorProductService,
    StyleAgentConfig, StyleAgentAppointment, AdminConfig,
    PaymentTransaction, PaymentAllocation,
)
from sqlalchemy import text, inspect

app = create_app()

# Startup banner — visible in Railway/gunicorn logs so you can confirm the app loaded
print(f"[TailorApp] App created | ENV={os.environ.get('FLASK_ENV', 'development')} "
      f"| DB={app.config['SQLALCHEMY_DATABASE_URI'][:40]}... "
      f"| DEBUG={app.config.get('DEBUG', False)}", flush=True)


@app.cli.command('init-db')
def init_db():
    """Initialize the database with tables and seed data."""
    db.create_all()

    if not User.query.filter_by(email='admin@tailorapp.com').first():
        admin = User(name='Super Admin', email='admin@tailorapp.com',
                     phone='9000000000', role='admin', approval_status='approved')
        admin.set_password('admin123')
        db.session.add(admin)
        print('Admin user created: admin@tailorapp.com / admin123')

    # ── All 11 garment categories (Jeans/Denim excluded — not a tailoring item) ──
    designs_data = [
        {
            'name': 'Blouse',
            'description': 'Traditional & designer blouse stitching',
            'base_price': 500,
            'icon': 'bi-scissors',
            'measurement_fields': json.dumps([
                {'key': 'chest', 'label': 'Chest (inches)'},
                {'key': 'waist', 'label': 'Waist (inches)'},
                {'key': 'shoulder_width', 'label': 'Shoulder Width (inches)'},
                {'key': 'sleeve_length', 'label': 'Sleeve Length (inches)'},
                {'key': 'blouse_length', 'label': 'Blouse Length (inches)'},
                {'key': 'neck_depth_front', 'label': 'Neck Depth Front (inches)'},
                {'key': 'neck_depth_back', 'label': 'Neck Depth Back (inches)'},
            ]),
            'design_options': json.dumps([
                {'group': 'Neckline', 'options': ['Round neck', 'V-neck', 'Boat neck', 'Square neck', 'Sweetheart', 'Off-shoulder', 'Halter neck', 'Collar neck', 'Keyhole neck', 'Backless']},
                {'group': 'Sleeve Style', 'options': ['Puff sleeve', 'Bell sleeve', 'Bishop sleeve', 'Cap sleeve', 'Sleeveless', 'Cold shoulder', 'Full sleeve', 'Half sleeve', '3/4 sleeve', 'Flutter sleeve']},
                {'group': 'Back Style', 'options': ['Deep back', 'Tie-back', 'Zip back', 'Open back', 'Pleated back', 'Bow back']},
                {'group': 'Embellishment', 'options': ['Embroidery', 'Mirror work', 'Sequins', 'Lace trim', 'Ruffle hem', 'Smocking', 'Plain']},
            ]),
        },
        {
            'name': 'Lehenga',
            'description': 'Bridal & party lehenga stitching',
            'base_price': 2000,
            'icon': 'bi-stars',
            'measurement_fields': json.dumps([
                {'key': 'waist', 'label': 'Waist (inches)'},
                {'key': 'hip', 'label': 'Hip (inches)'},
                {'key': 'length', 'label': 'Skirt Length (inches)'},
                {'key': 'flare', 'label': 'Flare / Kali count'},
            ]),
            'design_options': json.dumps([
                {'group': 'Silhouette', 'options': ['A-line', 'Fishtail/Mermaid', 'Circular', 'Straight/Pencil', 'Layered/Tiered', 'Sharara style']},
                {'group': 'Waistband', 'options': ['High waist', 'Mid waist', 'Low waist', 'Broad belt', 'Elasticated']},
                {'group': 'Hem Length', 'options': ['Floor length', 'Calf length', 'Knee length', 'Asymmetric']},
                {'group': 'Work/Design', 'options': ['Zari work', 'Bandhani', 'Gota patti', 'Block print', 'Sequin', 'Resham embroidery', 'Mirror work', 'Plain']},
            ]),
        },
        {
            'name': 'Shirt',
            'description': 'Formal & casual shirt stitching',
            'base_price': 400,
            'icon': 'bi-person-standing',
            'measurement_fields': json.dumps([
                {'key': 'neck', 'label': 'Neck (inches)'},
                {'key': 'chest', 'label': 'Chest (inches)'},
                {'key': 'waist', 'label': 'Waist (inches)'},
                {'key': 'shoulder', 'label': 'Shoulder (inches)'},
                {'key': 'sleeve_length', 'label': 'Sleeve Length (inches)'},
                {'key': 'shirt_length', 'label': 'Shirt Length (inches)'},
            ]),
            'design_options': json.dumps([
                {'group': 'Collar', 'options': ['Classic collar', 'Mandarin/Band collar', 'Button-down collar', 'Spread collar', 'Polo collar', 'Ruffle collar', 'Peter Pan collar']},
                {'group': 'Sleeve', 'options': ['Full sleeve', 'Half sleeve', '3/4 sleeve', 'Sleeveless', 'Roll-up cuff', 'French cuff']},
                {'group': 'Fit', 'options': ['Regular fit', 'Slim fit', 'Oversized', 'Cropped', 'Boxy', 'Boyfriend fit']},
                {'group': 'Style Detail', 'options': ['Front tuck', 'Side slit', 'Gathered front', 'Peplum hem', 'Cargo pockets', 'Lace inset', 'Plain']},
            ]),
        },
        {
            'name': 'Trouser',
            'description': 'Formal & casual trouser / pant stitching',
            'base_price': 350,
            'icon': 'bi-list-columns',
            'measurement_fields': json.dumps([
                {'key': 'waist', 'label': 'Waist (inches)'},
                {'key': 'hip', 'label': 'Hip (inches)'},
                {'key': 'thigh', 'label': 'Thigh (inches)'},
                {'key': 'knee', 'label': 'Knee (inches)'},
                {'key': 'inseam', 'label': 'Inseam Length (inches)'},
                {'key': 'outseam', 'label': 'Outseam Length (inches)'},
            ]),
            'design_options': json.dumps([
                {'group': 'Silhouette', 'options': ['Straight leg', 'Slim/Skinny', 'Wide leg', 'Bootcut', 'Flared', 'Tapered', 'Cigarette']},
                {'group': 'Rise', 'options': ['High rise', 'Mid rise', 'Low rise', 'Ultra high waist']},
                {'group': 'Waistband', 'options': ['Flat front', 'Pleated front', 'Elasticated', 'Drawstring', 'Belt loops', 'Paperbag waist']},
                {'group': 'Length', 'options': ['Full length', 'Ankle length', 'Cropped', 'Capri', 'Shorts', 'Bermuda']},
            ]),
        },
        # ── 8 new categories ──────────────────────────────────
        {
            'name': 'Saree Blouse',
            'description': 'Saree-specific blouse with traditional & modern back designs',
            'base_price': 550,
            'icon': 'bi-gem',
            'measurement_fields': json.dumps([
                {'key': 'chest', 'label': 'Chest (inches)'},
                {'key': 'waist', 'label': 'Waist (inches)'},
                {'key': 'shoulder_width', 'label': 'Shoulder Width (inches)'},
                {'key': 'sleeve_length', 'label': 'Sleeve Length (inches)'},
                {'key': 'blouse_length', 'label': 'Blouse Length (inches)'},
                {'key': 'back_neck_depth', 'label': 'Back Neck Depth (inches)'},
                {'key': 'front_neck_depth', 'label': 'Front Neck Depth (inches)'},
            ]),
            'design_options': json.dumps([
                {'group': 'Neckline', 'options': ['Pothys neck', 'Princess cut', 'Elbow back neck', 'Fancy collar', 'Jacket style', 'High neck', 'Round neck', 'V-neck']},
                {'group': 'Sleeve', 'options': ['Sleeveless', 'Short sleeve', 'Long sleeve', 'Frilled sleeve', 'Crochet sleeve', 'Puff sleeve']},
                {'group': 'Back Design', 'options': ['Pot back', 'Criss-cross', 'Saree fall back', 'Deep U', 'Piping border', 'Plain back']},
                {'group': 'Style', 'options': ['Padded', 'Corset blouse', 'Crop top', 'Saree gown blouse', 'Regular']},
            ]),
        },
        {
            'name': 'Salwar Suit',
            'description': 'Full salwar suit stitching — kurta, bottom & dupatta',
            'base_price': 900,
            'icon': 'bi-people',
            'measurement_fields': json.dumps([
                {'key': 'chest', 'label': 'Chest (inches)'},
                {'key': 'waist', 'label': 'Waist (inches)'},
                {'key': 'hip', 'label': 'Hip (inches)'},
                {'key': 'shoulder', 'label': 'Shoulder (inches)'},
                {'key': 'kurta_length', 'label': 'Kurta Length (inches)'},
                {'key': 'sleeve_length', 'label': 'Sleeve Length (inches)'},
                {'key': 'salwar_length', 'label': 'Salwar/Bottom Length (inches)'},
            ]),
            'design_options': json.dumps([
                {'group': 'Kurta Style', 'options': ['A-line', 'Straight', 'Anarkali', 'Flared', 'High-low', 'Side slit', 'Asymmetric hem']},
                {'group': 'Bottom Type', 'options': ['Straight salwar', 'Churidar', 'Palazzo', 'Dhoti', 'Patiala', 'Cigarette pants', 'Sharara']},
                {'group': 'Neckline', 'options': ['Mandarin/Chinese collar', 'V-neck', 'Round neck', 'Keyhole', 'Embroidered yoke']},
                {'group': 'Dupatta Style', 'options': ['No dupatta', 'Front drape', 'Shoulder drape', 'Cape style', 'Attached dupatta']},
            ]),
        },
        {
            'name': 'Kurti',
            'description': 'Kurti / tunic stitching in all lengths and styles',
            'base_price': 450,
            'icon': 'bi-palette',
            'measurement_fields': json.dumps([
                {'key': 'chest', 'label': 'Chest (inches)'},
                {'key': 'waist', 'label': 'Waist (inches)'},
                {'key': 'hip', 'label': 'Hip (inches)'},
                {'key': 'shoulder', 'label': 'Shoulder (inches)'},
                {'key': 'length', 'label': 'Kurti Length (inches)'},
                {'key': 'sleeve_length', 'label': 'Sleeve Length (inches)'},
            ]),
            'design_options': json.dumps([
                {'group': 'Length', 'options': ['Short/Tunic', 'Mid thigh', 'Knee length', 'Long (60"+)', 'High-low']},
                {'group': 'Cut & Style', 'options': ['A-line', 'Straight', 'Asymmetric', 'Kaftan', 'Peplum', 'Jacket kurti']},
                {'group': 'Sleeve', 'options': ['Sleeveless', 'Half sleeve', 'Full sleeve', 'Roll-up sleeve', 'Bell sleeve']},
                {'group': 'Detail', 'options': ['Pintuck', 'Schiffli lace', 'Chikan embroidery', 'Tie-dye', 'Printed', 'Solid plain']},
            ]),
        },
        {
            'name': 'Skirt',
            'description': 'Skirt stitching — all silhouettes from mini to maxi',
            'base_price': 400,
            'icon': 'bi-triangle',
            'measurement_fields': json.dumps([
                {'key': 'waist', 'label': 'Waist (inches)'},
                {'key': 'hip', 'label': 'Hip (inches)'},
                {'key': 'length', 'label': 'Skirt Length (inches)'},
            ]),
            'design_options': json.dumps([
                {'group': 'Silhouette', 'options': ['A-line', 'Pencil/Straight', 'Pleated', 'Gathered/Full', 'Asymmetric', 'Wrap', 'Mini', 'Midi', 'Maxi']},
                {'group': 'Waist', 'options': ['High waist', 'Elasticated', 'Yoke waist', 'Tie waist']},
                {'group': 'Detail', 'options': ['Slit', 'Frill hem', 'Layered tulle', 'Leather look', 'Printed', 'Embroidered', 'Plain']},
            ]),
        },
        {
            'name': 'Dress/Frock',
            'description': 'Full dress & frock stitching for all occasions',
            'base_price': 1200,
            'icon': 'bi-stars',
            'measurement_fields': json.dumps([
                {'key': 'bust', 'label': 'Bust (inches)'},
                {'key': 'waist', 'label': 'Waist (inches)'},
                {'key': 'hip', 'label': 'Hip (inches)'},
                {'key': 'shoulder', 'label': 'Shoulder (inches)'},
                {'key': 'dress_length', 'label': 'Dress Length (inches)'},
                {'key': 'sleeve_length', 'label': 'Sleeve Length (inches)'},
            ]),
            'design_options': json.dumps([
                {'group': 'Silhouette', 'options': ['A-line', 'Bodycon', 'Shift', 'Wrap', 'Fit-and-flare', 'Sheath', 'Tent/Trapeze', 'Empire waist']},
                {'group': 'Neckline', 'options': ['V-neck', 'Halter', 'Sweetheart', 'Off-shoulder', 'Strapless', 'High neck', 'Cowl neck', 'Round neck']},
                {'group': 'Length', 'options': ['Mini', 'Midi', 'Maxi', 'Tea length', 'Asymmetric']},
                {'group': 'Sleeve', 'options': ['Sleeveless', 'Spaghetti straps', 'Cap', 'Flutter', 'Full sleeve', 'Puffed']},
            ]),
        },
        {
            'name': 'Jacket/Blazer',
            'description': 'Jacket & blazer stitching — formal, ethnic & casual',
            'base_price': 1500,
            'icon': 'bi-briefcase',
            'measurement_fields': json.dumps([
                {'key': 'chest', 'label': 'Chest (inches)'},
                {'key': 'waist', 'label': 'Waist (inches)'},
                {'key': 'shoulder', 'label': 'Shoulder (inches)'},
                {'key': 'sleeve_length', 'label': 'Sleeve Length (inches)'},
                {'key': 'back_length', 'label': 'Back Length (inches)'},
            ]),
            'design_options': json.dumps([
                {'group': 'Style', 'options': ['Single-breasted', 'Double-breasted', 'Nehru jacket', 'Bomber', 'Biker', 'Denim jacket', 'Long coat', 'Crop blazer']},
                {'group': 'Closure', 'options': ['Button', 'Zip', 'Snap buttons', 'Open front', 'Hook & bar']},
                {'group': 'Collar', 'options': ['Notch lapel', 'Peak lapel', 'Shawl lapel', 'Mandarin', 'Hoodie collar']},
                {'group': 'Detail', 'options': ['Padded shoulders', 'Structured', 'Unstructured', 'Quilted', 'Embroidered', 'Patch pockets']},
            ]),
        },
        {
            'name': 'Ethnic/Indo-Western',
            'description': 'Fusion & ethnic Indo-western garment stitching',
            'base_price': 2500,
            'icon': 'bi-flower1',
            'measurement_fields': json.dumps([
                {'key': 'bust', 'label': 'Bust (inches)'},
                {'key': 'waist', 'label': 'Waist (inches)'},
                {'key': 'hip', 'label': 'Hip (inches)'},
                {'key': 'shoulder', 'label': 'Shoulder (inches)'},
                {'key': 'length', 'label': 'Garment Length (inches)'},
                {'key': 'sleeve_length', 'label': 'Sleeve Length (inches)'},
            ]),
            'design_options': json.dumps([
                {'group': 'Style', 'options': ['Dhoti dress', 'Cape gown', 'Palazzo set', 'Jacket lehenga', 'Saree gown', 'Indowestern kurta', 'Fusion skirt set']},
                {'group': 'Neckline', 'options': ['Mandarin', 'Illusion neck', 'Deep V', 'Choker neck', 'Round neck']},
                {'group': 'Silhouette', 'options': ['Mermaid gown', 'Ball gown', 'Column', 'Layered cape', 'A-line']},
                {'group': 'Occasion', 'options': ['Bridal', 'Reception', 'Festive', 'Casual', 'Office fusion']},
            ]),
        },
    ]

    for d in designs_data:
        existing = Design.query.filter_by(name=d['name']).first()
        if not existing:
            design = Design(**d)
            db.session.add(design)
            print(f"  Design added: {d['name']}")
        else:
            # Update design_options on existing designs (non-destructive)
            if not existing.design_options or existing.design_options == '[]':
                existing.design_options = d.get('design_options', '[]')
                print(f"  Design options updated: {d['name']}")

    if not User.query.filter_by(email='tailor1@tailorapp.com').first():
        t_user = User(name='Ravi Kumar', email='tailor1@tailorapp.com',
                      phone='9111111111', role='tailor', approval_status='approved')
        t_user.set_password('tailor123')
        db.session.add(t_user)
        db.session.flush()
        profile = TailorProfile(
            user_id=t_user.id,
            shop_name='Ravi Fashion Studio',
            address='12, MG Road, Bangalore, Karnataka',
            latitude=12.9716,
            longitude=77.5946,
            specializations=json.dumps(['Blouse', 'Lehenga']),
            experience_years=8,
            bio='Specialising in bridal wear and ethnic designs for over 8 years.',
        )
        db.session.add(profile)
        print('Demo tailor created: tailor1@tailorapp.com / tailor123')

    if not User.query.filter_by(email='delivery1@tailorapp.com').first():
        d_user = User(name='Arjun Singh', email='delivery1@tailorapp.com',
                      phone='9222222222', role='delivery', approval_status='approved')
        d_user.set_password('delivery123')
        db.session.add(d_user)
        print('Demo delivery agent created: delivery1@tailorapp.com / delivery123')

    if not User.query.filter_by(email='customer1@tailorapp.com').first():
        c_user = User(name='Priya Sharma', email='customer1@tailorapp.com',
                      phone='9333333333', role='customer', approval_status='approved')
        c_user.set_password('customer123')
        db.session.add(c_user)
        print('Demo customer created: customer1@tailorapp.com / customer123')

    db.session.commit()
    print('\nDatabase initialised successfully!')


@app.cli.command('migrate-db')
def migrate_db():
    """Add new columns/tables introduced in the Phase 1-4 feature update (non-destructive)."""
    with app.app_context():
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()

        # Create any entirely new tables (family_profiles, password_reset_tokens, order_items, messages)
        db.create_all()
        print('New tables created (if not existing).')

        # Add new columns to 'tailor_profiles' if they don't exist
        tailor_cols = {c['name'] for c in inspector.get_columns('tailor_profiles')}
        tailor_additions = [
            ('shop_photo', "VARCHAR(200) DEFAULT ''"),
        ]
        for col, typedef in tailor_additions:
            if col not in tailor_cols:
                db.session.execute(text(f'ALTER TABLE tailor_profiles ADD COLUMN {col} {typedef}'))
                print(f'  tailor_profiles.{col} added.')

        # Add new columns to 'designs' if they don't exist
        design_cols = {c['name'] for c in inspector.get_columns('designs')}
        design_additions = [
            ('design_options', "TEXT DEFAULT '[]'"),
        ]
        for col, typedef in design_additions:
            if col not in design_cols:
                db.session.execute(text(f'ALTER TABLE designs ADD COLUMN {col} {typedef}'))
                print(f'  designs.{col} added.')

        # Add new columns to 'cart_items' if they don't exist
        cart_cols = {c['name'] for c in inspector.get_columns('cart_items')}
        cart_additions = [
            ('selected_variants', "TEXT DEFAULT '{}'"),
        ]
        for col, typedef in cart_additions:
            if col not in cart_cols:
                db.session.execute(text(f'ALTER TABLE cart_items ADD COLUMN {col} {typedef}'))
                print(f'  cart_items.{col} added.')

        # Add new columns to 'order_items' if they don't exist
        oi_cols = {c['name'] for c in inspector.get_columns('order_items')}
        oi_additions = [
            ('selected_variants', "TEXT DEFAULT '{}'"),
        ]
        for col, typedef in oi_additions:
            if col not in oi_cols:
                db.session.execute(text(f'ALTER TABLE order_items ADD COLUMN {col} {typedef}'))
                print(f'  order_items.{col} added.')

        # Add new columns to 'orders' if they don't exist
        orders_cols = {c['name'] for c in inspector.get_columns('orders')}
        order_additions = [
            ('family_profile_id', 'INTEGER REFERENCES family_profiles(id)'),
            ('tailor_receipt_otp', "VARCHAR(6) DEFAULT ''"),
            ('tailor_receipt_verified', 'BOOLEAN DEFAULT 0'),
            ('tailor_handover_otp', "VARCHAR(6) DEFAULT ''"),
            ('tailor_handover_verified', 'BOOLEAN DEFAULT 0'),
            ('style_agent_appointment_date', "VARCHAR(10) DEFAULT ''"),
            ('style_agent_appointment_time', "VARCHAR(5) DEFAULT ''"),
            ('auto_assigned_style_agent_id', 'INTEGER REFERENCES users(id)'),
            ('admin_assigned_at', 'DATETIME'),
            ('customer_confirmed_slot', 'BOOLEAN DEFAULT 0'),
            ('work_images', "TEXT DEFAULT '[]'"),
        ]
        for col, typedef in order_additions:
            if col not in orders_cols:
                db.session.execute(text(f'ALTER TABLE orders ADD COLUMN {col} {typedef}'))
                print(f'  orders.{col} added.')

        # Make design_id nullable on SQLite: note SQLite doesn't support ALTER COLUMN,
        # but since design_id already exists with a value in all existing rows,
        # we just add the new foreign-key columns and the ORM will treat it as nullable.

        # Add new columns to 'notifications' if they don't exist
        notif_cols = {c['name'] for c in inspector.get_columns('notifications')}
        notif_additions = [
            ('title', "VARCHAR(200) DEFAULT ''"),
            ('body', "TEXT DEFAULT ''"),
            ('type', "VARCHAR(20) DEFAULT 'info'"),
            ('order_id', 'INTEGER REFERENCES orders(id)'),
        ]
        for col, typedef in notif_additions:
            if col not in notif_cols:
                db.session.execute(text(f'ALTER TABLE notifications ADD COLUMN {col} {typedef}'))
                print(f'  notifications.{col} added.')

        # Phase 1: Style agent config default row
        if 'style_agent_configs' in inspector.get_table_names():
            pass  # table already exists via create_all above

        # AdminConfig table (singleton for system-wide settings)
        if 'admin_configs' not in inspector.get_table_names():
            db.create_all()
            print('  admin_configs table created.')

        # Ensure AdminConfig singleton exists
        if not AdminConfig.query.first():
            config = AdminConfig(id=1)
            db.session.add(config)
            print('  Default AdminConfig created.')

        # Widen measurement_preference VARCHAR(20 → 30) — 'delivery_will_measure' is 21 chars,
        # SQLite silently truncated but PostgreSQL enforces the limit strictly.
        try:
            db.session.execute(text(
                "ALTER TABLE orders ALTER COLUMN measurement_preference TYPE VARCHAR(30)"
            ))
            print('  orders.measurement_preference widened to VARCHAR(30).')
        except Exception:
            db.session.rollback()  # SQLite doesn't support ALTER COLUMN TYPE — safe to ignore

        try:
            db.session.execute(text(
                "ALTER TABLE cart_items ALTER COLUMN measurement_preference TYPE VARCHAR(30)"
            ))
            print('  cart_items.measurement_preference widened to VARCHAR(30).')
        except Exception:
            db.session.rollback()  # SQLite — safe to ignore

        db.session.commit()
        print('Migration complete.')


@app.cli.command('seed-catalogue')
def seed_catalogue():
    """Seed ProductDesign + DesignVariant catalogue data for all 11 garment categories."""

    def get_design(name):
        d = Design.query.filter_by(name=name).first()
        if not d:
            print(f'  ⚠  Design "{name}" not found — run init-db first.')
        return d

    # ── Helper: build sample_designs list from each category ──────────────────

    def blouse_entries(design_id):
        return [
            {'design_id': design_id, 'name': 'Round Neck Blouse', 'display_order': 1,
             'description': 'Classic round neck, perfect for silk & cotton sarees.',
             'base_price_modifier': 0, 'fabric_suggestions': json.dumps(['Silk', 'Cotton', 'Net', 'Brocade']),
             'variants': [
                 {'variant_group': 'Sleeve Style', 'variant_options': json.dumps(['Full Sleeve', 'Half Sleeve', 'Sleeveless', 'Cap Sleeve']), 'price_modifier': 0},
                 {'variant_group': 'Back Pattern', 'variant_options': json.dumps(['Plain Back', 'Backless', 'Bow Back', 'Potli Button']), 'price_modifier': 50},
                 {'variant_group': 'Padding', 'variant_options': json.dumps(['With Padding', 'Without Padding']), 'price_modifier': 30},
             ]},
            {'design_id': design_id, 'name': 'V-Neck Blouse', 'display_order': 2,
             'description': 'Deep V-neck, great for heavy embroidered fabrics.',
             'base_price_modifier': 50, 'fabric_suggestions': json.dumps(['Silk', 'Georgette', 'Velvet']),
             'variants': [
                 {'variant_group': 'Sleeve Style', 'variant_options': json.dumps(['Full Sleeve', 'Half Sleeve', 'Sleeveless']), 'price_modifier': 0},
                 {'variant_group': 'Neck Depth', 'variant_options': json.dumps(['Shallow', 'Medium', 'Deep']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Bridal Blouse', 'display_order': 3,
             'description': 'Heavily embellished bridal blouse with mirror work & embroidery.',
             'base_price_modifier': 500, 'fabric_suggestions': json.dumps(['Silk', 'Velvet', 'Brocade', 'Kanjivaram']),
             'variants': [
                 {'variant_group': 'Embroidery Type', 'variant_options': json.dumps(['Zardosi', 'Mirror Work', 'Thread Work', 'Stone Work', 'Kundan']), 'price_modifier': 200},
                 {'variant_group': 'Sleeve Style', 'variant_options': json.dumps(['Full Sleeve', 'Puff Sleeve', 'Bell Sleeve', 'Flutter Sleeve']), 'price_modifier': 100},
                 {'variant_group': 'Back Style', 'variant_options': json.dumps(['Deep Back', 'Tie Back', 'Criss-Cross', 'Bow Back']), 'price_modifier': 150},
             ]},
            {'design_id': design_id, 'name': 'Sleeveless Blouse', 'display_order': 4,
             'description': 'Clean modern silhouette, ideal for festive wear.',
             'base_price_modifier': -50, 'fabric_suggestions': json.dumps(['Cotton', 'Linen', 'Silk', 'Crepe']),
             'variants': [
                 {'variant_group': 'Neckline', 'variant_options': json.dumps(['Round Neck', 'Square Neck', 'Boat Neck', 'Sweetheart', 'Off-shoulder']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Puff Sleeve Blouse', 'display_order': 5,
             'description': 'Trendy puff sleeves for a fashion-forward look.',
             'base_price_modifier': 100, 'fabric_suggestions': json.dumps(['Cotton', 'Organza', 'Silk', 'Satin']),
             'variants': [
                 {'variant_group': 'Puff Size', 'variant_options': json.dumps(['Small Puff', 'Large Puff', 'Bishop Sleeve']), 'price_modifier': 0},
                 {'variant_group': 'Neckline', 'variant_options': json.dumps(['Round Neck', 'Square Neck', 'V-Neck']), 'price_modifier': 0},
             ]},
        ]

    def saree_blouse_entries(design_id):
        return [
            {'design_id': design_id, 'name': 'Pot Back Blouse', 'display_order': 1,
             'description': 'Traditional pot back design, beloved in South Indian bridal wear.',
             'base_price_modifier': 100, 'fabric_suggestions': json.dumps(['Kanjivaram', 'Silk', 'Brocade']),
             'variants': [
                 {'variant_group': 'Neckline', 'variant_options': json.dumps(['Pothys Neck', 'Round Neck', 'Princess Cut']), 'price_modifier': 0},
                 {'variant_group': 'Sleeve', 'variant_options': json.dumps(['Short Sleeve', 'Elbow Sleeve', 'Sleeveless']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Corset Saree Blouse', 'display_order': 2,
             'description': 'Structured corset silhouette for modern saree draping.',
             'base_price_modifier': 300, 'fabric_suggestions': json.dumps(['Velvet', 'Satin', 'Silk']),
             'variants': [
                 {'variant_group': 'Closure', 'variant_options': json.dumps(['Back Hook', 'Side Zip', 'Lace-up']), 'price_modifier': 50},
                 {'variant_group': 'Sleeve', 'variant_options': json.dumps(['Sleeveless', 'Spaghetti Strap', 'Off-shoulder']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'High Neck Saree Blouse', 'display_order': 3,
             'description': 'Elegant high neck with full coverage, suits formal occasions.',
             'base_price_modifier': 50, 'fabric_suggestions': json.dumps(['Net', 'Georgette', 'Silk']),
             'variants': [
                 {'variant_group': 'Sleeve', 'variant_options': json.dumps(['Full Sleeve', 'Frilled Sleeve', 'Crochet Sleeve']), 'price_modifier': 0},
                 {'variant_group': 'Back Design', 'variant_options': json.dumps(['Piping Border', 'Criss-Cross', 'Deep U']), 'price_modifier': 0},
             ]},
        ]

    def lehenga_entries(design_id):
        return [
            {'design_id': design_id, 'name': 'A-Line Lehenga', 'display_order': 1,
             'description': 'Flares gently from waist — flattering for all body types.',
             'base_price_modifier': 0, 'fabric_suggestions': json.dumps(['Net', 'Georgette', 'Silk', 'Crepe']),
             'variants': [
                 {'variant_group': 'Waistband', 'variant_options': json.dumps(['High Waist', 'Mid Waist', 'Low Waist']), 'price_modifier': 0},
                 {'variant_group': 'Hem Length', 'variant_options': json.dumps(['Floor Length', 'Calf Length', 'Asymmetric']), 'price_modifier': 0},
                 {'variant_group': 'Work', 'variant_options': json.dumps(['Zari Work', 'Sequin', 'Mirror Work', 'Plain']), 'price_modifier': 200},
             ]},
            {'design_id': design_id, 'name': 'Bridal Circular Lehenga', 'display_order': 2,
             'description': 'Full circular flare with heavy kali count, ideal for bridal wear.',
             'base_price_modifier': 1500, 'fabric_suggestions': json.dumps(['Kanjivaram', 'Brocade', 'Velvet']),
             'variants': [
                 {'variant_group': 'Kali Count', 'variant_options': json.dumps(['8 Kali', '12 Kali', '16 Kali', '20 Kali']), 'price_modifier': 300},
                 {'variant_group': 'Embroidery', 'variant_options': json.dumps(['Zardosi', 'Gota Patti', 'Resham', 'Kundan']), 'price_modifier': 500},
             ]},
            {'design_id': design_id, 'name': 'Sharara Style Lehenga', 'display_order': 3,
             'description': 'Wide-legged sharara silhouette for a retro-chic look.',
             'base_price_modifier': 200, 'fabric_suggestions': json.dumps(['Chiffon', 'Georgette', 'Crepe']),
             'variants': [
                 {'variant_group': 'Waistband', 'variant_options': json.dumps(['Elasticated', 'Broad Belt', 'Drawstring']), 'price_modifier': 0},
             ]},
        ]

    def salwar_entries(design_id):
        return [
            {'design_id': design_id, 'name': 'Anarkali Suit', 'display_order': 1,
             'description': 'Floor-length flared Anarkali kurta with fitted churidar.',
             'base_price_modifier': 300, 'fabric_suggestions': json.dumps(['Georgette', 'Chiffon', 'Net', 'Crepe']),
             'variants': [
                 {'variant_group': 'Length', 'variant_options': json.dumps(['Knee Length', 'Calf Length', 'Floor Length']), 'price_modifier': 0},
                 {'variant_group': 'Bottom', 'variant_options': json.dumps(['Churidar', 'Straight Salwar', 'Palazzo']), 'price_modifier': 0},
                 {'variant_group': 'Neckline', 'variant_options': json.dumps(['Round Neck', 'V-Neck', 'Mandarin Collar', 'Keyhole']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Palazzo Suit', 'display_order': 2,
             'description': 'Straight kurta with wide flared palazzo bottoms — breezy & chic.',
             'base_price_modifier': 100, 'fabric_suggestions': json.dumps(['Linen', 'Cotton', 'Rayon', 'Crepe']),
             'variants': [
                 {'variant_group': 'Kurta Style', 'variant_options': json.dumps(['Straight', 'A-line', 'High-low']), 'price_modifier': 0},
                 {'variant_group': 'Dupatta', 'variant_options': json.dumps(['No Dupatta', 'Plain Dupatta', 'Embroidered Dupatta', 'Cape Style']), 'price_modifier': 100},
             ]},
            {'design_id': design_id, 'name': 'Patiala Suit', 'display_order': 3,
             'description': 'Traditional Patiala salwar with fitted kurta.',
             'base_price_modifier': 0, 'fabric_suggestions': json.dumps(['Cotton', 'Silk', 'Phulkari Fabric']),
             'variants': [
                 {'variant_group': 'Kurta Length', 'variant_options': json.dumps(['Short (Hip Length)', 'Mid Thigh', 'Knee Length']), 'price_modifier': 0},
                 {'variant_group': 'Embroidery', 'variant_options': json.dumps(['Phulkari', 'Plain', 'Chikankari']), 'price_modifier': 150},
             ]},
        ]

    def kurti_entries(design_id):
        return [
            {'design_id': design_id, 'name': 'A-Line Kurti', 'display_order': 1,
             'description': 'Classic A-line silhouette, flattering and comfortable for daily wear.',
             'base_price_modifier': 0, 'fabric_suggestions': json.dumps(['Cotton', 'Rayon', 'Linen', 'Georgette']),
             'variants': [
                 {'variant_group': 'Length', 'variant_options': json.dumps(['Tunic', 'Mid Thigh', 'Knee Length', 'Long']), 'price_modifier': 0},
                 {'variant_group': 'Sleeve', 'variant_options': json.dumps(['Sleeveless', 'Half Sleeve', 'Full Sleeve', 'Bell Sleeve']), 'price_modifier': 0},
                 {'variant_group': 'Neckline', 'variant_options': json.dumps(['Round Neck', 'V-Neck', 'Mandarin Collar', 'Keyhole']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Kaftan Kurti', 'display_order': 2,
             'description': 'Loose, flowing kaftan style — ultra comfortable for all occasions.',
             'base_price_modifier': 50, 'fabric_suggestions': json.dumps(['Rayon', 'Muslin', 'Crepe', 'Georgette']),
             'variants': [
                 {'variant_group': 'Print', 'variant_options': json.dumps(['Printed', 'Solid Plain', 'Tie-Dye', 'Block Print']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Jacket Kurti', 'display_order': 3,
             'description': 'Kurti with an attached or separate jacket layer for layered look.',
             'base_price_modifier': 200, 'fabric_suggestions': json.dumps(['Cotton', 'Chanderi', 'Silk']),
             'variants': [
                 {'variant_group': 'Jacket Style', 'variant_options': json.dumps(['Long Jacket', 'Short Jacket', 'Dhoti Style']), 'price_modifier': 0},
                 {'variant_group': 'Inner Kurti', 'variant_options': json.dumps(['Sleeveless', 'Short Sleeve']), 'price_modifier': 0},
             ]},
        ]

    def skirt_entries(design_id):
        return [
            {'design_id': design_id, 'name': 'A-Line Skirt', 'display_order': 1,
             'description': 'Universally flattering A-line cut in any length.',
             'base_price_modifier': 0, 'fabric_suggestions': json.dumps(['Cotton', 'Linen', 'Denim', 'Crepe']),
             'variants': [
                 {'variant_group': 'Length', 'variant_options': json.dumps(['Mini', 'Midi', 'Maxi']), 'price_modifier': 0},
                 {'variant_group': 'Waist', 'variant_options': json.dumps(['High Waist', 'Mid Waist', 'Elasticated']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Pleated Skirt', 'display_order': 2,
             'description': 'Box or knife pleats for volume and movement.',
             'base_price_modifier': 100, 'fabric_suggestions': json.dumps(['Chiffon', 'Satin', 'Polyester', 'Cotton']),
             'variants': [
                 {'variant_group': 'Pleat Type', 'variant_options': json.dumps(['Box Pleat', 'Knife Pleat', 'Inverted Pleat']), 'price_modifier': 0},
                 {'variant_group': 'Length', 'variant_options': json.dumps(['Mini', 'Midi', 'Maxi']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Pencil Skirt', 'display_order': 3,
             'description': 'Slim fitted pencil silhouette for professional and party wear.',
             'base_price_modifier': 50, 'fabric_suggestions': json.dumps(['Ponte', 'Crepe', 'Velvet', 'Wool']),
             'variants': [
                 {'variant_group': 'Slit', 'variant_options': json.dumps(['No Slit', 'Back Slit', 'Side Slit']), 'price_modifier': 0},
             ]},
        ]

    def dress_entries(design_id):
        return [
            {'design_id': design_id, 'name': 'A-Line Dress', 'display_order': 1,
             'description': 'Timeless A-line silhouette for any occasion.',
             'base_price_modifier': 0, 'fabric_suggestions': json.dumps(['Cotton', 'Georgette', 'Crepe', 'Chiffon']),
             'variants': [
                 {'variant_group': 'Neckline', 'variant_options': json.dumps(['Round Neck', 'V-Neck', 'Off-shoulder', 'Sweetheart']), 'price_modifier': 0},
                 {'variant_group': 'Sleeve', 'variant_options': json.dumps(['Sleeveless', 'Cap Sleeve', 'Flutter', 'Full Sleeve']), 'price_modifier': 0},
                 {'variant_group': 'Length', 'variant_options': json.dumps(['Mini', 'Midi', 'Maxi', 'Tea Length']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Bodycon Dress', 'display_order': 2,
             'description': 'Fitted bodycon style that hugs the silhouette.',
             'base_price_modifier': 100, 'fabric_suggestions': json.dumps(['Jersey', 'Velvet', 'Crepe', 'Satin']),
             'variants': [
                 {'variant_group': 'Neckline', 'variant_options': json.dumps(['V-Neck', 'Halter', 'Strapless', 'High Neck']), 'price_modifier': 0},
                 {'variant_group': 'Length', 'variant_options': json.dumps(['Mini', 'Midi', 'Maxi']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Wrap Dress', 'display_order': 3,
             'description': 'Adjustable wrap silhouette — flattering and versatile.',
             'base_price_modifier': 50, 'fabric_suggestions': json.dumps(['Jersey', 'Chiffon', 'Crepe']),
             'variants': [
                 {'variant_group': 'Sleeve', 'variant_options': json.dumps(['Short Sleeve', 'Full Sleeve', 'Sleeveless']), 'price_modifier': 0},
                 {'variant_group': 'Length', 'variant_options': json.dumps(['Midi', 'Maxi', 'Mini']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Empire Waist Gown', 'display_order': 4,
             'description': 'High empire waist with flowing skirt — elegant for formal events.',
             'base_price_modifier': 500, 'fabric_suggestions': json.dumps(['Chiffon', 'Georgette', 'Net', 'Satin']),
             'variants': [
                 {'variant_group': 'Neckline', 'variant_options': json.dumps(['Sweetheart', 'V-Neck', 'Halter', 'Off-shoulder']), 'price_modifier': 0},
                 {'variant_group': 'Sleeve', 'variant_options': json.dumps(['Sleeveless', 'Puffed', 'Flutter']), 'price_modifier': 100},
             ]},
        ]

    def jacket_entries(design_id):
        return [
            {'design_id': design_id, 'name': 'Formal Blazer', 'display_order': 1,
             'description': 'Single or double-breasted blazer for office and formal occasions.',
             'base_price_modifier': 0, 'fabric_suggestions': json.dumps(['Wool', 'Polyester Blend', 'Linen', 'Tweed']),
             'variants': [
                 {'variant_group': 'Breasting', 'variant_options': json.dumps(['Single-breasted', 'Double-breasted']), 'price_modifier': 0},
                 {'variant_group': 'Lapel', 'variant_options': json.dumps(['Notch Lapel', 'Peak Lapel', 'Shawl Lapel']), 'price_modifier': 0},
                 {'variant_group': 'Fit', 'variant_options': json.dumps(['Regular', 'Slim', 'Oversized', 'Cropped']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Nehru Jacket', 'display_order': 2,
             'description': 'Traditional Nehru collar mandarin jacket for ethnic occasions.',
             'base_price_modifier': 200, 'fabric_suggestions': json.dumps(['Brocade', 'Silk', 'Khadi', 'Velvet']),
             'variants': [
                 {'variant_group': 'Length', 'variant_options': json.dumps(['Short', 'Mid', 'Long']), 'price_modifier': 0},
                 {'variant_group': 'Embellishment', 'variant_options': json.dumps(['Plain', 'Embroidered', 'Printed', 'Quilted']), 'price_modifier': 100},
             ]},
            {'design_id': design_id, 'name': 'Bomber Jacket', 'display_order': 3,
             'description': 'Casual bomber with ribbed collar, cuffs and hem.',
             'base_price_modifier': 100, 'fabric_suggestions': json.dumps(['Satin', 'Nylon', 'Velvet', 'Denim']),
             'variants': [
                 {'variant_group': 'Closure', 'variant_options': json.dumps(['Zip', 'Snap Buttons', 'Open Front']), 'price_modifier': 0},
                 {'variant_group': 'Detail', 'variant_options': json.dumps(['Plain', 'Embroidered', 'Printed', 'Patched']), 'price_modifier': 100},
             ]},
        ]

    def ethnic_entries(design_id):
        return [
            {'design_id': design_id, 'name': 'Saree Gown', 'display_order': 1,
             'description': 'Pre-stitched saree gown — elegance of saree, ease of a gown.',
             'base_price_modifier': 500, 'fabric_suggestions': json.dumps(['Georgette', 'Net', 'Chiffon', 'Silk']),
             'variants': [
                 {'variant_group': 'Silhouette', 'variant_options': json.dumps(['A-line', 'Mermaid', 'Column']), 'price_modifier': 0},
                 {'variant_group': 'Drape Style', 'variant_options': json.dumps(['Classic Pallu', 'Cape Pallu', 'Butterfly Drape']), 'price_modifier': 100},
                 {'variant_group': 'Occasion', 'variant_options': json.dumps(['Bridal', 'Reception', 'Festive', 'Casual']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Indowestern Kurta', 'display_order': 2,
             'description': 'Fusion kurta blending Indian and western design elements.',
             'base_price_modifier': 200, 'fabric_suggestions': json.dumps(['Cotton', 'Linen', 'Khadi', 'Silk Blend']),
             'variants': [
                 {'variant_group': 'Style', 'variant_options': json.dumps(['Dhoti Pant Style', 'Asymmetric Hem', 'Jacket Style', 'Sherwani Style']), 'price_modifier': 0},
                 {'variant_group': 'Occasion', 'variant_options': json.dumps(['Casual', 'Festive', 'Office Fusion']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Cape Gown', 'display_order': 3,
             'description': 'Dramatic layered cape over a fitted gown — bridal & reception favourite.',
             'base_price_modifier': 1000, 'fabric_suggestions': json.dumps(['Net', 'Organza', 'Silk', 'Georgette']),
             'variants': [
                 {'variant_group': 'Cape Length', 'variant_options': json.dumps(['Waist Length', 'Floor Length', 'Trail']), 'price_modifier': 200},
                 {'variant_group': 'Embellishment', 'variant_options': json.dumps(['Sequin', 'Embroidery', 'Mirror Work', 'Plain']), 'price_modifier': 300},
             ]},
        ]

    def shirt_entries(design_id):
        return [
            {'design_id': design_id, 'name': 'Formal Dress Shirt', 'display_order': 1,
             'description': 'Classic formal shirt — office, events, and business meetings.',
             'base_price_modifier': 0, 'fabric_suggestions': json.dumps(['Cotton', 'Poplin', 'Linen', 'Oxford']),
             'variants': [
                 {'variant_group': 'Collar', 'variant_options': json.dumps(['Classic Collar', 'Spread Collar', 'Button-Down Collar']), 'price_modifier': 0},
                 {'variant_group': 'Sleeve', 'variant_options': json.dumps(['Full Sleeve', '3/4 Sleeve', 'French Cuff']), 'price_modifier': 0},
                 {'variant_group': 'Fit', 'variant_options': json.dumps(['Regular Fit', 'Slim Fit', 'Relaxed Fit']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Casual Shirt', 'display_order': 2,
             'description': 'Relaxed casual shirt for everyday wear.',
             'base_price_modifier': -50, 'fabric_suggestions': json.dumps(['Cotton', 'Linen', 'Chambray', 'Flannel']),
             'variants': [
                 {'variant_group': 'Sleeve', 'variant_options': json.dumps(['Half Sleeve', 'Full Sleeve', 'Roll-up Sleeve']), 'price_modifier': 0},
                 {'variant_group': 'Fit', 'variant_options': json.dumps(['Regular', 'Oversized', 'Boxy']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Designer Shirt', 'display_order': 3,
             'description': 'Fashion-forward designer shirt with unique details.',
             'base_price_modifier': 150, 'fabric_suggestions': json.dumps(['Satin', 'Silk', 'Crepe', 'Georgette']),
             'variants': [
                 {'variant_group': 'Collar', 'variant_options': json.dumps(['Mandarin Collar', 'Ruffle Collar', 'Peter Pan Collar', 'Polo Collar']), 'price_modifier': 0},
                 {'variant_group': 'Style', 'variant_options': json.dumps(['Gathered Front', 'Peplum Hem', 'Lace Inset', 'Side Slit']), 'price_modifier': 50},
             ]},
        ]

    def trouser_entries(design_id):
        return [
            {'design_id': design_id, 'name': 'Formal Trousers', 'display_order': 1,
             'description': 'Classic formal trousers for office and events.',
             'base_price_modifier': 0, 'fabric_suggestions': json.dumps(['Wool Blend', 'Polyester', 'Cotton Twill']),
             'variants': [
                 {'variant_group': 'Silhouette', 'variant_options': json.dumps(['Straight Leg', 'Slim Fit', 'Tapered']), 'price_modifier': 0},
                 {'variant_group': 'Waistband', 'variant_options': json.dumps(['Flat Front', 'Pleated Front', 'Belt Loops']), 'price_modifier': 0},
                 {'variant_group': 'Rise', 'variant_options': json.dumps(['High Rise', 'Mid Rise']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Wide Leg Trousers', 'display_order': 2,
             'description': 'Relaxed wide-leg silhouette — trendy and comfortable.',
             'base_price_modifier': 50, 'fabric_suggestions': json.dumps(['Linen', 'Cotton', 'Crepe', 'Rayon']),
             'variants': [
                 {'variant_group': 'Waist', 'variant_options': json.dumps(['Elasticated', 'Drawstring', 'Paperbag Waist', 'Belt Loops']), 'price_modifier': 0},
                 {'variant_group': 'Length', 'variant_options': json.dumps(['Full Length', 'Ankle Length', 'Cropped']), 'price_modifier': 0},
             ]},
            {'design_id': design_id, 'name': 'Palazzo', 'display_order': 3,
             'description': 'Flowy palazzo-style wide trousers, great for Indian fusion looks.',
             'base_price_modifier': 0, 'fabric_suggestions': json.dumps(['Georgette', 'Chiffon', 'Crepe', 'Cotton']),
             'variants': [
                 {'variant_group': 'Waist', 'variant_options': json.dumps(['Elasticated', 'Drawstring', 'Tie Waist']), 'price_modifier': 0},
             ]},
        ]

    # ── Build all sample_designs ───────────────────────────────────────────────
    all_sample_designs = []
    for name, fn in [
        ('Blouse', blouse_entries), ('Saree Blouse', saree_blouse_entries),
        ('Lehenga', lehenga_entries), ('Salwar Suit', salwar_entries),
        ('Kurti', kurti_entries), ('Skirt', skirt_entries),
        ('Dress/Frock', dress_entries), ('Jacket/Blazer', jacket_entries),
        ('Ethnic/Indo-Western', ethnic_entries), ('Shirt', shirt_entries),
        ('Trouser', trouser_entries),
    ]:
        d = get_design(name)
        if d:
            all_sample_designs.extend(fn(d.id))

    # Default style agent config
    if not StyleAgentConfig.query.first():
        default_config = StyleAgentConfig(
            config_name='Standard Hours (10 AM – 6 PM)',
            start_hour=10, end_hour=18, slot_duration_minutes=30, is_active=True,
        )
        db.session.add(default_config)
        print('Default style agent schedule config created.')

    added = 0
    for sd in all_sample_designs:
        variants_data = sd.pop('variants', [])
        if not ProductDesign.query.filter_by(design_id=sd['design_id'], name=sd['name']).first():
            pd_obj = ProductDesign(**sd)
            db.session.add(pd_obj)
            db.session.flush()
            for vd in variants_data:
                v = DesignVariant(product_design_id=pd_obj.id, **vd)
                db.session.add(v)
            added += 1
            print(f'  Added: {pd_obj.name}')

    db.session.commit()
    print(f'\nCatalogue seed complete — {added} product designs added.')


if __name__ == '__main__':
    # Never hard-code debug=True. Set FLASK_DEBUG=1 in your .env for local dev.
    debug = os.environ.get('FLASK_DEBUG', '0').strip() == '1'
    app.run(debug=debug)
