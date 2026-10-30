"""Maintained travel interface. Local models implement the backend contract around it.

Runtime destination imagery is optional, locally generated and never model context.
This foundation is disclosed in the run audit; it is not model-generated work.
"""
import base64,hashlib,json,re
from pathlib import Path
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
  svg='<svg xmlns="http://www.w3.org/2000/svg" width="768" height="768"><rect width="768" height="768" fill="'+colors[name]+'"/><circle cx="550" cy="160" r="85" fill="#eddcab"/><path d="M0 560 220 270 440 560 640 320 768 560V768H0" fill="#36594f"/><path d="M0 650Q300 460 768 650V768H0" fill="#bdc8a2"/><path d="M80 620V450H220V620M300 620V390H400V620" fill="#f0d7a9"/></svg>'
  return 'data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode()
 html=source['index.html'].replace('__HERO_IMAGE__',image('hero')).replace('__LISBON_IMAGE__',image('Lisbon'))
 html=html.replace('__DESTINATION_IMAGES__',''.join('<img id="art-'+city+'" src="'+image(city)+'" alt="Illustrative destination scene">' for city in colors if city!='hero'))
 destination.mkdir(parents=True,exist_ok=True)
 for name,text in source.items():(destination/name).write_text(html if name=='index.html' else text)
 return {'type':'maintained travel frontend','source_hash':hashlib.sha256(''.join(source.values()).encode()).hexdigest(),'files':list(FILES),'imagery':'local AI-created scenes' if assets else 'local vector scenes','disclosure':'Frontend foundation installed without model inference; local agents build backend and QA.'}
