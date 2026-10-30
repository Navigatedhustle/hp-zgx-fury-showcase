# Example 17 — problems and what answers them (variant A, cinematic)

## Input
```json
{"role":"problem-solution","source":{"title":"Why AI can't run in the fab today","table":[["Barrier","What answers it"],["Fab data can't leave the network","The model runs inside the fab, on one tower"],["Models don't fit in 96 GB of GPU memory","748 GB of coherent memory in one address space"],["No room for a rack and 40 kW","1,600 W, cooling built in, deskside"]]}}
```

## Why
Three barriers, three answers — the shape is a disclosure, not a table. `.acc` puts each barrier as a heading the room reads at once, and opens its answer one click at a time, so nobody reads ahead. The headings are real `<button>`s, so Tab and Enter drive it as well as the mouse, and the audience can reopen any row afterwards. The final step lands the `.callout`, which is the one sentence that covers all three — so the slide still says everything essential with every row closed.

## Output
<meta>{"pattern":"problem-solution","title":"Three barriers, one box","steps":4,"theme":"light","auto":false,"notes":["Three reasons AI has stayed outside the fab.","Click: <b>data can't leave</b> — so the model comes to the data.","Click: <b>models don't fit</b> — 748 GB coherent, one address space.","Click: <b>no room, no power</b> — 1,600 W, cooling built in.","Click: every barrier had the same shape, and the same answer."],"sources":"Specifications per HP.com."}</meta>
<html>
<div class="eyebrow">Why this hasn't happened yet</div>
<h1 class="title">Three barriers, one box</h1>
<div class="sub">Three reasons AI has stayed outside the fab — and what each one actually needs.</div>
<div class="body-area">
  <div class="acc fill" data-acc>
    <div>
      <button class="head"><i data-icon="lock" class="icon s"></i>Fab data can't leave the network</button>
      <div class="body">Security won't sign off on wafer maps crossing a firewall, and the review alone takes months. So the model comes to the data: inference runs inside the fab, on one tower, and nothing leaves.</div>
    </div>
    <div>
      <button class="head"><i data-icon="layers" class="icon s"></i>Models don't fit in 96 GB of GPU memory</button>
      <div class="body">A workstation card tops out long before a useful model does. ZGX Fury holds 748 GB of coherent memory in one address space — the whole model, no sharding, no host round-trips.</div>
    </div>
    <div>
      <button class="head"><i data-icon="thermal" class="icon s"></i>There is no room for a rack and 40 kW</button>
      <div class="body">Fab floor space is measured in wafer starts, not square metres. 1,600 W, cooling built in, standing beside the desk of the engineer who needs it.</div>
    </div>
  </div>
  <div class="callout appear mt-m" data-final><b>Every barrier is the same barrier.</b> The model was in the wrong place.</div>
</div>
</html>
<css>
.acc{justify-content:center}
.acc .head{gap:14px}
.acc .body{max-width:1100px}
</css>
<script>
let open;
function mount(root){ open = H.accordion(H.$('[data-acc]', root), -1); }
function go(root, step){
  open(step >= 1 ? Math.min(step, 3) - 1 : -1);
  H.$('[data-final]', root).classList.toggle('in', step >= 4);
}
</script>
