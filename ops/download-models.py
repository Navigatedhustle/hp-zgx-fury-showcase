#!/usr/bin/env python3
"""Download immutable upstream files; resume via HF's local metadata, verify hashes."""
import argparse,concurrent.futures,hashlib,json,os,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def digest(path,algorithm,git_blob=False):
 h=hashlib.new(algorithm)
 if git_blob:h.update(('blob '+str(path.stat().st_size)+'\0').encode())
 with path.open('rb') as stream:
  for chunk in iter(lambda:stream.read(8*1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def selected_records(profile='gb300',quant='Q8_0',directory=None):
 manifest=json.loads((ROOT/'config/model-files.json').read_text())
 # Accept older immutable releases as well as the profile-indexed manifest.
 if isinstance(manifest,list):
  if profile!='gb300':raise ValueError('No GB10 model pins in this manifest')
  records=manifest
 else:records=manifest[profile]
 records=[{**model,'files':[dict(item) for item in model['files'] if not item.get('quant') or item['quant']==quant]} for model in records]
 if directory:
  records=[model for model in records if model['directory']==directory]
  if not records:raise ValueError('Unknown model directory for selected profile: '+directory)
 if profile=='gb10':
  for model in records:
   if not re.fullmatch(r'[0-9a-f]{40}',model['revision']):raise ValueError('GB10 model needs immutable revision')
   for item in model['files']:
    path=Path(item['path'])
    if path.is_absolute() or '..' in path.parts:raise ValueError('Unsafe model path')
    if item['algorithm']!='sha256' or not re.fullmatch(r'[0-9a-f]{64}',item['hash']):raise ValueError('GB10 model needs SHA256')
 return records

def main():
 p=argparse.ArgumentParser();p.add_argument('--verify-only',action='store_true')
 p.add_argument('--profile',choices=['gb300','gb10'],default='gb300')
 p.add_argument('--quant',choices=['Q8_0','Q6_K','Q4_K_XL', 'Q4_K_M'],default='Q8_0')
 p.add_argument('--model',help='Download only this pinned directory in the selected profile')
 args=p.parse_args()
 from huggingface_hub import hf_hub_download
 records=selected_records(args.profile,args.quant,args.model)
 creative_path=ROOT/'config/creative-models.json'
 if args.profile=='gb300' and not args.model and creative_path.is_file():
  creative=json.loads(creative_path.read_text())
  if creative.get('candidate_profile') in ('base','longlive'):
   candidates=[creative]
   if creative['candidate_profile']=='longlive':candidates+=creative['reviewed_adapters']
   for candidate in candidates:
    files=[]
    for item in candidate['files']:
     sha=item.get('sha256');blob=item.get('git_blob_sha1')
     if not sha and not blob:raise RuntimeError('Creative asset lacks a pinned digest')
     files.append({'path':item['path'],'size':item['bytes'],'algorithm':'sha256' if sha else 'sha1','hash':sha or blob})
    records.append({'repo':candidate['repo'],'revision':candidate['revision'],'directory':candidate['repo'].split('/')[-1],'files':files})
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
 if any(model['repo']=='hexgrad/Kokoro-82M' for model in records):
  manifest=ROOT/'build/sources/atlas-gpt-main/models/kokoro.json';manifest.parent.mkdir(parents=True,exist_ok=True)
  kokoro=next(model for model in records if model['repo']=='hexgrad/Kokoro-82M')
  manifest.write_text(json.dumps({'path':str(ROOT/'models/Kokoro-82M'),'revision':kokoro['revision']}))
 print('All pinned model files verified.',flush=True)
if __name__=='__main__':main()
