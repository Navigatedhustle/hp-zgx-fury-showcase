#!/usr/bin/env python3
"""Build the pinned MIT llama.cpp for GB10 without touching system software."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    pin = json.loads((ROOT / 'config/gb10-build.json').read_text())['llama_cpp']
    source = ROOT / '.tools/llama.cpp'
    if not source.exists():
        source.parent.mkdir(exist_ok=True)
        subprocess.run(['git', 'init', str(source)], check=True)
        subprocess.run(['git', '-C', str(source), 'fetch', '--depth', '1', pin['repo'], pin['revision']], check=True)
        subprocess.run(['git', '-C', str(source), 'checkout', '--detach', pin['revision']], check=True)
    actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != pin['revision']:
        raise RuntimeError('Existing llama.cpp revision differs; refusing to overwrite it')
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no']):
        raise RuntimeError('Pinned llama.cpp checkout has tracked modifications')
    archive = subprocess.check_output(['git', '-C', str(source), 'archive', '--format=tar', 'HEAD'])
    if hashlib.sha256(archive).hexdigest() != pin['source_tar_sha256']:
        raise RuntimeError('llama.cpp source archive SHA256 mismatch')
    if hashlib.sha256((source / 'LICENSE').read_bytes()).hexdigest() != pin['license_sha256']:
        raise RuntimeError('llama.cpp license SHA256 mismatch')
    build = source / 'build'
    subprocess.run(['cmake', '-S', str(source), '-B', str(build), '-DGGML_CUDA=ON',
                    '-DCMAKE_CUDA_ARCHITECTURES=' + pin['cuda_architectures'], '-DCMAKE_BUILD_TYPE=Release',
                    '-DLLAMA_BUILD_TESTS=OFF', '-DLLAMA_BUILD_EXAMPLES=OFF', '-DLLAMA_BUILD_APP=OFF',
                    '-DLLAMA_BUILD_UI=OFF', '-DLLAMA_OPENSSL=OFF'], check=True)
    subprocess.run(['cmake', '--build', str(build), '--parallel', str(pin['build_parallel']),
                    '--target', 'llama-server', 'llama-bench'], check=True)


if __name__ == '__main__':
    main()
