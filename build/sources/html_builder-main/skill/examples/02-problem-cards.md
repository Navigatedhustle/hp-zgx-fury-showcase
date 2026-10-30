# Example 02 — four problem cards (variant B, refined)

## Input
```json
{"role":"problem","source":{"title":"Challenges","bullets":["Data control: recipes, traces and metrology are IP and can't leave the fab","Power: AI-ready data-centre power takes quarters and costs tens of millions per MW","Memory: fab-sized workstations hold 48 GB; a 70B model uses 35 GB of it","Thermal: whatever enters the cleanroom must cool itself"]}}
```

## Why
The source title "Challenges" is a topic, not a message — rewrite it as an assertion. Four parallel items -> 2x2 grid of equal cards. Each card: icon, one-word label in blue (the scannable layer), a headline (the claim), one supporting sentence. Cards reveal one per step so the presenter controls pacing. No JS needed: `.appear` elements reveal in order automatically.

## Output
<meta>{"pattern":"cards","title":"Fabs can't run AI where the data lives","steps":4,"theme":"light","notes":["Semiconductor manufacturers <b>cannot run AI inside the fab today</b> — four reasons.","<b>Data control.</b> Recipes are trade secrets. The compute has to come inside the fab.","<b>Power.</b> A data centre takes quarters and millions.","<b>Memory.</b> 48 GB workstations — a 70B model eats 35 of it.","<b>Thermal.</b> Whatever we bring inside has to cool itself."],"sources":""}</meta>
<html>
<div class="eyebrow">The constraint</div>
<h1 class="title">Semiconductor fabs can’t run AI where the data lives</h1>
<div class="pcards">
  <div class="card row appear"><i data-icon="lock" class="icon l"></i><div><div class="plab">Data control</div><h3>Your crown jewels cannot leave the fab</h3><p>Recipes, traces and metrology are the IP. So the compute has to come to the data.</p></div></div>
  <div class="card row appear"><i data-icon="bolt" class="icon l"></i><div><div class="plab">Power</div><h3>AI-ready power is measured in quarters</h3><p>Data-centre capacity costs tens of millions per megawatt and lands long after the decision.</p></div></div>
  <div class="card row appear"><i data-icon="data" class="icon l"></i><div><div class="plab">Memory</div><h3>Fab-sized workstations hold 48 GB</h3><p>A 70B model takes 35 of that. What’s left is one tool, one window.</p></div></div>
  <div class="card row appear"><i data-icon="thermal" class="icon l"></i><div><div class="plab">Thermal</div><h3>Your cleanroom shouldn’t become a chiller plant</h3><p>No facility water, no CDUs, no HVAC redesign in your most expensive real estate.</p></div></div>
</div>
</html>
<css>
.pcards{display:grid;grid-template-columns:1fr 1fr;gap:26px;margin-top:38px;flex:1;padding-bottom:26px}
.pcards .card{padding:28px 32px}
.pcards h3{font-size:20px;margin-bottom:8px}
.pcards p{font-size:16px}
</css>
<script>
</script>
