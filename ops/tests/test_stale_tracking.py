"""Stale records cannot authorize signals or duplicate an existing healthy app."""
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import control
from runtime import COMPONENTS,ROOT
class StaleTrackingTests(unittest.TestCase):
 def row(self):return {'pid':10,'pgid':10,'uid':control.os.getuid(),'cwd':str(ROOT),'exe':str((ROOT/'.venv/bin/python').resolve()),'start':'new','args':COMPONENTS['agent']['command']}
 def test_start_reconciles_stale_record_with_verified_existing_process(self):
  row=self.row();registry={'agent':{'leader':{**control.fingerprint(row),'start':'old'},'members':[]}}
  with tempfile.TemporaryDirectory() as folder,patch.object(control,'STATE',Path(folder)),patch.object(control,'discover',return_value=row),patch.object(control,'processes',return_value=[row]),patch.object(control,'ready',return_value=True),patch.object(control,'save'),patch.object(control.subprocess,'Popen') as launch:
   control.start_one('agent',registry)
   launch.assert_not_called();self.assertEqual(registry['agent']['leader']['start'],'new')
 def test_stop_does_not_signal_reused_pid_in_stale_member_record(self):
  row=self.row();registry={'agent':{'leader':{**control.fingerprint(row),'start':'old'},'members':[{**control.fingerprint(row),'start':'old'}]}}
  with patch.object(control,'discover',return_value=None),patch.object(control,'process',return_value=row),patch.object(control,'port_open',return_value=False),patch.object(control,'save'),patch.object(control.os,'kill') as kill,patch.object(control.os,'killpg') as group:
   control.stop_one('agent',registry);kill.assert_not_called();group.assert_not_called();self.assertNotIn('agent',registry)
