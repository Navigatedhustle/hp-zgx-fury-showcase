import os
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def test_rotation_keeps_open_writer_identity_and_bounds_archives(tmp_path):
    from showcase_app.runtime_privacy import rotate_logs
    path=tmp_path/'owned.log'
    with path.open('ab',buffering=0) as writer:
        inode=os.fstat(writer.fileno()).st_ino
        for _ in range(5):
            writer.write(b'x'*4096)
            rotate_logs(tmp_path,maximum=1024,archives=3)
            assert path.stat().st_size==0
            assert path.stat().st_ino==inode
        writer.write(b'after rotation')
    assert path.read_bytes()==b'after rotation'
    assert len(list(tmp_path.glob('owned.log.*')))==3
    assert all(p.stat().st_size<=1024 and p.stat().st_mode&0o777==0o600 for p in tmp_path.iterdir())


def test_service_policy_sets_private_modes_and_a_hard_core_limit(tmp_path):
    code='from showcase_app.runtime_privacy import service_policy;import resource,os;from pathlib import Path;service_policy(Path('+repr(str(tmp_path))+'));print(resource.getrlimit(resource.RLIMIT_CORE));p=Path('+repr(str(tmp_path/'state/token'))+');p.write_text("fictional");print(oct(p.stat().st_mode&0o777))'
    r=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,check=True)
    assert r.stdout.splitlines()==['(0, 0)','0o600']
    assert (tmp_path/'state').stat().st_mode&0o777==0o700
