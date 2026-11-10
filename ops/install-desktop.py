#!/usr/bin/env python3
"""Install relocatable desktop entries for the selected, existing launcher."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def desktop_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'

def install(profile):
    applications = Path.home() / '.local/share/applications'
    applications.mkdir(parents=True, exist_ok=True)
    if profile == 'gb10':
        text = ('[Desktop Entry]\nVersion=1.0\nType=Application\nName=HP ZGX Nano Experience\n'
                'Comment=Launch the Nano Collective local AI experience center\n'
                'Exec=' + desktop_quote(ROOT / 'ops/nano-desktop.sh') + '\n'
                'Path=' + str(ROOT) + '\nIcon=' + str(ROOT / 'showcase_app/assets/hp-logo-keyline.png') + '\n'
                'Terminal=false\nCategories=Development;\nStartupNotify=false\n')
        target = applications / 'hp-zgx-nano-experience.desktop'
    else:
        text = ('[Desktop Entry]\nType=Application\nName=Fury AI Showcase\nComment=Launch local demonstration\nExec=' +
                desktop_quote(ROOT / 'launch.sh') + '\nTerminal=true\nCategories=Development;\n')
        target = applications / 'fury-showcase.desktop'
    target.write_text(text)
    target.chmod(0o755)
    print('Installed ' + str(target))
    if profile == 'gb10':
        desktop = Path.home() / 'Desktop'
        if shutil.which('xdg-user-dir'):
            result = subprocess.run(['xdg-user-dir', 'DESKTOP'], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                desktop = Path(result.stdout.strip())
        # On headless hosts keep the application entry without inventing a GUI directory.
        if desktop.is_dir() and desktop != Path.home():
            shortcut = desktop / 'HP-ZGX-Nano-Experience.desktop'
            shutil.copy2(target, shortcut)
            shortcut.chmod(0o755)
            if shutil.which('gio'):
                subprocess.run(['gio', 'set', str(shortcut), 'metadata::trusted', 'true'], capture_output=True)
            print('Installed ' + str(shortcut))
    return target

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', choices=['gb10', 'gb300'], default='gb10' if os.getenv('FURY_PROFILE') == 'gb10' else 'gb300')
    install(parser.parse_args().profile)

if __name__ == '__main__':
    main()
