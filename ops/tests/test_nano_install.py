"""Installer and portable desktop behavior without downloads or model startup."""
import asyncio
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'ops' / (name + '.py'))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_check_only_never_enters_setup(tmp_path):
    (tmp_path / 'ops').mkdir()
    shutil.copy2(ROOT / 'install.sh', tmp_path / 'install.sh')
    (tmp_path / 'ops/nano-preflight.py').write_text('print("Checked prerequisites")\n')
    # No launch.sh exists: an attempted setup would fail this check-only run.
    result = subprocess.run(['bash', 'install.sh', '--check'], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.strip() == 'Checked prerequisites'
    assert not (tmp_path / '.venv').exists()


def test_installer_stops_before_setup_when_prerequisites_fail(tmp_path):
    (tmp_path / 'ops').mkdir()
    shutil.copy2(ROOT / 'install.sh', tmp_path / 'install.sh')
    (tmp_path / 'ops/nano-preflight.py').write_text('raise SystemExit(7)\n')
    (tmp_path / 'launch.sh').write_text('#!/bin/sh\ntouch unexpected-setup\n')
    (tmp_path / 'launch.sh').chmod(0o755)
    result = subprocess.run(['bash', 'install.sh'], cwd=tmp_path, capture_output=True)
    assert result.returncode == 7 and not (tmp_path / 'unexpected-setup').exists()


def test_headless_install_prepares_but_does_not_launch_models(tmp_path):
    (tmp_path / 'ops').mkdir()
    shutil.copy2(ROOT / 'install.sh', tmp_path / 'install.sh')
    (tmp_path / 'ops/nano-preflight.py').write_text('pass\n')
    (tmp_path / 'launch.sh').write_text('#!/bin/sh\nprintf "%s:%s" "$FURY_PROFILE" "$*" > setup-call\n')
    (tmp_path / 'launch.sh').chmod(0o755)
    result = subprocess.run(['bash', 'install.sh', '--no-desktop'], cwd=tmp_path, capture_output=True)
    assert result.returncode == 0
    assert (tmp_path / 'setup-call').read_text() == 'gb10:setup'
    assert not (tmp_path / '.venv').exists()


def test_portable_desktop_entry_handles_spaces_without_a_shell(monkeypatch, tmp_path):
    desktop = module('install-desktop')
    installation = tmp_path / 'Nano Demo 100%'
    installation.mkdir()
    home = tmp_path / 'new-user'
    (home / 'Desktop').mkdir(parents=True)
    monkeypatch.setattr(desktop, 'ROOT', installation)
    monkeypatch.setattr(desktop.Path, 'home', classmethod(lambda cls: home))
    monkeypatch.setattr(desktop.shutil, 'which', lambda name: None)
    entry = desktop.install('gb10')
    text = entry.read_text()
    assert 'Exec="' + str(installation).replace('%', '%%') + '/ops/nano-desktop.sh"' in text
    assert 'Terminal=false' in text and '/home/demo/' not in text
    assert (home / 'Desktop/HP-ZGX-Nano-Experience.desktop').read_text() == text
    assert entry.stat().st_mode & 0o111
    if shutil.which('desktop-file-validate'):
        subprocess.run(['desktop-file-validate', str(entry)], check=True)


def test_browser_launcher_has_a_headless_manual_url_fallback(monkeypatch, capsys):
    browser = module('open-nano-browser')
    monkeypatch.setattr(browser, 'browser_environment', lambda: {})
    browser.main()
    assert 'http://127.0.0.1:18808/free' in capsys.readouterr().out


def test_public_robot_is_used_without_a_private_override(monkeypatch, tmp_path):
    monkeypatch.setenv('FURY_PROFILE', 'gb10')
    monkeypatch.setenv('FURY_STAGE_RUNTIME', '1')
    import sys
    sys.path.insert(0, str(ROOT / 'ops'))
    from showcase_app import stage_api
    monkeypatch.setattr(stage_api, 'ROOT', tmp_path)
    assets = tmp_path / 'showcase_app/assets'
    assets.mkdir(parents=True)
    (assets / 'nano-agent.png').write_bytes(b'public decorative artwork')
    response = asyncio.run(stage_api.agent_art())
    assert Path(response.path) == assets / 'nano-agent.png' and response.media_type == 'image/png'
