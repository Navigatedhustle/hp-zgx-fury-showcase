# Example 10 — agenda / section divider (variant B, refined)

## Input
```json
{"role":"agenda","source":{"title":"Agenda","bullets":["Why AI can't run in the fab today","What late detection costs","ZGX Fury: the data centre, deskside","The economics","Next steps"]}}
```

## Why
Navy theme marks a structural slide and gives the deck rhythm. Numbered list (nlist) in two columns: big numbers on the left side are the eyebrow and title; items are short, parallel phrases with one supporting line. No steps — an agenda is read at a glance.

## Output
<meta>{"pattern":"agenda","title":"Agenda","steps":0,"theme":"navy","notes":["Five parts, about twenty minutes.","The <b>economics</b> section is interactive — have your wafer cost ready."],"sources":""}</meta>
<html>
<div class="agenda">
  <div class="vcenter">
    <div class="eyebrow">Agenda</div>
    <h1 class="title">Twenty minutes.<br>One decision.</h1>
    <div class="sub">From the constraint to the economics — with <b>your numbers</b>.</div>
  </div>
  <ol class="nlist">
    <li><div>Why AI can’t run in the fab today<p>Four barriers: data, power, memory, thermal.</p></div></li>
    <li><div>What late detection costs<p>A live calculator with your wafer cost.</p></div></li>
    <li><div>ZGX Fury: the data center, deskside<p>748 GB coherent memory in one tower.</p></div></li>
    <li><div>The economics<p>How one early catch pays for the system.</p></div></li>
    <li><div>Next steps<p>Start on Nano today.</p></div></li>
  </ol>
</div>
</html>
<css>
.agenda{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:80px;align-items:center}
.nlist{gap:26px}
.nlist li{color:#fff}
.nlist li::before{color:var(--sky)}
.nlist li p{color:#C7D3EC}
</css>
<script>
</script>
