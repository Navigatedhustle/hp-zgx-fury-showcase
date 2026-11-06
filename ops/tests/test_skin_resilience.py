"""Fault injection uses fictional data, isolated files and no network."""
import asyncio
import importlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock
import httpx
import pytest
from showcase_app import skin,skin_runtime,skin_research

FIXTURE=Path(__file__).parent/'fixtures/skin/northwind.svg'


@pytest.fixture
def private_state(tmp_path,monkeypatch):
 monkeypatch.setattr(skin,'STATE',tmp_path/'state/skin')
 skin.initialize()
 return skin.STATE


@pytest.mark.parametrize('broken',['not json','[]','null','42','{"name":"Northwind Beverages"}'])
def test_broken_active_state_falls_back(private_state,broken):
 (private_state/'active.json').write_text(broken)
 assert skin.snapshot()['active'] is None
 assert skin.snapshot()['sample_pack'] is None


@pytest.mark.parametrize('damage',['missing_logo','bad_theme','semantic_override','bad_colors','bad_name','nonfinite_metadata'])
def test_cached_damage_cannot_apply(private_state,damage):
 asset=skin_research.logo_asset(FIXTURE.read_bytes(),'image/svg+xml')
 value=skin.cache_candidate('Northwind Beverages',{'source':'fictional fixture'},asset)
 if damage=='missing_logo':(private_state/'cache'/value['id']/'logo.svg').unlink()
 if damage=='bad_theme':value['theme']={'variables':[]}
 if damage=='semantic_override':value['theme']['variables']['--mc-red']='#000000'
 if damage=='bad_colors':value['colors']=[['#ffffff','bad']]
 if damage=='bad_name':value['name']=['Northwind Beverages']
 if damage=='nonfinite_metadata':value['retrieved']=float('nan')
 skin.write_json(private_state/'cache'/value['id']/'skin.json',value)
 skin.write_json(private_state/'active.json',value)
 assert skin.snapshot()['active'] is None
 assert skin.recent()==[]
 with pytest.raises(ValueError):skin.apply_skin(value['id'])


@pytest.mark.parametrize('config',['[]','{"idle_hours":"broken"}','{"idle_hours":-1}','not json'])
def test_bad_optional_config_defaults(tmp_path,monkeypatch,config):
 monkeypatch.setattr(skin,'ROOT',tmp_path);(tmp_path/'config/skin_packs').mkdir(parents=True)
 (tmp_path/'config/skin.json').write_text(config)
 (tmp_path/'config/skin_packs/broken.json').write_text('[]')
 assert skin.settings()=={'idle_hours':8,'presentations_booth_palette':False}
 assert skin.packs()=={}


def test_corrupt_counter_is_unknown_and_stops_public_fetch(private_state):
 (private_state/'web-counter.json').write_text('[]')
 assert skin.public_count() is None
 with pytest.raises(skin_research.LookupError):skin.count_request()
 assert (private_state/'web-counter.json').read_text()=='[]'


@pytest.mark.parametrize('color',['black','white'])
def test_neutral_raster_with_no_chromatic_pixels_still_applies(private_state,color):
 import io
 from PIL import Image
 stream=io.BytesIO();Image.new('RGBA',(32,32),color).save(stream,format='PNG')
 asset=skin_research.logo_asset(stream.getvalue(),'image/png')
 value=skin.cache_candidate('Northwind Beverages',{'source':'fictional fixture'},asset)
 applied=skin.apply_skin(value['id'])['active']
 assert applied['theme']['monochrome']
 assert applied['theme']['variables']=={}


def test_missing_optional_dependency_does_not_prevent_core_import(monkeypatch):
 import builtins
 original=builtins.__import__
 def unavailable(name,globals=None,locals=None,fromlist=(),level=0):
  if name=='showcase_app' and 'skin' in fromlist:raise ImportError('fictional missing dependency')
  return original(name,globals,locals,fromlist,level)
 with monkeypatch.context() as scoped:
  scoped.setattr(builtins,'__import__',unavailable)
  importlib.reload(skin_runtime)
  assert skin_runtime.service is None
  assert skin_runtime.snapshot()['active'] is None
 importlib.reload(skin_runtime)


