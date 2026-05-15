# Configurable Admin Settings & Flexible Style Agent Booking

## Overview

This implementation adds system-wide admin-configurable settings to TailorApp, allowing the platform to operate in flexible modes:

1. **Tailor acceptance window** - Configurable response time (default: 2 hours)
2. **Style agent slot booking mode** - Toggle between customer-selectable and admin-assigned
3. **Auto-confirm on timeout** - Whether to auto-confirm expired orders

---

## New Models

### AdminConfig (Singleton)
Stores system-wide settings. Access via `AdminConfig.get()`.

```python
AdminConfig.get()  # Returns the singleton config instance
```

**Fields:**
- `tailor_acceptance_window_hours` (int, default=2): Hours tailor has to accept/reject
- `enable_style_agent_slot_booking` (bool, default=True): Enable customer slot selection
- `auto_confirm_orders_if_no_response` (bool, default=False): Auto-confirm on timeout
- `updated_at` (DateTime): Last update timestamp

---

## Order Model Enhancements

New fields added to track style agent appointments:

```python
order.style_agent_appointment_date       # YYYY-MM-DD (customer or admin selected)
order.style_agent_appointment_time       # HH:MM
order.auto_assigned_style_agent_id       # FK to assigned delivery agent
order.admin_assigned_at                  # When admin assigned (DateTime)
order.customer_confirmed_slot            # Boolean confirmation flag
order.style_agent                        # Relationship to assigned agent
```

---

## Admin Panel Features

### 1. System Settings Page
**Route:** `/admin/settings`

Admin can configure:
- Tailor acceptance window (1-24 hours)
- Enable/disable style agent slot booking
- Auto-confirm expired orders toggle

**Current Config Display:**
- Shows all current settings
- Last update timestamp
- Status badges (Enabled/Disabled)

### 2. Manual Style Agent Assignment
**Route:** `/admin/orders/<order_id>/assign-style-agent`

When `enable_style_agent_slot_booking` is **disabled**:
- Admin can manually select a style agent from available delivery agents
- System automatically notifies customer
- Customer receives email and in-app notification
- Customer must confirm the assignment

**Current Assignment Info:**
- Shows if agent is already assigned
- Displays confirmation status (Confirmed/Pending)
- Assigned timestamp

---

## Customer Experience

### Mode 1: Style Agent Slot Booking Enabled (Default)
1. Customer adds items to cart
2. During checkout, customer **selects a date and time slot** for style agent visit
3. Order is placed with appointment details saved
4. System later assigns an available agent to that slot

**Template:** Cart shows slot selection fields

### Mode 2: Style Agent Slot Booking Disabled
1. Customer adds items to cart
2. During checkout, **no slot selection shown**
3. Order is placed without style agent assignment
4. Admin manually assigns a style agent after tailor accepts
5. Customer gets notified and must **confirm the assignment**
6. Route: `POST /orders/<order_id>/confirm-style-agent`

---

## Workflow Examples

### Example 1: Standard Flow (Slot Booking Enabled)
```
1. Customer places order → selects style agent slot (e.g., "2026-05-15 14:00")
2. Order saved with style_agent_appointment_date/time
3. Tailor accepts order
4. Admin later assigns available agent to that slot
5. System sends StyleAgentAppointment record
```

### Example 2: Manual Assignment Flow (Slot Booking Disabled)
```
1. Customer places order → NO slot selection shown
2. Admin: order.status == 'accepted'
3. Admin clicks "Assign Style Agent" button
4. Admin selects delivery agent from list
5. Order updated: auto_assigned_style_agent_id, admin_assigned_at set
6. Customer gets notification: "Agent X has been assigned, please confirm"
7. Customer visits order detail → clicks "Confirm Style Agent"
8. Order.customer_confirmed_slot = True
9. Appointment can now proceed
```

---

## Database Migration

### Running Migrations

```bash
# Initialize database (creates tables)
flask init-db

# Or migrate existing database (adds new columns)
flask migrate-db
```

**New columns added to `orders`:**
- `style_agent_appointment_date`
- `style_agent_appointment_time`
- `auto_assigned_style_agent_id`
- `admin_assigned_at`
- `customer_confirmed_slot`

**New table created:**
- `admin_configs` (singleton)

---

## API Endpoints

### Admin Routes
| Route | Method | Purpose |
|-------|--------|---------|
| `/admin/settings` | GET | View settings page |
| `/admin/settings` | POST | Update settings |
| `/admin/orders/<id>/assign-style-agent` | GET | Show assignment form |
| `/admin/orders/<id>/assign-style-agent` | POST | Assign style agent |

### Customer Routes
| Route | Method | Purpose |
|-------|--------|---------|
| `/orders/<id>/confirm-style-agent` | POST | Customer confirms assigned slot |

---

## Email Notifications

### New Method: `send_style_agent_assigned(order, agent)`
Sent when admin manually assigns a style agent.

