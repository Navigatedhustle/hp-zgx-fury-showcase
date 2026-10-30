#!/usr/bin/env python3
"""Download immutable upstream files; resume via HF's local metadata, verify hashes."""
import argparse,concurrent.futures,hashlib,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
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
 for model in records:
  folder=ROOT/'models'/model['directory'];folder.mkdir(parents=True,exist_ok=True)
  total=sum(f['size'] for f in model['files']);print(f"{model['repo']} @ {model['revision']} — {total/1024**3:.2f} GiB",flush=True)
  def fetch(record):
   path=folder/record['path']
   if not args.verify_only:
    hf_hub_download(model['repo'],record['path'],revision=model['revision'],local_dir=folder,token=os.getenv('HF_TOKEN') or False)
   if not path.is_file() or path.stat().st_size!=record['size']:raise RuntimeError('Missing or wrong-sized asset: '+str(path))
   marker=folder/'.verified'/record['path'];stamp=str(path.stat().st_mtime_ns)+':'+str(record['size'])+':'+record['hash']
   if args.verify_only or not marker.exists() or marker.read_text()!=stamp:
    print('Verifying '+model['directory']+'/'+record['path'],flush=True)
    if digest(path,record['algorithm'],record['algorithm']=='sha1')!=record['hash']:raise RuntimeError('Checksum failed: '+str(path)+'; remove this file and rerun setup')
    marker.parent.mkdir(parents=True,exist_ok=True);marker.write_text(stamp)
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(fetch,model['files']))
 manifest=ROOT/'build/sources/atlas-gpt-main/models/kokoro.json';manifest.parent.mkdir(parents=True,exist_ok=True)
 pins=json.loads((ROOT/'config/model-pins.json').read_text())
 manifest.write_text(json.dumps({'path':str(ROOT/'models/Kokoro-82M'),'revision':pins['hexgrad/Kokoro-82M']['revision']}))
 print('All pinned model files verified.',flush=True)
if __name__=='__main__':main()
