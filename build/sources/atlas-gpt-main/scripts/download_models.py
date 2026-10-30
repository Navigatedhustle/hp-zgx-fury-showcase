"""Install-time downloads only; all inference uses local cached paths."""
import concurrent.futures
import json
import os
from pathlib import Path
os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
from huggingface_hub import hf_hub_download, snapshot_download

ROOT = Path(__file__).resolve().parents[1]
JOBS = {
    'brain': ('ggml-org/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-GGUF', ['NVIDIA-Nemotron-3.5-Lightning-30B-A3B-Q4_0.gguf']),
    'asr': ('nvidia/Nemotron-3.5-ASR-Streaming-0.6B', ['nemotron-3.5-asr-streaming-0.6b.q8_0.gguf']),
    'tts': ('nvidia/magpie_tts_multilingual_357m', ['magpie_tts_multilingual_357m.v2607.f16.gguf']),
    'codec': ('nvidia/nemo-nano-codec-22khz-1.89kbps-21.5fps', ['nemo_nano_codec_22khz_1.89kbps_21.5fps.decoder.f16.gguf']),
    'decisions': ('jaredpalmer/kev-4b', ['*.json', '*.safetensors', 'head.pt', '*.txt', 'README.md']),
    'decision_base': ('Qwen/Qwen3.5-4B-Base', ['*.json', '*.safetensors', '*.txt', 'LICENSE', 'README.md']),
}
def download(item):
    role, (repo, patterns) = item
    print(f'START {role} {repo}', flush=True)
    path = snapshot_download(repo, allow_patterns=patterns, token=False, max_workers=3)
    (ROOT/'models'/f'{role}.json').write_text(json.dumps({'repo':repo, 'path':path, 'patterns':patterns}, indent=2))
    print(f'READY {role} {path}', flush=True)
    return role
if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for future in concurrent.futures.as_completed([pool.submit(download,j) for j in JOBS.items()]):
            try: print('DONE', future.result(), flush=True)
            except Exception as exc: print('FAILED', repr(exc), flush=True)
