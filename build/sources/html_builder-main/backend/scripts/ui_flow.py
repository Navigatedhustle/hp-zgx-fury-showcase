"""Drive the real UI: upload a deck, watch import, design, choose, revise, export. Screenshots to data/ui_flow."""
import asyncio, sys
from pathlib import Path
from playwright.async_api import async_playwright, expect

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parents[2]
DECK = ROOT / "evals" / "decks" / "hp_wolf_print_security.pptx"
OUT = ROOT / "data" / "ui_flow"; OUT.mkdir(parents=True, exist_ok=True)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1500, "height": 950}, accept_downloads=True)
        pg = await ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
        await pg.goto(BASE)
        await pg.set_input_files("input[type=file]", str(DECK))
        await pg.wait_for_url("**/plan", timeout=30000)
        await pg.wait_for_timeout(700)
        await pg.screenshot(path=str(OUT / "1_import.png"))
        await expect(pg.get_by_role("heading", name="Slide plan")).to_be_visible(timeout=120000)
        await pg.screenshot(path=str(OUT / "2_plan.png"))
        await pg.get_by_role("button", name="Design 5 slides").click()
        await pg.wait_for_url("**/review**", timeout=15000)
        await pg.wait_for_timeout(2500)
        await pg.screenshot(path=str(OUT / "3_designing.png"))
        await expect(pg.get_by_role("button", name="Use Cinematic")).to_be_enabled(timeout=180000)
        await pg.wait_for_timeout(2500)
        await pg.screenshot(path=str(OUT / "4_review.png"))
        await pg.keyboard.press("2")
        await pg.wait_for_timeout(2000)
        await pg.screenshot(path=str(OUT / "5_after_choose.png"))
        await pg.locator("#comment").fill("Make it more visual and highlight the 56% statistic.")
        await pg.get_by_role("button", name="Revise").click()
        await pg.wait_for_timeout(2500)
        await pg.screenshot(path=str(OUT / "6_revising.png"))
        await pg.wait_for_timeout(12000)
        await pg.screenshot(path=str(OUT / "7_revised.png"))
        qa = pg.get_by_role("button", name="Quality").first
        if await qa.count():
            await qa.click(); await pg.wait_for_timeout(600)
            await pg.screenshot(path=str(OUT / "8_quality.png"))
            await pg.keyboard.press("Escape")
            await pg.wait_for_timeout(800)
        await pg.goto(pg.url.split("/review")[0] + "/export")
        await pg.wait_for_timeout(3500)
        await pg.screenshot(path=str(OUT / "9_export.png"))
        async with pg.expect_download() as dl:
            await pg.get_by_role("button", name="Download HTML deck").click()
        d = await dl.value
        await d.save_as(str(OUT / d.suggested_filename))
        print("downloaded", d.suggested_filename, (OUT / d.suggested_filename).stat().st_size)
        print("console errors:", errs[:8])
        await b.close()
asyncio.run(main())
