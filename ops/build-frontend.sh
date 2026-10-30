#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/.tools/node-v24.22.0-linux-arm64/bin:$PATH"
npm ci --prefix build/sources/html_builder-main/frontend
npm run build --prefix build/sources/html_builder-main/frontend
