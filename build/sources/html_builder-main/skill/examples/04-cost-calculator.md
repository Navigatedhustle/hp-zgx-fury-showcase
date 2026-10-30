# Example 04 — live cost timeline calculator (variant A, cinematic)

## Input
```json
{"role":"cost-of-inaction","source":{"title":"Cost of late detection","bullets":["Standard lot: 25 wafers","Advanced-node wafer: ~$22,000","Yield analysis lands at T+72h","Detecting at T+24h saves most of the lot"]}}
```

## Why
The source has numbers that multiply — that is a calculator waiting to happen. The audience types their own wafer cost and the slide recomputes live. Steps tell the story: (1) the clock runs and today's red track fills to 72h, (2) the fab-local track stops at the detection point, (3) the verdict appears. Inputs live in H.state so later slides can reuse the same numbers. The shape comes from the runtime: `.clock` for the readout, a `.lane` per scenario, `.verdict` for the answer — the slide only overrides what is genuinely specific. All queries are scoped to `root`. `go` is idempotent: it sets the state for a step, and only animates when moving forward.

## Output
<meta>{"pattern":"calculator","title":"Catching defects early saves money","steps":3,"theme":"light","auto":false,"notes":["<b>What does standing still cost?</b>","25 wafers a lot, about <b>$22,000</b> a wafer.","Click: the clock runs. Yield analysis lands at <b>T+72h</b> — the whole lot is gone.","Click: catch it at T+24h instead.","Click: <b>this is what waiting costs.</b> Ask the room for their wafer cost and type it in."],"sources":"Illustrative arithmetic using a standard 25-wafer 300 mm lot and public wafer-cost estimates."}</meta>
<html>
<div class="eyebrow">The cost of standing still</div>
<h1 class="title">Catching defects early saves money.</h1>
<div class="exc">
  <div class="row between ctl">
    <div class="row gap-l">
      <div class="field"><label>Cost per wafer</label><div class="box"><i>$</i><input type="number" min="0" step="500" data-wafer></div></div>
      <div class="field"><label>Wafers in a lot</label><div class="box"><input type="number" min="1" max="50" data-lot style="width:48px"></div></div>
      <div class="field det"><label>Detection at</label><div class="slider"><input type="range" min="1" max="72" step="1" data-det><b data-det-out>T+24 h</b></div></div>
    </div>
    <div class="clockwrap"><div class="clock num" data-clock>T+0<small>h</small></div><div class="label">since drift began</div></div>
  </div>
  <div class="lane" data-lane="a">
    <div class="row between"><div><div class="label">Today</div><div class="lname">Yield analysis lands at T+72 h</div></div><div class="lval num" data-a-val>$0</div></div>
    <div class="track"><div class="fillbar alert" data-a-bar></div></div>
  </div>
  <div class="lane dim" data-lane="b">
    <div class="row between"><div><div class="label">Inference in the fab</div><div class="lname">Detected at <span data-b-at>T+24 h</span></div></div><div class="lval num" data-b-val>$0</div></div>
    <div class="track"><div class="fillbar good" data-b-bar></div></div>
  </div>
  <div class="verdict appear" data-step="3">
    <div class="vmain num" data-gap>$0</div>
    <p><b>This is what waiting costs.</b> One lot, one late detection.</p>
  </div>
</div>
</html>
<css>
.exc{flex:1;display:flex;flex-direction:column;gap:16px;margin-top:22px;min-height:0}
.ctl{align-items:flex-end}
.det{min-width:380px}
.clockwrap{text-align:right}
.lane{flex:1;transition:opacity .4s}
.lname{margin-top:2px}
.track{height:42px}
</css>
<script>
const HZ = 72;
let root, showT = 0, cancel = null, lastStep = 0;
const S = H.state;
S.init('wafer', 22000); S.init('lot', 25); S.init('detH', 24);
const exposure = h => Math.min(1, h / HZ) * S.get('wafer') * S.get('lot');

function paint(t){
  showT = t;
  const det = S.get('detH');
  H.$('[data-a-bar]', root).style.width = (t / HZ * 100) + '%';
  H.$('[data-a-val]', root).textContent = H.fmt.money(exposure(t));
  const b = Math.min(t, det);
  H.$('[data-b-bar]', root).style.width = (b / HZ * 100) + '%';
  H.$('[data-b-val]', root).textContent = H.fmt.money(exposure(b));
  H.$('[data-b-at]', root).textContent = 'T+' + det + ' h';
  H.$('[data-det-out]', root).textContent = 'T+' + det + ' h';
  H.$('[data-clock]', root).innerHTML = 'T+' + Math.round(t) + '<small>h</small>';
  H.$('[data-gap]', root).textContent = H.fmt.money(exposure(HZ) - exposure(det));
}

function mount(r){
  root = r;
  const w = H.$('[data-wafer]', root), l = H.$('[data-lot]', root), d = H.$('[data-det]', root);
  w.value = S.get('wafer'); l.value = S.get('lot'); d.value = S.get('detH');
  w.addEventListener('input', () => S.set('wafer', Math.max(0, +w.value || 0)));
  l.addEventListener('input', () => S.set('lot', Math.max(1, +l.value || 1)));
  d.addEventListener('input', () => S.set('detH', +d.value));
  S.on(() => paint(showT));
  paint(0);
}

function go(r, step){
  if (cancel) cancel();
  const a = H.$('[data-lane="a"]', r), b = H.$('[data-lane="b"]', r);
  H.$('.verdict', r).classList.toggle('in', step >= 3);
  a.classList.toggle('dim', step === 2);
  b.classList.toggle('dim', step < 2);
  if (step === 0) paint(0);
  else if (step === 1 && lastStep < 1) cancel = H.animate(2400, k => paint(HZ * k));
  else paint(HZ);
  lastStep = step;
}
</script>
