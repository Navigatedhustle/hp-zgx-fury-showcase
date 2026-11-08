"""Exercise the production packager against private stage and brand sentinels."""
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ['state/stage/stage.local.json', 'state/stage/backup/S1.mp4',
           'state/stage/runs/session.json', 'state/brand/hp_logo.svg']


def test_stage_runtime_ignored_and_never_selected():
    selected = json.loads((ROOT / 'config/distribution-files.json').read_text())
    assert not any(Path(p).parts[0] == 'state' for p in selected)
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    assert not any(p.startswith('state/') for p in tracked)
    for name in PRIVATE:
        assert subprocess.run(['git', 'check-ignore', '-q', name], cwd=ROOT).returncode == 0
        assert name not in selected and name not in tracked


def test_actual_archives_exclude_private_stage_and_logo(tmp_path):
    (tmp_path / 'ops').mkdir()
    (tmp_path / 'config').mkdir()
    shutil.copyfile(ROOT / 'ops/package-release.py', tmp_path / 'ops/package-release.py')
    (tmp_path / 'public.txt').write_text('fictional public fixture\n')
    selected = ['public.txt']
    (tmp_path / 'config/distribution-files.json').write_text(json.dumps(selected))
    sha = hashlib.sha256((tmp_path / 'public.txt').read_bytes()).hexdigest()
    (tmp_path / 'SOURCE-SHA256SUMS').write_text(sha + '  public.txt\n')
    sentinel = b'PRIVATE_STAGE_SENTINEL'
    for name in PRIVATE:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(sentinel)
    subprocess.run([sys.executable, str(tmp_path / 'ops/package-release.py'), '--version', 'v0.0.0-gb10-test',
                    '--output', str(tmp_path / 'dist')], check=True, capture_output=True)
    for archive in (tmp_path / 'dist').glob('*.zip'):
        with zipfile.ZipFile(archive) as packed:
            assert len(packed.namelist()) == 1
            assert all('/state/' not in name and sentinel not in packed.read(name) for name in packed.namelist())
    for archive in (tmp_path / 'dist').glob('*.tar.gz'):
        with tarfile.open(archive) as packed:
            assert len(packed.getmembers()) == 1
            assert all('/state/' not in item.name and sentinel not in packed.extractfile(item).read() for item in packed.getmembers())
