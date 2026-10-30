#!/usr/bin/env bash
# Scan the explicitly included source and, if present, all repository history.
set -euo pipefail
cd "$(dirname "$0")/.."
case "$(uname -m)" in
 aarch64) architecture=arm64; checksum=e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080 ;;
 x86_64) architecture=x64; checksum=551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb ;;
 *) echo 'Secret scanner supports Linux ARM64/x86_64'; exit 1 ;;
esac
scanner="$PWD/.tools/gitleaks-8.30.1"
if [[ ! -x "$scanner/gitleaks" ]]; then
 mkdir -p "$scanner"
 curl -fsSL --retry 3 "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_${architecture}.tar.gz" -o "$scanner/archive.tar.gz"
 echo "$checksum  $scanner/archive.tar.gz" | sha256sum -c -
 tar -xf "$scanner/archive.tar.gz" -C "$scanner"
fi
selected="$(mktemp -d)"
trap 'rm -rf "$selected"' EXIT
python3 - "$selected" <<'PY'
import json,shutil,sys
from pathlib import Path
root=Path.cwd();dest=Path(sys.argv[1])
for name in json.loads((root/'config/distribution-files.json').read_text()):
 p=dest/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(root/name,p)
PY
"$scanner/gitleaks" dir "$selected" --config .gitleaks.toml --redact
if git rev-parse --git-dir >/dev/null 2>&1; then "$scanner/gitleaks" git . --config .gitleaks.toml --log-opts=--all --redact; fi
