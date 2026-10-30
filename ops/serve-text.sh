#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/.model-venv/bin:$PATH"
export C_INCLUDE_PATH="$PWD/.local-debs/extracted/usr/include:$PWD/.local-debs/extracted/usr/include/python3.12:$PWD/.local-debs/extracted/usr/include/aarch64-linux-gnu/python3.12"
exec .venv/bin/python ops/launch-frankfurt-model.py qwen
