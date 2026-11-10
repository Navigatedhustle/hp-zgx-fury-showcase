#!/usr/bin/env bash
# Portable desktop entry point; all models stay under launch.sh ownership.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p state
exec 9>state/desktop-launch.lock
flock -n 9 || exit 0
export FURY_PROFILE=gb10 FURY_NO_BROWSER=1
if ! ./launch.sh free 9>&- >>state/desktop-launch.log 2>&1; then
  if command -v notify-send >/dev/null; then notify-send --urgency=critical 'HP ZGX Nano Experience' 'Launch failed. See state/desktop-launch.log in the installation.'; fi
  exit 1
fi
.venv/bin/python ops/open-nano-browser.py 9>&-
