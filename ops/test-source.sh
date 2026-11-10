#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-.venv/bin/python}"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright"
PYTHONPATH=build/sources/fury_agent_factory "$PY" -m pytest -q build/sources/fury_agent_factory/tests
"$PY" -m pytest -q ops/tests ops/acceptance/test_gateway.py ops/acceptance/test_booth.py
if [[ -z "${FURY_NODE:-}" ]]; then
 FURY_NODE="$PWD/.tools/node-v24.22.0-linux-arm64/bin/node"
 if [[ ! -x "$FURY_NODE" ]]; then
  FURY_NODE="$("$PY" -c 'from pathlib import Path; import playwright; print(Path(playwright.__file__).parent / "driver/node")')"
 fi
fi
"$FURY_NODE" --test ops/tests/test_frontier_cost.js
