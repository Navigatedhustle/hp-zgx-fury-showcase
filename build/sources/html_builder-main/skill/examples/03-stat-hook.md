# Example 03 — stat hook (variant A, cinematic)

## Input
```json
{"role":"hook","source":{"title":"Market opportunity","bullets":["72 hours: typical time for yield analysis to land after a process drift","Every wafer processed in that window is at risk","Inference inside the fab can cut detection to minutes"]}}
```

## Why
One number carries this slide, so it gets 196px and counts up on the first click while the presenter says it out loud. The runtime's `.hook` gives the whole shape: `.lead` beside the number at 40px, then `.turn` — the "so what" — separated by a rule on the second click. Almost no chrome, and almost no slide CSS: this is the most legible slide in the deck.

## Output
<meta>{"pattern":"stat-hook","title":"72 hours of blind production","steps":2,"theme":"light","notes":["<b>How long until you know a tool drifted?</b> Pause.","Click: <b>72 hours</b>. Every wafer in that window is suspect.","Click: inference in the fab closes that window to <b>minutes</b>."],"sources":"Illustrative. Varies by fab, process step and metrology cadence."}</meta>
<html>
<div class="hook">
  <div class="row gap-l appear" data-anim="fade">
    <div class="mega-num num"><span data-count="72">0</span><i>h</i></div>
    <div class="lead">until yield analysis tells you a tool drifted out of spec.</div>
  </div>
  <div class="turn appear">Inference inside the fab closes that window to <span class="blue">minutes.</span></div>
</div>
</html>
<css>
.mega-num{flex:none}
.mega-num i{font-style:normal;font-size:96px;letter-spacing:-.03em}
</css>
<script>
</script>
