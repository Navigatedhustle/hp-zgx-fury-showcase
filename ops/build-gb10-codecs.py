#!/usr/bin/env python3
"""Download SHA256-pinned permissive recorder headers and build locally."""
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
folder = ROOT / '.tools/stage-codecs'
pins = json.loads((ROOT / 'config/gb10-build.json').read_text())['stage_recorder_sources']
for source in pins:
    target = folder / source['name']
    target.mkdir(parents=True, exist_ok=True)
    for spec in source['files']:
        path = target / spec['path']
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != spec['sha256']:
            data = urllib.request.urlopen(spec['url'], timeout=60).read()
            if hashlib.sha256(data).hexdigest() != spec['sha256']:
                raise RuntimeError('Recorder source checksum mismatch')
            path.write_bytes(data)
implementations = []
for name, header, macro in [('h264', 'minih264e.h', 'MINIH264_IMPLEMENTATION'), ('mp4', 'minimp4.h', 'MINIMP4_IMPLEMENTATION'), ('png', 'stb_image.h', 'STB_IMAGE_IMPLEMENTATION')]:
    path = folder / (name + '.c')
    path.write_text('#define ' + macro + '\n#define STBI_ONLY_PNG\n#include \"' + header + '\"\n')
    implementations.append(str(path))
subprocess.run(['cc', '-O3', '-std=c99', '-D_POSIX_C_SOURCE=200809L', '-DH264E_MAX_THREADS=0', '-I' + str(folder / 'minih264'), '-I' + str(folder / 'minimp4'),
                '-I' + str(folder / 'stb'), str(ROOT / 'ops/gb10-video-encode.c'), *implementations, '-lm', '-o', str(folder / 'encode')], check=True)
print('Built local H.264 recorder with SHA256-verified permissive headers')
