import sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'build/sources/fury_agent_factory'))
from devteam_sandbox import execute


def test_near_cap_workspace_is_refused_before_running_generated_code(tmp_path):
    code=tmp_path/'code';code.mkdir();data=tmp_path/'data';data.mkdir()
    (code/'test_bound.py').write_text('raise RuntimeError("Generated code should not execute")')
    with (data/'existing.bin').open('wb') as f:f.truncate(64*1024**2+1)
    with pytest.raises(RuntimeError,match='workspace'):execute(code,data,'test')


def test_many_individually_small_files_cannot_fill_the_host_disk(tmp_path):
    code=tmp_path/'code';code.mkdir();data=tmp_path/'data';data.mkdir()
    (code/'test_bound.py').write_text('from pathlib import Path\nfor i in range(150):Path("/data/part"+str(i)).write_bytes(b"x"*1024**2)\n')
    with pytest.raises(RuntimeError,match='workspace'):execute(code,data,'test')
    assert sum(p.stat().st_size for p in data.iterdir())<160*1024**2
