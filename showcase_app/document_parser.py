"""Bounded local parsers in a networkless, credential-free subprocess."""
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = None  # Resolve the owner's cache only in the parent, never inside the namespace.
WORKER = ROOT / 'ops/parse-worker.py'


def validate_container(path, mode):
    path = Path(path)
    limit = 8 if mode == 'translate' else 50 if mode == 'presentation' else 300
    if path.stat().st_size > limit * 1024**2:
        raise ValueError('Document exceeds the bounded parser size')
    suffix = path.suffix.lower()
    with path.open('rb') as stream:
        signature = stream.read(8)
    if suffix == '.pdf':
        if not signature.startswith(b'%PDF-'):
            raise ValueError('The content is not a PDF')
    elif suffix in ('.docx', '.pptx'):
        if not signature.startswith(b'PK\x03\x04'):
            raise ValueError('The content is not an Office document')
        maximum = 32 if mode == 'translate' else 256 if mode == 'presentation' else 1024
        member_maximum = maximum // 4
        with zipfile.ZipFile(path) as archive:
            items = archive.infolist()
            if len(items) > (2048 if mode != 'pptx' else 10000):
                raise ValueError('Office archive has too many entries')
            names = set()
            total = 0
            for item in items:
                name = item.filename
                parts = PurePosixPath(name)
                if (not name or parts.is_absolute() or '..' in parts.parts or '\\' in name
                        or ':' in name or name in names or (item.flag_bits & 1)
                        or ((item.external_attr >> 16) & 0o170000) == 0o120000):
                    raise ValueError('Unsafe Office archive entry')
                names.add(name)
                total += item.file_size
                if (total > maximum * 1024**2 or item.file_size > member_maximum * 1024**2
                        or item.file_size > max(1, item.compress_size) * 200):
                    raise ValueError('Office archive expansion exceeds parser bounds')
            expected = 'word/document.xml' if suffix == '.docx' else 'ppt/presentation.xml'
            if expected not in names or '[Content_Types].xml' not in names:
                raise ValueError('Office content does not match its type')
    elif suffix not in ('.txt', '.md'):
        raise ValueError('Unsupported document type')


def translation_pages(path):
    """Called only by the isolated worker after container validation."""
    suffix = path.suffix.lower()
    if suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted or len(reader.pages) > 25:
            raise ValueError('Use up to 25 unencrypted text pages')
        pages = [p.extract_text() or '' for p in reader.pages]
    elif suffix == '.docx':
        from docx import Document
        paragraphs = [p.text for p in Document(path).paragraphs if p.text.strip()]
        pages = ['\n\n'.join(paragraphs[i:i + 8]) for i in range(0, len(paragraphs), 8)]
    else:
        text = path.read_bytes().decode('utf-8-sig')
        if '\0' in text:
            raise ValueError('Binary content is not a text document')
        pages = text.split('\f') if '\f' in text else [text[i:i + 5000] for i in range(0, len(text), 5000)]
    if (not pages or len(pages) > 25 or sum(map(len, pages)) > 100000
            or any(not p.strip() or len(p) > 12000 for p in pages)):
        raise ValueError('Use up to 25 text pages and 100000 characters; scanned pages need OCR')
    return pages


def run_parser(mode, path, *, kind=None, hint=None, assets=None, renders=None):
    if mode not in ('translate', 'presentation', 'skin-logo', 'pptx', 'pptx-count') or not shutil.which('bwrap'):
        raise ValueError('The bounded local parser is unavailable')
    path = Path(path).resolve(strict=True)
    options = {'kind': kind, 'hint': hint}
    command = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session', '--clearenv',
               '--setenv', 'PATH', '/usr/bin', '--setenv', 'LANG', 'C.UTF-8',
               '--setenv', 'OPENBLAS_NUM_THREADS', '1', '--setenv', 'OMP_NUM_THREADS', '1',
               '--setenv', 'XDG_CACHE_HOME', '/tmp/cache', '--ro-bind', '/usr', '/usr']
    for library in ('/lib', '/lib64'):
        if Path(library).exists():
            command += ['--ro-bind', library, library]
    command += ['--symlink', 'usr/bin', '/bin', '--proc', '/proc', '--dev', '/dev', '--size', '67108864', '--tmpfs', '/tmp']
    for directory in (Path(sys.prefix), ROOT / 'showcase_app', ROOT / 'build/sources/html_builder-main/backend/app', Path('/etc/fonts')):
        if directory.exists():
            command += ['--ro-bind', str(directory), str(directory)]
    command += ['--ro-bind', str(WORKER), str(WORKER), '--ro-bind', str(path), '/input/document' + path.suffix.lower()]
    if assets is not None:
        assets = Path(assets).resolve()
        assets.mkdir(parents=True, exist_ok=True, mode=0o700)
        command += ['--bind', str(assets), '/output/assets']
        options['assets'] = '/output/assets'
    if renders is not None and Path(renders).is_dir():
        command += ['--ro-bind', str(Path(renders).resolve()), '/input/renders']
        options['renders'] = '/input/renders'
    command += [sys.executable, '-I', str(WORKER), mode, '/input/document' + path.suffix.lower(), json.dumps(options)]
    try:
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(command, stdout=output, stderr=subprocess.DEVNULL, timeout=45 if mode.startswith('pptx') else 15)
            if result.returncode or os.fstat(output.fileno()).st_size > 64 * 1024**2:
                raise ValueError('Document could not be safely parsed within its resource limits')
            output.seek(0)
            return json.load(output)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        raise ValueError('Document could not be safely parsed within its resource limits') from error


def parse_bytes(raw, suffix, mode='translate', **options):
    if suffix not in ('.pdf', '.docx', '.txt', '.md', '.svg', '.png', '.bin'):
        raise ValueError('Unsupported parser input')
    cache = CACHE or Path.home() / '.cache/fury-showcase/parsers'
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    cache.chmod(0o700)
    with tempfile.TemporaryDirectory(prefix='parse-', dir=cache) as folder:
        path = Path(folder) / ('document' + suffix)
        path.write_bytes(raw)
        path.chmod(0o600)
        return run_parser(mode, path, **options)
