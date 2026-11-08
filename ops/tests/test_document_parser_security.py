"""Parser resource regressions use synthetic documents, never visitor media."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
from docx import Document
import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_docx_inflation_is_rejected_without_inflating_application_memory(tmp_path):
    base = io.BytesIO()
    Document().save(base)
    specimen = tmp_path / 'fictional-expanded.docx'
    with zipfile.ZipFile(base) as original, zipfile.ZipFile(specimen, 'w', compression=zipfile.ZIP_DEFLATED) as output:
        for name in original.namelist():
            if name != 'word/document.xml':
                output.writestr(name, original.read(name))
        with output.open('word/document.xml', 'w') as stream:
            stream.write(b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>')
            for _ in range(64):
                stream.write(b'a' * (1024 * 1024))
            stream.write(b'</w:t></w:r></w:p></w:body></w:document>')
    probe = r'''
import json,sys
from pathlib import Path
from showcase_app.workloads import read_document
rejected=False
try:read_document(Path(sys.argv[1]).read_bytes(),'fictional.docx')
except Exception:rejected=True
peak=next(int(x.split()[1]) for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmHWM:'))
print(json.dumps({'rejected':rejected,'peak_rss_kib':peak}))
'''
    result = subprocess.run([sys.executable, '-c', probe, str(specimen)], cwd=ROOT,
                            env={**os.environ, 'PYTHONPATH': str(ROOT)}, capture_output=True,
                            text=True, timeout=20, check=True)
    measured = json.loads(result.stdout)
    assert measured['rejected']
    assert 0 < measured['peak_rss_kib'] < 128 * 1024, measured


def test_legitimate_utf8_document_keeps_its_text():
    from showcase_app.workloads import read_document
    assert read_document('Fictional inspection 42. Café.'.encode(), 'fixture.txt') == ['Fictional inspection 42. Café.']


def test_parser_has_no_in_process_fallback_when_namespace_is_unavailable(monkeypatch):
    from showcase_app import document_parser
    from showcase_app.workloads import read_document
    monkeypatch.setattr(document_parser.shutil, 'which', lambda name: None)
    with pytest.raises(ValueError, match='unavailable'):
        read_document(b'Fictional text', 'fixture.txt')


def test_image_mime_cannot_select_a_different_decoder():
    import base64
    from PIL import Image
    from showcase_app.creative import reference_image
    raw = io.BytesIO()
    Image.new('RGB', (10, 10)).save(raw, 'GIF')
    with pytest.raises((ValueError, OSError)):
        reference_image('data:image/png;base64,' + base64.b64encode(raw.getvalue()).decode())


def test_svg_css_escape_cannot_hide_an_external_paint_url():
    from showcase_app.skin_research import sanitize_svg
    raw = b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0L1 1" fill="u\\72l(\\68ttps://127.0.0.1/image)"/></svg>'
    _, root = sanitize_svg(raw)
    assert 'fill' not in list(root)[0].attrib
