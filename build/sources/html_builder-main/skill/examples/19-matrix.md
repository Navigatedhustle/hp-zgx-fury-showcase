# Example 19 — 2×2 positioning matrix (variant B, refined)

## Input
```json
{"role":"positioning","source":{"title":"Where deskside inference sits","table":[["","Data leaves the site","Data stays on site"],["Small models","Cloud API","Workstation GPU"],["Whole models","Rented cluster","ZGX Fury"]],"texts":["Only one quadrant does both"]}}
```

## Why
Two axes with four named positions is a matrix, not a table — drawing it as one lets the room see the empty corner before anyone explains it. `.matrix` supplies the quadrants and the axis labels; `.quad.hl` marks where we are, and it re-points its own colours on every theme, so no `.theme-navy` override is needed. Quadrants reveal one click at a time, ending on ours — with `data-anim="fade"`, because a quadrant that slides up would briefly poke out of the matrix's clipped box. No JavaScript.

## Output
<meta>{"pattern":"matrix","title":"One corner keeps the data and the whole model","steps":4,"theme":"light","notes":["Two questions decide every option: does the data leave, and does the whole model fit?","Click: a cloud API — fastest to start, and the data leaves.","Click: a rented cluster — the model fits, the data still leaves.","Click: a workstation GPU — data stays, but the model has to be cut down.","Click: <b>ZGX Fury</b> is the only corner that answers both."],"sources":"Positioning is illustrative."}</meta>
<html>
<div class="eyebrow">The choice</div>
<h1 class="title">One corner keeps the data and the whole model</h1>
<div class="matrix body-area">
  <div class="ax y"><span>Small models</span><span>Whole models</span></div>
  <div class="quads">
    <div class="quad appear" data-anim="fade" data-step="2">
      <div class="label">Rented cluster</div>
      <h3>The model fits</h3>
      <p>Whole models run, but wafer data still crosses the firewall and the meter never stops.</p>
    </div>
    <div class="quad hl appear" data-anim="fade" data-step="4">
      <div class="label">ZGX Fury</div>
      <h3>Both, deskside</h3>
      <p>748 GB coherent memory inside the fab. Nothing leaves, nothing is cut down.</p>
    </div>
    <div class="quad tint appear" data-anim="fade" data-step="1">
      <div class="label">Cloud API</div>
      <h3>Fastest to start</h3>
      <p>Nothing to install — and every prompt carries fab data off site.</p>
    </div>
    <div class="quad tint appear" data-anim="fade" data-step="3">
      <div class="label">Workstation GPU</div>
      <h3>The data stays</h3>
      <p>96 GB is the ceiling, so the model gets cut down until it fits.</p>
    </div>
  </div>
  <div class="ax x"><span>Data leaves the site</span><span>Data stays on site</span></div>
</div>
</html>
<css>
.matrix{margin-top:22px}
.quad{padding:20px 24px}
.quad p{font-size:14.5px}
</css>
<script>
</script>
