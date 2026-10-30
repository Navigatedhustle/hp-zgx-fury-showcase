"""Shared static experience chrome. No inference or external asset dependencies."""
from pathlib import Path
ASSETS=Path(__file__).parent/'assets'
def header(active='Showcase'):
 return '<a class="hp-skip" href="#main">Skip to content</a><header class="hp-shell"><a class="hp-home" href="http://localhost:8080"><img class="hp-logo" src="/showcase-assets/hp-logo-keyline.png" width="48" height="48" alt="HP"><span>HP ZGX Fury<br>demo experience</span></a><nav aria-label="Experience"><a href="http://localhost:8080/#catalog">Demos</a><a href="http://localhost:8080/#why">Why HP ZGX Fury</a><a href="http://localhost:8080/#concurrency">Shared AI</a><a href="http://localhost:8080/#presenter">Presenter guide</a><a href="http://localhost:8080/operator">Operator</a><button type="button" class="hp-theme" aria-label="Change color theme">Theme: system</button></nav></header>'
def document(title,body,script=''):
 return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+' · HP ZGX Fury</title><link rel="stylesheet" href="/showcase-assets/design.css"><link rel="stylesheet" href="/showcase-assets/hp-shell.css"><script defer src="/showcase-assets/hp-shell.js"></script><script defer src="/showcase-assets/device-navigation.js"></script></head><body>'+header()+body+('<script>'+script+'</script>' if script else '')+'</body></html>'
def footer():
 return '<footer class="footer"><span>HP ZGX Fury demo experience · Local inference</span><span>Fictional demonstration data · Review outputs before use</span></footer>'
