"""
Demo Data Seeder — TailorApp
Run: python seed_demo_data.py

Creates:
  • 25 tailor accounts (tailor01@demo.com … tailor25@demo.com, password: Demo@1234)
  • 5  customer accounts (customer1@demo.com … customer5@demo.com, password: Demo@1234)
  • MeasurementTemplate for each tailor × design they specialise in
  • TailorProductService entries linking tailors to catalogue designs

Idempotent — safe to run multiple times (skips existing emails).
"""

import sys
import os
import json
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import (User, TailorProfile, Design,
                        TailorMeasurementTemplate, ProductDesign,
                        TailorProductService)

app = create_app()

# ─────────────────────────────────────────────────────────────────────────────
# Data tables
# ─────────────────────────────────────────────────────────────────────────────

DEMO_PASSWORD = "Demo@1234"

# 25 tailors: (name, shop_name, city_address, specialisations, experience_yrs, bio, rating, rating_count)
TAILORS = [
    # ── Mumbai — Women's wear ──────────────────────────────────────────────
    ("Priya Sharma",    "Priya's Boutique",
     "Shop 3, Linking Road, Bandra West, Mumbai 400050",
     ["Blouse", "Saree Blouse", "Lehenga", "Skirt"],
     12, "Specialising in designer blouses and bridal lehengas for over a decade.", 4.8, 31),

    ("Sunita Devi",     "Sunita Stitches",
     "Ground Floor, Dadar Market Complex, Dadar, Mumbai 400014",
     ["Salwar Suit", "Kurti", "Blouse", "Dress/Frock"],
     8,  "Known for crisp stitching and quick turnaround on everyday wear.", 4.5, 19),

    ("Rekha Patel",     "Rekha Fashion Studio",
     "1st Floor, Hill Road, Bandra, Mumbai 400050",
     ["Saree Blouse", "Blouse", "Ethnic/Indo-Western", "Dress/Frock"],
     15, "Expert in traditional saree blouses with modern design sensibility.", 4.9, 47),

    ("Meena Agarwal",   "Meena Couture",
     "Shop 7, Lokhandwala Complex, Andheri West, Mumbai 400053",
     ["Lehenga", "Ethnic/Indo-Western", "Salwar Suit", "Dress/Frock"],
     10, "Creating couture-quality lehengas and indo-western fusion outfits.", 4.7, 28),

    ("Kavita Singh",    "Kavita Creations",
     "2nd Floor, Colaba Causeway, Colaba, Mumbai 400005",
     ["Kurti", "Blouse", "Skirt", "Salwar Suit"],
     6,  "Young designer who blends contemporary cuts with ethnic sensibility.", 4.3, 14),

    # ── Delhi — Men's wear ─────────────────────────────────────────────────
    ("Raj Kumar",       "Raj Tailors & Co.",
     "Shop 12, Karol Bagh Market, New Delhi 110005",
     ["Shirt", "Trouser", "Jacket/Blazer", "Ethnic/Indo-Western"],
     20, "Multi-generational tailoring shop known across Delhi for perfect fits.", 4.9, 62),

    ("Suresh Nair",     "Suresh Menswear",
     "Ground Floor, Connaught Place, New Delhi 110001",
     ["Shirt", "Trouser", "Ethnic/Indo-Western"],
     14, "Premium formal shirts and trousers for the corporate professional.", 4.6, 33),

    ("Mohan Das",       "Mohan & Sons Tailors",
     "Shop 5, Lajpat Nagar Central Market, New Delhi 110024",
     ["Jacket/Blazer", "Shirt", "Trouser"],
     18, "Specialists in bespoke suits, blazers, and formal occasion wear.", 4.8, 41),

    ("Vikram Yadav",    "Vikram Fashion House",
     "1st Floor, Sarojini Nagar Market, New Delhi 110023",
     ["Trouser", "Shirt", "Ethnic/Indo-Western"],
     9,  "Affordable and reliable stitching for everyday wear and office fashion.", 4.2, 22),

    ("Anand Verma",     "Anand Bespoke Suits",
     "Shop 8, Hauz Khas Village, New Delhi 110016",
     ["Jacket/Blazer", "Ethnic/Indo-Western", "Shirt"],
     16, "Hand-stitched bespoke suits and sherwani for weddings and galas.", 4.7, 38),

    # ── Bangalore — Mixed ─────────────────────────────────────────────────
    ("Padma Rao",       "Padma's Fashion Corner",
     "Shop 4, Commercial Street, Bengaluru 560001",
     ["Blouse", "Kurti", "Salwar Suit", "Dress/Frock"],
     11, "Contemporary ethnic wear with an eye for detail and comfort.", 4.6, 25),

    ("Krishna Murthy",  "Krishna Tailors",
     "Ground Floor, Brigade Road, Bengaluru 560025",
     ["Shirt", "Trouser", "Jacket/Blazer"],
     13, "Professional tailors for corporate formals and semi-formals.", 4.5, 30),

    ("Lakshmi Iyer",    "Lakshmi Fashions",
     "2nd Floor, Gandhi Bazaar, Basavanagudi, Bengaluru 560004",
     ["Saree Blouse", "Blouse", "Lehenga", "Ethnic/Indo-Western"],
     17, "Traditional South Indian expertise in silk blouses and bridal wear.", 4.8, 52),

    ("Rajan Pillai",    "Rajan Menswear",
     "Shop 2, MG Road, Bengaluru 560001",
     ["Shirt", "Trouser", "Ethnic/Indo-Western"],
     7,  "Neat and precise stitching, popular with the IT crowd for formals.", 4.1, 16),

    ("Saranya Kumar",   "Saranya Designs",
     "1st Floor, Jayanagar 4th Block, Bengaluru 560011",
     ["Salwar Suit", "Kurti", "Skirt", "Ethnic/Indo-Western"],
     9,  "Trendy ethnic wear fused with modern cuts and comfort fabrics.", 4.4, 21),

    # ── Chennai — Mixed ───────────────────────────────────────────────────
    ("Gomathy Venkat",  "Gomathy Boutique",
     "Shop 6, T. Nagar, Chennai 600017",
     ["Blouse", "Saree Blouse", "Skirt", "Dress/Frock"],
     14, "Expert in elaborate kanjivaram blouses and South Indian bridal wear.", 4.9, 58),

    ("Shankar Raja",    "Shankar Tailors",
     "2nd Floor, Anna Nagar, Chennai 600040",
     ["Shirt", "Trouser", "Jacket/Blazer"],
     16, "Known for impeccable finishing on formals and office wear.", 4.7, 35),

    ("Ambika Srinivas", "Ambika Fashion House",
     "Ground Floor, Mylapore, Chennai 600004",
     ["Lehenga", "Dress/Frock", "Ethnic/Indo-Western", "Salwar Suit"],
     12, "Designer lehengas and party dresses — crafted for Chennai's vibrant fashion scene.", 4.5, 27),

    ("Murugan Selvam",  "Murugan Stitching Centre",
     "Shop 3, Vadapalani, Chennai 600026",
     ["Shirt", "Trouser", "Salwar Suit"],
     10, "Budget-friendly tailoring with consistent quality and quick delivery.", 4.0, 18),

    ("Valli Natarajan", "Valli Designs",
     "1st Floor, Besant Nagar, Chennai 600090",
     ["Kurti", "Blouse", "Salwar Suit", "Ethnic/Indo-Western"],
     8,  "Young boutique specialising in trendy kurtis and party-ready salwar suits.", 4.3, 20),

    # ── Pune / Hyderabad / Kolkata / Ahmedabad / Jaipur ──────────────────
    ("Pooja Kulkarni",  "Pooja Fashions",
     "Shop 9, FC Road, Shivajinagar, Pune 411005",
     ["Blouse", "Saree Blouse", "Lehenga", "Salwar Suit", "Kurti"],
     13, "One-stop boutique for all women's occasion wear — sarees to lehengas.", 4.7, 44),

    ("Rajesh Reddy",    "Rajesh Tailors",
     "Ground Floor, Banjara Hills Road No. 12, Hyderabad 500034",
     ["Shirt", "Trouser", "Ethnic/Indo-Western"],
     11, "Precise formals and elegant sherwanis for the Hyderabad professional.", 4.4, 26),

    ("Durga Banerjee",  "Durga Couture",
     "2nd Floor, Park Street, Kolkata 700016",
     ["Lehenga", "Dress/Frock", "Ethnic/Indo-Western", "Blouse"],
     15, "Fusion of Bengali craft traditions with contemporary silhouettes.", 4.8, 39),

    ("Amit Shah",       "Amit Menswear",
     "Shop 5, C.G. Road, Navrangpura, Ahmedabad 380009",
     ["Shirt", "Jacket/Blazer", "Trouser", "Ethnic/Indo-Western"],
     12, "Quality menswear at competitive prices — formals to festive sherwanis.", 4.6, 29),

    ("Nalini Joshi",    "Nalini Boutique",
     "Ground Floor, M.I. Road, Jaipur 302001",
     ["Blouse", "Lehenga", "Salwar Suit", "Ethnic/Indo-Western", "Kurti"],
     19, "A Rajasthani atelier famed for hand-embroidered lehengas and vibrant ethnic wear.", 4.9, 67),
]

# 5 demo customers
CUSTOMERS = [
    ("Aarav Kumar",    "customer1@demo.com"),
    ("Sneha Patil",    "customer2@demo.com"),
    ("Ramesh Iyer",    "customer3@demo.com"),
    ("Deepa Nair",     "customer4@demo.com"),
    ("Arjun Malhotra", "customer5@demo.com"),
]

# Price multipliers per experience band (so senior tailors tend to charge more)
def price_mult(exp):
    if exp >= 15: return random.uniform(1.10, 1.30)
    if exp >= 8:  return random.uniform(0.95, 1.15)
    return random.uniform(0.80, 1.00)


# ─────────────────────────────────────────────────────────────────────────────
# Seed logic
# ─────────────────────────────────────────────────────────────────────────────

def seed():
    print("\n=== TailorApp Demo Data Seeder ===", flush=True)

    with app.app_context():
        designs_map = {d.name: d for d in Design.query.all()}
        if not designs_map:
            print("ERROR: No designs found. Run 'flask init-db' first.\n")
            sys.exit(1)

        print(f"Found {len(designs_map)} designs: {', '.join(designs_map.keys())}\n")

        # Customer accounts
        print("--- Creating customer accounts ---")
        for name, email in CUSTOMERS:
            if User.query.filter_by(email=email).first():
                print(f"  SKIP  {email} (exists)")
                continue
            u = User(name=name, email=email, phone="9800000000", role="customer", approval_status="approved")
            u.set_password(DEMO_PASSWORD)
            db.session.add(u)
            print(f"  OK    {email}")
        db.session.commit()

        # ── Tailor accounts ─────────────────────────────────────────────────
        print("\n--- Creating tailor accounts ---")
        for idx, (name, shop, address, specs, exp, bio, rating, rcount) in enumerate(TAILORS, 1):
            email = f"tailor{idx:02d}@demo.com"

            user = User.query.filter_by(email=email).first()
            if user:
                print(f"  SKIP  {email} (exists)")
                tp = TailorProfile.query.filter_by(user_id=user.id).first()
            else:
                user = User(name=name, email=email, phone=f"98{idx:08d}",
                            role="tailor", approval_status="approved")
                user.set_password(DEMO_PASSWORD)
                db.session.add(user)
                db.session.flush()  # get user.id

                tp = TailorProfile(
                    user_id=user.id,
                    shop_name=shop,
                    address=address,
                    bio=bio,
                    experience_years=exp,
                    rating=rating,
                    rating_count=rcount,
                    is_active=True,
                    is_available=True,
                    latitude=None,
                    longitude=None,
                )
                tp.set_specializations(specs)
                db.session.add(tp)
                db.session.flush()
                print(f"  OK    {email} — {shop} ({len(specs)} designs)")

            # ── MeasurementTemplate per design ──────────────────────────────
            if tp is None:
                db.session.commit()
                continue

            mult = price_mult(exp)
            for design_name in specs:
                design = designs_map.get(design_name)
                if not design:
                    continue
                existing_tmpl = TailorMeasurementTemplate.query.filter_by(
                    tailor_id=tp.id, design_id=design.id
                ).first()
                if existing_tmpl:
                    continue
                custom_price = round(design.base_price * mult / 50) * 50  # round to ₹50
                tmpl = TailorMeasurementTemplate(
                    tailor_id=tp.id,
                    design_id=design.id,
                    custom_price=float(custom_price),
                    measurement_fields=json.dumps(design.get_measurement_fields()),
                )
                db.session.add(tmpl)

            # ── TailorProductService for catalogue items ─────────────────────
            for design_name in specs:
                design = designs_map.get(design_name)
                if not design:
                    continue
                product_designs = ProductDesign.query.filter_by(
                    design_id=design.id, is_active=True
                ).all()
                for pd in product_designs:
                    existing_svc = TailorProductService.query.filter_by(
                        tailor_id=tp.id, product_design_id=pd.id
                    ).first()
                    if existing_svc:
                        continue
                    svc_price = round(pd.effective_base_price() * mult / 50) * 50
                    expertise = "expert" if exp >= 12 else ("intermediate" if exp >= 6 else "basic")
                    svc = TailorProductService(
                        tailor_id=tp.id,
                        product_design_id=pd.id,
                        custom_price=float(svc_price),
                        estimated_days=random.randint(3, 10),
                        expertise_level=expertise,
                        is_available=True,
                    )
                    db.session.add(svc)

            db.session.commit()

        # ── Summary ─────────────────────────────────────────────────────────
        print("\n--- Summary ---")
        tailor_count = TailorProfile.query.count()
        tmpl_count   = TailorMeasurementTemplate.query.count()
        svc_count    = TailorProductService.query.count()
        cust_count   = User.query.filter_by(role='customer').count()
        print(f"  Tailor profiles : {tailor_count}")
        print(f"  Customers       : {cust_count}")
        print(f"  Design templates: {tmpl_count}")
        print(f"  Catalogue svcs  : {svc_count}")

        print("\n--- Demo Login Credentials ---")
        print("  Customers  : customer1@demo.com … customer5@demo.com  / Demo@1234")
        print("  Tailors    : tailor01@demo.com  … tailor25@demo.com   / Demo@1234")
        print("\nDone!\n")


if __name__ == "__main__":
    seed()
