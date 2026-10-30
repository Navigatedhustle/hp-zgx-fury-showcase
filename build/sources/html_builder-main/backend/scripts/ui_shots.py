"""Screenshot every app screen for visual review. Usage: ui_shots.py [base_url] [project_id]"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
PID = sys.argv[2] if len(sys.argv) > 2 else ""
OUT = Path(__file__).resolve().parents[2] / "data" / "ui_shots"
OUT.mkdir(parents=True, exist_ok=True)


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for scheme in ("light", "dark"):
            ctx = await b.new_context(viewport={"width": 1600, "height": 1000}, color_scheme=scheme)
            pg = await ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
            await pg.goto(BASE + "/")
            await pg.wait_for_timeout(1500)
            await pg.screenshot(path=str(OUT / f"{scheme}_home.png"))
            if PID:
                for tab in ("plan", "review", "export"):
                    await pg.goto(f"{BASE}/p/{PID}/{tab}")
                    await pg.wait_for_timeout(3500)
                    await pg.screenshot(path=str(OUT / f"{scheme}_{tab}.png"))
                if scheme == "light":
                    await pg.goto(f"{BASE}/p/{PID}/review")
                    await pg.wait_for_timeout(2500)
                    btn = pg.get_by_role("button", name="Show original")
                    if await btn.count():
                        await btn.first.click()
                    await pg.locator("#comment").fill("Make the title shorter")
                    await pg.wait_for_timeout(800)
                    await pg.screenshot(path=str(OUT / "light_review_original.png"))
                    mobile = await b.new_context(viewport={"width": 390, "height": 844})
                    mp = await mobile.new_page()
                    await mp.goto(BASE + "/")
                    await mp.wait_for_timeout(1200)
                    await mp.screenshot(path=str(OUT / "mobile_home.png"))
                    await mobile.close()
            print(scheme, "errors:", errors[:5])
            await ctx.close()
        await b.close()


asyncio.run(main())
