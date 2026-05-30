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
_poppler_ok=false
if command -v pdftoppm >/dev/null 2>&1; then
  _poppler_ok=true
  log "  [OK] pdftoppm: $(command -v pdftoppm)"
  pdftoppm -v 2>&1 | head -1 || true
else
  log "  [WARN] pdftoppm not on PATH — check cropper may fail at runtime."
  log "  Attempting poppler-utils install (non-fatal, required for DI imaging leg)..."
  # Always attempt (even in production fast-path). Oryx/apt.txt is not 100% reliable for this package.
  # Keep it quick and non-blocking for the Azure warmup probe.
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    timeout 20 apt-get update -qq 2>/dev/null || log "  [WARN] apt-get update skipped or timed out (continuing)."
    if timeout 45 apt-get install -y -qq poppler-utils 2>/dev/null; then
      if command -v pdftoppm >/dev/null 2>&1; then
        _poppler_ok=true
        log "  [OK] pdftoppm installed via apt: $(command -v pdftoppm)"
        pdftoppm -v 2>&1 | head -1 || true
      else
        log "  [WARN] apt install finished but pdftoppm still not on PATH."
      fi
    else
      log "  [WARN] Could not install poppler-utils (timeout / sandbox). Imaging leg will be disabled until fixed."
      log "  Ensure apt.txt contains poppler-utils and the next deploy triggers a full Oryx build."
    fi
  else
    log "  [WARN] apt-get not available in this container — rely on apt.txt + Oryx build for poppler-utils."
  fi
fi
if [ "$_poppler_ok" = "true" ]; then
  log "IMAGING_LEG poppler=ok — geometric cropper v5 + per-crop DI enabled."
else
  log "IMAGING_LEG poppler=missing — register-only DI; check cropper will be skipped."
fi
unset _poppler_ok

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

RUN_SMOKE=$(echo "${SLAM_RUN_GATE_A3_SMOKE:-}" | tr '[:upper:]' '[:lower:]')
if [ "$RUN_SMOKE" = "true" ] || [ "$RUN_SMOKE" = "1" ] || [ "$RUN_SMOKE" = "yes" ]; then
  mkdir -p /home/site/wwwroot/tmp
  if [ -f /home/site/wwwroot/tmp/HCC_2026-04.pdf ] && [ -f /home/site/wwwroot/tmp/Auto_Body_Center_Jan_26_Statement.pdf ]; then
    log "SLAM_RUN_GATE_A3_SMOKE: starting headless Gate A3 DI smoke in background (logs -> wwwroot/tmp/gate-a3-smoke.log)."
    (
      python Scripts/Python/run_gate_a3_headless_smoke.py >>/home/site/wwwroot/tmp/gate-a3-smoke.log 2>&1
      _rc=$?
      log "SLAM_RUN_GATE_A3_SMOKE: headless smoke finished (exit ${_rc}). See wwwroot/tmp/gate-a3-smoke.log and stdout SMOKE_EVIDENCE lines."
    ) &
  else
    log "WARNING: SLAM_RUN_GATE_A3_SMOKE set but canonical PDFs missing under wwwroot/tmp."
  fi
fi

log "STREAMLIT_LAUNCH: exec streamlit on 0.0.0.0:${PORT:-8000} (Azure warmup probe targets this port)."
log "STREAMLIT_READY pending: first HTTP response may take 20-40s while heavy imports load."
exec python -m streamlit run App/app.py \
  --server.port "${PORT:-8000}" \
  --server.address 0.0.0.0 \
  --server.headless true
