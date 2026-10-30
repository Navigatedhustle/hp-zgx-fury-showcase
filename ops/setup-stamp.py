import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FILES=['ops/apps-requirements.lock','ops/models-requirements.lock','ops/lead-requirements.lock','config/model-files.json','ops/bootstrap.sh','build/sources/html_builder-main/frontend/package-lock.json']
def signature():
 # Source changes must rebuild the shipped editor on release upgrades/rollback.
 frontend=ROOT/'build/sources/html_builder-main/frontend'
 ui=[frontend/'index.html']+sorted((frontend/'src').rglob('*'))
 paths=[ROOT/p for p in FILES]+[p for p in ui if p.is_file()]
 return hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode()+b'\0'+p.read_bytes() for p in paths)).hexdigest()
if __name__=='__main__':
 p=ROOT/'state/setup.json';p.parent.mkdir(exist_ok=True);p.write_text(json.dumps({'signature':signature()}))
