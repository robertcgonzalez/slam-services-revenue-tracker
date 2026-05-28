#!/usr/bin/env bash
set -euo pipefail

# Optional .env load for SLAM_GH_TOKEN
if [[ -f ".env" ]]; then
  # shellcheck disable=SC1091
  source ".env"
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is not installed."
  exit 1
fi

if [[ -n "${SLAM_GH_TOKEN:-}" ]]; then
  echo "Authenticating GitHub CLI with token from environment/.env..."
  printf '%s' "${SLAM_GH_TOKEN}" | gh auth login --with-token --scopes codespace
else
  echo "SLAM_GH_TOKEN not found. Starting interactive login..."
  gh auth login --scopes codespace
fi

echo
echo "Auth status:"
gh auth status
echo
echo "Available Codespaces:"
gh cs list
