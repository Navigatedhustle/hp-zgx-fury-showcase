# Example 07 — "what fits" explorer (variant A, cinematic)

## Input
```json
{"role":"proof","source":{"title":"Memory capacity comparison","table":[["Configuration","Memory"],["Typical accelerator","48 GB"],["ZGX Nano","128 GB"],["ZGX Fury","748 GB"],["Two Fury, paired","1,496 GB"]],"texts":["Model footprints at FP4: 70B ≈ 45 GB, 200B ≈ 120 GB, 1T ≈ 620 GB, 2T ≈ 1,240 GB"]}}
```

## Why
A capacity table is dull; a "pick a model, see what it fits in" explorer makes the same data self-evident. Each step selects the next model size so the presenter can walk up the ladder; the audience can also click any preset. Bars that overflow turn red-striped and say DOES NOT FIT. Left column keeps the argument in words so the slide still reads without interaction.

## Output
<meta>{"pattern":"explorer","title":"Four barriers. One box.","steps":4,"theme":"light","auto":false,"notes":["Back to the <b>four challenges</b>.","Step the gauges: <b>70B</b> barely fits a typical card.","<b>200B</b> fits Nano. <b>1T</b> needs Fury. <b>2T</b> needs a pair.","<i>Click any model button to answer 'what about X?'</i>"],"sources":"Model footprints are approximate weights plus KV headroom at NVFP4. Not vendor-published."}</meta>
<html>
<div class="eyebrow">HP ZGX Fury</div>
<h1 class="title">Four barriers. One box.</h1>
<div class="wrap">
  <div class="bars">
    <div class="bar"><span class="dot">1</span><div><h3>Data control <i>→ it never leaves the fab</i></h3><p>Inference runs inside the fab boundary. No egress, no third party.</p></div></div>
    <div class="bar"><span class="dot">2</span><div><h3>Memory <i>→ the whole fleet in one window</i></h3><p>252 GB of HBM3e — a 70B model and a million tokens of context, resident.</p></div></div>
    <div class="bar"><span class="dot">3</span><div><h3>Power <i>→ 1,600 W on a standard circuit</i></h3><p>No megawatt build-out, no substation conversation.</p></div></div>
    <div class="bar"><span class="dot">4</span><div><h3>Thermal <i>→ self-contained cooling</i></h3><p>No CDU, no facility water, no HVAC redesign.</p></div></div>
  </div>
  <div class="mem">
    <div class="label">Pick a model</div>
    <div class="seg" data-models>
      <button class="btn" data-v="0">70B FP4</button><button class="btn" data-v="1">200B FP4</button><button class="btn" data-v="2">1T NVFP4</button><button class="btn" data-v="3">2T NVFP4</button>
    </div>
    <div class="caps" data-caps></div>
  </div>
</div>
</html>
<css>
.wrap{flex:1;display:grid;grid-template-columns:620px 1fr;gap:44px;margin-top:24px;padding-bottom:34px;min-height:0}
.bars{display:flex;flex-direction:column;gap:14px}
.bar{border:1.5px solid var(--rule);border-radius:13px;padding:20px 24px;display:flex;gap:18px;align-items:flex-start;flex:1}
.bar h3{font-size:19px;margin-bottom:6px}
.bar h3 i{font-style:normal;color:var(--blue)}
.bar p{font-size:14.5px;color:var(--mute);line-height:1.45}
.mem{display:flex;flex-direction:column;gap:14px}
.caps{flex:1;display:flex;flex-direction:column;justify-content:space-evenly}
.cap .row{justify-content:space-between;margin-bottom:7px}
.cap .name{font-size:15.5px;font-weight:700}
.cap .name em{font-style:normal;color:var(--mute);font-family:var(--mono);font-size:13px;margin-left:6px}
.cap .stat{font-family:var(--mono);font-size:13.5px;font-weight:700}
.cap .stat.no{color:var(--alert)} .cap .stat.yes{color:var(--good)}
.over-lab{position:absolute;left:12px;top:50%;transform:translateY(-50%);font-family:var(--mono);font-size:11.5px;font-weight:700;color:#fff;letter-spacing:.08em}
</css>
<script>
const CAPS = [{name:'Typical accelerator', note:'48 GB', gb:48}, {name:'ZGX Nano', note:'128 GB', gb:128}, {name:'ZGX Fury', note:'748 GB', gb:748}, {name:'Two Fury, paired', note:'1,496 GB', gb:1496}];
const MODELS = [45, 120, 620, 1240];
let root, setModel;

function paint(sel){
  const need = sel >= 0 ? MODELS[sel] : null;
  CAPS.forEach((c, i) => {
    const cap = H.$('[data-cap="' + i + '"]', root);
    const fill = H.$('.fillbar', cap), stat = H.$('.stat', cap), lab = H.$('.over-lab', cap);
    if (need == null) { fill.style.width = '0'; stat.textContent = ''; lab.textContent = ''; return; }
    const fits = need <= c.gb;
    fill.style.width = Math.min(100, need / c.gb * 100) + '%';
    fill.classList.toggle('over', !fits);
    stat.className = 'stat ' + (fits ? 'yes' : 'no');
    stat.textContent = fits ? need + ' / ' + c.gb + ' GB' : 'needs ' + need + ' GB';
    lab.textContent = fits ? '' : 'DOES NOT FIT';
  });
}

function mount(r){
  root = r;
  H.$('[data-caps]', root).innerHTML = CAPS.map((c, i) =>
    `<div class="cap" data-cap="${i}"><div class="row"><div class="name">${c.name}<em>${c.note}</em></div><div class="stat"></div></div>
     <div class="track"><div class="fillbar"></div><div class="over-lab"></div></div></div>`).join('');
  setModel = H.segmented(H.$('[data-models]', root), v => paint(+v));
  paint(-1);
}

function go(r, step){
  if (step === 0) { H.$$('[data-models] .btn', r).forEach(b => b.classList.remove('sel')); paint(-1); }
  else setModel(step - 1);
}
</script>
