#!/usr/bin/env python3
"""Local, read-only diagnostics; output may contain local paths, so don't upload it."""
import subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1]
for command in [[sys.executable,'ops/preflight.py','--ports'],['./showcase','status']]:
 subprocess.run(command,cwd=r)
for path in sorted((r/'logs').glob('*.log')):
 print('\n'+path.name+': last 12 lines')
 print('\n'.join(path.read_text(errors='replace').splitlines()[-12:]))
