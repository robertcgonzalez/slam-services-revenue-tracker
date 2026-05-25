#!/bin/bash
set -e

echo "=== SLAM Services Startup Script (Revenue Tracker v2.32) ==="
cd /home/site/wwwroot
export SLAM_LOG_LEVEL="${SLAM_LOG_LEVEL:-INFO}"

echo "Working directory: $(pwd)"
echo "Python: $(python --version 2>&1)"

DATA_DIR="Data/Revenue_Tracker_Migration"
if [ -d "$DATA_DIR" ]; then
  echo "Data folder found: $DATA_DIR"
  ls -la "$DATA_DIR" | head -20
else
  echo "WARNING: $DATA_DIR not found — app will show CSV path error unless USE_POSTGRES=true."
  echo "Top-level wwwroot contents:"
  ls -la | head -30
fi

echo "Upgrading pip..."
python -m pip install --upgrade pip --disable-pip-version-check -q

echo "Installing Python packages from requirements.txt..."
python -m pip install --no-cache-dir -r requirements.txt --disable-pip-version-check

USE_PG=$(echo "${USE_POSTGRES:-}" | tr '[:upper:]' '[:lower:]')
if [ "$USE_PG" = "true" ] || [ "$USE_PG" = "1" ] || [ "$USE_PG" = "yes" ]; then
  echo "USE_POSTGRES enabled — running database health check..."
  if [ -n "${POSTGRES_HOST:-}" ] || [ -n "${DATABASE_URL:-}" ]; then
    python Scripts/health_check.py --verify-only || \
      echo "WARNING: PostgreSQL health check failed — app will attempt CSV fallback at runtime."
  else
    echo "WARNING: USE_POSTGRES=true but no POSTGRES_HOST or DATABASE_URL set."
  fi
else
  echo "CSV mode (USE_POSTGRES not enabled)."
  if [ -d "$DATA_DIR" ]; then
    python Scripts/health_check.py --csv || \
      echo "WARNING: CSV health check failed — verify Clients.csv and RevenueRequests.csv."
  fi
fi

echo "Starting Streamlit on dynamic PORT ${PORT:-8000}..."
python -m streamlit run App/app.py \
  --server.port "${PORT:-8000}" \
  --server.address 0.0.0.0 \
  --server.headless true
