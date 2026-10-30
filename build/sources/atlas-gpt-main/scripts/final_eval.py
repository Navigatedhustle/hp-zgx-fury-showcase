"""Run final acceptance sequentially so benchmark jobs do not contend."""
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for module in ['scripts.voice_browser_qa','scripts.voice_browser_qa','scripts.evaluate_atlas','scripts.browser_qa','scripts.camera_qa','scripts.acceptance']:
 print('Checking',module,flush=True)
 subprocess.run([str(ROOT/'.venv/bin/python'),'-m',module],cwd=ROOT,timeout=150,check=True)
print('Final acceptance passed.',flush=True)
