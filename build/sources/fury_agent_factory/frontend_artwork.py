"""Pin disclosed supplied artwork per new short run without adding network access."""
import base64,hashlib,json,os
from pathlib import Path

SOURCE=Path(__file__).resolve().parent/'travel_portal/assets/mediterranean-retreat.webp'
NAME='supplied-artwork.json'

def pin_artwork(root):
    target=Path(root)/NAME
    if target.exists() or not SOURCE.is_file():return
    raw=SOURCE.read_bytes()
    if len(raw)>1_000_000:raise ValueError('Supplied artwork exceeds the local display budget')
    payload={'schema':1,'sha256':hashlib.sha256(raw).hexdigest(),
             'hero':'data:image/webp;base64,'+base64.b64encode(raw).decode(),
             'disclosure':'Application code generated live; fictional hero artwork supplied before the build.'}
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump(payload,f)

def artwork_for(code):
    code=Path(code)
    for folder in (code,*list(code.parents)[:5]):
        path=folder/NAME
        if not path.is_file():continue
        if path.stat().st_size>1_500_000:raise ValueError('Invalid pinned artwork size')
        data=json.loads(path.read_text());uri=data.get('hero','')
        if not uri.startswith('data:image/webp;base64,'):raise ValueError('Invalid pinned artwork type')
        raw=base64.b64decode(uri.split(',',1)[1],validate=True)
        if hashlib.sha256(raw).hexdigest()!=data.get('sha256'):raise ValueError('Pinned artwork checksum mismatch')
        return {'hero':uri}
    return {}

def artwork_script(code):
    artwork=artwork_for(code)
    return script_for(artwork)

def script_for(artwork):
    return 'window.furyArtwork=Object.freeze('+json.dumps(artwork)+');Object.entries(window.furyArtwork).forEach(([name,uri])=>document.documentElement.style.setProperty("--fury-artwork-"+name,"url("+uri+")"));' if artwork else ''
