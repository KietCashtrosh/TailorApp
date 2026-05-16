#!/usr/bin/env bash
# ─────────────────────────────────────────────────────
# Railway startup script — runs before gunicorn starts.
# All flask commands are idempotent (safe to re-run).
#
# NOTE: flask init-db already creates admin, demo tailor,
# delivery agent and customer — no separate seed-admin /
# seed-delivery commands needed.
# ─────────────────────────────────────────────────────
set -e

echo ">>> [1/3] Creating DB tables + seeding accounts..."
flask init-db

echo ">>> [2/3] Applying column migrations..."
flask migrate-db

echo ">>> [3/3] Seeding product catalogue..."
flask seed-catalogue

echo ">>> All done. Starting gunicorn..."
exec gunicorn run:app \
  --workers 2 \
  --bind "0.0.0.0:${PORT}" \
  --timeout 120 \
  --preload \
  --access-logfile - \
  --error-logfile -