def test_skin_storage_failure_does_not_abort_lifecycle(monkeypatch):
 service=Mock();service.initialize.side_effect=OSError('fictional read-only disk')
 async def shutdown():raise OSError('fictional cleanup failure')
 service.shutdown=shutdown
 monkeypatch.setattr(skin_runtime,'service',service)
 skin_runtime.initialize();asyncio.run(skin_runtime.shutdown())


def test_optional_failure_does_not_stop_real_core_collector_or_sse(tmp_path,monkeypatch):
 from showcase_app import operator,telemetry
 service=Mock();service.snapshot.side_effect=ValueError('fictional corrupt skin');service.public_count.side_effect=OSError('fictional unreadable counter')
 monkeypatch.setattr(skin_runtime,'service',service)
 monkeypatch.setattr(operator,'sync_agent',lambda:None)
 @contextmanager
 def connect():
  db=sqlite3.connect(':memory:');db.execute('CREATE TABLE events (started REAL)')
  try:yield db
  finally:db.close()
 monkeypatch.setattr(operator,'connect',connect)
 original=httpx.AsyncClient
 def client(**kwargs):
  return original(**kwargs,transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'ready':True,'external_api_calls':0})))
 monkeypatch.setattr(operator.httpx,'AsyncClient',client)
 async def sample(live):return {'gpu':{'hbm_used_mib':1,'utilization':0,'power_w':100},'external_api_calls':0}
 monkeypatch.setattr(telemetry,'sample',sample)
 from showcase_app import event
 monkeypatch.setattr(event,'ROOT',tmp_path)
 directory=tmp_path/'state/slides';directory.mkdir(parents=True)
 with sqlite3.connect(directory/'app.db') as db:db.execute('CREATE TABLE events (started REAL)')
 monitor=event.Monitor(event.Store(tmp_path/'event.sqlite'))
 async def run():
  await monitor.refresh(operator.collect_live)
  first=monitor.latest_live['timestamp']
  await monitor.refresh(operator.collect_live)
  assert monitor.latest_live['timestamp']>first
  stream=json.loads(monitor.stream)
  assert stream['skin']['active'] is None
  assert stream['telemetry']['external_api_calls']==0
  assert stream['telemetry']['public_web_lookups'] is None
  assert stream['event']['timestamp']>0
 asyncio.run(run())


def test_independent_reset_does_not_need_skin_service(tmp_path,monkeypatch):
 from fastapi.testclient import TestClient
 from showcase_app import operator
 monkeypatch.setattr(operator,'ROOT',tmp_path)
 path=tmp_path/'state/skin/active.json';path.parent.mkdir(parents=True);path.write_text('broken')
 monkeypatch.setattr(skin_runtime,'service',None)
 client=TestClient(operator.app)
 assert client.post('/api/appearance/reset',headers={'origin':'https://evil.invalid'}).status_code==403
 assert path.exists()
 assert client.post('/api/appearance/reset').status_code==200
 assert not path.exists()


@pytest.mark.parametrize('broken',['not json','[]','{"name":[]}','{"name":"Northwind Beverages"}'])
def test_launch_status_survives_bad_skin_or_config(tmp_path,monkeypatch,broken):
 monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
 spec=importlib.util.spec_from_file_location('skin_status_control',Path(__file__).resolve().parents[1]/'control.py')
 control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
 monkeypatch.setattr(control,'ROOT',tmp_path);monkeypatch.setattr(control,'STATE',tmp_path/'state')
 (tmp_path/'state/skin').mkdir(parents=True);(tmp_path/'state/skin/active.json').write_text(broken)
 (tmp_path/'config').mkdir();(tmp_path/'config/skin.json').write_text('[]')
 assert control.skin_status() in ('default · HP ZGX Fury','Northwind Beverages')
