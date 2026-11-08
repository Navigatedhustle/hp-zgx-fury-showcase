"""Reject untrusted manifest structure before any download or path creation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import pytest


@pytest.mark.parametrize('change', [
    {'revision': 'main'}, {'directory': '../escape'},
    {'file_path': '../../escape.bin'}, {'file_algorithm': 'sha1'},
    {'file_hash': 'not-a-digest'},
])
def test_invalid_manifest_never_reaches_downloader(monkeypatch, tmp_path, change):
    path = Path(__file__).resolve().parents[1] / 'download-models.py'
    spec = importlib.util.spec_from_file_location('manifest_security_probe', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(sys, 'argv', ['download-models.py'])
    record = {'repo': 'fictional/fixture', 'revision': 'a' * 40, 'directory': 'fixture',
              'files': [{'path': 'fixture.bin', 'size': 3, 'algorithm': 'sha256', 'hash': hashlib.sha256(b'abc').hexdigest()}]}
    for key, value in change.items():
        if key.startswith('file_'):
            record['files'][0][key[5:]] = value
        else:
            record[key] = value
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/model-files.json').write_text(json.dumps([record]))
    import huggingface_hub
    def forbidden(*args, **kwargs):
        raise AssertionError('An invalid manifest reached the downloader')
    monkeypatch.setattr(huggingface_hub, 'hf_hub_download', forbidden)
    with pytest.raises((RuntimeError, ValueError), match='manifest|revision|digest|path|directory'):
        module.main()
    assert not (tmp_path / 'escape').exists()
    assert not (tmp_path / 'models').exists()
