"""GB10 gateway entry point with process-local offline enforcement."""
import os
import sys
from pathlib import Path

if os.getenv('FURY_PROFILE') != 'gb10':
    raise RuntimeError('This service requires the GB10 profile')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'build/sources/atlas-gpt-main'))
from atlas.offline_guard import install

install()
from showcase_app.gateway import app
app.openapi_url = None
app.router.routes[:] = [route for route in app.router.routes if getattr(route, 'path', '') not in ('/docs', '/redoc', '/openapi.json', '/docs/oauth2-redirect')]
