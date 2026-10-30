# Example 12 — sources / references table (variant B, refined)

## Input
```json
{"role":"appendix","source":{"title":"References","bullets":["Advanced-node wafer cost $20k–$30k — EE Times and TrendForce estimates, 2025–26","25 wafers in a standard lot — SEMI standard","ZGX Fury specs — HP Z AI Stations official specifications (https://www.hp.com/us-en/workstations/ai-stations.html)","ZGX Fury price $90k–$220k — public retail estimates, 2026"]}}
```

## Why
Appendix slides are for trust: a clean two-column table, claim on the left (bold), source on the right (mono, linked when a URL exists). The title says why the slide exists. No steps, no decoration. Keep it inside the stage: at most ~8 rows at this size.

## Output
<meta>{"pattern":"references","title":"Where every number comes from","steps":0,"theme":"light","notes":["<b>Backup.</b> Links are live — open one if they challenge a number."],"sources":""}</meta>
<html>
<div class="eyebrow">Appendix</div>
<h1 class="title">Where every number comes from.</h1>
<div class="sub">All figures are public or clearly marked as estimates.</div>
<table class="table mt-m">
  <thead><tr><th>Claim</th><th>Source</th></tr></thead>
  <tbody>
    <tr><td class="c">Advanced-node wafer cost, $20k–$30k</td><td class="s">EE Times and TrendForce estimates, 2025–26</td></tr>
    <tr><td class="c">25 wafers in a standard lot</td><td class="s">SEMI standard 300 mm lot size</td></tr>
    <tr><td class="c">ZGX Fury — 748 GB coherent memory, 20 PF FP4</td><td class="s"><a href="https://www.hp.com/us-en/workstations/ai-stations.html" target="_blank" rel="noopener">HP Z AI Stations — official specifications</a></td></tr>
    <tr><td class="c">ZGX Fury price, $90k–$220k</td><td class="s">Public retail estimates, 2026. HP has not published pricing.</td></tr>
  </tbody>
</table>
</html>
<css>
.c{width:52%;font-weight:700}
.s{color:var(--mute);font-family:var(--mono);font-size:14px}
</css>
<script>
</script>
