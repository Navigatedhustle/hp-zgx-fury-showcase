"""Release clean file-cache copies of pinned GB10 weights after model upload."""
import json
import os
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]


def memory():
    wanted = {'MemFree', 'MemAvailable', 'Cached', 'AnonPages', 'SwapFree'}
    return {line.split(':')[0]: int(line.split()[1]) * 1024
            for line in Path('/proc/meminfo').read_text().splitlines()
            if line.split(':')[0] in wanted}


def release_model_cache(directory, quant=None):
    """Advise only manifest-listed regular weight files; never evict model tensors."""
    if os.getenv('FURY_PROFILE') != 'gb10':
        raise RuntimeError('Weight cache advice requires the GB10 profile')
    entries = json.loads((ROOT / 'config/model-files.json').read_text())['gb10']
    entry = next((row for row in entries if row['directory'] == directory), None)
    if entry is None:
        raise ValueError('Unknown pinned GB10 model directory')
    before = memory()
    files = []
    for spec in entry['files']:
        if Path(spec['path']).suffix not in {'.gguf', '.safetensors', '.pth', '.pt'}:
            continue
        if spec.get('quant') and spec['quant'] != quant:
            continue
        path = ROOT / 'models' / directory / spec['path']
        expected = (ROOT / 'models').resolve() / directory / spec['path']
        if path.resolve(strict=True) != expected or not path.is_relative_to(ROOT / 'models'):
            raise ValueError('Pinned weight path must not traverse a symlink')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size != spec['size']:
                raise ValueError('Pinned weight size/type mismatch')
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
        finally:
            os.close(fd)
        files.append(spec['path'])
    return {'directory': directory, 'files': files, 'before': before, 'after': memory(),
            'model_weights_released': False, 'global_cache_setting_changed': False}
