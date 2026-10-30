#!/usr/bin/env bash
# Kadai Khata - Production Startup Script for Render
set -euo pipefail

echo "=========================================================="
echo "==> Kadai Khata: Production Startup"
echo "=========================================================="

# 0. Ensure DATABASE_PATH parent directory is writable if specified
if [ -n "${DATABASE_PATH:-}" ]; then
    DB_DIR="$(dirname "$DATABASE_PATH")"
    echo "==> Ensuring directory for DATABASE_PATH exists: ${DB_DIR}"
    mkdir -p "${DB_DIR}"
fi

# 1. Apply database migrations
echo "==> Running database migrations..."
if ! python manage.py migrate --no-input; then
    echo "ERROR: Database migration failed. Check database permissions and DATABASE_PATH." >&2
    exit 1
fi
echo "==> Database migrations applied successfully."

# 2. Seed demo data only if there are no customers
echo "==> Checking if demo seeding is needed..."
if ! python manage.py seed_demo_data --if-empty; then
    echo "ERROR: Demo data seeding failed." >&2
    exit 1
fi
echo "==> Demo data checked / seeded successfully."

# 3. Start Gunicorn web server with gthread and 120s timeout
PORT="${PORT:-8000}"
echo "==> Starting Gunicorn on 0.0.0.0:${PORT} (gthread, 2 workers, 4 threads, 120s timeout)..."
exec gunicorn kadai_khata.wsgi:application \
    --bind "0.0.0.0:${PORT}" \
    --workers 2 \
    --threads 4 \
    --worker-class gthread \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -

