#!/usr/bin/env bash
# SLAM Services — GitHub Codespaces post-create provisioning (v2.44).
#
# Runs once when a new Codespace is provisioned (or when the dev
# container is rebuilt). Idempotent — safe to re-run by hand via
# "Codespaces: Rebuild Container" if anything goes sideways.
#
# Stages:
#   1. System packages — poppler-utils for pdf2image, libgl/libglib
#      for opencv-python-headless raster ops.
#   2. Project venv at .venv/ + upgrade pip/setuptools/wheel.
#   3. Core dependencies from requirements.txt (matches Azure F1
#      App Service runtime).
#   4. Heavy Local Enhanced OCR libs (pdfplumber + pdf2image + easyocr
#      + pillow + opencv-python-headless + numpy) — same set as
#      `AzureFunctions/ocr_processor/requirements.txt`.
#   5. Dev tooling (ruff + black + ipython) for the in-Codespaces
#      lint/format/REPL workflow.
#   6. EasyOCR English model pre-warm — downloads the ~30 MB model
#      into ~/.EasyOCR so the first real OCR call isn't a cold start.
#   7. Shell aliases (slam-run / slam-lint / slam-format / slam-health)
#      appended to ~/.bashrc.
#
# Logs are streamed to the Codespaces "Creating Codespace" panel
# in real time; rerun visibility via `cat /workspaces/.codespaces/.persistedshare/creation.log`.

set -euo pipefail

readonly REPO_DIR="${PWD}"
readonly VENV_DIR="${REPO_DIR}/.venv"
readonly STAGE_TS_START="$(date -u +%s)"

# ANSI helpers for readable Codespaces "Creating Codespace" log output.
_blue()   { printf '\033[1;34m%s\033[0m\n' "$*"; }
_green()  { printf '\033[1;32m%s\033[0m\n' "$*"; }
_yellow() { printf '\033[1;33m%s\033[0m\n' "$*"; }

_blue "================================================================"
_blue " SLAM Services — Codespaces provisioning (v2.44)"
_blue " Workspace: ${REPO_DIR}"
_blue " Python:    $(python3 --version 2>&1 || echo 'unknown')"
_blue "================================================================"

# ---------------------------------------------------------------------------
# 1) System packages — poppler is required by pdf2image's PDF rasterization
#    (`convert_from_bytes`); libgl1 + libglib2.0-0 are the minimum runtime
#    libs for opencv-python-headless on Debian. tesseract is NOT installed —
#    we use easyocr (pure Python + Torch) instead.
# ---------------------------------------------------------------------------
_blue "[1/7] Installing system packages (poppler-utils, libgl1, libglib2.0-0)..."
sudo apt-get update -y -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
  poppler-utils \
  libgl1 \
  libglib2.0-0 \
  ca-certificates \
  curl \
  jq
sudo apt-get autoremove -y -qq
sudo apt-get clean
_green "      System packages OK."

# ---------------------------------------------------------------------------
# 2) Project virtual environment — keeps Codespaces parity with Robert's
#    local Windows .venv workflow and isolates the heavy OCR libs from
#    the system Python.
# ---------------------------------------------------------------------------
_blue "[2/7] Creating .venv (Python 3.10)..."
if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
  _green "      Created ${VENV_DIR}."
else
  _yellow "      Reusing existing ${VENV_DIR}."
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade --quiet pip setuptools wheel
_green "      pip $(pip --version | awk '{print $2}') ready."

# ---------------------------------------------------------------------------
# 3) Core deps — Azure F1 App Service runtime (Streamlit, pandas, plotly,
#    pdfplumber, sqlalchemy, psycopg2-binary, python-dotenv).
# ---------------------------------------------------------------------------
_blue "[3/7] Installing core dependencies from requirements.txt..."
if [[ -f "${REPO_DIR}/requirements.txt" ]]; then
  pip install --quiet --upgrade -r "${REPO_DIR}/requirements.txt"
  _green "      Core requirements installed."
else
  _yellow "      requirements.txt not found at repo root — skipping."
fi

# ---------------------------------------------------------------------------
# 4) Heavy Local Enhanced OCR libs (v2.43.2) — same set as the Azure
#    OCR Function (`AzureFunctions/ocr_processor/requirements.txt`),
#    minus `azure-functions`. Total install size ~1.5 GB (PyTorch is
#    the bulk of that).
# ---------------------------------------------------------------------------
_blue "[4/7] Installing heavy Local Enhanced OCR libraries..."
_yellow "      ↳ This includes PyTorch (~700 MB) — first install is slow (~3-5 min)."
pip install --quiet --upgrade \
  "pdfplumber>=0.11" \
  "pdf2image>=1.17" \
  "pillow>=10.0" \
  "numpy>=1.26" \
  "opencv-python-headless>=4.8" \
  "easyocr>=1.7"
