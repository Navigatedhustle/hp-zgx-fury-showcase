# Example 09 — two-step roadmap with CTA (variant B, refined)

## Input
```json
{"role":"next-steps","source":{"title":"Next steps","bullets":["Now: use the tested GB300 community demonstration profile","Next: verify your own prerequisites and operating envelope","Source: github.com/Navigatedhustle/hp-zgx-fury-showcase","Setup: follow the repository QUICKSTART"],"images":[{"key":"nano","alt":"HP ZGX Nano"},{"key":"fury","alt":"HP ZGX Fury"}]}}
```

## Why
Chronology -> two rows, each with a product image frame and a step block (when / what / tagline / detail). The CTA gets the blue block with real links. Three appear steps: now, later, act.

## Output
<meta>{"pattern":"roadmap","title":"You can start before Fury ships","steps":3,"theme":"light","notes":["<b>Start on a ZGX Nano today.</b>","<b>Prototype on Nano</b>, move to <b>Fury</b> for production.","<b>Pre-order, or talk to sales.</b>"],"sources":"HP ZGX Fury — expected later in 2026."}</meta>
<html>
<div class="eyebrow">Next step</div>
<h1 class="title">You can start before Fury ships.</h1>
<div class="wrap">
  <div class="prow appear">
    <figure class="figure"><img class="nano" src="asset:nano" alt="HP ZGX Nano"><figcaption>HP ZGX Nano</figcaption></figure>
    <div class="step"><div class="when">Now</div><h3>Start on ZGX Nano</h3><div class="tagline">The perfect developer companion</div><p>128 GB, models to 200B parameters, shipping today. Pilot one yield use case on real fab data.</p></div>
  </div>
  <div class="prow appear">
    <figure class="figure"><img class="fury" src="asset:fury" alt="HP ZGX Fury"><figcaption>HP ZGX Fury</figcaption></figure>
    <div class="step"><div class="when">Later in 2026</div><h3>Move the pilot to production</h3><div class="tagline">A data center, deskside</div><p>The validated workload steps up to 748 GB. Pre-order now to hold a place in the queue.</p></div>
  </div>
  <div class="cta appear">
    <a href="https://github.com/Navigatedhustle/hp-zgx-fury-showcase" target="_blank" rel="noopener">Open the community demonstration <span>Public source and instructions</span></a>
    <a href="https://github.com/Navigatedhustle/hp-zgx-fury-showcase/blob/main/QUICKSTART.md" target="_blank" rel="noopener">Read the quickstart <span>QUICKSTART.md</span></a>
  </div>
</div>
</html>
<css>
.wrap{flex:1;min-height:0;display:grid;grid-template-rows:minmax(0,1fr) minmax(0,1fr) auto;gap:18px;margin-top:20px;padding-bottom:14px}
.prow{display:grid;grid-template-columns:300px 1fr;gap:40px;align-items:center;min-height:0;height:100%}
.figure{height:100%;padding:16px;gap:10px}
.figure img.nano{max-width:76%;max-height:44%}
.figure img.fury{max-height:78%;max-width:60%}
.step{border-left:4px solid var(--blue);padding:6px 0 6px 24px}
.when{font-family:var(--mono);font-size:12.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--blue);font-weight:700;margin-bottom:8px}
.step h3{font-size:27px;margin-bottom:5px}
.tagline{font-size:17px;font-weight:700;color:var(--blue);margin-bottom:9px}
.step p{font-size:17px;line-height:1.5;color:var(--mute);max-width:62ch}
.cta{background:var(--blue);border-radius:var(--r-m);padding:20px 26px;display:flex;flex-direction:column;gap:10px}
.cta a{color:#fff;text-decoration:none;font-size:17px;display:flex;justify-content:space-between;gap:20px;border-bottom:1px solid rgba(255,255,255,.28);padding-bottom:9px}
.cta a:last-child{border:none;padding-bottom:0}
.cta a span{font-family:var(--mono);font-size:14.5px;opacity:.92}
.cta a:focus-visible{outline:3px solid #fff;outline-offset:3px}
</css>
<script>
</script>
