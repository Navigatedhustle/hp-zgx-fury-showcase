#!/usr/bin/env bash
# Nano install entry point. Downloads into this checkout; never changes host policy.
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-}" in
 --check) exec python3 ops/nano-preflight.py ;;
 --no-desktop|'') ;;
 *) echo 'Usage: ./install.sh [--check|--no-desktop]' >&2; exit 2 ;;
esac
python3 ops/nano-preflight.py
FURY_PROFILE=gb10 ./launch.sh setup
if [[ "${1:-}" != --no-desktop ]]; then
  FURY_PROFILE=gb10 .venv/bin/python ops/install-desktop.py --profile gb10
fi
printf '\nInstall complete. Launch: ./launch.sh free\nPresenter: ./launch.sh stage\n'
