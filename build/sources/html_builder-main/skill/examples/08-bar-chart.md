# Example 08 — data chart with narrative steps (variant A, cinematic)

## Input
```json
{"role":"evidence","source":{"title":"Adoption by quarter","chart":{"type":"bar","categories":["Q1","Q2","Q3","Q4","Q1'","Q2'"],"series":[{"name":"Deployed units","values":[120,180,260,410,640,910]}]},"texts":["Growth accelerated after the toolkit launch in Q3"]}}
```

## Why
Charts from the source are rebuilt as live SVG (H.chart.bars) — never pasted as images. Title states the insight, not the metric. Step 1 draws the first three quarters, step 2 the rest; step 3 reveals the annotation that explains the inflection, and highlights the post-launch bars. The KPI card on the right gives the one number to remember.

## Output
<meta>{"pattern":"chart","title":"Adoption tripled after the toolkit launched","steps":3,"theme":"light","auto":false,"notes":["Units deployed per quarter.","Click: steady, linear growth for three quarters.","Click: then the curve bends.","Click: that is the <b>toolkit launch</b>. Developers started on familiar ground."],"sources":"Illustrative data."}</meta>
<html>
<div class="eyebrow">Adoption</div>
<h1 class="title">Adoption tripled after the toolkit launched</h1>
<div class="split wide-right body-area">
  <div class="stack">
    <div class="card tint kpi appear" data-step="2">
      <div class="stat"><div class="v"><span data-count="3.5" data-decimals="1">0</span><small>×</small></div><div class="k">growth in two quarters after launch</div><div class="d">From 260 units in Q3 to 910 in Q2'.</div></div>
    </div>
    <div class="callout appear" data-step="3"><b>The inflection is the toolkit.</b> Developers could start on the tools they already use.</div>
  </div>
  <div class="chartbox">
    <div class="legend"><span><i></i>Deployed units per quarter</span></div>
    <div class="plot" data-plot></div>
  </div>
</div>
</html>
<css>
.chartbox{display:flex;flex-direction:column;gap:14px;min-height:0}
.stack{justify-content:center}
</css>
<script>
let chart;
const VALUES = [120, 180, 260, 410, 640, 910];
function mount(root){
  chart = H.chart.bars(H.$('[data-plot]', root), {labels:['Q1','Q2','Q3','Q4',"Q1'","Q2'"], values:VALUES, format:v => H.fmt.num(v)});
}
function go(root, step){
  chart.show(step === 0 ? 0 : step === 1 ? 3 : 6);
  H.$$('.chart .bar', root).forEach((b, i) => b.classList.toggle('muted', step >= 3 && i < 3));
  H.$$('[data-step]', root).forEach(n => n.classList.toggle('in', step >= +n.dataset.step));
  const k = H.$('[data-count]', root);
  if (step >= 2) H.countTo(k, 3.5, 900, x => H.fmt.num(x, 1)); else H.resetCount(k, x => H.fmt.num(x, 1));
}
</script>
