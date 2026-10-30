#!/usr/bin/env bash
# Stop Atlas-specific services; keep shared language weights available to the other demos.
set -euo pipefail
cd "$(dirname "$0")/../../.."
exec python3 ops/start-services.py stop atlas asr tts
