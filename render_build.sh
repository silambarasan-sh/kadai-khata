#!/usr/bin/env bash
# Kadai Khata - Production Build Script for Render
set -euo pipefail

echo "=========================================================="
echo "==> Kadai Khata: Production Build"
echo "=========================================================="

echo "==> Installing dependencies..."
if ! pip install -r requirements.txt; then
    echo "ERROR: pip install failed. Check requirements.txt and Python version." >&2
    exit 1
fi

echo "==> Collecting static assets (whitenoise)..."
if ! python manage.py collectstatic --no-input --clear; then
    echo "ERROR: collectstatic failed." >&2
    exit 1
fi

echo "==> Build completed successfully."

