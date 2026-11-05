#!/usr/bin/env python3
"""Audit exact index blobs; never print secret matches or secret values."""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',default='state/publish-audit.json');parser.add_argument('--forbid-term-file');args=parser.parse_args()
 entries=git('ls-files','--stage','-z').split(b'\0');files=[];issues=[]
 forbidden=[]
 if args.forbid_term_file:forbidden=[x.strip().lower().encode() for x in Path(args.forbid_term_file).read_text().splitlines() if x.strip()]
 for raw in entries:
  if not raw:continue
  header,pathraw=raw.split(b'\t',1);mode,oid,stage=header.decode().split();path=pathraw.decode();p=Path(path);data=git('cat-file','blob',oid)
  reason=[]
  if mode not in ('100644','100755'):reason.append('non-regular source entry')
  if len(data)>=100*1024**2:reason.append('GitHub single-file size limit')
  if any(x in p.parts for x in ['.git','.venv','.model-venv','.image-venv','node_modules','__pycache__','.codex','.ssh','.tools','logs','reports','handoff','state']):reason.append('local/private directory')
  if p.name.startswith('.env') and p.name!='.env.example':reason.append('environment file')
  if p.name=='.publication.json':reason.append('old destination metadata')
  approved_document = path in {'docs/Colorado-Deployment-v2.1.0.pdf', 'docs/Colorado-Deployment-v2.1.1.pdf', 'docs/Colorado-Deployment-v2.2.0.pdf'}
  if not approved_document and p.suffix.lower() in {'.pdf','.zip','.safetensors','.gguf','.onnx','.pt','.pth','.pem','.key','.p12','.pfx','.sqlite','.db','.log','.wav','.mp4','.pptx'}:reason.append('private/runtime/large artifact type')
  secret_patterns=[rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',rb'\bgh[pousr]_[A-Za-z0-9]{30,}\b',rb'\bgithub_pat_[A-Za-z0-9_]{30,}\b',rb'\bAKIA[A-Z0-9]{16}\b',rb'\bsk-[A-Za-z0-9_-]{30,}\b',rb'tskey-[A-Za-z0-9_-]{20,}']
  if any(re.search(pattern,data) for pattern in secret_patterns):reason.append('credential-shaped content')
  if any(term in data.lower() or term in pathraw.lower() for term in forbidden):reason.append('owner-excluded content')
  if reason:issues.append({'path':path,'reasons':reason})
  files.append({'path':path,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'git_blob':oid,'mode':mode})
 result={'files':files,'count':len(files),'bytes':sum(f['bytes'] for f in files),'issues':issues,'scope':'Exact staged Git blobs, sizes, path policy, credential patterns and any locally supplied forbidden terms. Manual synthetic-data and asset provenance review is also required.'}
 output=ROOT/args.output;output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2))
 print(json.dumps({'files':result['count'],'bytes':result['bytes'],'issues':issues,'manifest':str(output)},indent=2));return bool(issues)
if __name__=='__main__':sys.exit(main())
