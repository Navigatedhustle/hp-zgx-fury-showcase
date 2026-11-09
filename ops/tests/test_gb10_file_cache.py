"""Cache advice is limited to pinned regular GB10 weights, without writes."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('gb10_file_cache', ROOT / 'ops/gb10_file_cache.py')
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)


def fixture(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, 'ROOT', tmp_path)
    monkeypatch.setenv('FURY_PROFILE', 'gb10')
    (tmp_path / 'config').mkdir()
    folder = tmp_path / 'models/pinned'
    folder.mkdir(parents=True)
    (folder / 'weight.gguf').write_bytes(b'weights')
    (folder / 'README.md').write_text('notice')
    (tmp_path / 'config/model-files.json').write_text(json.dumps({'gb10': [
        {'directory': 'pinned', 'files': [{'path': 'weight.gguf', 'size': 7},
                                        {'path': 'README.md', 'size': 6}]}]}))
    calls = []
    monkeypatch.setattr(cache.os, 'posix_fadvise', lambda *args: calls.append(args))
    return folder, calls


def test_only_pinned_weights_are_advised_and_content_is_unchanged(monkeypatch, tmp_path):
    folder, calls = fixture(monkeypatch, tmp_path)
    result = cache.release_model_cache('pinned')
    assert result['files'] == ['weight.gguf'] and len(calls) == 1
    assert calls[0][1:] == (0, 0, cache.os.POSIX_FADV_DONTNEED)
    assert (folder / 'weight.gguf').read_bytes() == b'weights'
    assert not result['model_weights_released']


def test_symlink_and_wrong_size_are_refused(monkeypatch, tmp_path):
    folder, calls = fixture(monkeypatch, tmp_path)
    (folder / 'weight.gguf').write_bytes(b'wrong')
    with pytest.raises(ValueError, match='size/type'):
        cache.release_model_cache('pinned')
    (tmp_path / 'outside').write_bytes(b'weights')
    (folder / 'weight.gguf').unlink()
    (folder / 'weight.gguf').symlink_to(tmp_path / 'outside')
    with pytest.raises(ValueError, match='symlink'):
        cache.release_model_cache('pinned')
    assert not calls


def test_profile_and_unknown_directory_are_refused(monkeypatch, tmp_path):
    _, calls = fixture(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match='Unknown'):
        cache.release_model_cache('../outside')
    monkeypatch.setenv('FURY_PROFILE', 'gb300')
    with pytest.raises(RuntimeError, match='GB10'):
        cache.release_model_cache('pinned')
    assert not calls
