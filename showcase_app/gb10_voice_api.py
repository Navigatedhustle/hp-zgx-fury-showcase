"""Existing local Kokoro service with GB10 stage control protections."""
import os

if os.getenv('FURY_PROFILE') != 'gb10':
    raise RuntimeError('This service requires the GB10 profile')

from atlas.tts_server import app
from showcase_app.gb10_security import StageRequestGuard

app.add_middleware(StageRequestGuard, limit=8192)
