import asyncio, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import RUNTIME_DIR, ROOT_DIR
from app.qa.render_check import check_spec
from app.skillpack import examples
from app.spec import parse_spec

BROKEN = """<meta>{"pattern":"cards","title":"Broken","steps":2}</meta>
<html><div class="eyebrow">Test</div><h1 class="title">A very long title that goes on and on and on and on and on and on and wraps several lines for sure</h1>
<div class="grid-3" style="height:1400px"><div class="card"><h3>One</h3><p style="font-size:9px">tiny</p></div></div>
<p class="x" style="position:absolute;left:1500px;top:100px;width:400px">Overflowing text to the right</p>
<img src="asset:nope" alt="missing"></html>
<css>body{background:red} .x{color:#eee}</css>
<script>function go(root, step){ if(step==2) undefinedFn(); }</script>"""

async def main():
    assets = {p.stem: p for p in (RUNTIME_DIR / "img").iterdir()}
    out = ROOT_DIR / "data" / "qa_smoke"
    t = time.time()
    ex = examples()
    jobs = []
    for i, e in enumerate(ex[:4]):
        spec, _ = parse_spec(e.output, f"e{i}")
        jobs.append(check_spec(spec, f"e{i}", assets, out / f"e{i}"))
    spec, issues = parse_spec(BROKEN, "bad")
    print("parse issues:", [x.message for x in issues]); print("scoped css:", spec.css)
    jobs.append(check_spec(spec, "bad", assets, out / "bad"))
    reps = await asyncio.gather(*jobs)
    for r in reps:
        print("steps", r.steps, "shots", r.shots)
        for f in r.findings: print("   ", f.severity, f.code, f.message)
    print("secs", round(time.time() - t, 1))
asyncio.run(main())
