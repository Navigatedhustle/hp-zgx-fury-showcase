"""Runtime identity checks using explicit filesystem/metadata fixtures."""
import tempfile,unittest
from pathlib import Path
from devteam_routes import runtime_identity
class RuntimeIdentityTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.folder=self.root/'models/DeepSeek-V4-Flash-NVFP4';self.meta=self.folder/'.cache/huggingface/download/config.json.metadata';self.meta.parent.mkdir(parents=True);self.meta.write_text('fixture-immutable-sha\nfixture-etag\n');self.pins={'nvidia/DeepSeek-V4-Flash-NVFP4':{'revision':'fixture-immutable-sha'}};self.record={'id':'fury-lead','root':str(self.folder),'max_model_len':16384}
 def identity(self,record=None):return runtime_identity('fury-lead',record or self.record,self.pins,self.root)
 def test_alias_root_and_pin_must_all_agree(self):
  r=self.identity();self.assertTrue(r['identity_verified']);self.assertEqual(r['name'],'DeepSeek V4 Flash');self.assertEqual(r['max_context'],16384);self.assertNotIn(str(self.root),str(r))
 def test_wrong_checkpoint_or_alias_is_not_confirmed(self):
  self.assertFalse(self.identity({**self.record,'root':str(self.root/'other-model')})['identity_verified']);self.assertFalse(self.identity({**self.record,'id':'different-model'})['identity_verified'])
 def test_wrong_revision_is_not_confirmed(self):
  self.meta.write_text('different-revision\n');self.assertFalse(self.identity()['identity_verified'])
 def test_missing_metadata_or_runtime_stays_unknown(self):
  self.meta.unlink();self.assertIsNone(self.identity()['identity_verified']);self.assertIsNone(runtime_identity('fury-lead',None,self.pins,self.root)['identity_verified'])
