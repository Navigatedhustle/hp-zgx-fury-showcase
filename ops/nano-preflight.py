#!/usr/bin/env python3
"""Read-only prerequisites for the pinned Ubuntu ARM64 / GB10 installer."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def inspect():
    checks = []
    def add(name, ok, fix=''):
        checks.append({'name': name, 'ok': bool(ok), 'fix': fix})
    add('Linux ARM64', platform.system() == 'Linux' and platform.machine() == 'aarch64', 'Use the tested Ubuntu ARM64 GB10 workstation.')
    release = {}
    try:
        release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    except OSError:
        pass
    add('Ubuntu 24.04', release.get('ID', '').strip('"') == 'ubuntu' and release.get('VERSION_ID', '').strip('"') == '24.04', 'This pinned Python/header build targets Ubuntu 24.04.')
    packages = 'git curl ca-certificates xz-utils build-essential cmake pkg-config python3.12 python3.12-venv bubblewrap apparmor-utils util-linux libsndfile1 libespeak-ng1 fonts-liberation fonts-noto-core'
    for name in ('git', 'curl', 'tar', 'xz', 'gcc', 'g++', 'make', 'cmake', 'pkg-config', 'apt-get', 'dpkg-deb', 'flock', 'systemd-run', 'aa-exec', 'nvidia-smi'):
        add(name, shutil.which(name), 'Install ordinary prerequisites: sudo apt-get install ' + packages if name != 'nvidia-smi' else 'Use the vendor-provisioned NVIDIA host; do not replace its driver through this installer.')
    if shutil.which('aa-exec'):
        policy = subprocess.run(['aa-exec', '-p', 'chrome', '--', '/usr/bin/true'], capture_output=True)
        add('Existing Chrome AppArmor browser policy', policy.returncode == 0, 'Ask the administrator for the narrowly scoped browser user-namespace policy described in docs/NANO_GUIDE.md; do not disable AppArmor.')
    python = shutil.which('python3.12')
    ready = bool(python and subprocess.run([python, '-c', 'import venv,ensurepip'], capture_output=True).returncode == 0)
    add('Python 3.12 with venv/ensurepip', ready, 'Install python3.12-venv through your administrator.')
    add('CUDA compiler', Path('/usr/local/cuda/bin/nvcc').is_file() or shutil.which('nvcc'), 'Use a host with its vendor-supported CUDA toolkit already configured; tested toolkit is 13.0.')
    try:
        name = subprocess.check_output(['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'], text=True, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        name = ''
    add('NVIDIA GB10', 'GB10' in name, 'Nano Collective needs a GB10 / 128 GB workstation. The full Fury profile is separate.')
    try:
        total = next(int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemTotal:'))
    except (OSError, StopIteration, ValueError):
        total = 0
    add('128 GB class unified memory', total >= 110 * 2**30, 'This is the full four-model Nano profile; it has no automatic smaller-model substitution.')
    add('200 GiB free installation space', shutil.disk_usage(ROOT).free >= 200 * 2**30, 'Selected weights are about 95.9 GiB, plus wheels, compiler/browser caches and outputs.')
    add('User systemd session', subprocess.run(['systemctl', '--user', 'show-environment'], capture_output=True).returncode == 0 if shutil.which('systemctl') else False, 'Log in as an ordinary desktop user or through its user session. Do not run install/launch with sudo.')
    return checks

def main():
    checks = inspect()
    for row in checks:
        print(('OK   ' if row['ok'] else 'FAIL ') + row['name'])
        if not row['ok']:
            print('     ' + row['fix'])
    return int(not all(row['ok'] for row in checks))

if __name__ == '__main__':
    sys.exit(main())
