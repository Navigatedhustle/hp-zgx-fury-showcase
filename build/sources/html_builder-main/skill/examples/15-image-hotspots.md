# Example 15 — image focus with hotspots (variant A, cinematic)

## Input
```json
{"role":"evidence","source":{"title":"Where inference sits on the line","bullets":["Metrology station streams 4 TB a shift","ZGX Fury sits in the tool bay, not the data centre","Operators see a drift call on the line-side display"],"images":[{"key":"fab","alt":"Semiconductor fab floor"}]}}
```

## Why
A photo only means something once you say where to look. `.hotspots` turns the figure into three numbered `.hotspot` buttons, each opening a `.note` — and because they are real `<button>`s, Tab and Enter work exactly like a click. `.note.up` / `.l` / `.r` keep each callout inside the stage. The numbered list on the right carries the same three facts in words, so the slide still reads with every note closed and prints correctly. `go` sets which hotspots exist and which one is open, so jumping to any step is safe.

## Output
<meta>{"pattern":"image-focus","title":"Inference sits on the line, not in the data centre","steps":3,"theme":"light","auto":false,"notes":["This is the tool bay, not a server room.","Click: the metrology station streams <b>4 TB a shift</b> and throws most of it away.","Click: the ZGX Fury sits right here, beside the tool.","Click: the operator gets the drift call on the <b>line-side display</b>."],"sources":"Illustrative placement. Photo: HP."}</meta>
<html>
<div class="eyebrow">On the fab floor</div>
<h1 class="title">Inference sits on the line, not in the data centre</h1>
<div class="split body-area">
  <figure class="figure photo hotspots" data-spots>
    <img src="asset:fab" alt="Semiconductor fab floor">
    <button class="hotspot" style="--x:24%;--y:32%">1<span class="note r"><b>Metrology station</b><span>4 TB a shift, summarised and then discarded.</span></span></button>
    <button class="hotspot" style="--x:54%;--y:64%">2<span class="note up"><b>ZGX Fury</b><span>In the tool bay. No raised floor, no facility build.</span></span></button>
    <button class="hotspot" style="--x:84%;--y:30%">3<span class="note l"><b>Line-side display</b><span>The drift call lands where the operator already looks.</span></span></button>
  </figure>
  <ol class="nlist vcenter">
    <li class="appear"><div>Metrology streams 4 TB a shift<p>Today it is summarised, then discarded.</p></div></li>
    <li class="appear"><div>The box sits in the tool bay<p>Deskside, beside the tool it watches.</p></div></li>
    <li class="appear"><div>The call lands line-side<p>On the display the operator already reads.</p></div></li>
  </ol>
</div>
</html>
<css>
.figure.photo{border-radius:var(--r-l)}
.hotspot{opacity:0;pointer-events:none;transition:opacity .35s var(--ease),transform .2s var(--ease)}
.hotspot.live{opacity:1;pointer-events:auto}
</css>
<script>
let spots;
function mount(root){ spots = H.hotspots(H.$('[data-spots]', root)); }
function go(root, step){
  H.$$('.hotspot', root).forEach((b, k) => b.classList.toggle('live', step > k));
  H.reveal(root, '.nlist li', step);
  spots.open(step > 0 ? step - 1 : -1);
}
</script>
