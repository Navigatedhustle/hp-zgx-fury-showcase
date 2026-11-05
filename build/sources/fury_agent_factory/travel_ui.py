"""Maintained travel interface. Local models implement the backend contract around it.

Runtime destination imagery is optional, locally generated and never model context.
This foundation is disclosed in the run audit; it is not model-generated work.
"""
import base64,hashlib,json,re
from pathlib import Path
from travel_art import scene
ROOT=Path(__file__).resolve().parent/'travel_portal'
FILES=('index.html','styles.css','app.js')

def install_frontend(destination):
 destination=Path(destination)
 # Only a new workspace may receive the foundation; never replace retained work.
 if any((destination/name).exists() for name in FILES):return None
 source={name:(ROOT/name).read_text() for name in FILES}
 try:assets=json.loads((ROOT/'art-data.json').read_text())
 except (OSError,ValueError):assets={}
 colors={'hero':'#53766c','Lisbon':'#d4a26c','Kyoto':'#78895c','Copenhagen':'#9aaeb8','Edinburgh':'#8c9e90','Porto':'#bb9475','Ljubljana':'#88a68a'}
 def image(name):
  value=assets.get(name,'')
  if isinstance(value,str) and len(value)<1500000 and re.fullmatch(r'data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+',value):return value
  supplied=ROOT/'assets/mediterranean-retreat.webp'
  if name=='hero' and supplied.is_file():return 'data:image/webp;base64,'+base64.b64encode(supplied.read_bytes()).decode()
  svg=scene('Lisbon' if name=='hero' else name)
  return 'data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode()
 html=source['index.html'].replace('__HERO_IMAGE__',image('hero')).replace('__LISBON_IMAGE__',image('Lisbon'))
 html=html.replace('__DESTINATION_IMAGES__',''.join('<img id="art-'+city+'" src="'+image(city)+'" alt="Illustrative destination scene">' for city in colors if city!='hero'))
 destination.mkdir(parents=True,exist_ok=True)
 for name,text in source.items():(destination/name).write_text(html if name=='index.html' else text)
 supplied=ROOT/'assets/mediterranean-retreat.webp'
 return {'type':'maintained travel frontend','source_hash':hashlib.sha256(''.join(source.values()).encode()).hexdigest(),'files':list(FILES),'imagery':'supplied AI-created hero and local vector scenes' if supplied.is_file() else 'local AI-created scenes' if assets else 'local vector scenes','hero_sha256':hashlib.sha256(supplied.read_bytes()).hexdigest() if supplied.is_file() else None,'disclosure':'Frontend foundation installed without model inference; local agents build backend and QA. Hero artwork and destination illustrations are supplied, not generated during the live backend build.'}
