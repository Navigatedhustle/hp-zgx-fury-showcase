#!/usr/bin/env bash
# Fury launch delegates to the shared supervisor; sanitized Nano binaries/48GiB guard are not used.
set -euo pipefail
cd "$(dirname "$0")/../../.."
exec python3 ops/start-services.py start text gateway asr tts atlas
