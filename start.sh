#!/usr/bin/env bash
# ─────────────────────────────────────────────────────
# Railway startup script — runs before gunicorn starts.
# All flask commands are idempotent (safe to re-run).
# ─────────────────────────────────────────────────────
set -e

echo ">>> [1/5] Creating DB tables..."
flask init-db

echo ">>> [2/5] Applying column migrations..."
flask migrate-db

echo ">>> [3/5] Seeding product catalogue..."
flask seed-catalogue

echo ">>> [4/5] Seeding admin + demo accounts..."
flask seed-admin

echo ">>> [5/5] Seeding delivery agents..."
flask seed-delivery

echo ">>> Setup complete. Starting gunicorn..."
exec gunicorn run:app \
  --workers 2 \
  --bind "0.0.0.0:${PORT}" \
  --timeout 120 \
  --preload \
  --access-logfile - \
  --error-logfile -
