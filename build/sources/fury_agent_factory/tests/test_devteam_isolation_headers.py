import asyncio,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from devteam import DevRun
import devteam_routes

class PreviewIsolationTests(unittest.TestCase):
 def test_automatic_policy_does_not_invent_human_participation(self):
  with tempfile.TemporaryDirectory() as folder:
   run=DevRun(store=Path(folder),automatic=True)
   humans=[a for a in run.snapshot()['actors'] if a['type']=='human']
   self.assertEqual([a['name'] for a in humans],['Operator']);self.assertTrue(all(a['presence']=='operator' and a['current_tps'] is None for a in humans));self.assertFalse(run.events)
 def test_human_work_has_no_inference_rate(self):
  with tempfile.TemporaryDirectory() as folder:
   run=DevRun(store=Path(folder))
   humans=[a for a in run.snapshot()['actors'] if a['type']=='human']
   self.assertEqual(len(humans),1)
   for actor in humans:
    self.assertIsNone(actor['tokens'])
    self.assertIsNone(actor['current_tps'])
    self.assertIsNone(actor['last_response_tps'])
 def test_generated_frame_cannot_use_network_or_external_forms(self):
  async def preview(*args):return {'html':'<h1>Fictional</h1><script>bad()</script>','css':'','js':'window.ready=true','version':{'version':1},'run_id':'fixture'}
  with patch.object(devteam_routes,'preview',preview):response=asyncio.run(devteam_routes.preview_frame())
  policy=response.headers['content-security-policy']
  for rule in ["default-src 'none'","connect-src 'none'","form-action 'none'","base-uri 'none'"]:
   self.assertIn(rule,policy)
  self.assertNotIn('bad()',response.body.decode())
  self.assertEqual(response.headers['cache-control'],'no-store')
