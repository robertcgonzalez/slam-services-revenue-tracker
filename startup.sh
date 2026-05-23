#!/bin/bash
set -e

echo "=== SLAM Services Startup Script ==="
cd /home/site/wwwroot

echo "Upgrading pip..."
python -m pip install --upgrade pip --disable-pip-version-check -q

echo "Installing Python packages from requirements.txt..."
python -m pip install --no-cache-dir -r requirements.txt --disable-pip-version-check

echo "Starting Streamlit on dynamic PORT ${PORT:-8000}..."
python -m streamlit run App/app.py \
  --server.port "${PORT:-8000}" \
  --server.address 0.0.0.0 \
  --server.headless true