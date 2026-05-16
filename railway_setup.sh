#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Railway one-time setup script
# Run this ONCE from: Railway dashboard → your service → Shell
#
#   bash railway_setup.sh
#
# Safe to re-run — all commands are idempotent.
# ─────────────────────────────────────────────────────────────

set -e   # stop on first error

echo "==> 1/5  Creating database tables..."
flask init-db

echo "==> 2/5  Applying column migrations..."
flask migrate-db

echo "==> 3/5  Seeding product catalogue..."
flask seed-catalogue

echo "==> 4/5  Seeding admin + legacy demo accounts..."
flask seed-admin

echo "==> 5/5  Seeding delivery agents..."
flask seed-delivery

echo ""
echo "✅  Setup complete!"
echo "    Admin login: admin@tailorapp.com / admin123"
echo "    Change the admin password immediately after first login."
