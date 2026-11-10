"""Networkless iframe wrapper and functional browser checks for the generated app."""
import html
import re
import shlex
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; font-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"

# Keep the model's controls, outputs and JavaScript; give those same DOM nodes
# the fixed stage layout before validating the actual arithmetic again.
STAGE_LAYOUT = r'''<style id="nano-stage-style">
body{margin:0!important;padding:12px!important;height:100vh!important;overflow:hidden!important;display:block!important;background:#101a2b!important;color:white!important;font:clamp(18px,6.8vh,64px)/1.15 Arial,Helvetica,"Liberation Sans",Arimo,sans-serif!important}
body *{box-sizing:border-box!important;font-family:Arial,Helvetica,"Liberation Sans",Arimo,sans-serif!important;box-shadow:none!important}
.nano-stage-roi{width:100%!important;max-width:none!important;margin:0!important;padding:0!important;display:grid!important;gap:.25em!important;align-content:start!important;background:transparent!important;border:0!important}
.nano-stage-roi h1{font:700 1.08em/1.1 Arial,Helvetica,sans-serif!important;margin:0!important;color:#d1ddf1!important;border-bottom:2px solid #7da5ff!important;padding:0 0 .2em!important}
.nano-stage-fields{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:.4em!important}
.nano-stage-field{display:flex!important;flex-direction:column!important;gap:.1em!important;font:inherit!important;color:white!important}
.nano-stage-field input{width:100%!important;min-width:0!important;max-width:100%!important;height:1.4em!important;margin:0!important;padding:.15em!important;border:2px solid #7da5ff!important;border-radius:3px!important;background:#0a0d14!important;color:white!important;font:inherit!important;position:static!important}
.nano-stage-roi #calculate{width:100%!important;margin:0!important;padding:.25em!important;height:1.7em!important;border:0!important;border-radius:3px!important;background:#004bdf!important;color:white!important;font:inherit!important;position:static!important}
.nano-stage-values{display:grid!important;grid-template-columns:1fr 1fr!important;gap:.5em!important}
.nano-stage-value{background:#0a0d14!important;padding:.25em!important;min-width:0!important}
.nano-stage-value small,.nano-stage-roi footer{display:block!important;font-size:.65em!important;color:#b4c1d7!important;margin:0!important;padding:0!important}
.nano-stage-roi #net,.nano-stage-roi #roi{display:block!important;font:700 1.4em/1.15 Arial,Helvetica,sans-serif!important;color:#d1ddf1!important;margin:0!important;padding:0!important;position:static!important}
@media(min-height:400px){body{font-size:max(28px,6.8vh)!important}.nano-stage-roi #net,.nano-stage-roi #roi{font-size:max(44px,1.4em)!important}}
</style><script>
(()=>{const skin=document.getElementById('nano-stage-style');if(skin)document.head.append(skin);function stageLayout(){const controls=['hourly','hours','cost'].map(id=>document.getElementById(id)),button=document.getElementById('calculate'),net=document.getElementById('net'),roi=document.getElementById('roi');if(controls.some(x=>!x)||!button||!net||!roi)return;const originalForm=button.closest('form'),root=originalForm||document.createElement('div');root.classList.add('nano-stage-roi');const heading=document.createElement('h1');heading.textContent='ROI calculator';const fields=document.createElement('div');fields.className='nano-stage-fields';controls.forEach((input,i)=>{const label=document.createElement('label');label.className='nano-stage-field';label.textContent=['Rate $ / h','Hours / mo','Cost $ / mo'][i];label.append(input);fields.append(label);});const values=document.createElement('div');values.className='nano-stage-values';[net,roi].forEach((output,i)=>{const box=document.createElement('div');box.className='nano-stage-value';const label=document.createElement('small');label.textContent=i?'Return on cost':'Net monthly value';box.append(label,output);values.append(box);});const foot=document.createElement('footer');foot.textContent='Fictional inputs · source 2026-11-08';root.replaceChildren(heading,fields,button,values,foot);document.body.replaceChildren(root);}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',stageLayout,{once:true});else stageLayout();})();
</script>'''


class ReferenceCheck(HTMLParser):
    def handle_starttag(self, tag, attrs):
        if tag in ('iframe', 'object', 'embed', 'base'):
            raise ValueError('Generated calculator contains an unsupported embedded resource')
        for name, value in attrs:
            if name.lower() in ('src', 'href', 'action', 'formaction', 'poster') and value:
                raise ValueError('Generated calculator must be self-contained')


