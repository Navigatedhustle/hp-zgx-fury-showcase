#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-.venv/bin/python}"
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright"
PYTHONPATH=build/sources/fury_agent_factory "$PY" -m pytest -q build/sources/fury_agent_factory/tests
"$PY" -m pytest -q ops/tests ops/acceptance/test_gateway.py ops/acceptance/test_booth.py
