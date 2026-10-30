# Example 11 — before / after comparison with toggle (variant A, cinematic)

## Input
```json
{"role":"comparison","source":{"title":"Cloud vs on-prem inference","table":[["","Cloud API","ZGX Fury on-prem"],["Data location","Leaves the fab","Stays in the fab"],["Cost model","Metered per token","Fixed capex"],["Latency","Network round-trip","Local"],["Setup","Security review, contracts","Days"]]}}
```

## Why
A comparison table becomes a two-state toggle the presenter flips while talking: rows keep their positions so the eye sees exactly what changed. The ledger itself is the runtime's `.rows`/`.crow`, so the only slide CSS left is the flip. Step 1 shows "Today", step 2 flips to "With ZGX Fury" and the summary callout lands. The audience can flip it back themselves with the segmented control. Changed values animate.

## Output
<meta>{"pattern":"compare","title":"Same workload. Different rules.","steps":2,"theme":"light","auto":false,"notes":["Four things change when inference moves inside the fab.","Click: today, with a cloud API.","Click: the same workload on ZGX Fury. <b>Data stays, cost is fixed.</b>"],"sources":""}</meta>
<html>
<div class="eyebrow">Cloud API vs. ZGX Fury</div>
<h1 class="title">Same workload. Different rules.</h1>
<div class="body-area">
  <div class="row between">
    <div class="seg" data-mode><button class="btn" data-v="cloud">Today · Cloud API</button><button class="btn" data-v="fury">With ZGX Fury</button></div>
    <div class="pill" data-pill>Today</div>
  </div>
  <div class="rows mt-m">
    <div class="crow"><div class="k">Data location</div><div class="val" data-cloud="Leaves the fab" data-fury="Stays in the fab"></div></div>
    <div class="crow"><div class="k">Cost model</div><div class="val" data-cloud="Metered per token" data-fury="Fixed, one capex line"></div></div>
    <div class="crow"><div class="k">Latency</div><div class="val" data-cloud="Network round-trip" data-fury="Local, same room"></div></div>
    <div class="crow"><div class="k">Time to start</div><div class="val" data-cloud="Security review + contracts" data-fury="Days"></div></div>
  </div>
  <div class="callout appear mt-auto" data-final><b>Nothing about the model changed.</b> Only where it runs — and that changes everything above.</div>
</div>
</html>
<css>
.crow .val.flip{transform:translateY(6px)}
</css>
<script>
let setMode;
function render(root, mode){
  H.$$('.val', root).forEach(v => {
    v.classList.add('flip');
    setTimeout(() => { v.textContent = v.dataset[mode]; v.classList.toggle('bad', mode === 'cloud'); v.classList.toggle('ok', mode === 'fury'); v.classList.remove('flip'); }, H.reduced() ? 0 : 140);
  });
  H.$('[data-pill]', root).textContent = mode === 'cloud' ? 'Today' : 'With ZGX Fury';
  H.$('[data-pill]', root).className = 'pill ' + (mode === 'cloud' ? 'alert' : 'good');
}
function mount(root){
  setMode = H.segmented(H.$('[data-mode]', root), v => render(root, v));
  H.$$('.val', root).forEach(v => { v.textContent = v.dataset.cloud; });
}
function go(root, step){
  H.$('.rows', root).classList.toggle('dim', step === 0);
  setMode(step >= 2 ? 'fury' : 'cloud');
  H.$('[data-final]', root).classList.toggle('in', step >= 2);
}
</script>
