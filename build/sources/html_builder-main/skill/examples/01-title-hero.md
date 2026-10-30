# Example 01 — title / hero (variant B, refined)

## Input
```json
{"role":"title","source":{"title":"HP ZGX Fury AI Stations","texts":["for Semiconductor Manufacturing","Anbu Valluvan Devadasan","Sr AI Engineer","08/13/2026","All figures in this deck come from public, open-source data."],"images":[{"key":"fury","alt":"HP ZGX Fury tower"},{"key":"gb300","alt":"NVIDIA GB300 board"}]}}
```

## Why
Split layout: the promise on the left, the product on the right on a tint panel. No steps — a title slide should be fully visible the moment it appears. Product gets the hero position, the chip is supporting evidence, captions in mono.

## Output
<meta>{"pattern":"title","title":"HP ZGX Fury AI Stations","steps":0,"theme":"light","bleed":true,"notes":["Good afternoon. I am <b>Anbu Valluvan</b>, Sr AI Engineer.","Today: deploying AI <b>inside the fab</b>, close to the data — and how <b>HP ZGX Fury</b> makes that possible."],"sources":""}</meta>
<html>
<div class="hero-grid">
  <div class="left vcenter">
    <h1 class="title hero">HP ZGX Fury AI Stations</h1>
    <div class="deck-sub">for Semiconductor Manufacturing</div>
    <div class="rule-bar"></div>
    <div class="meta"><b>Anbu Valluvan Devadasan</b><br>Sr AI Engineer<br>08 / 13 / 2026</div>
    <div class="fnote">All figures in this deck come from public, open-source data.</div>
  </div>
  <div class="right">
    <img class="logo" src="asset:hp" alt="HP">
    <figure class="hero-fig"><img src="asset:fury" alt="HP ZGX Fury"><figcaption>HP ZGX Fury</figcaption></figure>
    <figure class="chip-fig"><img src="asset:gb300" alt="NVIDIA GB300 Grace Blackwell Ultra board"><figcaption>NVIDIA GB300<br><span class="mute">Grace Blackwell Ultra</span></figcaption></figure>
  </div>
</div>
</html>
<css>
.hero-grid{flex:1;display:grid;grid-template-columns:1fr 1fr}
.left{position:relative;padding:88px 40px 64px 76px}
.deck-sub{font-size:33px;line-height:1.15;font-weight:700;letter-spacing:-.02em;color:var(--blue);margin-top:10px}
.meta{font-family:var(--mono);font-size:14.5px;color:var(--mute);line-height:1.95}
.meta b{color:var(--ink)}
.fnote{position:absolute;left:76px;bottom:62px}
.right{position:relative;background:linear-gradient(160deg,var(--tint-2),#E3E9FB)}
.logo{position:absolute;top:44px;right:52px;width:66px}
figure{position:absolute;margin:0;display:flex;flex-direction:column;align-items:center;gap:14px}
.hero-fig{left:62%;top:48%;transform:translate(-50%,-50%);width:50%}
.hero-fig img{width:100%;filter:drop-shadow(0 26px 34px rgba(10,16,40,.26))}
.chip-fig{left:54px;bottom:60px;width:19%;gap:11px}
.chip-fig img{width:100%;filter:drop-shadow(0 18px 30px rgba(10,16,40,.32))}
.chip-fig figcaption{font-size:10.5px}
</css>
<script>
</script>
