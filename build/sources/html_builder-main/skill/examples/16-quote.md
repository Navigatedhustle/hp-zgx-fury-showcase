# Example 16 — customer quote (variant B, refined)

## Input
```json
{"role":"proof","source":{"title":"Customer voice","texts":["\"We stopped asking whether the data could leave the fab. It doesn't.\" — Director of Yield Engineering, 300 mm logic fab"],"bullets":["Security review closed in 3 weeks instead of 9 months"]}}
```

## Why
A quote slide is one sentence and the person who said it — nothing else competes. Navy theme marks it as a beat rather than an argument; `.quote` supplies the 40px type and the curly marks, `.cite` the attribution. One `.appear` lands the proof number after the room has read the sentence, so the quote is never sharing attention with a statistic. No JavaScript.

## Output
<meta>{"pattern":"quote","title":"We stopped asking whether the data could leave","steps":1,"theme":"navy","notes":["Read it, then stop talking.","Click: the review that used to take <b>nine months</b> closed in <b>three weeks</b>.","Attribution is deliberately role-level — the fab is not named."],"sources":"Customer interview, 300 mm logic fab. Name withheld at the customer's request."}</meta>
<html>
<div class="eyebrow">In their words</div>
<div class="body-area vcenter">
  <blockquote class="quote">We stopped asking whether the data could leave the fab. It doesn't.</blockquote>
  <div class="cite">Director of Yield Engineering · 300 mm logic fab</div>
  <div class="row gap-l mt-l appear">
    <div class="stat">
      <div class="v num"><span data-count="3">0</span><small>wks</small></div>
      <div class="k">to close the security review</div>
      <div class="d">The same review took nine months the last time it was attempted.</div>
    </div>
    <div class="callout tint">Nothing about the model changed. Only where it runs.</div>
  </div>
</div>
</html>
<css>
.quote{max-width:1240px}
.row.gap-l{align-items:center}
.stat{flex:none;width:420px}
.callout{max-width:620px}
</css>
<script>
</script>
