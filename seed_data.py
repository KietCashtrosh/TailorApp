import json
from app import create_app, db
from app.models import User, TailorProfile, Design

def seed_data():
    app = create_app()
    with app.app_context():
        print("Starting data seeding...")

        # 1. Seed Designs (Models / Product Catalogue)
        designs_to_add = [
            {
                'name': 'Anarkali Suit',
                'description': 'Elegant full-length ethnic wear with beautiful flare.',
                'base_price': 1500,
                'icon': 'bi-magic',
                'image_filename': 'design_anarkali.jpeg',
                'measurement_fields': json.dumps([
                    {'key': 'chest', 'label': 'Chest (inches)'},
                    {'key': 'waist', 'label': 'Waist (inches)'},
                    {'key': 'length', 'label': 'Full Length (inches)'},
                    {'key': 'sleeve', 'label': 'Sleeve Length (inches)'}
                ])
            },
            {
                'name': 'Gown',
                'description': 'Designer evening gowns and western party wear.',
                'base_price': 2500,
                'icon': 'bi-gem',
                'image_filename': 'design_gown.jpeg',
                'measurement_fields': json.dumps([
                    {'key': 'chest', 'label': 'Chest (inches)'},
                    {'key': 'waist', 'label': 'Waist (inches)'},
                    {'key': 'shoulder', 'label': 'Shoulder (inches)'},
                    {'key': 'length', 'label': 'Gown Length (inches)'}
                ])
            },
            {
                'name': 'Salwar Suit',
                'description': 'Traditional salwar kameez sets with custom fitting.',
                'base_price': 800,
                'icon': 'bi-layers',
                'image_filename': 'design_salwar.jpeg',
                'measurement_fields': json.dumps([
                    {'key': 'chest', 'label': 'Chest (inches)'},
                    {'key': 'waist', 'label': 'Waist (inches)'},
                    {'key': 'hip', 'label': 'Hip (inches)'},
                    {'key': 'top_length', 'label': 'Kameez Length (inches)'},
                    {'key': 'bottom_length', 'label': 'Salwar Length (inches)'}
                ])
            },
            {
                'name': 'Plazzo Suit',
                'description': 'Modern plazzo sets with stylish silhouettes.',
                'base_price': 1000,
                'icon': 'bi-风',
                'image_filename': 'design_plazzo.jpeg',
                'measurement_fields': json.dumps([
                    {'key': 'chest', 'label': 'Chest (inches)'},
                    {'key': 'top_length', 'label': 'Top Length (inches)'},
                    {'key': 'bottom_length', 'label': 'Plazzo Length (inches)'},
                    {'key': 'thigh', 'label': 'Thigh (inches)'}
                ])
            },
            {
                'name': 'Designer Wear',
                'description': 'Custom premium designer outfits for special occasions.',
                'base_price': 5000,
                'icon': 'bi-palette',
                'image_filename': 'design_designer_wear.png',
                'measurement_fields': json.dumps([
                    {'key': 'full_body', 'label': 'Full Body Measurements Required'}
                ])
            }
        ]

        for d_data in designs_to_add:
            existing = Design.query.filter_by(name=d_data['name']).first()
            if not existing:
                design = Design(**d_data)
                db.session.add(design)
                print(f"Added Design: {d_data['name']}")
            else:
                print(f"Design {d_data['name']} already exists.")

        # 2. Seed Tailors
        tailors_to_add = [
            {
                'name': 'Suresh Boutique',
                'email': 'tailor2@tailorapp.com',
                'phone': '9888888881',
                'shop_name': 'Suresh Ethnic Wear',
                'address': '45, Indiranagar, Bangalore',
                'specializations': ['Salwar Suit', 'Anarkali Suit'],
                'bio': 'Expert in ethnic wear with 15 years of experience.'
            },
            {
                'name': 'Anita Designs',
                'email': 'tailor3@tailorapp.com',
                'phone': '9888888882',
                'shop_name': 'Anita Couture',
                'address': '78, Koramangala, Bangalore',
                'specializations': ['Blouse', 'Gown', 'Designer Wear'],
                'bio': 'Boutique owner specializing in premium designer wear.'
            },
            {
                'name': 'Modern Tailors',
                'email': 'tailor4@tailorapp.com',
                'phone': '9888888883',
                'shop_name': 'Modern Gents & Ladies Tailor',
                'address': '101, Jayanagar, Bangalore',
                'specializations': ['Shirt', 'Trouser', 'Salwar Suit'],
                'bio': 'Fast and reliable tailoring for everyday needs.'
            }
        ]

        for t_data in tailors_to_add:
            if not User.query.filter_by(email=t_data['email']).first():
                user = User(
                    name=t_data['name'],
                    email=t_data['email'],
                    phone=t_data['phone'],
                    role='tailor',
                    approval_status='approved'
                )
                user.set_password('tailor123')
                db.session.add(user)
                db.session.flush()

                profile = TailorProfile(
                    user_id=user.id,
                    shop_name=t_data['shop_name'],
                    address=t_data['address'],
                    specializations=json.dumps(t_data['specializations']),
                    experience_years=10,
                    bio=t_data['bio']
                )
                db.session.add(profile)
                print(f"Added Tailor: {t_data['shop_name']} ({t_data['email']})")
            else:
                print(f"Tailor {t_data['email']} already exists.")

        # 3. Seed Delivery Agents
        agents_to_add = [
            {'name': 'Rahul Verma', 'email': 'delivery2@tailorapp.com', 'phone': '9777777771'},
            {'name': 'Vikram Das', 'email': 'delivery3@tailorapp.com', 'phone': '9777777772'},
            {'name': 'Sandeep K', 'email': 'delivery4@tailorapp.com', 'phone': '9777777773'}
        ]

        for a_data in agents_to_add:
            if not User.query.filter_by(email=a_data['email']).first():
                user = User(
                    name=a_data['name'],
                    email=a_data['email'],
                    phone=a_data['phone'],
                    role='delivery',
                    approval_status='approved'
                )
                user.set_password('delivery123')
                db.session.add(user)
                print(f"Added Delivery Agent: {a_data['name']} ({a_data['email']})")
            else:
                print(f"Delivery agent {a_data['email']} already exists.")

        db.session.commit()
        print("Seeding completed successfully!")

if __name__ == '__main__':
    seed_data()
