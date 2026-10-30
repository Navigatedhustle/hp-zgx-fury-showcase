# Example 06 — product + spec count-ups (variant A, cinematic)

## Input
```json
{"role":"solution","source":{"title":"ZGX Fury specifications","bullets":["748 GB coherent memory (496 GB LPDDR5X + 252 GB HBM3e)","Run up to 1T parameter models locally, 20 PF FP4","800 Gb/s ConnectX-8 SuperNIC","1,600 W, cooling built in"],"images":[{"key":"fury","alt":"HP ZGX Fury"}]}}
```

## Why
Product on the left in a tint frame, four runtime `.spec` rows on the right — the component already has the metrics, so the slide writes no CSS for them. Each spec is a big mono number that counts up as its row appears (data-count inside .appear — no JS needed). Numbers are the headline; label + one line explain them. Thousands separators come from H.fmt automatically.

## Output
<meta>{"pattern":"specs","title":"ZGX Fury: the data center, deskside","steps":4,"theme":"light","notes":["That is where <b>HP ZGX Fury</b> comes in — a data centre at deskside.","<b>748 GB coherent memory</b>, 252 GB of it HBM3e.","Up to <b>1T NVFP4 models</b> locally, 800 Gb/s networking.","<b>Cooling built in.</b> One tower."],"sources":"Specifications per HP.com."}</meta>
<html>
<div class="eyebrow">NVIDIA GB300 Grace Blackwell Ultra Desktop Superchip</div>
<h1 class="title">ZGX Fury: the data center, deskside</h1>
<div class="sub">Built for local <b>inference</b> — running whole models where the wafers are made.</div>
<div class="wrap">
  <figure class="figure"><img src="asset:fury" alt="HP ZGX Fury"><figcaption>HP ZGX Fury</figcaption></figure>
  <div class="specs">
    <div class="spec appear"><i data-icon="layers" class="icon"></i><div class="v num"><span data-count="748">0</span> GB</div><div><div class="k">Coherent memory</div><div class="d">496 GB LPDDR5X plus 252 GB HBM3e in one pool.</div></div></div>
    <div class="spec appear"><i data-icon="gauge" class="icon"></i><div class="v num"><span data-count="1">0</span>T</div><div><div class="k">Parameter models, run locally</div><div class="d">20 PF of FP4 performance — the whole model.</div></div></div>
    <div class="spec appear"><i data-icon="bolt" class="icon"></i><div class="v num"><span data-count="800">0</span> Gb/s</div><div><div class="k">ConnectX-8 SuperNIC</div><div class="d">Real-time fab data ingestion.</div></div></div>
    <div class="spec appear"><i data-icon="thermal" class="icon"></i><div class="v num"><span data-count="1600">0</span> W</div><div><div class="k">One tower</div><div class="d">Cooling built in. No facility redesign.</div></div></div>
  </div>
</div>
</html>
<css>
.wrap{flex:1;display:grid;grid-template-columns:1fr 600px;gap:48px;margin-top:28px;padding-bottom:12px;min-height:0}
.figure img{max-width:62%}
</css>
<script>
</script>
