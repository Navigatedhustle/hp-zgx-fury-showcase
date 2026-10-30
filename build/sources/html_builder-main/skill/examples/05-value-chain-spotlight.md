# Example 05 — value chain with spotlight (variant A, cinematic)

## Input
```json
{"role":"landscape","source":{"title":"AI use cases across the value chain","bullets":["Silicon design — AI design assistants, IP reuse, EDA acceleration","Simulation — surrogate models for TCAD and lithography","Fab operations — yield optimisation, predictive maintenance, visual inspection","Robotics — wafer-handling vision, AMHS routing","Supply chain — forecasting, risk and planning","Institutional memory — capture what senior engineers know"],"footer":"Data needs to stay local"}}
```

## Why
Six parallel use cases -> 3x2 grid of clickable cards. Each click step reveals one card; after the last card the takeaway callout lands (data-step 7). Clicking a card spotlights it (others dim) so the presenter can dive into whichever one the audience cares about — interaction that serves a real conversation, not decoration.

## Output
<meta>{"pattern":"cards","title":"AI creates value across the entire chain","steps":7,"theme":"light","notes":["What we just saw was <b>one use case</b>.","There is value across the <b>entire chain</b> — click through each.","<b>One requirement: the data stays local.</b>","<i>Click any card to spotlight it when the room asks.</i>"],"sources":""}</meta>
<html>
<div class="eyebrow">Where the value is</div>
<h1 class="title">AI creates value across the entire chain</h1>
<div class="sub"><b>Edge AI accelerates it</b> — at the source, where the data already is.</div>
<div class="chain" data-chain>
  <button class="card appear"><i data-icon="chip" class="icon"></i><h3>Silicon design</h3><p>AI design assistants, IP reuse, EDA acceleration.</p></button>
  <button class="card appear"><i data-icon="wave" class="icon"></i><h3>Simulation</h3><p>Surrogate models for TCAD and lithography, in hours not weeks.</p></button>
  <button class="card appear"><i data-icon="factory" class="icon"></i><h3>Fab operations</h3><p>Yield optimisation, predictive maintenance, visual inspection.</p></button>
  <button class="card appear"><i data-icon="robot" class="icon"></i><h3>Robotics &amp; automation</h3><p>Wafer-handling vision, AMHS routing, closed-loop tool control.</p></button>
  <button class="card appear"><i data-icon="truck" class="icon"></i><h3>Supply chain</h3><p>Visibility, forecasting, risk and planning.</p></button>
  <button class="card appear"><i data-icon="brain" class="icon"></i><h3>Institutional memory</h3><p>Capturing what your most experienced engineers know before they retire.</p></button>
</div>
<div class="callout appear" data-step="7"><b>Data needs to stay local</b> — which is exactly why the compute has to come to the data.</div>
</html>
<css>
.chain{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;margin-top:34px;flex:1}
.chain .card{padding:24px}
.chain h3{font-size:20px}
.callout{margin-top:24px}
</css>
<script>
let clear;
function mount(root){ clear = H.spotlight(H.$('[data-chain]', root), '.card'); }
function go(root, step){ if (step === 0 && clear) clear(); }
</script>
