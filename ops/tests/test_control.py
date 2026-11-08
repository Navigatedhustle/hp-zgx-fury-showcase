"""Lifecycle safety tests use fake proc records; they never signal real services."""
import importlib.util,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import control
from runtime import ROOT,COMPONENTS
class ControlTests(unittest.TestCase):
 def row(self,name='agent'):
  return {'pid':10,'pgid':10,'uid':control.os.getuid(),'cwd':str(ROOT),'exe':str((ROOT/'.venv/bin/python').resolve()),'start':'1234','args':COMPONENTS[name]['command']}
 def test_identity_rejects_unrelated_cwd_user_and_role(self):
  row=self.row();self.assertTrue(control.identity(row,'agent'))
  for changes in [{'cwd':'/tmp/unrelated'},{'uid':-1},{'args':['python','-m','uvicorn','unrelated:app']},{'args':COMPONENTS['slides']['command']}]:self.assertFalse(control.identity({**row,**changes},'agent'))
 def test_legacy_package_migration_requires_exact_application(self):
  row=self.row('gateway');row['args']=[a.replace('showcase_app.','showcase.') for a in row['args']];self.assertTrue(control.identity(row,'gateway'));self.assertFalse(control.identity(row,'operator'))
 def test_pid_reuse_is_not_an_identity_match(self):
  row=self.row();saved=control.fingerprint(row)
  with patch.object(control,'process',return_value={**row,'start':'9999'}):self.assertFalse(control.unchanged(saved))
 def test_duplicate_and_nonisolated_processes_are_refused(self):
  row=self.row()
  with patch.object(control,'processes',return_value=[row,row]):
   with self.assertRaises(RuntimeError):control.discover('agent')
  with patch.object(control,'processes',return_value=[{**row,'pgid':9}]):
   with self.assertRaises(RuntimeError):control.discover('agent')
 def test_unknown_port_owner_does_not_receive_signal(self):
  with patch.object(control,'discover',return_value=None),patch.object(control,'port_open',return_value=True),patch.object(control.os,'killpg') as group,patch.object(control.os,'kill') as single:
   with self.assertRaises(RuntimeError):control.stop_one('agent',{})
   group.assert_not_called();single.assert_not_called()
 def test_mixed_session_is_not_signalled(self):
  row=self.row()
  with patch.object(control,'discover',return_value=row),patch.object(control,'processes',return_value=[row,{**row,'pid':11,'cwd':'/tmp/other'}]),patch.object(control.os,'killpg') as group:
   with self.assertRaises(RuntimeError):control.stop_one('agent',{})
   group.assert_not_called()
 def test_gpu_unknown_is_distinct_from_free(self):
  with patch.object(control.subprocess,'run',side_effect=FileNotFoundError):self.assertFalse(control.gpu_status()['verified'])
if __name__=='__main__':unittest.main()


def test_stop_uses_pinned_process_descriptors_instead_of_group_signals():
 row=ControlTests().row();registry={}
 with patch.object(control,'discover',return_value=row),patch.object(control,'processes',return_value=[row]),patch.object(control,'process',return_value=row),patch.object(control,'unchanged',side_effect=[True]+[False]*30),patch.object(control,'save'),patch.object(control,'port_open',return_value=False),patch.object(control.os,'killpg') as group,patch.object(control.os,'kill') as single,patch.object(control.os,'pidfd_open',return_value=123) as opened,patch.object(control.signal,'pidfd_send_signal') as sent,patch.object(control.os,'close'):
  control.stop_one('agent',registry)
  group.assert_not_called();single.assert_not_called()
  opened.assert_called_once_with(row['pid'],0)
  sent.assert_called_once_with(123,control.signal.SIGTERM,None,0)



def test_identity_change_while_opening_pidfd_fails_before_any_signal():
 row=ControlTests().row();saved=control.fingerprint(row)
 with patch.object(control.os,'pidfd_open',return_value=123),patch.object(control.os,'close') as close,patch.object(control,'process',return_value={**row,'start':'9999'}),patch.object(control.signal,'pidfd_send_signal') as sent:
  import pytest
  with pytest.raises(RuntimeError,match='identity changed'):control.signal_saved([saved])
  sent.assert_not_called();close.assert_called_once_with(123)
