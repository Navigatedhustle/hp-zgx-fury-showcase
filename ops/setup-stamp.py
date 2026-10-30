import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FILES=['ops/apps-requirements.lock','ops/models-requirements.lock','ops/lead-requirements.lock','config/model-files.json','ops/bootstrap.sh','build/sources/html_builder-main/frontend/package-lock.json']
def signature():return hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in FILES)).hexdigest()
if __name__=='__main__':
 p=ROOT/'state/setup.json';p.parent.mkdir(exist_ok=True);p.write_text(json.dumps({'signature':signature()}))
