"""Pin selection protects the existing Fury download set and isolates GB10 assets."""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('download_models', ROOT / 'ops/download-models.py')
downloads = importlib.util.module_from_spec(spec)
spec.loader.exec_module(downloads)


def test_default_fury_records_unchanged():
    original = json.loads(subprocess.check_output(
        ['git', 'show', '369ba6d4cb0f02a9a5fc6925197bb8df4a0dcb65:config/model-files.json'], cwd=ROOT))
    assert downloads.selected_records() == original


@pytest.mark.parametrize('quant', ['Q8_0', 'Q6_K', 'Q4_K_XL', 'Q4_K_M'])
def test_gb10_quant_isolated_and_sha256_pinned(quant):
    records = downloads.selected_records('gb10', quant)
    assert len(records) == 4
    assert not any('DeepSeek' in m['repo'] or 'Wan' in m['repo'] or 'zipformer' in m['repo'] for m in records)
    qwen = next(m for m in records if m['directory'] == 'Qwen3.6-35B-A3B-GGUF')
    assert [f['quant'] for f in qwen['files'] if f.get('quant')] == [quant]
    assert any(f['path'] == 'mmproj-F16.gguf' for f in qwen['files'])
    assert all(f['algorithm'] == 'sha256' and len(f['hash']) == 64 for m in records for f in m['files'])


def test_unknown_directory_refused():
    with pytest.raises(ValueError, match='Unknown model directory'):
        downloads.selected_records('gb10', directory='missing')


def test_known_directory_does_not_download_other_lanes():
    records = downloads.selected_records('gb10', directory='gpt-oss-120b-GGUF')
    assert len(records) == 1
    assert records[0]['repo'] == 'ggml-org/gpt-oss-120b-GGUF'
