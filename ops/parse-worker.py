#!/usr/bin/env python3
"""Trusted parser entrypoint; only run through document_parser's namespace."""
import base64
import json
from pathlib import Path
import resource
import sys

resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
resource.setrlimit(resource.RLIMIT_CPU, (30 if len(sys.argv) > 1 and sys.argv[1].startswith('pptx') else 10,) * 2)
resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024**2,) * 2)
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'build/sources/html_builder-main/backend'))


def main():
    from showcase_app.document_parser import validate_container, translation_pages
    mode, filename = sys.argv[1:3]
    options = json.loads(sys.argv[3])
    path = Path(filename)
    if mode == 'translate':
        validate_container(path, mode)
        return translation_pages(path)
    if mode == 'presentation':
        validate_container(path, mode)
        from app import docs
        text = docs.extract(path)
        if len(text.pages) > 500:
            raise ValueError('Too many document pages')
        images = docs.pictures(path)
        return {'pages': text.pages, 'truncated': text.truncated,
                'pictures': [base64.b64encode(p).decode() for p in images]}
    if mode == 'skin-logo':
        if path.stat().st_size > 2 * 1024**2:
            raise ValueError('Logo is too large')
        from showcase_app.skin_research import _logo_asset
        result = _logo_asset(path.read_bytes(), options['kind'], options.get('hint'))
        result['data'] = base64.b64encode(result['data']).decode()
        result['png'] = base64.b64encode(result['png']).decode()
        return result
    if mode == 'pptx':
        validate_container(path, mode)
        from app.ingest.pptx_parse import _parse_pptx
        return _parse_pptx(path, Path(options['assets']), Path(options['renders']) if options.get('renders') else None).model_dump()
    if mode == 'pptx-count':
        validate_container(path, 'pptx')
        from pptx import Presentation
        from app.ingest.pptx_parse import is_hidden
        return {'count': sum(1 for slide in Presentation(path).slides if not is_hidden(slide))}
    raise ValueError('Unsupported parser mode')


if __name__ == '__main__':
    try:
        print(json.dumps(main(), ensure_ascii=True))
    except Exception:
        # No document content, names, images, parser tracebacks or credentials in logs.
        sys.exit(2)
