#!/bin/bash
set -e

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

# Azure App Service sets WEBSITE_HOSTNAME; use a faster cold-start path to beat the ~30s warmup probe.
AZURE_PROD=false
if [ -n "${WEBSITE_HOSTNAME:-}" ]; then
  AZURE_PROD=true
  log "Azure production mode (WEBSITE_HOSTNAME=$WEBSITE_HOSTNAME) — fast cold-start path."
fi

log "=== SLAM Services Startup Script (Revenue Tracker — B2 imaging deps) ==="
cd /home/site/wwwroot
export SLAM_LOG_LEVEL="${SLAM_LOG_LEVEL:-INFO}"

# Oryx compressed builds extract antenv under /tmp/<id>/antenv; prefer that or wwwroot antenv.
if [ -f "/home/site/wwwroot/antenv/bin/activate" ]; then
  # shellcheck disable=SC1091
  . "/home/site/wwwroot/antenv/bin/activate"
  log "Using venv: /home/site/wwwroot/antenv"
else
  for _oryx_venv in /tmp/*/antenv; do
    if [ -f "${_oryx_venv}/bin/activate" ]; then
      # shellcheck disable=SC1091
      . "${_oryx_venv}/bin/activate"
      log "Using Oryx venv: ${_oryx_venv}"
      break
    fi
  done
  unset _oryx_venv
fi

log "Working directory: $(pwd)"
log "Python: $(python --version 2>&1)"
log "PORT=${PORT:-8000}"

DATA_DIR="Data/Revenue_Tracker_Migration"
if [ -d "$DATA_DIR" ]; then
  if [ "$AZURE_PROD" = "true" ]; then
    log "Data folder OK: $DATA_DIR (listing omitted in production fast path)."
  else
    log "Data folder found: $DATA_DIR"
    ls -la "$DATA_DIR" | head -20
  fi
else
  log "WARNING: $DATA_DIR not found — app will show CSV path error unless USE_POSTGRES=true."
  if [ "$AZURE_PROD" = "false" ]; then
    log "Top-level wwwroot contents:"
    ls -la | head -30
  fi
fi

if python -c "import streamlit, pandas" >/dev/null 2>&1; then
  log "Python deps OK (streamlit, pandas importable) — skipping pip install (Oryx antenv or prior install)."
else
  log "Installing Python packages from requirements.txt..."
  python -m pip install --upgrade pip --disable-pip-version-check -q
  python -m pip install --no-cache-dir -r requirements.txt --disable-pip-version-check
fi

log "Poppler probe (pdf2image / check cropper)..."
if command -v pdftoppm >/dev/null 2>&1; then
  log "  [OK] pdftoppm: $(command -v pdftoppm)"
  pdftoppm -v 2>&1 | head -1 || true
else
  log "  [WARN] pdftoppm not on PATH — check cropper may fail at runtime."
  if [ "$AZURE_PROD" = "true" ]; then
    log "  [WARN] Production: skipping runtime apt-get (non-fatal). Ensure apt.txt + Oryx build installed poppler-utils."
  else
    log "  [WARN] Attempting poppler-utils install (non-fatal)..."
    if apt-get update -qq && apt-get install -y -qq poppler-utils 2>/dev/null; then
      if command -v pdftoppm >/dev/null 2>&1; then
        log "  [OK] pdftoppm installed: $(command -v pdftoppm)"
      else
        log "  [WARN] apt install finished but pdftoppm still missing."
      fi
    else
      log "  [WARN] Could not install poppler-utils (sandbox/apt). Ensure apt.txt + Oryx build or custom image."
    fi
  fi
fi

run_health_check() {
  local label="$1"
  shift
  if [ "$AZURE_PROD" = "true" ] && command -v timeout >/dev/null 2>&1; then
    timeout 15 "$@" || log "WARNING: $label failed or timed out (15s) — continuing startup."
  else
    "$@" || log "WARNING: $label failed — continuing startup."
  fi
}

USE_PG=$(echo "${USE_POSTGRES:-}" | tr '[:upper:]' '[:lower:]')
if [ "$USE_PG" = "true" ] || [ "$USE_PG" = "1" ] || [ "$USE_PG" = "yes" ]; then
  log "USE_POSTGRES enabled — running database health check..."
  if [ -n "${POSTGRES_HOST:-}" ] || [ -n "${DATABASE_URL:-}" ]; then
    run_health_check "PostgreSQL health check" python Scripts/health_check.py --verify-only
  else
    log "WARNING: USE_POSTGRES=true but no POSTGRES_HOST or DATABASE_URL set."
  fi
else
  log "CSV mode (USE_POSTGRES not enabled)."
  if [ -d "$DATA_DIR" ]; then
    run_health_check "CSV health check" python Scripts/health_check.py --csv
  fi
fi

log "STREAMLIT_LAUNCH: exec streamlit on 0.0.0.0:${PORT:-8000} (Azure warmup probe targets this port)."
log "STREAMLIT_READY pending: first HTTP response may take 20-40s while heavy imports load."
exec python -m streamlit run App/app.py \
  --server.port "${PORT:-8000}" \
  --server.address 0.0.0.0 \
  --server.headless true
