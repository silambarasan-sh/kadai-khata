#!/usr/bin/env bash
# Kadai Khata - Production Build Script for Render
set -euo pipefail

echo "==> Installing dependencies..."
pip install -r requirements.txt

echo "==> Collecting static assets..."
python manage.py collectstatic --no-input --clear
