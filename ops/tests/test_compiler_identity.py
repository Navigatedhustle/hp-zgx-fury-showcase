"""Nested compiler groups need exact cache, executable and engine ancestry."""
import sys,os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import control as c

def fixture(tmp_path):
 leader={'pid':100,'uid':os.getuid(),'sid':100,'pgid':100,'start':'1','cwd':str(c.ROOT),'exe':'unused','args':[]}
 engine={**leader,'pid':101,'ppid':100,'start':'2','exe':str((c.ROOT/'.deepseek-venv/bin/python').resolve()),'args':['VLLM::EngineCore']}
 compiler={**leader,'pid':102,'ppid':101,'pgid':102,'start':'3','cwd':str(tmp_path/'.cache/flashinfer/0.7.0/103a/cached_ops/fused_moe_trtllm_sm100'),'exe':str(Path('/usr/bin/g++').resolve())}
 return leader,engine,compiler

def test_nested_compiler_group_is_scoped_by_session_and_live_engine(tmp_path):
 leader,engine,compiler=fixture(tmp_path)
 with patch.dict(os.environ,{'FLASHINFER_WORKSPACE_BASE':str(tmp_path)}):
  assert c.session_member_verified(compiler,leader,[leader,engine,compiler],'lead')
  for change in [{'sid':999},{'uid':-1},{'cwd':'/tmp/unrelated'},{'exe':'/bin/unrelated'},{'ppid':999},{'start':'0'}]:
   bad={**compiler,**change};assert not c.session_member_verified(bad,leader,[leader,engine,bad],'lead')