_green "      Heavy OCR libs installed."

# ---------------------------------------------------------------------------
# 5) Dev tooling — ruff and black are pinned in pyproject.toml's tool
#    config; ipython is just a quality-of-life REPL for poking at
#    Streamlit session state and pandas DataFrames.
# ---------------------------------------------------------------------------
_blue "[5/7] Installing dev tooling (ruff, black, ipython)..."
pip install --quiet --upgrade ruff black ipython
_green "      Dev tooling installed."

# ---------------------------------------------------------------------------
# 6) Pre-warm EasyOCR English model — downloads ~30 MB craft + recognition
#    weights into ~/.EasyOCR so the first /api/ocr/process call (or the
#    first Local Enhanced OCR run from the Bank Statements page) isn't a
#    30-60 s cold start. Best-effort — if the download fails (offline,
#    rate-limited) we keep going and warm on first real use.
# ---------------------------------------------------------------------------
_blue "[6/7] Pre-warming EasyOCR English model (~30 MB)..."
if python -c "
import sys
try:
    import easyocr
    easyocr.Reader(['en'], gpu=False, verbose=False)
    print('OK')
except Exception as exc:
    print(f'WARN: {exc}', file=sys.stderr)
    sys.exit(0)
" 2>&1 | tail -n 5; then
  _green "      EasyOCR model cached at ~/.EasyOCR."
else
  _yellow "      EasyOCR pre-warm failed (will warm on first real OCR call)."
fi

# ---------------------------------------------------------------------------
# 7) Shell aliases — only appended once (idempotency guard via marker).
# ---------------------------------------------------------------------------
_blue "[7/7] Installing shell aliases in ~/.bashrc..."
ALIAS_MARKER="# >>> SLAM Services aliases (v2.44) >>>"
if ! grep -qF "${ALIAS_MARKER}" "${HOME}/.bashrc" 2>/dev/null; then
  cat >> "${HOME}/.bashrc" <<'EOF'

# >>> SLAM Services aliases (v2.44) >>>
# Auto-activate the project venv on shell start so `python`, `streamlit`,
# and `ruff` always resolve to the venv copies.
if [[ -f "/workspaces/${RepositoryName:-${CODESPACE_VSCODE_FOLDER##*/}}/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1090
  source "/workspaces/${RepositoryName:-${CODESPACE_VSCODE_FOLDER##*/}}/.venv/bin/activate"
fi

alias slam-run='streamlit run App/app.py'
alias slam-lint='ruff check App/ Scripts/'
alias slam-format='ruff format App/ Scripts/ && ruff check --fix App/ Scripts/'
alias slam-health='python Scripts/health_check.py --csv'
alias slam-info='python -c "import App.local_enhanced_ocr as o; import json; caps=o.detect_capabilities(); print(json.dumps({\"version\": o.LOCAL_ENHANCED_OCR_VERSION, \"capabilities\": caps, \"dpi_text\": o.OCR_DPI_TEXT, \"dpi_crop\": o.OCR_DPI_CROP}, indent=2))"'
# <<< SLAM Services aliases (v2.44) <<<
EOF
  _green "      Aliases appended."
else
  _yellow "      Aliases already present — skipping."
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
STAGE_TS_END="$(date -u +%s)"
ELAPSED=$(( STAGE_TS_END - STAGE_TS_START ))

_blue "================================================================"
_green " ✅ SLAM Services Codespace ready in ${ELAPSED}s."
_blue "----------------------------------------------------------------"
_blue " Quick start:"
echo "   slam-run       → streamlit run App/app.py (open port 8501)"
echo "   slam-lint      → ruff check App/ Scripts/"
echo "   slam-format    → ruff format + ruff --fix"
echo "   slam-health    → CSV-mode health probe"
echo "   slam-info      → print Local Enhanced OCR capability matrix"
_blue "----------------------------------------------------------------"
_blue " Local Enhanced OCR (v2.44.3) defaults for Codespaces:"
echo "   SLAM_LOCAL_OCR_DPI_TEXT=200   (was 300 on Robert's local Windows)"
echo "   SLAM_LOCAL_OCR_DPI_CROP=220   (was 250 on Robert's local Windows; v2.44.3 bump from 180)"
echo "   SLAM_LOCAL_OCR_MAX_PAGES_RASTER=20"
echo "   SLAM_LOCAL_OCR_MAX_CHECKS=50   (v2.44.3 bump from 30)"
echo "   ↳ Override any of these via \`export SLAM_LOCAL_OCR_DPI_TEXT=300\`"
echo "     before running streamlit on a 16 GB+ Codespaces SKU."
_blue "----------------------------------------------------------------"
_blue " Heavy libs available — \`slam-info\` should show all 6 caps as true."
_blue "================================================================"
