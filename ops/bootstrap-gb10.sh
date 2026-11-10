#!/usr/bin/env bash
# Explicit GB10 model/build preparation. The show launcher never downloads at runtime.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -m)" == aarch64 ]] || { echo 'GB10 preparation requires Linux ARM64.' >&2; exit 1; }
[[ -x /usr/bin/python3.12 ]] || { echo 'Install Python3.12 and venv support before preparation.' >&2; exit 1; }
export FURY_PROFILE=gb10
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright"
mkdir -p state .cache .local-debs
exec 9>state/gb10-setup.lock
flock 9
for environment_path in .venv .model-venv; do
  [[ -x "$environment_path/bin/python" ]] || /usr/bin/python3.12 -m venv "$environment_path"
done
.venv/bin/python -m pip install --no-deps -r ops/apps-requirements.lock
.model-venv/bin/python -m pip install --no-deps -r ops/gb10-models-requirements.lock --extra-index-url https://download.pytorch.org/whl/cu130
if [[ ! -f .local-debs/extracted/usr/include/python3.12/Python.h ]]; then
  (
    cd .local-debs
    apt-get download libpython3.12-dev=3.12.3-1ubuntu0.17
  )
fi
.venv/bin/python - <<'PY'
import hashlib,json,subprocess
from pathlib import Path
pin=json.loads(Path('config/gb10-build.json').read_text())['python_headers']
archive=Path('.local-debs/libpython3.12-dev_'+pin['version']+'_'+pin['architecture']+'.deb')
if not archive.is_file() or hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()!=pin['sha256']:
    raise SystemExit('Pinned local Python header package is missing or has a different SHA256.')
subprocess.run(['dpkg-deb','-x',str(archive),'.local-debs/extracted'],check=True)
PY
.venv/bin/python ops/build-gb10-llama.py
.venv/bin/python -m playwright install chromium
profile_quant="$(.venv/bin/python -c 'import json; print(json.load(open("config/gb10.json"))["lanes"]["text"]["quant"])')"
model_quant="${FURY_GB10_QUANT:-$profile_quant}"
.venv/bin/python ops/download-models.py --profile gb10 --quant "$model_quant"
.venv/bin/python ops/build-gb10-codecs.py
echo 'GB10 preparation complete. Verify qualification and record this build before the show.'
