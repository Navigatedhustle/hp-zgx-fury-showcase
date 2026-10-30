"""Verify the exact final source with cold models, then freeze-ready evidence."""
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for module in ['scripts.cold_check','scripts.interaction_qa','scripts.space_qa','scripts.browser_qa','scripts.camera_qa']:
 print('FINAL',module,flush=True)
 subprocess.run([str(ROOT/'.venv/bin/python'),'-m',module],cwd=ROOT,timeout=250,check=True)
subprocess.run([str(ROOT/'.venv/bin/python'),'-m','pytest','-q','--junitxml=eval/test-results.xml'],cwd=ROOT,timeout=30,check=True)
subprocess.run([str(ROOT/'.venv/bin/python'),'-m','scripts.render_report'],cwd=ROOT,timeout=15,check=True)
print('Exact final source acceptance passed.',flush=True)
