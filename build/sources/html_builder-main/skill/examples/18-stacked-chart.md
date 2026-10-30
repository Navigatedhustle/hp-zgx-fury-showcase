# Example 18 — stacked chart with gridlines (variant A, cinematic)

## Input
```json
{"role":"evidence","source":{"title":"Where the 72 hours go","chart":{"type":"stackedBar","categories":["Q1","Q2","Q3","Q4"],"series":[{"name":"Queue for metrology","values":[31,29,28,6]},{"name":"Analysis run time","values":[24,23,22,4]},{"name":"Review and sign-off","values":[17,18,17,5]}]},"texts":["Q4 is the first quarter with inference on the line"]}}
```

## Why
A stacked source chart rebuilds as `H.chart.stackedBars` — never as an image, and never as hand-written SVG. `grid:true` draws the gridlines and the hour labels, because the whole point is comparing column heights across quarters. The three series take `.s1`–`.s3` automatically and the `.legend` names them in the same order. The KPI card carries the one number the room should leave with, and its `sparkline` shows the same trend at a glance.

## Output
<meta>{"pattern":"chart","title":"Q4 cut the wait from 72 hours to 15","steps":3,"theme":"light","auto":false,"notes":["Three things make up the wait, and none of them is the analysis itself.","Click: three quarters of queue, run time and sign-off — flat at about <b>72 hours</b>.","Click: Q4, the first quarter with inference on the line. <b>15 hours.</b>","Click: the queue is what collapsed. The analysis was never the slow part."],"sources":"Illustrative breakdown of a single process step."}</meta>
<html>
<div class="eyebrow">Time to a drift call</div>
<h1 class="title">Q4 cut the wait from 72 hours to 15</h1>
<div class="split wide-right body-area">
  <div class="stack vcenter">
    <div class="card tint kpi appear" data-step="2">
      <div class="stat">
        <div class="v"><span data-count="79" data-suffix="%">0</span></div>
        <div class="k">less waiting, quarter on quarter</div>
        <div class="d">72 hours in Q3, 15 hours in Q4.</div>
      </div>
      <div class="spark" data-spark></div>
    </div>
    <div class="callout appear" data-step="3"><b>The queue collapsed, not the analysis.</b> Running it in the fab removed the wait, not the work.</div>
  </div>
  <div class="chartbox">
    <div class="legend">
      <span><i class="s1"></i>Queue for metrology</span>
      <span><i class="s2"></i>Analysis run time</span>
      <span><i class="s3"></i>Review and sign-off</span>
    </div>
    <div class="plot" data-plot></div>
  </div>
</div>
</html>
<css>
.chartbox{display:flex;flex-direction:column;gap:14px;min-height:0}
.spark{height:46px;margin-top:14px}
.stack{gap:20px}
</css>
<script>
let chart;
const SERIES = [
  {name:'Queue for metrology', values:[31, 29, 28, 6]},
  {name:'Analysis run time',   values:[24, 23, 22, 4]},
  {name:'Review and sign-off', values:[17, 18, 17, 5]}
];
function mount(root){
  chart = H.chart.stackedBars(H.$('[data-plot]', root), {
    labels:['Q1', 'Q2', 'Q3', 'Q4'], series:SERIES, grid:4, max:80,
    format:v => v + ' h', ylabel:v => Math.round(v) + 'h'
  });
  H.chart.sparkline(H.$('[data-spark]', root), {values:[72, 70, 67, 15]});
}
function go(root, step){
  chart.show(step === 0 ? 0 : step === 1 ? 3 : 4);
  H.$$('[data-step]', root).forEach(n => n.classList.toggle('in', step >= +n.dataset.step));
  const k = H.$('[data-count]', root);
  if (step >= 2) H.countTo(k, 79, 900, x => H.fmt.num(x) + '%'); else H.resetCount(k, x => H.fmt.num(x) + '%');
}
</script>
