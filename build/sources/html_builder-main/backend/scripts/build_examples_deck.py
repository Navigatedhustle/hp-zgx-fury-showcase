"""Assemble all gold examples into one deck and screenshot each slide (runtime + examples gate)."""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.assemble import DeckInput, DeckSlide, assemble
from app.config import RUNTIME_DIR, ROOT_DIR
from app.skillpack import examples
from app.spec import parse_spec

out_dir = ROOT_DIR / "data" / "examples_deck"; out_dir.mkdir(parents=True, exist_ok=True)
slides = []
for i, ex in enumerate(examples()):
    sid = f"ex{i+1}"
    spec, issues = parse_spec(ex.output, sid)
    if issues: print(ex.name, [x.message for x in issues])
    slides.append(DeckSlide(id=sid, spec=spec))
assets = {p.stem: p for p in (RUNTIME_DIR / "img").iterdir()}
html = assemble(DeckInput(title="Gold examples", slides=slides, assets=assets))
deck = out_dir / "examples.html"; deck.write_text(html, encoding="utf-8")
print("deck", deck, len(html))

async def shots():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width":1600,"height":900})
        logs = []
        pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
        pg.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
        await pg.goto(deck.as_uri() + "?instant")
        await pg.wait_for_function("window.DECK && DECK.ready")
        n = await pg.evaluate("DECK.api.count()")
        for i in range(n):
            steps = await pg.evaluate(f"DECK.api.steps({i})")
            await pg.evaluate(f"DECK.api.goto({i}, {steps})")
            await pg.wait_for_timeout(250)
            await pg.screenshot(path=str(out_dir / f"slide{i+1:02d}.png"))
        print("errors", json.dumps(await pg.evaluate("DECK.api.errors()"), indent=1))
        print("\n".join(logs))
        await b.close()
asyncio.run(shots())
