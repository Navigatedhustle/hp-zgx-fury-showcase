"""Historical setup paths must fail before networking, process control or downloads."""
from pathlib import Path
import runpy
import sys
import pytest


@pytest.mark.parametrize('name', ['download_embed.py', 'download_models.py', 'download_kokoro.py',
                                  'download_vision.py', 'install_native.py', 'services.py'])
def test_legacy_model_setup_cannot_bypass_supported_launcher(monkeypatch, tmp_path, name):
    import huggingface_hub
    import requests
    import subprocess
    import urllib.request
    import os
    def forbidden(*args, **kwargs):
        raise AssertionError('Legacy setup attempted an external or process action')
    for module, key in [(huggingface_hub, 'snapshot_download'), (huggingface_hub, 'hf_hub_download'),
                        (requests, 'get'), (urllib.request, 'urlopen'), (urllib.request, 'urlretrieve'),
                        (subprocess, 'Popen'), (subprocess, 'run'), (os, 'kill'), (os, 'killpg')]:
        monkeypatch.setattr(module, key, forbidden)
    path = Path(__file__).resolve().parents[2] / 'build/sources/atlas-gpt-main/scripts' / name
    monkeypatch.syspath_prepend(str(path.parents[1]))
    monkeypatch.setattr(sys, 'argv', [str(path), 'start'])
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit, match=r'Use ./launch.sh setup'):
        runpy.run_path(str(path), run_name='__main__')
