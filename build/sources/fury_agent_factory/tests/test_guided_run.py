import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from guided_run import GuidedRun,EXAMPLE
class GuidedContracts(unittest.TestCase):
 def test_recording_is_complete_and_checksum_bound(self):
  recording=json.loads((EXAMPLE/'recording.json').read_text())
  self.assertTrue(all(recording['verification'].values()))
  self.assertGreater(len(recording['calls']),1)
  for name,digest in recording['files'].items():self.assertEqual(hashlib.sha256((EXAMPLE/name).read_bytes()).hexdigest(),digest)
 def test_guided_has_no_model_calls_and_fresh_data(self):
  with tempfile.TemporaryDirectory() as tmp,patch('devteam.ROOT',Path(tmp)):
   # Use constructor's normal bounded local run storage, then remove test output.
   import shutil
   r=GuidedRun()
   try:
    d=r.snapshot();self.assertEqual(d['mode'],'recorded');self.assertEqual(d['calls'],[]);self.assertTrue(d['versions']);self.assertFalse(r.data.exists())
   finally:shutil.rmtree(r.root)
