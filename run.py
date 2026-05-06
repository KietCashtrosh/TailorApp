import json
from app import create_app, db
from app.models import User, TailorProfile, Design
from sqlalchemy import text, inspect

app = create_app()


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
        },
    ]

    for d in designs_data:
        if not Design.query.filter_by(name=d['name']).first():
            design = Design(**d)
            db.session.add(design)

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

        # Add new columns to 'orders' if they don't exist
        orders_cols = {c['name'] for c in inspector.get_columns('orders')}
        order_additions = [
            ('family_profile_id', 'INTEGER REFERENCES family_profiles(id)'),
            ('tailor_receipt_otp', "VARCHAR(6) DEFAULT ''"),
            ('tailor_receipt_verified', 'BOOLEAN DEFAULT 0'),
            ('tailor_handover_otp', "VARCHAR(6) DEFAULT ''"),
            ('tailor_handover_verified', 'BOOLEAN DEFAULT 0'),
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

        db.session.commit()
        print('Migration complete.')


if __name__ == '__main__':
    app.run(debug=True)
