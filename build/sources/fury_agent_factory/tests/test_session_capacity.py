import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import api,devteam_routes as routes
class SessionTests(unittest.TestCase):
 def test_separate_clients_cannot_control_each_others_run(self):
  with patch.object(routes,'runs',{}):
   a=TestClient(api.app,base_url="http://localhost");b=TestClient(api.app,base_url="http://localhost")
   self.assertEqual(a.get('/api/devteam/run').json()['state'],'ready')
   self.assertEqual(b.get('/api/devteam/run').json()['state'],'ready')
   self.assertNotEqual(a.cookies.get('fury_factory_session'),b.cookies.get('fury_factory_session'))
   fake=__import__('types').SimpleNamespace(id='fixture',root=routes.ROOT,state='running',thread=__import__('types').SimpleNamespace(is_alive=lambda:True))
   routes.runs[a.cookies.get('fury_factory_session')]=fake
   self.assertEqual(b.get('/api/devteam/run').json()['state'],'ready')
   self.assertEqual(b.post('/api/devteam/stop').status_code,404)
   self.assertEqual(b.post('/api/devteam/runs',json={'automatic':True}).status_code,429)
   self.assertEqual(len(routes.runs),1)

class JavaScriptValidationTests(unittest.TestCase):
 def test_invalid_javascript_is_rejected_without_execution(self):
  import tempfile
  from pathlib import Path
  from devteam_sandbox import check_javascript
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'app.js').write_text('(()=>{')
   with self.assertRaisesRegex(ValueError,'syntax'):check_javascript(root)
   (root/'app.js').write_text('throw new Error("MUST NEVER EXECUTE");')
   check_javascript(root)

class WorkspaceManifestTests(unittest.TestCase):
 def test_runtime_directories_are_not_promoted(self):
  import tempfile
  from pathlib import Path
  from devteam import copy_workspace
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'source';source.mkdir();(source/'app.js').write_text('void 0;');(source/'__pycache__').mkdir();(source/'__pycache__/cache.pyc').write_bytes(b'fixture');(source/'unowned.txt').write_text('fixture')
   copy_workspace(source,root/'snapshot');self.assertEqual([p.name for p in (root/'snapshot').iterdir()],['app.js'])

class ArchivedSessionTests(unittest.TestCase):
 def test_retained_session_follows_archived_workspace(self):
  import tempfile
  from pathlib import Path
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);rid='0123456789ab';archived=root/'devruns-archive'/rid;archived.mkdir(parents=True)
   r=SimpleNamespace(id=rid,root=root/'devruns'/rid)
   token=routes.session.set('fixture')
   try:
    with patch.object(routes,'ROOT',root),patch.object(routes,'runs',{'fixture':r}):self.assertEqual(routes.get_current().root,archived)
   finally:routes.session.reset(token)
