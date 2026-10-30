#!/usr/bin/env python3
"""Maintainer-only: explicitly review Git's selected source paths, then refresh policy."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0');paths=sorted(set(p for p in paths if p)|{'config/distribution-files.json','SOURCE-SHA256SUMS'})
(ROOT/'config/distribution-files.json').write_text(json.dumps(paths,indent=2)+'\n')
(ROOT/'SOURCE-SHA256SUMS').write_text(''.join(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()+'  '+p+'\n' for p in paths if p!='SOURCE-SHA256SUMS'))
print('Review the selected list and all exclusions before publishing:',len(paths),'files')
