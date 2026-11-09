"""Release unused process-local load/render buffers on unified-memory GB10."""
import ctypes
import gc
from pathlib import Path


def snapshot():
    fields = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    return {'rss_bytes': int(fields.get('VmRSS', '0 kB').split()[0]) * 1024,
            'swap_bytes': int(fields.get('VmSwap', '0 kB').split()[0]) * 1024,
            'available_bytes': next(int(line.split()[1]) * 1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))}


def release_unused_buffers():
    import torch
    before = snapshot()
    gc.collect()
    if torch.cuda.is_initialized():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
    ctypes.CDLL(None).malloc_trim(0)
    return {'before': before, 'after': snapshot(), 'model_weights_released': False}
