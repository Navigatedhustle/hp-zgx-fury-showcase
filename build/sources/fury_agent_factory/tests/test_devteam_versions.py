import asyncio,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from devteam import DevRun
import devteam_routes as routes
class PublishedVersionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.run=DevRun(store=Path(self.tmp.name),automatic=True)
  self.run.tests={'passed':True}
  for content in ['first','second']:
   self.run.apply({'files':{'index.html':content,'backend.py':content}});self.run.promote(content)
 def test_retained_frame_and_backend_use_the_requested_version(self):
  with patch.object(routes,'get_current',return_value=self.run):
   page=asyncio.run(routes.preview(1,self.run.id));self.assertEqual(page['html'],'first')
   with patch.object(routes,'execute',return_value={'status':200,'body':{'fixture':True}}) as execute:
    req=routes.BackendRequest(method='GET',path='/hotels',body={},version=1,run_id=self.run.id)
    reply=asyncio.run(routes.backend(req))
    self.assertEqual(execute.call_args.args[0],self.run.root/'version-1')
    self.assertEqual(execute.call_args.args[3],{'method':'GET','path':'/hotels','body':{}})
    self.assertEqual(reply['preview_version'],1);self.assertEqual(reply['preview_hash'],self.run.versions[0]['hash'])
 def test_stale_run_or_unknown_version_cannot_reach_backend(self):
  with patch.object(routes,'get_current',return_value=self.run),patch.object(routes,'execute') as execute:
   for run_id,version,status in [('old-run',1,409),(self.run.id,999,404)]:
    with self.assertRaises(HTTPException) as error:asyncio.run(routes.backend(routes.BackendRequest(method='GET',path='/hotels',version=version,run_id=run_id)))
    self.assertEqual(error.exception.status_code,status)
   execute.assert_not_called()
 def test_parent_frame_policy_blocks_foreign_navigation(self):
  response=asyncio.run(routes.page());self.assertIn("frame-src 'self'",response.headers['content-security-policy'])
