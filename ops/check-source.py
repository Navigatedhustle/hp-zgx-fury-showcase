#!/usr/bin/env python3
"""Dependency-free distribution audit: syntax, inclusion policy, private paths, hashes."""
import ast,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 paths=json.loads((ROOT/'config/distribution-files.json').read_text());errors=[]
 if (ROOT/'.git').exists():
  tracked=set(subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0'))-{''}
  if tracked!=set(paths):errors.append('Tracked files differ from explicit inclusion policy; review and run ops/update-distribution.py')
 for name in paths:
  p=ROOT/name
  if Path(name).is_absolute() or '..' in Path(name).parts or p.is_symlink() or not p.is_file():errors.append(name+': unsafe/missing inclusion');continue
  if any(part in {'models','state','logs','reports','.venv','.model-venv','.deepseek-venv','.cache','.tools','node_modules','devruns','devruns-archive'} for part in Path(name).parts):errors.append(name+': runtime/private directory')
  if p.suffix.lower() in {'.safetensors','.gguf','.onnx','.pth','.pt','.sqlite','.db','.pem','.key'}:errors.append(name+': forbidden runtime/credential asset')
  data=p.read_bytes()
  if len(data)>25*1024**2:errors.append(name+': oversized source')
  if re.search(rb'/home/[^/\s]+/(?:gtc-fury|frankfurt-upgrade)|[a-z0-9-]+\.tail[a-z0-9]+\.ts\.net|-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY|\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}|tskey-[A-Za-z0-9_-]{20,}',data):errors.append(name+': private content pattern')
  if p.suffix=='.py':
   try:ast.parse(data,filename=name)
   except SyntaxError as e:errors.append(name+': '+str(e))
  if p.suffix=='.sh' or name=='showcase':
   r=subprocess.run(['bash','-n',str(p)],capture_output=True,text=True)
   if r.returncode:errors.append(name+': shell syntax')
 if (ROOT/'SOURCE-SHA256SUMS').exists():
  for line in (ROOT/'SOURCE-SHA256SUMS').read_text().splitlines():
   checksum,name=line.split('  ',1)
   if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=checksum:errors.append(name+': source hash mismatch')
 print(json.dumps({'files':len(paths),'errors':errors},indent=2));return bool(errors)
if __name__=='__main__':sys.exit(main())