**Template:** Notifies customer with:
- Assigned agent name and contact
- Order number
- Request to confirm in app

**Usage:**
```python
from app.services import email_service
email_service.send_style_agent_assigned(order, agent)
```

---

## UI Components

### Admin Settings Template
- **File:** `admin/settings.html`
- Checkbox toggles for:
  - Style agent slot booking
  - Auto-confirm on timeout
- Number input for tailor window hours
- Current config display card

### Admin Assign Style Agent Template
- **File:** `admin/assign_style_agent.html`
- Order details card
- Dropdown to select available agents
- Current assignment info (if any)
- Confirmation status display

### Customer Cart Enhancement
- **File:** `customer/cart.html`
- Conditional style agent slot section
- Date picker (min = tomorrow, max = 30 days)
- Time slot dropdown (generated from StyleAgentConfig)
- Only shows when `enable_style_agent_slot_booking = True`

### Admin Order Detail Enhancement
- **File:** `admin/order_detail.html`
- New "Style Agent" card showing:
  - Current assignment status
  - Confirmation status (if assigned)
  - "Assign Style Agent" button (if not assigned and slot booking disabled)
  - Customer-selected slot (if slot booking enabled)

---

## Configuration Examples

### Configuration 1: Customer-Selectable Slots (Default)
```python
config = AdminConfig.get()
config.enable_style_agent_slot_booking = True
config.tailor_acceptance_window_hours = 2
config.auto_confirm_orders_if_no_response = False
db.session.commit()
```

### Configuration 2: Admin-Assigns Manually
```python
config = AdminConfig.get()
config.enable_style_agent_slot_booking = False
config.tailor_acceptance_window_hours = 4
config.auto_confirm_orders_if_no_response = True
db.session.commit()
```

---

## Error Handling

### Cart Checkout Validation
- If slot booking enabled, validates date and time are provided
- Shows error: "Please select a style agent visit slot."
- Redirects back to cart

### Admin Assignment
- Validates agent exists and has `role='delivery'`
- Validates order exists and belongs to admin context
- Creates notification for customer

### Customer Confirmation
- Validates order exists and belongs to customer
- Validates agent was actually assigned
- Prevents re-confirmation (idempotent)

---

## Future Enhancements

1. **Bulk Style Agent Assignment** - Admin assigns multiple orders at once
2. **Auto-Assignment Algorithm** - Automatically assign agents based on:
   - Agent availability/load
   - Customer location (proximity)
   - Agent specialization
3. **Customer Slot Rejection** - Customer can reject assigned slot and request new time
4. **Agent Availability Calendar** - Integrate with agent schedules
5. **Appointment Reminders** - Auto-send SMS/email reminders before appointment
6. **Real-time ETA Countdown** - Show countdown to tailor completion in customer app

---

## Testing Checklist

- [ ] Admin can update settings
- [ ] Settings persist across sessions
- [ ] Cart shows slot booking fields when enabled
- [ ] Cart hides slot booking fields when disabled
- [ ] Checkout validates slot selection (when enabled)
- [ ] Checkout saves appointment dates to order
- [ ] Admin can assign style agent to order
- [ ] Customer receives notification of assignment
- [ ] Customer can confirm assigned slot
- [ ] Order detail shows assignment status
- [ ] Email notifications are sent correctly
- [ ] Database migration creates all new columns/tables

---

## Admin Quick Start

1. **Log in as admin** (email: `admin@tailorapp.com`)
2. **Navigate to:** Admin Panel → System Settings (bottom left)
3. **Configure:**
   - Set tailor window hours
   - Toggle style agent slot booking
   - Toggle auto-confirm
4. **Save settings**
5. **For manual assignment:**
   - Go to Orders → Select order (status must be 'accepted')
   - Scroll to "Style Agent" section
   - Click "Assign Style Agent"
   - Select agent from dropdown
   - Submit
6. **Customer gets notified automatically**

---

## Database Schema Reference

### admin_configs table
```sql
CREATE TABLE admin_configs (
  id INTEGER PRIMARY KEY,
  tailor_acceptance_window_hours INTEGER DEFAULT 2,
  enable_style_agent_slot_booking BOOLEAN DEFAULT 1,
  auto_confirm_orders_if_no_response BOOLEAN DEFAULT 0,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### orders table (new columns)
```sql
ALTER TABLE orders ADD COLUMN style_agent_appointment_date VARCHAR(10) DEFAULT '';
ALTER TABLE orders ADD COLUMN style_agent_appointment_time VARCHAR(5) DEFAULT '';
ALTER TABLE orders ADD COLUMN auto_assigned_style_agent_id INTEGER REFERENCES users(id);
ALTER TABLE orders ADD COLUMN admin_assigned_at DATETIME;
ALTER TABLE orders ADD COLUMN customer_confirmed_slot BOOLEAN DEFAULT 0;
```

---

**Implementation Date:** May 9, 2026  
**Module:** Phase 1 - Configurable Admin Settings & Flexible Style Agent Booking
