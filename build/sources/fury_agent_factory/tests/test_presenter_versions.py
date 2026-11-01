"""Regression coverage for retained versions, usage and private run evidence."""
import asyncio,time,unittest,tempfile
from pathlib import Path
from collections import deque
from unittest.mock import patch
from fastapi import HTTPException
from devteam import DevRun
import devteam_routes as routes
class PresenterContracts(unittest.TestCase):
 def test_checked_version_selection_never_silently_falls_forward(self):
  class Run:versions=[{'version':1},{'version':3}]
  self.assertEqual(routes.published_version(Run(),1),1)
  self.assertEqual(routes.published_version(Run()),3)
  with self.assertRaises(HTTPException):routes.published_version(Run(),2)
 def test_completed_call_does_not_keep_animating_as_generation(self):
  with tempfile.TemporaryDirectory() as tmp:
   r=DevRun(store=Path(tmp));r.calls=[{'id':'one','actor':'maya','usage':{'completion_tokens':30},'live_supported':True,'status':'complete','_samples':deque([(time.monotonic(),30)]),'_text':''}]
   self.assertEqual(r.snapshot()['calls'][0]['current_tps'],0)
 def test_terminal_elapsed_is_frozen_and_start_is_durable(self):
  with tempfile.TemporaryDirectory() as tmp:
   r=DevRun(store=Path(tmp));r.started=time.time()-10;r.state='finished';r.event('terminal',state='finished');before=r.snapshot()['elapsed_s']
   with patch('devteam.time.time',return_value=time.time()+100):self.assertEqual(r.snapshot()['elapsed_s'],before)
   import json
   self.assertEqual(json.loads((r.root/'audit.json').read_text())['started'],r.started)
 def test_watch_cannot_disclose_other_session(self):
  class Run:id='owner'
  with patch.object(routes,'run',return_value=Run()):
   with self.assertRaises(HTTPException) as e:asyncio.run(routes.watch_travel('another'))
   self.assertEqual(e.exception.status_code,404)
 def test_session_retention_never_evicts_an_active_recording(self):
  from types import SimpleNamespace
  active=SimpleNamespace(id='recorded',thread=None,mode='recorded',snapshot=lambda:{'state':'running'})
  idle=SimpleNamespace(id='idle',thread=None)
  newest=SimpleNamespace(id='new',thread=None)
  stored={'recorded-owner':active,**{'idle-'+str(i):idle for i in range(99)}}
  token=routes.session.set('new-owner')
  try:
   with patch.object(routes,'runs',stored),patch.object(routes,'persist_sessions'):
    routes.set_current(newest)
    self.assertIn('recorded-owner',stored)
    self.assertEqual(len(stored),100)
  finally:routes.session.reset(token)
