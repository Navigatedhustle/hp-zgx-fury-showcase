# Example 14 — rollout timeline (variant B, refined)

## Input
```json
{"role":"plan","source":{"title":"Rollout plan","bullets":["Month 0: pilot on one etch tool, two engineers","Month 1: drift detection live on the etch line","Month 2: security review closed, no wafer data leaves the fab","Month 3: lithography added on the same ZGX Fury","Month 4: toolkit opened to 40 process engineers","Month 6: all 9 process steps covered, detection in minutes"],"texts":["One box. No new facility work."]}}
```

## Why
Six milestones do not fit the horizontal `.timeline` — at 1fr per column the text squashes — so this uses `.timeline.vert`, which runs the rail down the left and lets each milestone keep a readable line. Milestones reveal in pairs so the presenter gets three beats, not six. The card on the left holds the constraint that makes the plan credible; nothing on this slide needs JavaScript.

## Output
<meta>{"pattern":"timeline","title":"Fab-wide in six months, on one box","steps":3,"theme":"light","notes":["The plan is deliberately small at the start.","Click: <b>one tool, two engineers</b> — detection live inside a month.","Click: security signs off because <b>no wafer data leaves the fab</b>. Lithography joins the same box.","Click: by month six all <b>9 process steps</b> are covered and the toolkit is open to <b>40 engineers</b>."],"sources":"Illustrative schedule based on a single-tool pilot."}</meta>
<html>
<div class="eyebrow">Rollout</div>
<h1 class="title">Fab-wide in six months, on one box</h1>
<div class="split body-area">
  <div class="timeline vert">
    <div class="tl done appear" data-step="1"><div class="when">Month 0</div><h3>Pilot lands</h3><p>One etch tool, two process engineers.</p></div>
    <div class="tl done appear" data-step="1"><div class="when">Month 1</div><h3>Drift detection live</h3><p>Running on the etch line, in production.</p></div>
    <div class="tl appear" data-step="2"><div class="when">Month 2</div><h3>Security review closed</h3><p>No wafer data leaves the fab.</p></div>
    <div class="tl appear" data-step="2"><div class="when">Month 3</div><h3>Lithography added</h3><p>Second line, same ZGX Fury.</p></div>
    <div class="tl appear" data-step="3"><div class="when">Month 4</div><h3>Engineers self-serve</h3><p>Toolkit opened to 40 process engineers.</p></div>
    <div class="tl appear" data-step="3"><div class="when">Month 6</div><h3>All 9 process steps</h3><p>Detection in minutes, fab-wide.</p></div>
  </div>
  <div class="stack vcenter">
    <div class="card tint">
      <i data-icon="server" class="icon"></i>
      <h3>One box. No facility work.</h3>
      <p>Every milestone above runs on the same deskside tower. Nothing here waits on a data-centre build or a new power feed.</p>
    </div>
    <div class="fnote">Schedule assumes the pilot tool is already instrumented.</div>
  </div>
</div>
</html>
<css>
.timeline.vert h3{font-size:19px}
.timeline.vert p{font-size:15px}
.timeline.vert .tl:not(:last-child){padding-bottom:18px}
</css>
<script>
</script>
