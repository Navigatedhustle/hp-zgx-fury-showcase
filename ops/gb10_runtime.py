"""GB10 qualification commands, selected explicitly through the existing controller."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def components():
    quant = os.getenv('FURY_GB10_QUANT', 'Q8_0')
    quants = {'Q8_0': 'Q8_0', 'Q6_K': 'UD-Q6_K', 'Q4_K_XL': 'UD-Q4_K_XL'}
    if quant not in quants:
        raise ValueError('Unknown GB10 Qwen quant; no model substitution permitted')
    engine = '.tools/llama.cpp/build/bin/llama-server'
    definitions = [
        ('lead', 18100, 'gpt-oss-120b', 'gpt-oss-120b-GGUF/gpt-oss-120b-MXFP4.gguf', 32768, 2),
        ('text', 18000, 'Qwen3.6-35B-A3B', 'Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-' + quants[quant] + '.gguf', 49152, 3),
    ]
    result = {}
    for name, port, alias, filename, context, slots in definitions:
        model_path = str(ROOT / 'models' / filename)
        command = [engine, '--model', model_path, '--alias', alias, '--host', '127.0.0.1', '--port', str(port),
                   '--ctx-size', str(context), '--parallel', str(slots), '--n-gpu-layers', '999', '--flash-attn', 'on',
                   '--jinja', '--offline', '--metrics', '--no-webui', '--threads', '8', '--fit', 'off',
                   '--lazy-mode', 'off', '--kv-unified-per-slot', '16384', '--perf']
        if name == 'text':
            command += ['--mmproj', str(ROOT / 'models/Qwen3.6-35B-A3B-GGUF/mmproj-F16.gguf')]
        if os.getenv('FURY_GB10_NO_MMAP') == '1':
            # This pinned upstream replaces the historical --no-mmap with this spelling.
            command += ['--load-mode', 'none']
        result[name] = {'engine': 'llama.cpp', 'port': port, 'health': '/health', 'model': alias,
                        'model_path': model_path, 'command': command, 'startup_timeout': 900}
    return result


def environment():
    pins = json.loads((ROOT / 'config/gb10-build.json').read_text())
    return {**os.environ, **pins['offline_environment'], 'CUDA_VISIBLE_DEVICES': os.getenv('FURY_GPU', '0'),
            'PYTHONUNBUFFERED': '1', 'FURY_PROFILE': 'gb10'}
