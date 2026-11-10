#!/usr/bin/env python3
"""Open the cached, sandboxed browser without relying on a system default app."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / '.cache/ms-playwright')
sys.path.insert(0, str(ROOT))

def browser_environment():
    spec = importlib.util.spec_from_file_location('nano_desktop_environment', ROOT / 'ops/gb10-stage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {**os.environ, **module.desktop_environment()}

def main():
    env = browser_environment()
    if not env.get('DISPLAY'):
        print('No local desktop detected. Open http://127.0.0.1:18808/free on the Nano.')
        return
    try:
        windows = subprocess.run(['wmctrl', '-l'], env=env, text=True, capture_output=True, check=True)
        for row in windows.stdout.splitlines():
            fields = row.split(None, 3)
            if len(fields) == 4 and fields[3].startswith('HP ZGX Nano · Free Mode'):
                subprocess.run(['wmctrl', '-ia', fields[0]], env=env, check=True)
                return
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    from playwright.sync_api import sync_playwright
    from showcase_app.gb10_miniapp import chromium_wrapper
    with sync_playwright() as playwright:
        executable = Path(playwright.chromium.executable_path)
    if not executable.is_file():
        raise RuntimeError('Cached Chromium is missing. Rerun ./install.sh.')
    folder = ROOT / 'state/stage'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'desktop-browser.log').open('ab') as log:
        subprocess.Popen([str(chromium_wrapper(executable)), '--user-data-dir=' + str(folder / 'free-browser-profile'),
            '--app=http://127.0.0.1:18808/free', '--no-first-run', '--no-default-browser-check',
            '--disable-background-networking', '--disable-component-update', '--disable-sync',
            '--proxy-server=http://127.0.0.1:9', '--proxy-bypass-list=127.0.0.1;localhost',
            '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1, EXCLUDE [::1]',
            '--autoplay-policy=no-user-gesture-required'], cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=log, start_new_session=True, close_fds=True)

if __name__ == '__main__':
    main()
