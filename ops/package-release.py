#!/usr/bin/env python3
"""Package ONLY the reviewed explicit list; works with or without Git metadata."""
import argparse,hashlib,json,stat,tarfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--version',default='v2.0.0');p.add_argument('--output',type=Path,default=ROOT/'dist');a=p.parse_args()
if not __import__('re').fullmatch(r'v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?',a.version):raise SystemExit('Invalid version')
files=json.loads((ROOT/'config/distribution-files.json').read_text());prefix='hp-zgx-fury-showcase-'+a.version;a.output.mkdir(parents=True,exist_ok=True)
for name in files:
 f=ROOT/name
 if not f.is_file() or f.is_symlink() or Path(name).is_absolute() or '..' in Path(name).parts:raise SystemExit('Unsafe inclusion: '+name)
for line in (ROOT/'SOURCE-SHA256SUMS').read_text().splitlines():
 expected,name=line.split('  ',1)
 if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:raise SystemExit('Changed since review: '+name)
archives=[]
with tarfile.open(a.output/(prefix+'.tar.gz'),'w:gz') as archive:
 for name in files:
  info=archive.gettarinfo(str(ROOT/name),arcname=prefix+'/'+name);info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0
  with (ROOT/name).open('rb') as stream:archive.addfile(info,stream)
archives.append(a.output/(prefix+'.tar.gz'))
with zipfile.ZipFile(a.output/(prefix+'.zip'),'w',compression=zipfile.ZIP_DEFLATED) as archive:
 for name in files:
  info=zipfile.ZipInfo(prefix+'/'+name,date_time=(2026,10,30,0,0,0));info.external_attr=((ROOT/name).stat().st_mode&0xffff)<<16;info.compress_type=zipfile.ZIP_DEFLATED;archive.writestr(info,(ROOT/name).read_bytes())
archives.append(a.output/(prefix+'.zip'))
(a.output/'SHA256SUMS').write_text(''.join(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+f.name+'\n' for f in archives))
print('\n'.join(str(f) for f in archives))
