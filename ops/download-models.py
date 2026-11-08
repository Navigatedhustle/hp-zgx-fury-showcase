#!/usr/bin/env python3
"""Download immutable upstream files; resume via HF's local metadata, verify hashes."""
import argparse,concurrent.futures,hashlib,json,os,re
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]

def validate_manifest(records):
 if not isinstance(records,list) or not records:raise RuntimeError('Invalid model manifest')
 directories=set()
 for model in records:
  if not isinstance(model,dict) or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',model.get('repo','')):raise RuntimeError('Invalid manifest repository')
  if not re.fullmatch('[0-9a-f]{40}',model.get('revision','')):raise RuntimeError('Model revision must be an immutable commit digest')
  directory=model.get('directory','')
  if directory in ('.','..') or not re.fullmatch(r'[A-Za-z0-9_.-]+',directory) or directory in directories:raise RuntimeError('Invalid or duplicate model directory in manifest')
  directories.add(directory);seen=set();files=model.get('files')
  if not isinstance(files,list) or not files:raise RuntimeError('Invalid manifest file list')
  for record in files:
   name=record.get('path','') if isinstance(record,dict) else ''
   path=PurePosixPath(name)
   if not name or path.is_absolute() or '..' in path.parts or '.' in path.parts or '\\' in name or '\0' in name or str(path)!=name or name in seen:raise RuntimeError('Unsafe model manifest path')
   seen.add(name)
   if type(record.get('size')) is not int or record['size']<0:raise RuntimeError('Invalid manifest file size')
   if record.get('algorithm')!='sha256' or not re.fullmatch('[0-9a-f]{64}',record.get('hash','')):raise RuntimeError('Every model manifest file needs a SHA256 digest')

def digest(path,algorithm,git_blob=False):
 h=hashlib.new(algorithm)
 if git_blob:h.update(('blob '+str(path.stat().st_size)+'\0').encode())
 with path.open('rb') as stream:
  for chunk in iter(lambda:stream.read(8*1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def main():
 from huggingface_hub import hf_hub_download
 p=argparse.ArgumentParser();p.add_argument('--verify-only',action='store_true');args=p.parse_args()
 records=json.loads((ROOT/'config/model-files.json').read_text())
 creative_path=ROOT/'config/creative-models.json'
 if creative_path.is_file():
  creative=json.loads(creative_path.read_text())
  if creative.get('candidate_profile') in ('base','longlive'):
   candidates=[creative]
   if creative['candidate_profile']=='longlive':candidates+=creative['reviewed_adapters']
   for candidate in candidates:
    files=[]
    for item in candidate['files']:
     sha=item.get('sha256')
     if not sha:raise RuntimeError('Creative asset lacks a pinned SHA256 digest')
     files.append({'path':item['path'],'size':item['bytes'],'algorithm':'sha256','hash':sha})
    records.append({'repo':candidate['repo'],'revision':candidate['revision'],'directory':candidate['repo'].split('/')[-1],'files':files})
 validate_manifest(records)
 models=(ROOT/'models').resolve()
 for model in records:
  folder=ROOT/'models'/model['directory']
  if not folder.resolve().is_relative_to(models):raise RuntimeError('Unsafe model directory path')
  if args.verify_only and not folder.is_dir():raise RuntimeError('Missing pinned model directory: '+model['directory'])
  if not args.verify_only:folder.mkdir(parents=True,exist_ok=True)
  total=sum(f['size'] for f in model['files']);print(f"{model['repo']} @ {model['revision']} — {total/1024**3:.2f} GiB",flush=True)
  def fetch(record):
   path=folder/record['path']
   if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):raise RuntimeError('Unsafe model asset path')
   if not args.verify_only:
    hf_hub_download(model['repo'],record['path'],revision=model['revision'],local_dir=folder,token=os.getenv('HF_TOKEN') or False)
   if not path.is_file() or path.stat().st_size!=record['size']:raise RuntimeError('Missing or wrong-sized asset: '+str(path))
   marker=folder/'.verified'/record['path'];stamp=str(path.stat().st_mtime_ns)+':'+str(record['size'])+':'+record['hash']
   # A metadata marker is informational; every setup/download and verify-only
   # invocation authenticates the actual bytes against the pinned SHA256.
   print('Verifying '+model['directory']+'/'+record['path'],flush=True)
   if digest(path,'sha256')!=record['hash']:raise RuntimeError('Checksum failed: '+str(path)+'; remove this file and rerun setup')
   if not args.verify_only:marker.parent.mkdir(parents=True,exist_ok=True);marker.write_text(stamp)
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(fetch,model['files']))
 manifest=ROOT/'build/sources/atlas-gpt-main/models/kokoro.json';manifest.parent.mkdir(parents=True,exist_ok=True)
 pins=json.loads((ROOT/'config/model-pins.json').read_text())
 manifest.write_text(json.dumps({'path':str(ROOT/'models/Kokoro-82M'),'revision':pins['hexgrad/Kokoro-82M']['revision']}))
 print('All pinned model files verified.',flush=True)
if __name__=='__main__':main()
