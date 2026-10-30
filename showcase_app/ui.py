"""Shared static booth chrome. No inference or external asset dependencies."""
from pathlib import Path
ASSETS=Path(__file__).parent/'assets'
def header(active='Showcase'):
 return '''<a class="sr-only" href="#main">Skip to content</a><header class="masthead"><a class="brand" href="http://localhost:8080"><span class="hp-lockup"><img src="/showcase-assets/hp.svg" alt="HP"></span><span><strong>HP ZGX Fury</strong><small>powered by NVIDIA GB300</small></span></a><nav class="topnav" aria-label="Showcase"><a class="text-link" href="http://localhost:8080">All experiences</a><a class="text-link" href="http://localhost:8080/operator">Live on Fury ↗</a></nav><div class="nvidia-lockup"><span>AI WEEK<br>FRANKFURT</span><img src="/showcase-assets/nvidia.svg" alt="NVIDIA"></div></header>'''
def document(title,body,script=''):
 return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+' · HP ZGX Fury</title><link rel="stylesheet" href="/showcase-assets/design.css"></head><body>'+header()+body+('<script>'+script+'</script>' if script else '')+'</body></html>'
def footer():
 return '<footer class="footer"><span>HP ZGX Fury powered by NVIDIA GB300 · Inference on Fury host</span><span>Frankfurt access requires WAN · Synthetic demonstration data</span></footer>'
