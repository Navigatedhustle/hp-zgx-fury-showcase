#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 ops/preflight.py
mkdir -p state .cache
exec 9>state/setup.lock
flock 9
export UV_CACHE_DIR="$PWD/.cache/uv" HF_HOME="$PWD/.cache/huggingface" HF_HUB_DISABLE_IMPLICIT_TOKEN=1
if [[ ! -x .tools/uv-aarch64-unknown-linux-gnu/uv ]]; then
 mkdir -p .tools
 curl --fail --location --retry 3 --continue-at - https://github.com/astral-sh/uv/releases/download/0.13.1/uv-aarch64-unknown-linux-gnu.tar.gz -o .tools/uv.tar.gz
 (cd .tools; printf '%s  %s\n' 9041c73c99fdc5892cf128140beb354eca9231d502068cc36e6cb53a8e59ad14 uv.tar.gz | sha256sum -c -; tar -xf uv.tar.gz)
fi
UV_BIN="$PWD/.tools/uv-aarch64-unknown-linux-gnu/uv"
for env in .venv .model-venv .deepseek-venv; do
 [[ -x "$env/bin/python" ]] || "$UV_BIN" venv --python /usr/bin/python3.12 "$env"
done
"$UV_BIN" pip install --python .venv/bin/python -r ops/apps-requirements.lock
"$UV_BIN" pip install --python .model-venv/bin/python -r ops/models-requirements.lock --extra-index-url https://download.pytorch.org/whl/cu132 --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
"$UV_BIN" pip install --python .deepseek-venv/bin/python -r ops/lead-requirements.lock --extra-index-url https://download.pytorch.org/whl/cu130 --index-strategy unsafe-best-match
mkdir -p .local-debs
if [[ ! -f .local-debs/extracted/usr/include/python3.12/Python.h ]]; then
 (cd .local-debs; apt-get download libpython3.12-dev; for pkg in libpython3.12-dev*.deb; do dpkg-deb -x "$pkg" extracted; done)
fi
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright"
.venv/bin/python -m playwright install chromium
if [[ ! -x .tools/node-v24.22.0-linux-arm64/bin/node ]]; then
 mkdir -p .tools
 curl --fail --location --retry 3 --continue-at - https://nodejs.org/dist/v24.22.0/node-v24.22.0-linux-arm64.tar.xz -o .tools/node-v24.22.0-linux-arm64.tar.xz
 (cd .tools; printf '%s  %s\n' fef00bb4d36e1c50104a9775a10359beee98f162b4104dd12472c75065c6a143 node-v24.22.0-linux-arm64.tar.xz | sha256sum -c -; tar -xf node-v24.22.0-linux-arm64.tar.xz)
fi
bash ops/build-frontend.sh
.venv/bin/python ops/download-models.py
.venv/bin/python ops/setup-stamp.py
