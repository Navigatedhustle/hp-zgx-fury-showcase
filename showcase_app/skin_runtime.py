"""Failure boundary: optional appearance must never stop core demo telemetry."""
import logging

try:
 from showcase_app import skin as service
except Exception:
 service=None


def snapshot():
 try:
  if service is not None:return service.snapshot()
 except Exception:
  pass
 # Unknown counters stay unknown; an appearance fault is not zero web traffic.
 return {'active':None,'sample_pack':None,'booth_palette':False,
         'public_web_lookups':public_count(),'revision':'default-unavailable','available':False}


def public_count():
 try:return service.public_count() if service is not None else None
 except Exception:return None


def initialize():
 try:
  if service is not None:service.initialize()
 except Exception:
  logging.getLogger(__name__).warning('Optional appearance storage unavailable; core demo continues')


async def shutdown():
 try:
  if service is not None:await service.shutdown()
 except Exception:
  logging.getLogger(__name__).warning('Optional appearance cleanup failed; core shutdown continues')
