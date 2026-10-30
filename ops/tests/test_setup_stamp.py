"""A release UI upgrade must invalidate setup even when dependency locks are unchanged."""
import importlib.util,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('setup_stamp',Path(__file__).parents[1]/'setup-stamp.py');stamp=importlib.util.module_from_spec(spec);spec.loader.exec_module(stamp)
class SetupStampTests(unittest.TestCase):
 def test_editor_source_and_entrypoint_invalidate_without_lock_change(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(stamp,'ROOT',Path(folder)):
   for name in stamp.FILES:
    p=stamp.ROOT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('pinned fixture')
   front=stamp.ROOT/'build/sources/html_builder-main/frontend';(front/'src').mkdir(parents=True,exist_ok=True);(front/'index.html').write_text('entry')
   source=front/'src/main.tsx';source.write_text('old editor');old=stamp.signature();self.assertEqual(old,stamp.signature())
   source.write_text('new editor');new=stamp.signature();self.assertNotEqual(old,new)
   (front/'index.html').write_text('new shell');self.assertNotEqual(new,stamp.signature())
 def test_generated_outputs_do_not_invalidate_setup(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(stamp,'ROOT',Path(folder)):
   for name in stamp.FILES:
    p=stamp.ROOT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('pinned fixture')
   front=stamp.ROOT/'build/sources/html_builder-main/frontend';(front/'src').mkdir(parents=True,exist_ok=True);(front/'index.html').write_text('entry')
   before=stamp.signature();(front/'dist').mkdir();(front/'dist/generated.js').write_text('build output');self.assertEqual(before,stamp.signature())
if __name__=='__main__':unittest.main()
