#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
exec python -m uvicorn api:app --host 127.0.0.1 --port 8501
