"""The maintained UI reduces repeated wiring work without claiming inference."""
from travel_ui import install_frontend
from travel_run import TravelRun

def test_foundation_is_complete_and_disclosed_without_model_calls(tmp_path):
 r=TravelRun(store=tmp_path/'runs')
 assert not r.calls
 for filename in ('index.html','app.js','styles.css'):assert (r.candidate/filename).stat().st_size>1000
 assert r.product['frontend_foundation']['disclosure'].startswith('Frontend foundation installed without model inference')
 frontend=[t for t in r.tasks if t['owns'][0] in ('index.html','app.js','styles.css')]
 assert len(frontend)==3 and all(t['status']=='merged' for t in frontend)
 assert all(t['status']=='pending' for t in r.tasks if t not in frontend)
 assert not any(c['passed'] for c in r.product['criteria'])

def test_foundation_never_overwrites_retained_source(tmp_path):
 (tmp_path/'app.js').write_text('existing user work')
 assert install_frontend(tmp_path) is None
 assert (tmp_path/'app.js').read_text()=='existing user work'
 assert not (tmp_path/'index.html').exists()

def test_portal_template_renders_without_optional_image_artifacts(tmp_path,monkeypatch):
 import travel_ui
 from pathlib import Path
 source=tmp_path/'source';source.mkdir()
 for name in travel_ui.FILES:(source/name).write_text((travel_ui.ROOT/name).read_text())
 monkeypatch.setattr(travel_ui,'ROOT',source)
 out=tmp_path/'new';result=install_frontend(out)
 html=(out/'index.html').read_text()
 assert result['imagery']=='local vector scenes'
 assert '__HERO_IMAGE__' not in html and '__DESTINATION_IMAGES__' not in html
 assert 'data:image/svg+xml;base64,' in html
