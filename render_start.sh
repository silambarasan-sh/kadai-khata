#!/usr/bin/env bash
# Kadai Khata - Production Startup Script for Render
set -euo pipefail

echo "=========================================================="
echo "==> Kadai Khata: Production Startup"
echo "=========================================================="

# 1. Apply database migrations
echo "==> Running database migrations..."
python manage.py migrate --no-input

# 2. Seed demo data only if there are no customers
echo "==> Checking if demo seeding is needed..."
python manage.py seed_demo_data --if-empty

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
