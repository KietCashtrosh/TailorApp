# TailorApp — Functional Documentation

> **Version:** MVP 1.0  
> **Stack:** Python 3 · Flask · SQLAlchemy · Bootstrap 5  
> **Last updated:** May 2026

---

## Table of Contents

1. [Overview](#1-overview)
2. [Tech Stack & Project Structure](#2-tech-stack--project-structure)
3. [Setup & Running the App](#3-setup--running-the-app)
4. [User Roles & Access Control](#4-user-roles--access-control)
5. [Database Models](#5-database-models)
6. [Order Lifecycle (State Machine)](#6-order-lifecycle-state-machine)
7. [Portal: Authentication](#7-portal-authentication)
8. [Portal: Customer](#8-portal-customer)
9. [Portal: Tailor](#9-portal-tailor)
10. [Portal: Delivery Agent / Style Agent](#10-portal-delivery-agent--style-agent)
11. [Portal: Admin](#11-portal-admin)
12. [Services](#12-services)
13. [API Endpoints (JSON)](#13-api-endpoints-json)
14. [Configuration Reference](#14-configuration-reference)
15. [Demo Accounts](#15-demo-accounts)

---

## 1. Overview

TailorApp is a multi-sided marketplace connecting **customers** who need custom clothing stitched, with **tailors** who provide stitching services, facilitated by **delivery/style agents** who handle fabric pickup and garment delivery — all orchestrated by an **admin**.

### Core Business Flow

```
Customer browses catalogue / tailors
    ↓
Adds to cart or places direct order
    ↓
Tailor accepts / rejects (within configurable window)
    ↓
Style Agent visits customer — collects fabric + takes measurements
    ↓
Tailor stitches garment
    ↓
Style Agent picks up from tailor and delivers to customer
    ↓
Customer pays, reviews, and rates
```

### Key Differentiators
- **Family Profiles** — order for multiple family members under one account
- **OTP-verified handoffs** — every pickup and delivery is verified with a 6-digit OTP
- **Per-tailor pricing** — tailors set their own prices per design; admin can override with offer prices
- **Multi-item cart** — customer can add items from multiple tailors; checkout creates one order per tailor
- **In-app chat** — real-time messaging between customer and tailor on each order
- **Style Agent slot booking** — customer selects preferred visit date/time at checkout (admin-toggleable)

---

## 2. Tech Stack & Project Structure

### Stack
| Layer | Technology |
|---|---|
| Backend | Python 3, Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF (CSRF), Flask-Mail |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Frontend | Bootstrap 5.3, Bootstrap Icons 1.11, HTMX 1.9, vanilla JS |
| Fonts | Inter (body), Playfair Display (headings) — Google Fonts |
| Auth | Session-based via Flask-Login, bcrypt password hashing |

### Project Structure
```
Claude_Tailor_App/
├── run.py                        # App entrypoint
├── config.py                     # Config class
├── .env                          # Environment variables (not committed)
├── .env.example                  # Template for .env
├── app/
│   ├── __init__.py               # App factory, blueprint registration
│   ├── extensions.py             # db, login_manager, csrf, mail instances
│   ├── models.py                 # All SQLAlchemy models
│   ├── blueprints/
│   │   ├── auth/routes.py        # Login, register, forgot/reset password
│   │   ├── customer/routes.py    # Customer portal
│   │   ├── tailor/routes.py      # Tailor portal
│   │   ├── delivery/routes.py    # Delivery/Style Agent portal
│   │   └── admin/routes.py       # Admin portal
│   ├── services/
│   │   ├── email_service.py      # Flask-Mail wrappers (fire-and-forget)
│   │   └── payment_service.py    # Simulated payment gateway
│   ├── templates/
│   │   ├── base.html             # Master layout (navbar, bottom nav, flash)
│   │   ├── auth/                 # login, register, forgot_password, reset_password
│   │   ├── customer/             # home, tailors, tailor_detail, cart, orders, etc.
│   │   ├── tailor/               # dashboard, orders, order_detail, profile, etc.
│   │   ├── delivery/             # dashboard, assignments, appointments
│   │   ├── admin/                # dashboard, orders, users, designs, analytics, etc.
│   │   └── errors/               # 404, 500
│   └── static/
│       ├── css/style.css         # Design system & component library
│       └── uploads/              # User-uploaded files (design images, catalogue)
```

---

## 3. Setup & Running the App

### 1. Install dependencies
```bash
cd Claude_Tailor_App
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
```
Edit `.env`:
```
SECRET_KEY=your-random-secret-key-here

# Email (required for notifications — see §12)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your@gmail.com

# Database (optional — defaults to SQLite)
# DATABASE_URL=postgresql://user:password@localhost:5432/tailorapp
```

### 3. Initialise the database
```bash
python run.py            # Creates tables on first run
# OR
flask shell
>>> from app.extensions import db
>>> db.create_all()
```

### 4. Create admin user (first run)
```bash
flask shell
>>> from app.models import User, db
>>> u = User(name='Admin', email='admin@tailorapp.com', role='admin')
>>> u.set_password('admin123')
>>> db.session.add(u)
>>> db.session.commit()
```

### 5. Run
```bash
python run.py            # http://127.0.0.1:5000
```

---

## 4. User Roles & Access Control

| Role | Description | Approval | Home Route |
|---|---|---|---|
| `customer` | Browses, orders, tracks | Auto-approved | `/` |
| `tailor` | Manages orders, prices, profile | Admin must approve | `/tailor/` |
| `delivery` | Handles fabric pickup/delivery & style agent visits | Admin must approve | `/delivery/` |
| `admin` | Full system control | Auto-approved (seeded) | `/admin/` |

### Role Guards
Each blueprint has a dedicated decorator:
- `customer_required` — redirects non-customers to login
- `tailor_required` — redirects non-tailors to login
- `delivery_required` — redirects non-delivery users to login
- `admin_required` — redirects non-admins to login

### Login Behaviour
- Customers with family profiles are redirected to the **profile selector** after login (if no active profile is set in session)
- Unapproved tailors/delivery agents see a "pending approval" message and cannot log in
- Rejected accounts see a "not approved" error message

### Session Variables
| Key | Type | Description |
|---|---|---|
| `active_profile_id` | int | Currently selected family profile for ordering |

### Context Processor (injected into every template)
| Variable | Description |
|---|---|
| `unread_notif_count` | Count of unread notifications for current user |
| `cart_count` | Number of items in customer's cart (0 for other roles) |
| `active_family_profile` | `FamilyProfile` object if one is active in session, else `None` |

---

## 5. Database Models

### User
Primary authentication and identity record for all roles.

| Field | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `name` | String(100) | |
| `email` | String(120) unique | Login identifier |
| `phone` | String(15) | |
| `password_hash` | String(256) | bcrypt |
| `role` | String(20) | `admin` / `tailor` / `delivery` / `customer` |
| `is_active` | Boolean | Soft-disable account |
| `approval_status` | String(20) | `approved` / `pending` / `rejected` |
| `default_pickup_address` | Text | Pre-filled in cart/order forms |
| `default_delivery_address` | Text | Pre-filled in cart/order forms |

---

### FamilyProfile
Linked to a customer; allows ordering on behalf of family members with separate saved measurements.

| Field | Type | Notes |
|---|---|---|
| `user_id` | FK → users | Parent customer |
| `name` | String(100) | |
| `relation` | String(50) | Self, Spouse, Child, Parent, etc. |
| `gender` | String(10) | |
| `date_of_birth` | String(20) | |
| `avatar_color` | String(20) | Hex colour for UI avatar circle |

---

### TailorProfile
Extended profile for tailor users.

| Field | Type | Notes |
|---|---|---|
| `user_id` | FK → users | One-to-one |
| `shop_name` | String(150) | |
| `address` | Text | |
| `latitude`, `longitude` | Float | For "Near Me" distance calculation |
| `specializations` | Text | JSON array of design names |
| `experience_years` | Integer | |
| `rating` | Float | Recomputed on every review submission |
| `rating_count` | Integer | |
| `is_active` | Boolean | Whether listed on Find Tailors |
| `is_available` | Boolean | Shop open/closed toggle |
| `bio` | Text | Short description shown on profile |

---

### Design
Defines a garment category (e.g. Blouse, Shirt, Lehenga).

| Field | Type | Notes |
|---|---|---|
| `name` | String(50) unique | |
| `base_price` | Float | Platform default price |
| `icon` | String(50) | Bootstrap Icons class |
| `measurement_fields` | Text | JSON: `[{"key": "chest", "label": "Chest (in)"}]` |
| `is_active` | Boolean | |

---

### TailorMeasurementTemplate
Per-tailor customisation of measurement fields and pricing for each design.

| Field | Type | Notes |
|---|---|---|
| `tailor_id` | FK → tailor_profiles | |
| `design_id` | FK → designs | Unique together |
| `measurement_fields` | Text | JSON override (or falls back to Design's fields) |
| `custom_price` | Float | Tailor's price (overrides `base_price`) |
| `admin_offer_price` | Float | Admin promotional override (takes priority over `custom_price`) |

**Effective price logic:**
```
admin_offer_price > custom_price > design.base_price
```

---

### Order
Core transactional record.

| Field | Type | Notes |
|---|---|---|
| `order_number` | String(20) unique | Format: `ORDYYMMDDxxxxxx` |
| `customer_id` | FK → users | |
| `tailor_id` | FK → tailor_profiles | |
| `design_id` | FK → designs | `NULL` for multi-item (cart) orders |
| `family_profile_id` | FK → family_profiles | Optional — who the order is for |
| `measurements` | Text | JSON key-value map |
| `measurement_preference` | String | `delivery_will_measure` / `use_saved` / `provided_by_customer` |
| `status` | String(30) | See §6 |
| `pickup_address` | Text | Where agent collects fabric |
| `delivery_address` | Text | Where finished garment is delivered |
| `estimated_price` | Float | Set at order creation |
| `final_price` | Float | Set by tailor on acceptance |
| `discount_amount` | Float | From coupon |
| `coupon_code` | String | |
| `payment_method` | String | `cod` / `online` / `cash` |
| `payment_status` | String | `unpaid` / `paid` / `cod_pending` |
| `tailor_receipt_otp` | String(6) | Tailor confirms fabric received from agent |
| `tailor_handover_otp` | String(6) | Agent confirms pickup of finished garment |
| `style_agent_appointment_date` | String | Preferred visit date (YYYY-MM-DD) |
| `style_agent_appointment_time` | String | Preferred visit time (HH:MM) |
| `auto_assigned_style_agent_id` | FK → users | Admin-assigned style agent |
| `customer_confirmed_slot` | Boolean | Customer confirmed admin assignment |

---

### OrderItem
For multi-item (cart) orders — each item within an order.

| Field | Type | Notes |
|---|---|---|
| `order_id` | FK → orders | |
| `design_id` | FK → designs | |
| `quantity` | Integer | |
| `unit_price` | Float | Price at time of order |
| `fabric_description` | Text | |
| `measurements` | Text | JSON |

---

### DeliveryAssignment
Links a delivery agent to a specific task within an order.

| Field | Type | Notes |
|---|---|---|
| `order_id` | FK → orders | |
| `delivery_agent_id` | FK → users | |
| `assignment_type` | String | `pickup_fabric` / `deliver_clothes` |
| `status` | String | `assigned` / `picked_up` / `delivered` |
| `pickup_otp` | String(6) | Customer shares this with agent at pickup |
| `delivery_otp` | String(6) | Customer shares this with agent at delivery |
| `pickup_otp_verified` | Boolean | |
| `delivery_otp_verified` | Boolean | |

---

### CartItem
Staging area before checkout. One row per design+tailor combination.

| Field | Type | Notes |
|---|---|---|
| `customer_id` | FK → users | |
| `tailor_id` | FK → tailor_profiles | |
| `design_id` | FK → designs | |
| `quantity` | Integer | |
| `measurement_preference` | String | Same options as Order |
| `measurements` | Text | JSON |

---

### Coupon

| Field | Type | Notes |
|---|---|---|
| `code` | String(30) unique | Uppercase |
| `discount_type` | String | `percent` / `fixed` |
| `discount_value` | Float | % or ₹ amount |
| `min_order_amount` | Float | Minimum cart value |
| `max_uses` | Integer | 0 = unlimited |
| `uses_count` | Integer | Incremented on use |
| `valid_from`, `valid_to` | DateTime | Validity window |
| `is_active` | Boolean | |

---

### Notification
In-app notification inbox for all user roles.

| Field | Type | Notes |
|---|---|---|
| `user_id` | FK → users | |
| `title` | String(200) | Bold heading in notification list |
| `body` | Text | Description text |
| `type` | String | `info` / `success` / `warning` / `danger` |
| `order_id` | FK → orders | Optional deep-link context |
| `link` | String | URL to navigate to |
| `is_read` | Boolean | |

**Helper:** `notify(user_id, message, link='')` — creates a basic notification. `Notification.create(...)` — creates a rich notification with title + body.

---

### CustomerMeasurement
Persistent store of a customer's measurements per design (updated by delivery agent or self-entry).

| Field | Type | Notes |
|---|---|---|
| `customer_id` | FK → users | |
| `design_id` | FK → designs | Unique together |
| `measurements` | Text | JSON |
| `taken_by_id` | FK → users | Which agent recorded them (nullable) |

---

### Review
Post-delivery rating submitted by customer.

| Field | Type | Notes |
|---|---|---|
| `order_id` | FK → orders | One-to-one |
| `tailor_rating` | Integer | 1–5 |
| `tailor_comment` | Text | |
| `delivery_rating` | Integer | 1–5 (optional) |
| `delivery_comment` | Text | |

Submitting a review triggers recomputation of `TailorProfile.rating` (rolling average).

---

### ProductDesign / DesignVariant / DesignImage / TailorProductService
Multi-level catalogue system.

```
Design (Category)         e.g. Blouse
  └── ProductDesign       e.g. Round-Neck Blouse
        ├── DesignVariant e.g. Sleeve: [Half, Full, None]
        ├── DesignImage   e.g. main photo, gallery, size chart
        └── TailorProductService  → per-tailor price, ETA, availability
```

---

### StyleAgentAppointment
A customer-booked visit by a Style Agent.

| Field | Type | Notes |
|---|---|---|
| `customer_id` | FK → users | |
| `style_agent_id` | FK → users | Assigned by admin |
| `appointment_date` | String | YYYY-MM-DD |
| `appointment_time` | String | HH:MM |
| `service_type` | String | `measurement_only` / `fabric_pickup_only` / `both` |
| `status` | String | `pending` → `confirmed` → `agent_assigned` → `arrived` → `completed` |
| `customer_address` | Text | Where agent visits |

---

### StyleAgentConfig
Admin-configurable working hours for appointment slot generation.

| Field | Type | Notes |
|---|---|---|
| `start_hour` | Integer | Default: 10 (10:00 AM) |
| `end_hour` | Integer | Default: 18 (6:00 PM) |
| `slot_duration_minutes` | Integer | Default: 30 |

`generate_slots()` produces `["10:00", "10:30", ...]` within the configured window.

---

### AdminConfig (Singleton)
System-wide toggleable settings. Always retrieve via `AdminConfig.get()`.

| Field | Default | Description |
|---|---|---|
| `tailor_acceptance_window_hours` | 2 | Hours a tailor has to accept before auto-action |
| `enable_style_agent_slot_booking` | True | Show/hide slot picker at cart checkout |
| `auto_confirm_orders_if_no_response` | False | Auto-accept if tailor doesn't respond in time |

---

### PaymentTransaction / PaymentAllocation
Simulated payment records.

**PaymentTransaction:** one per payment attempt. Status: `pending` → `success` / `failed` / `refund_initiated` / `refunded`.

**PaymentAllocation:** how a successful payment is split:
- Platform: 10% (configurable via `PLATFORM_FEE_PERCENT`)
- Tailor: 80% (configurable via `TAILOR_SHARE_PERCENT`)
- Style Agent: 10% (configurable via `AGENT_SHARE_PERCENT`)

---

## 6. Order Lifecycle (State Machine)

```
PLACED
  ├── accepted ──→ fabric_pickup ──→ fabric_collected ──→ stitching ──→ ready ──→ out_for_delivery ──→ DELIVERED
  ├── rejected
  └── cancelled  (only from 'placed')
```

### Status Transitions

| From | To | Who | Trigger |
|---|---|---|---|
| — | `placed` | Customer | Place order or cart checkout |
| `placed` | `accepted` | Tailor | Accept order in portal |
| `placed` | `rejected` | Tailor | Reject order in portal |
| `placed` | `cancelled` | Customer | Cancel before tailor accepts |
| `accepted` | `fabric_pickup` | Admin | Assign delivery agent (pickup task) |
| `fabric_pickup` | `fabric_collected` | Delivery Agent | Verify pickup OTP from customer |
| `fabric_collected` | `stitching` | Tailor | Verify tailor receipt OTP from agent |
| `stitching` | `ready` | Tailor | Mark as ready in portal |
| `ready` | `out_for_delivery` | Delivery Agent | Verify tailor handover OTP |
| `out_for_delivery` | `delivered` | Delivery Agent | Verify delivery OTP from customer |

### OTP Flow

```
When pickup_fabric assignment is created:
  → DeliveryAssignment.pickup_otp   (shown to customer)
  → DeliveryAssignment.delivery_otp (also shown to customer)

When fabric_collected:
  → Order.tailor_receipt_otp generated  (shown to delivery agent → give to tailor)

When order marked 'ready':
  → Order.tailor_handover_otp generated  (tailor gives to delivery agent)
```

---

## 7. Portal: Authentication

**Blueprint prefix:** `/auth`

| Route | Method | Description |
|---|---|---|
| `/auth/login` | GET, POST | Login form. Validates credentials, checks approval status, handles "remember me". Redirects to profile selector for customers with family profiles. |
| `/auth/register` | GET, POST | Registration. Role selection (customer/tailor/delivery). Tailors/delivery start as `pending`. Creates `TailorProfile` automatically for tailor registrations. |
| `/auth/forgot-password` | GET, POST | Generates `PasswordResetToken` (1-hour expiry). In demo mode: shows reset link in flash message. In production: emails the link. |
| `/auth/reset-password/<token>` | GET, POST | Token-validated password reset form. Marks token as `used` after success. |
| `/auth/logout` | GET | Clears session (`active_profile_id`), logs out, redirects to login. |

**Password Reset Token:** `secrets.token_urlsafe(32)`, valid for 1 hour, single-use. Previous unused tokens for the same user are invalidated when a new one is created.

---

## 8. Portal: Customer

**Blueprint prefix:** `/` (root)  
**Access guard:** `customer_required` (except public pages: home, tailors, tailor_detail, catalogue)

### 8.1 Public Pages

| Route | Description |
|---|---|
| `GET /` | **Home** — displays design categories, featured tailors, hero CTA |
| `GET /tailors` | **Find Tailors** — filterable/searchable tailor listing with "Near Me" geolocation sort |
| `GET /tailors/<id>` | **Tailor Detail** — shop info, design services with pricing, "Order" and "Add to Cart" CTAs |
| `GET /catalogue` | **Catalogue Level 1** — design category grid |
| `GET /catalogue/<id>` | **Catalogue Level 2** — sub-designs under a category |
| `GET /catalogue/design/<id>` | **Catalogue Level 3** — design detail with variants, images, tailors who can stitch it |

#### Tailor Search Filters
- `search` — shop name or address keyword
- `design` — filter by specialization
- `min_rating` — minimum rating (3.5 / 4.0 / 4.5)
- `sort` — `rating`, `price_asc`, `price_desc`, `distance` (requires geolocation)
- `lat`, `lng` — user coordinates for distance sort (browser Geolocation API)

---

### 8.2 Profile Management

| Route | Description |
|---|---|
| `GET /profile` | View/edit name, phone, default pickup/delivery addresses |
| `GET /profiles` | List family profiles |
| `GET /profiles/select` | Post-login profile selector |
| `GET/POST /profiles/new` | Create a family profile |
| `GET/POST /profiles/<id>/edit` | Edit a family profile |
| `POST /profiles/<id>/delete` | Delete a family profile |
| `POST /profiles/<id>/activate` | Set active ordering profile in session |
| `POST /profiles/clear` | Switch back to ordering as self |
| `GET /measurements` | View saved measurements per design |

---

### 8.3 Cart

| Route | Description |
|---|---|
| `GET /cart` | View cart with items, addresses, payment, slot picker |
| `GET/POST /cart/add` | Add item to cart. Shows measurement form. If same design+tailor already in cart, increments quantity. |
| `POST /cart/remove/<item_id>` | Remove item from cart |
| `POST /cart/update/<item_id>` | Increment or decrement quantity (`action=increase/decrease`) |
| `POST /cart/checkout` | Convert cart to orders (one order per tailor), apply coupon, store style agent slot, clear cart |

**Cart Checkout Logic:**
1. Groups cart items by tailor
2. Creates one `Order` per tailor group
3. Creates `OrderItem` records for each item within that order
4. Applies coupon discount per-order
5. Saves style agent slot date/time on each order (if `enable_style_agent_slot_booking` is `True`)
6. Saves updated default addresses to user profile
7. Sends in-app notification to each tailor
8. Clears all cart items

---

### 8.4 Orders

| Route | Description |
|---|---|
| `GET /orders` | My Orders list with status filter tabs (paginated, 10/page) |
| `GET/POST /order/new` | Direct single-item order form (bypasses cart) |
| `GET /orders/<id>` | Order detail — summary, progress, OTP codes, measurements, chat, review |
| `POST /orders/<id>/cancel` | Cancel (only allowed while status = `placed`) |
| `GET/POST /orders/<id>/review` | Submit review (only when status = `delivered`, one per order) |
| `POST /orders/<id>/pay` | Trigger payment via payment service |
| `POST /orders/<id>/confirm-style-agent` | Customer confirms admin-assigned style agent |

**Direct Order Flow:**
1. Customer selects tailor + design
2. Chooses measurement preference:
   - `delivery_will_measure` — agent measures at pickup
   - `use_saved` — uses `CustomerMeasurement` record
   - `provided_by_customer` — fills form, saved to `CustomerMeasurement`
3. Optionally enters coupon code (validated client-side via `/api/coupon/validate`)
4. Order created with status `placed`
5. Tailor notified via in-app notification
6. Email sent via `email_service.send_order_placed()`

---

### 8.5 Style Agent Appointments

| Route | Description |
|---|---|
| `GET /appointments` | View all appointments |
| `GET/POST /appointments/book` | Book a style agent visit (date, time slot, service type, address) |
| `POST /appointments/<id>/cancel` | Cancel (not allowed for `completed` or already `cancelled`) |

**Appointment Flow:**
1. Customer selects date (within `BOOKING_ADVANCE_DAYS` from tomorrow) and time slot from active `StyleAgentConfig`
2. Appointment created with status `pending`
3. Admin assigns a delivery agent → status `agent_assigned`
4. Agent marks `arrived` when at customer location
5. Agent marks `completed` with notes → customer notified + email sent

---

### 8.6 Messaging

| Route | Description |
|---|---|
| `POST /orders/<id>/messages/send` | Send a chat message to the tailor |
| `GET /api/orders/<id>/messages` | Poll for new messages since `?since=<last_id>` (JSON) |

Chat is polled every 5 seconds from the order detail page. New messages appended to DOM without page reload.

---

### 8.7 Notifications

| Route | Description |
|---|---|
| `GET /my-notifications` | View all notifications; marks all as read |
| `GET /api/notifications/count` | Badge count poll (notifications + cart count, JSON) |

Notification badge in navbar is polled every **30 seconds** via the base template JS.

---

## 9. Portal: Tailor

**Blueprint prefix:** `/tailor`  
**Access guard:** `tailor_required`

### Dashboard
`GET /tailor/`

Shows live stats:
- **New** — orders with status `placed`
- **Active** — orders in `accepted`, `fabric_pickup`, `fabric_collected`, `stitching`
- **Ready** — orders with status `ready`
- **Completed** — delivered orders count

Last 8 orders shown as a quick list.

---

### Orders

| Route | Description |
|---|---|
| `GET /tailor/orders` | Paginated order list (15/page) with status filter |
| `GET /tailor/orders/<id>` | Full order detail with history, measurements, chat |
| `POST /tailor/orders/<id>/update-status` | Move order through allowed transitions |
| `POST /tailor/orders/<id>/verify-receipt` | Verify tailor receipt OTP to start stitching |

**Allowed Status Transitions (Tailor):**

| Current | Can Move To |
|---|---|
| `placed` | `accepted` or `rejected` |
| `fabric_collected` | `stitching` (via OTP verification) |
| `stitching` | `ready` |

When accepting: tailor can set `estimated_days` and `final_price`.  
When marking ready: `tailor_handover_otp` is auto-generated for agent pickup verification.

---

### Profile & Measurement Templates

| Route | Description |
|---|---|
| `GET/POST /tailor/profile` | Edit shop name, address, bio, experience, GPS coords, specializations |
| `GET /tailor/measurement-templates` | List all designs with template status |
| `GET/POST /tailor/measurement-templates/<design_id>` | Create/edit custom measurement fields and price for a design |
| `POST /tailor/measurement-templates/<design_id>/reset` | Delete custom template, fall back to global defaults |
| `POST /tailor/availability/toggle` | Toggle shop open/closed (affects Find Tailors listing) |

---

### Messaging & Notifications

Same structure as customer-side — chat polled every 5 seconds, notification badge polled every 30 seconds via `/tailor/api/notifications/count`.

---

## 10. Portal: Delivery Agent / Style Agent

**Blueprint prefix:** `/delivery`  
**Access guard:** `delivery_required`

A single delivery user type handles two distinct workflows:

1. **Delivery Assignments** — physical pickup/delivery of fabric and garments for orders
2. **Style Agent Appointments** — home visits to take measurements and/or collect fabric

### Delivery Assignments

| Route | Description |
|---|---|
| `GET /delivery/` | Dashboard: active assignments + completed count |
| `GET /delivery/assignments` | All assignments with status filter |
| `GET /delivery/assignments/<id>` | Assignment detail with OTP form and measurement form |
| `POST /delivery/assignments/<id>/verify-otp` | Verify OTP for `pickup`, `tailor_handover`, or `deliver` actions |
| `POST /delivery/assignments/<id>/save-measurements` | Record measurements during fabric pickup (saved to order + `CustomerMeasurement`) |

**OTP Verification Actions:**

| `action` | OTP Used | Effect |
|---|---|---|
| `pickup` | `DeliveryAssignment.pickup_otp` | Status → `picked_up`; if `pickup_fabric`, generates `tailor_receipt_otp`, order → `fabric_collected` |
| `tailor_handover` | `Order.tailor_handover_otp` | Assignment status → `picked_up`; order → `out_for_delivery` |
| `deliver` | `DeliveryAssignment.delivery_otp` | Assignment status → `delivered`; if `deliver_clothes`, order → `delivered` |

---

### Style Agent Appointments

| Route | Description |
|---|---|
| `GET /delivery/my-appointments` | All appointments assigned to this agent |
| `GET /delivery/my-appointments/<id>` | Appointment detail |
| `POST /delivery/my-appointments/<id>/arrived` | Mark arrived at customer location |
| `POST /delivery/my-appointments/<id>/complete` | Mark completed (with agent notes); customer notified + email sent |
| `POST /delivery/my-appointments/<id>/reschedule` | Flag for rescheduling (admin follows up) |

---

## 11. Portal: Admin

**Blueprint prefix:** `/admin`  
**Access guard:** `admin_required`

### 11.1 Dashboard
`GET /admin/`

Real-time stats:
- Total orders, pending orders, delivered orders
- Total active tailors, total customers, total delivery agents
- Pending approvals count
- Last 10 orders table

---

### 11.2 User Management

| Route | Description |
|---|---|
| `GET /admin/approvals` | Pending tailor/delivery registrations awaiting approval |
| `POST /admin/approvals/<id>/approve` | Approve user; notifies them |
| `POST /admin/approvals/<id>/reject` | Reject user; notifies them |
| `GET /admin/users` | All users with role/status filter |
| `POST /admin/users/<id>/toggle` | Enable/disable user account |
| `GET /admin/users/add-tailor` | Add tailor directly (admin-seeded) |
| `GET /admin/users/add-delivery` | Add delivery agent directly |

---

### 11.3 Order Management

| Route | Description |
|---|---|
| `GET /admin/orders` | Paginated order list with status/search filter |
| `GET /admin/orders/<id>` | Full order detail including style agent assignment |
| `POST /admin/orders/<id>/assign-delivery` | Create `DeliveryAssignment` for pickup or delivery; generates OTPs |
| `POST /admin/orders/<id>/update-status` | Force-update any order status |
| `POST /admin/orders/<id>/add-note` | Add admin note to order |
| `GET /admin/orders/export` | Export filtered orders as CSV |

---

### 11.4 Design Management

| Route | Description |
|---|---|
| `GET /admin/designs` | List all designs |
| `GET/POST /admin/designs/new` | Create design with measurement fields |
| `GET/POST /admin/designs/<id>/edit` | Edit design |
| `POST /admin/designs/<id>/toggle` | Activate/deactivate |

---

### 11.5 Catalogue Management

| Route | Description |
|---|---|
| `GET /admin/catalogue` | List all `ProductDesign` entries |
| `GET/POST /admin/catalogue/new` | Create sub-design with variants, images, fabric suggestions |
| `GET/POST /admin/catalogue/<id>/edit` | Edit sub-design |
| `POST /admin/catalogue/<id>/images/upload` | Upload image (stored in `static/uploads/catalogue/`) |
| `POST /admin/catalogue/<id>/images/<img_id>/delete` | Remove image |

---

### 11.6 Tailor Offer Pricing

`GET /admin/tailors/<tailor_id>/offers`  
`POST /admin/tailors/<tailor_id>/offers/<design_id>/set`

Admin can set `admin_offer_price` on any `TailorMeasurementTemplate`, which overrides the tailor's own price (useful for platform-wide promotions).

---

### 11.7 Coupon Management

| Route | Description |
|---|---|
| `GET /admin/coupons` | List all coupons |
| `GET/POST /admin/coupons/new` | Create coupon (percent or fixed, with validity and usage limits) |
| `GET/POST /admin/coupons/<id>/edit` | Edit coupon |
| `POST /admin/coupons/<id>/toggle` | Activate/deactivate |

---

### 11.8 Style Agent Appointments

| Route | Description |
|---|---|
| `GET /admin/appointments` | All appointments with status filter |
| `POST /admin/appointments/<id>/assign-agent` | Assign a delivery user as style agent; status → `agent_assigned` |
| `POST /admin/appointments/<id>/confirm` | Confirm appointment; status → `confirmed`; customer emailed |
| `POST /admin/appointments/<id>/cancel` | Cancel with reason; customer notified |
| `GET /admin/schedule-config` | Manage `StyleAgentConfig` (working hours, slot duration) |

---

### 11.9 Style Agent Assignment for Orders

| Route | Description |
|---|---|
| `GET /admin/orders/<id>/assign-style-agent` | Form to assign a style agent to an order |
| `POST /admin/orders/<id>/assign-style-agent` | Saves assignment; customer notified + emailed |

Customer then confirms via `POST /orders/<id>/confirm-style-agent`.

---

### 11.10 Reviews

`GET /admin/reviews` — read-only list of all submitted reviews with ratings.

---

### 11.11 Analytics

`GET /admin/analytics`

- Orders per day (last 30 days)
- Revenue per day
- Top tailors by order count
- Status distribution breakdown

---

### 11.12 Financial

`GET /admin/financial`

- All `PaymentTransaction` records
- Per-transaction allocation breakdown (platform / tailor / agent)
- Payout status tracking

---

### 11.13 System Settings

`GET/POST /admin/settings`

Manages `AdminConfig` singleton:
- **Tailor acceptance window** (hours) — how long tailors have to accept before auto-action triggers
- **Style agent slot booking** (on/off) — show/hide the slot picker on cart checkout
- **Auto-confirm orders** (on/off) — auto-accept orders if tailor doesn't respond in time

---

## 12. Services

### Email Service (`app/services/email_service.py`)

**Fire-and-forget** — all email errors are caught and logged. A mail failure never breaks the order flow.

**Requires SMTP config in `.env`** (see §3). Without it, emails are silently skipped.

| Function | Triggered When | Recipient |
|---|---|---|
| `send_order_placed(order)` | Order created | Customer |
| `send_order_accepted(order)` | Tailor accepts | Customer |
| `send_order_ready(order)` | Order marked ready | Customer |
| `send_order_delivered(order)` | Order delivered | Customer |
| `send_appointment_confirmed(appt)` | Admin confirms appointment | Customer |
| `send_appointment_completed(appt)` | Agent completes visit | Customer |
| `send_payment_success(order, txn)` | Successful payment | Customer |
| `send_payment_failed(order, txn)` | Failed payment | Customer |
| `send_refund_initiated(order, amount)` | Refund triggered | Customer |
| `send_style_agent_assigned(order, agent)` | Admin assigns style agent | Customer |

All emails use an inline HTML template with TailorApp branding.

---

### Payment Service (`app/services/payment_service.py`)

Simulated gateway — **not a real payment processor**.

**`process_payment(order, payment_method)`**
- 95% success rate (random simulation)
- Creates `PaymentTransaction` record
- On success: creates `PaymentAllocation` rows (platform 10%, tailor 80%, agent 10%)
- Updates `order.payment_status` to `paid` or leaves `unpaid`
- Sends email notification either way
- Returns `(success: bool, transaction: PaymentTransaction)`

**`initiate_refund(order, amount=None)`**
- Finds latest successful transaction
- Sets status to `refund_initiated`
- Marks all allocations as `refunded`
- Sends refund email
- Returns the transaction

**To integrate a real gateway (Razorpay/Stripe):** replace `process_payment()` internals — the return signature `(bool, transaction)` and the allocation/email calls should remain unchanged.

---

## 13. API Endpoints (JSON)

| Endpoint | Auth | Description |
|---|---|---|
| `GET /api/designs/<id>/fields` | Optional | Measurement fields + base price for a design. If `?tailor_id=` provided, returns tailor-specific fields and price. Returns `saved_measurements` if user is logged in. |
| `GET /api/coupon/validate` | Customer | Validates coupon code against order amount. Returns `{valid, discount, message}`. |
| `GET /api/notifications/count` | Customer | Returns `{count, cart_count}` for badge updates. |
| `GET /api/orders/<id>/messages` | Customer | Poll messages since `?since=<id>`. Returns array of `{id, sender, content, time, is_mine}`. |
| `GET /tailor/api/notifications/count` | Tailor | Returns `{count}` for tailor notification badge. |
| `GET /tailor/api/orders/<id>/messages` | Tailor | Same structure as customer messages API. |
| `GET /admin/notifications` | Admin | Returns `{unassigned, new_orders, pending_approvals}`. |
| `GET /delivery/notifications` | Delivery | Returns `{new_assignments}`. |

---

## 14. Configuration Reference

All values set in `.env` or `config.py`.

| Key | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(required)* | Flask session signing key |
| `DATABASE_URL` | `sqlite:///tailor_app.db` | Database connection string |
| `MAIL_SERVER` | — | SMTP server host |
| `MAIL_PORT` | 587 | SMTP port |
| `MAIL_USE_TLS` | True | Enable STARTTLS |
| `MAIL_USERNAME` | — | SMTP login username |
| `MAIL_PASSWORD` | — | SMTP login password (use App Password for Gmail) |
| `MAIL_DEFAULT_SENDER` | `noreply@tailorapp.com` | From address |
| `UPLOAD_FOLDER` | `app/static/uploads` | Base path for file uploads |
| `ALLOWED_EXTENSIONS` | `{png, jpg, jpeg, webp}` | Allowed image types |
| `BOOKING_ADVANCE_DAYS` | 30 | Max days ahead a style agent appointment can be booked |
| `DEFAULT_TAILOR_SORT` | `distance` | Default sort on Find Tailors (falls back to `rating` if no location) |
| `PLATFORM_FEE_PERCENT` | 10 | Platform's share of each payment |
| `TAILOR_SHARE_PERCENT` | 80 | Tailor's share of each payment |
| `AGENT_SHARE_PERCENT` | 10 | Style agent's share of each payment |

---

## 15. Demo Accounts

| Role | Email | Password |
|---|---|---|
| Admin | admin@tailorapp.com | admin123 |
| Tailor | tailor1@tailorapp.com | tailor123 |
| Delivery/Style Agent | delivery1@tailorapp.com | delivery123 |
| Customer | customer1@tailorapp.com | customer123 |

---

## Appendix: URL Map Summary

```
/auth/login                         Auth: Login
/auth/register                      Auth: Register
/auth/forgot-password               Auth: Forgot Password
/auth/reset-password/<token>        Auth: Reset Password
/auth/logout                        Auth: Logout

/                                   Customer: Home
/tailors                            Customer: Find Tailors
/tailors/<id>                       Customer: Tailor Detail
/catalogue                          Customer: Catalogue (Level 1)
/catalogue/<id>                     Customer: Catalogue (Level 2)
/catalogue/design/<id>              Customer: Catalogue (Level 3)
/order/new                          Customer: Direct Order
/orders                             Customer: My Orders
/orders/<id>                        Customer: Order Detail
/orders/<id>/cancel                 Customer: Cancel Order
/orders/<id>/review                 Customer: Submit Review
/orders/<id>/pay                    Customer: Pay Order
/orders/<id>/confirm-style-agent    Customer: Confirm Style Agent
/orders/<id>/messages/send          Customer: Send Chat Message
/cart                               Customer: View Cart
/cart/add                           Customer: Add to Cart
/cart/remove/<id>                   Customer: Remove from Cart
/cart/update/<id>                   Customer: Update Quantity
/cart/checkout                      Customer: Checkout
/profile                            Customer: My Profile
/measurements                       Customer: My Measurements
/profiles                           Customer: Family Profiles
/profiles/select                    Customer: Select Profile
/profiles/new                       Customer: New Family Profile
/profiles/<id>/edit                 Customer: Edit Family Profile
/profiles/<id>/delete               Customer: Delete Family Profile
/profiles/<id>/activate             Customer: Activate Profile
/profiles/clear                     Customer: Clear Active Profile
/appointments                       Customer: My Appointments
/appointments/book                  Customer: Book Appointment
/appointments/<id>/cancel           Customer: Cancel Appointment
/my-notifications                   Customer: Notifications
/api/designs/<id>/fields            API: Design Fields + Price
/api/coupon/validate                API: Validate Coupon
/api/notifications/count            API: Badge Counts
/api/orders/<id>/messages           API: Poll Messages

/tailor/                            Tailor: Dashboard
/tailor/orders                      Tailor: Orders List
/tailor/orders/<id>                 Tailor: Order Detail
/tailor/orders/<id>/update-status   Tailor: Update Status
/tailor/orders/<id>/verify-receipt  Tailor: Verify Receipt OTP
/tailor/profile                     Tailor: Edit Profile
/tailor/availability/toggle         Tailor: Toggle Open/Closed
/tailor/measurement-templates       Tailor: Measurement Templates
/tailor/measurement-templates/<id>  Tailor: Edit Template
/tailor/my-notifications            Tailor: Notifications

/delivery/                          Delivery: Dashboard
/delivery/assignments               Delivery: All Assignments
/delivery/assignments/<id>          Delivery: Assignment Detail
/delivery/assignments/<id>/verify-otp       Delivery: Verify OTP
/delivery/assignments/<id>/save-measurements Delivery: Save Measurements
/delivery/my-appointments           Delivery: Style Agent Appointments
/delivery/my-appointments/<id>      Delivery: Appointment Detail
/delivery/my-appointments/<id>/arrived      Delivery: Mark Arrived
/delivery/my-appointments/<id>/complete     Delivery: Mark Completed
/delivery/my-appointments/<id>/reschedule   Delivery: Reschedule

/admin/                             Admin: Dashboard
/admin/approvals                    Admin: Pending Approvals
/admin/users                        Admin: All Users
/admin/orders                       Admin: All Orders
/admin/orders/<id>                  Admin: Order Detail
/admin/orders/<id>/assign-delivery  Admin: Assign Delivery Agent
/admin/designs                      Admin: Design Management
/admin/catalogue                    Admin: Catalogue Management
/admin/tailors/<id>/offers          Admin: Tailor Offer Pricing
/admin/coupons                      Admin: Coupon Management
/admin/appointments                 Admin: Appointments
/admin/schedule-config              Admin: Slot Configuration
/admin/analytics                    Admin: Analytics
/admin/financial                    Admin: Financials
/admin/reviews                      Admin: Reviews
/admin/settings                     Admin: System Settings
```

---

*End of Functional Documentation — TailorApp MVP 1.0*
