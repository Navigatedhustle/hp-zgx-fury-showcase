# Example 13 — closing Q&A over photo (variant B, refined)

## Input
```json
{"role":"closing","source":{"title":"Questions?","images":[{"key":"fab","alt":"Semiconductor fab floor with wafer-handling robotics"}]}}
```

## Why
Full-bleed photo, radial shade for contrast, one huge word. `bleed` removes padding; theme dark keeps the stamp readable. Questions for the room go in the notes, not on the slide.

## Output
<meta>{"pattern":"closing","title":"Q&A","steps":0,"theme":"dark","bleed":true,"notes":["<b>Q&amp;A.</b> Leave this up for the whole discussion.","<i>Let silence do the work.</i>","Would you buy this? What would stop you?"],"sources":""}</meta>
<html>
<img class="bg-img" src="asset:fab" alt="Semiconductor fab floor with wafer-handling robotics">
<div class="bg-shade"></div>
<div class="on-top center fill"><div class="qamark">Q&amp;A</div></div>
</html>
<css>
.qamark{font-size:190px;font-weight:800;letter-spacing:-.05em;line-height:.9;color:#fff;text-shadow:0 12px 64px rgba(0,0,0,.62)}
</css>
<script>
</script>
