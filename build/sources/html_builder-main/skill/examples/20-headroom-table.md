# Example 20 — capacity table with a threshold gauge (variant B, refined)

## Input
```json
{"role":"evidence","source":{"title":"Memory headroom by model","table":[["Model","Weights (NVFP4)","KV cache at 128k","Total","Fits in 748 GB"],["Llama 3.1 70B","35 GB","20 GB","55 GB","Yes"],["Mixtral 8x22B","70 GB","24 GB","94 GB","Yes"],["Llama 3.1 405B","203 GB","40 GB","243 GB","Yes"],["Frontier 1T class","500 GB","120 GB","620 GB","Yes"]],"texts":["96 GB workstation cards stop at the second row"]}}
```

## Why
Dense facts belong in a `.table`, but a column of totals does not show headroom — so the last column is a `.rail` per row, all on the same 748 GB scale. The scale itself lives once, in a `<tfoot>` cell, which keeps it aligned with the bars above for free: a `.mark` for the 96 GB workstation ceiling plus `.ticks` for the scale. Rows reveal one at a time so the bars grow down the page. The "illustrative" caveat goes in `sources`, not on the slide.

## Output
<meta>{"pattern":"table","title":"Every model we care about fits, with room left","steps":4,"theme":"light","notes":["Weights plus KV cache is the number that matters — not parameter count.","Click: <b>70B</b> at 55 GB. A workstation card can just about hold this one.","Click: <b>8x22B</b> at 94 GB — already at the 96 GB ceiling once you add context.","Click: <b>405B</b> at 243 GB.","Click: a <b>1T-class</b> model at 620 GB still leaves 128 GB free."],"sources":"NVFP4 weights plus KV cache at 128k context. Illustrative: exact sizes vary by tokenizer and batch."}</meta>
<html>
<div class="eyebrow">Memory headroom</div>
<h1 class="title">Every model we care about fits, with room left</h1>
<div class="sub">748 GB of coherent memory, measured against <b>weights plus KV cache</b> — not parameter count.</div>
<div class="body-area">
  <table class="table">
    <thead><tr><th>Model</th><th class="num">Weights</th><th class="num">KV cache</th><th class="num">Total</th><th>Against 748 GB</th></tr></thead>
    <tbody>
      <tr class="appear"><td>Llama 3.1 70B</td><td class="num">35 GB</td><td class="num">20 GB</td><td class="num">55 GB</td>
        <td><div class="rail"><div class="track"><div class="fillbar" style="width:7.4%"></div></div></div></td></tr>
      <tr class="appear"><td>Mixtral 8x22B</td><td class="num">70 GB</td><td class="num">24 GB</td><td class="num">94 GB</td>
        <td><div class="rail"><div class="track"><div class="fillbar" style="width:12.6%"></div></div></div></td></tr>
      <tr class="appear"><td>Llama 3.1 405B</td><td class="num">203 GB</td><td class="num">40 GB</td><td class="num">243 GB</td>
        <td><div class="rail"><div class="track"><div class="fillbar" style="width:32.5%"></div></div></div></td></tr>
      <tr class="appear hl"><td>Frontier 1T class</td><td class="num">500 GB</td><td class="num">120 GB</td><td class="num">620 GB</td>
        <td><div class="rail"><div class="track"><div class="fillbar" style="width:82.9%"></div></div></div></td></tr>
    </tbody>
    <tfoot><tr><td colspan="4"></td><td>
      <div class="rail scale">
        <div class="track"></div>
        <div class="mark alert start" style="--at:12.8%"><b>96 GB card ceiling</b></div>
      </div>
      <div class="ticks"><span>0</span><span>187</span><span>374</span><span>561</span><span>748 GB</span></div>
    </td></tr></tfoot>
  </table>
  <div class="callout tint mt-auto"><b>128 GB still free at 1T class.</b> The ceiling was never the model — it was the card underneath it.</div>
</div>
</html>
<css>
.table{margin-top:8px}
.table td{vertical-align:middle;padding:26px 16px}
.table th:last-child,.table td:last-child{width:34%}
.table tfoot td{border-bottom:none;padding-top:20px}
.rail{padding-top:0}
.rail .track{height:20px}
.scale{padding-top:22px}
.scale .track{height:12px}
</css>
<script>
</script>