def secure_html(source):
    if not isinstance(source, str) or not 50 <= len(source.encode()) <= 65536:
        raise ValueError('Generated calculator has an invalid size')
    ReferenceCheck().feed(source)
    if re.search(r'url\s*\(|https?://|file://', source, re.I):
        raise ValueError('Generated calculator contains a URL')
    return '<meta http-equiv="Content-Security-Policy" content="' + html.escape(CSP, quote=True) + '">' + source


def preview_document(source):
    parent_csp = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-src 'self'; connect-src 'none'; base-uri 'none'; form-action 'none'"
    return '<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="' + html.escape(parent_csp, quote=True) + '"></head><body style="margin:0"><iframe sandbox="allow-scripts" style="border:0;width:100vw;height:100vh" srcdoc="' + html.escape(source, quote=True) + '"></iframe></body></html>'


def chromium_wrapper(browser_path):
    folder = ROOT / 'state/stage/tools'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'chromium'
    # Apply the already-installed Ubuntu Chrome policy; Chromium's own sandbox stays on.
    script = '#!/bin/sh\nexec /usr/bin/aa-exec -p chrome -- ' + shlex.quote(str(browser_path)) + ' "$@"\n'
    if not path.exists() or path.read_text() != script:
        path.write_text(script)
        path.chmod(0o700)
    return path


async def launch_browser(playwright, **options):
    return await playwright.chromium.launch(executable_path=str(chromium_wrapper(playwright.chromium.executable_path)),
        chromium_sandbox=True, headless=True,
        proxy={'server': 'http://127.0.0.1:9', 'bypass': '127.0.0.1,localhost'},
        args=['--disable-gpu', '--disable-background-networking', '--disable-component-update', '--disable-sync',
              '--disable-domain-reliability', '--dns-prefetch-disable', '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1, EXCLUDE [::1]'], **options)


def numeric(text):
    cleaned = text.replace(',', '').replace('−', '-')
    found = re.search(r'([+-]?)\s*[$€£]?\s*(\d+(?:\.\d+)?)', cleaned)
    if not found:
        raise ValueError('Calculator did not display a numeric result')
    return float(found.group(2)) * (-1 if found.group(1) == '-' else 1)


async def validate_app(source, folder):
    from playwright.async_api import async_playwright
    wrapped = secure_html(source) + STAGE_LAYOUT
    attempted = []
    async with async_playwright() as playwright:
        browser = await launch_browser(playwright)
        try:
            page = await browser.new_page(viewport={'width': 640, 'height': 380})
            page.set_default_timeout(3000)

            async def deny(route):
                attempted.append(route.request.url)
                await route.abort()

            await page.route('**/*', deny)
            await page.set_content(preview_document(wrapped), wait_until='load')
            frame = page.frame_locator('iframe')
            cases = [(75, 20, 500, 1000, 200), (80, 10, 400, 400, 100), (100, 5, 1000, -500, -50)]
            for hourly, hours, cost, net, roi in cases:
                await frame.locator('#hourly').fill(str(hourly))
                await frame.locator('#hours').fill(str(hours))
                await frame.locator('#cost').fill(str(cost))
                await frame.locator('#calculate').click()
                if abs(numeric(await frame.locator('#net').inner_text()) - net) > .05 or abs(numeric(await frame.locator('#roi').inner_text()) - roi) > .05:
                    raise ValueError('Generated calculator failed a real input/output check')
            await frame.locator('#cost').fill('0')
            await frame.locator('#calculate').click()
            zero = (await frame.locator('#roi').inner_text()).strip().upper()
            if not re.search(r'\bN/A\b|\bUNDEFINED\b', zero) or re.search(r'\d', zero):
                raise ValueError('Calculator must handle a zero cost without a false ROI')
            for selector, value in [('#hourly', '75'), ('#hours', '20'), ('#cost', '500')]:
                await frame.locator(selector).fill(value)
            await frame.locator('#calculate').click()
            if attempted:
                raise ValueError('Generated calculator attempted a resource request')
            await page.screenshot(path=str(folder / 'calculator.png'))
        finally:
            await browser.close()
    (folder / 'calculator.html').write_text(wrapped)
    return {'file': 'calculator.html', 'preview': 'calculator.png', 'checks_passed': 4, 'network_requests': 0}
