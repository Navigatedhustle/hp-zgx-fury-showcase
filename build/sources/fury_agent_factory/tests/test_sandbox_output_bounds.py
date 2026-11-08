"""Generated output must not turn the coordinator into an unbounded pipe buffer."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_oversized_sandbox_output_does_not_fill_coordinator_memory():
    factory = Path(__file__).resolve().parents[1]
    probe = r'''
import json,tempfile
from pathlib import Path
from devteam_sandbox import execute
with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);code=root/'code';code.mkdir()
    (code/'backend.py').write_text("import os\ndef handle(request,path):\n os.write(1,b'x'*(64*1024**2))\n return {}\n")
    rejected=False
    try:execute(code,root/'data','api')
    except RuntimeError:rejected=True
    peak=next(int(line.split()[1]) for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmHWM:'))
    print(json.dumps({'rejected':rejected,'peak_rss_kib':peak}))
'''
    result = subprocess.run([sys.executable, '-c', probe], env={**os.environ, 'PYTHONPATH': str(factory)},
                            capture_output=True, text=True, timeout=20, check=True)
    measured = json.loads(result.stdout)
    assert measured['rejected']
    # A fresh stdlib coordinator is small. Capturing a 64 MiB text pipe exceeded
    # this bound before the fix; file-limited capture stays well below it.
    assert 0 < measured['peak_rss_kib'] < 96 * 1024, measured


def test_js_parser_does_not_inherit_host_node_options(monkeypatch, tmp_path):
    from devteam_sandbox import check_javascript
    (tmp_path / 'app.js').write_text('throw new Error("THIS MUST ONLY BE PARSED");')
    monkeypatch.setenv('NODE_OPTIONS', '--require=/fury-host-only-do-not-load.js')
    monkeypatch.setenv('FURY_FICTIONAL_CREDENTIAL', 'fictional environment canary')
    check_javascript(tmp_path)
