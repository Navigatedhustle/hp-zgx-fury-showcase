#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")"
export HF_HOME="$PWD/.cache/huggingface" HF_HUB_DISABLE_IMPLICIT_TOKEN=1 PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright"
export XDG_CACHE_HOME="$PWD/.cache" FURY_PROFILE=frankfurt
# Use local caches even if the launching user has personal global inference settings.
unset VLLM_CACHE_ROOT VLLM_CONFIG_ROOT
export VLLM_CACHE_ROOT="$PWD/.cache/vllm" VLLM_CONFIG_ROOT="$PWD/.cache/vllm-config"
command="${1:-start}"
case "$command" in
 setup) exec bash ops/bootstrap.sh ;;
 stop|status|restart) shift || true; exec ./showcase "$command" "$@" ;;
 diagnostics) exec python3 ops/diagnostics.py ;;
 recover) shift; exec .venv/bin/python ops/recover.py "$@" ;;
 skin) shift; exec .venv/bin/python ops/skin.py "$@" ;;
 desktop) exec python3 ops/install-desktop.py ;;
 start)
  python3 ops/preflight.py --ports
  if ! python3 - <<'PY'
import json,sys
sys.path.insert(0,'ops');from pathlib import Path
from importlib.machinery import SourceFileLoader
m=SourceFileLoader('setup_stamp','ops/setup-stamp.py').load_module()
try:ok=json.loads(Path('state/setup.json').read_text())['signature']==m.signature()
except (OSError,ValueError,KeyError):ok=False
sys.exit(0 if ok and all(Path(p+'/bin/python').exists() for p in ['.venv','.model-venv','.deepseek-venv']) else 1)
PY
  then bash ops/bootstrap.sh; fi
  ./showcase start
  echo 'Dashboard ready: http://localhost:8080/'
  if [[ "${FURY_NO_BROWSER:-0}" != 1 && ( -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ) ]] && command -v xdg-open >/dev/null; then
   xdg-open http://localhost:8080/ >/dev/null 2>&1 || true
  fi ;;
 *) echo 'Usage: ./launch.sh [start|setup|stop|status|diagnostics|recover COMPONENT|restart COMPONENT|desktop|skin prep NAMES...|skin list|skin clear]' >&2; exit 2 ;;
esac
