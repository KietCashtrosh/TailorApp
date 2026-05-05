# TailorApp — Runbook

Quick reference for running, resetting, and seeding the app.

---

## Prerequisites

- Python venv located at `C:\User_works\Project-Es\myenv`
- Project located at `C:\User_works\Project-Es\myenv\Claude_Tailor_App`

---

## 1. Activate the Virtual Environment

Open a **PowerShell** terminal and run:

```powershell
C:\User_works\Project-Es\myenv\Scripts\Activate.ps1
```

Your prompt will change to show `(myenv)` when active.

> If you get an execution policy error, run this once:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

---

## 2. Navigate to the Project

```powershell
cd C:\User_works\Project-Es\myenv\Claude_Tailor_App
```

---

## 3. Run the Application

```powershell
python run.py
```

The app starts at: **http://127.0.0.1:5000**

> Press `Ctrl+C` to stop the server.

---

## 4. Initialize the Database (First Time)

Run this **once** when setting up a fresh database — it creates all tables and seeds demo data:

```powershell
$env:FLASK_APP = "run.py"
flask init-db
```

Expected output:
```
Admin user created: admin@tailorapp.com / admin123
Demo tailor created: tailor1@tailorapp.com / tailor123
Demo delivery agent created: delivery1@tailorapp.com / delivery123
Demo customer created: customer1@tailorapp.com / customer123

Database initialised successfully!
```

---

## 5. Delete the Database

Stop the server first (`Ctrl+C`), then delete the file:

```powershell
Remove-Item tailor_app.db
```

Or using the Windows file explorer — delete `tailor_app.db` from the project root folder.

> The database file is `tailor_app.db` in `C:\User_works\Project-Es\myenv\Claude_Tailor_App\`.

---

## 6. Reset and Re-Seed the Database

Full reset — deletes everything and starts fresh with demo data:

```powershell
# Step 1: Delete the old database
Remove-Item tailor_app.db

# Step 2: Re-create tables and seed demo data
$env:FLASK_APP = "run.py"
flask init-db

# Step 3: Run the app
python run.py
```

---

## 7. Demo Accounts

These accounts are created automatically by `flask init-db`:

| Role | Email | Password | Portal |
|------|-------|----------|--------|
| Admin | admin@tailorapp.com | admin123 | http://127.0.0.1:5000/admin/ |
| Tailor | tailor1@tailorapp.com | tailor123 | http://127.0.0.1:5000/tailor/ |
| Delivery | delivery1@tailorapp.com | delivery123 | http://127.0.0.1:5000/delivery/ |
| Customer | customer1@tailorapp.com | customer123 | http://127.0.0.1:5000/ |

---

## 8. Environment Variables (Optional)

Copy `.env.example` to `.env` to override defaults:

```powershell
Copy-Item .env.example .env
```

Edit `.env` to set a custom secret key or switch to PostgreSQL:

```env
SECRET_KEY=your-random-secret-here

# PostgreSQL (leave commented for SQLite dev)
# DATABASE_URL=postgresql://user:password@localhost:5432/tailor_app
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Activate venv | `C:\User_works\Project-Es\myenv\Scripts\Activate.ps1` |
| Run app | `python run.py` |
| Init / seed DB | `$env:FLASK_APP = "run.py"; flask init-db` |
| Delete DB | `Remove-Item tailor_app.db` |
| Full reset | Delete DB → `flask init-db` → `python run.py` |
