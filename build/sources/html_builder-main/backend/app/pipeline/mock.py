"""Offline mock of the LLM (LLM_MOCK=true): deterministic plans and template-built specs.

Lets the whole app (pipeline, QA, UI, export) run without the GB300. Output is decent but generic — not a quality reference.
"""
from __future__ import annotations

import html
import json
import re

from ..spec import SlideSpec, SpecMeta

ICON_HINTS = [
    (r"secur|protect|lock|trust|privacy", "shield"), (r"cost|price|spend|\$|budget|saving", "dollar"), (r"time|week|day|hour|fast", "clock"),
    (r"data|storage|memory", "data"), (r"power|energy|watt", "bolt"), (r"cloud", "cloud"), (r"network|connect", "network"),
    (r"team|people|customer|user", "users"), (r"grow|increase|up ", "trending-up"), (r"model|ai|intelligen", "brain"),
    (r"install|deploy|launch|pilot", "rocket"), (r"monitor|detect|inspect", "eye"), (r"check|success|criteria", "check"),
]


def _icon(text: str, i: int) -> str:
    low = text.lower()
    for rx, name in ICON_HINTS:
        if re.search(rx, low):
            return name
    return ["layers", "target", "lightbulb", "settings", "sparkles", "flag"][i % 6]


def _lines(content: dict) -> list[str]:
    out = []
    for block in content.get("text") or []:
        for ln in block.get("lines", []):
            t = ln.strip().strip("*").strip()
            if t:
                out.append(t)
    return out


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def plan(slides: list[dict]) -> dict:
    n = len(slides)
    out = []
    for s in slides:
        c, idx = s["content"], s["index"]
        title = c.get("title") or ""
        lines = _lines(c)
        low = title.lower()
        if idx == 1:
            pattern, role, theme = "title", "title", "light"
        elif "agenda" in low:
            pattern, role, theme = "agenda", "agenda", "navy"
        elif c.get("charts"):
            pattern, role, theme = "chart", "evidence", "light"
        elif c.get("tables"):
            pattern, role, theme = "compare", "comparison", "light"
        elif c.get("images"):
            pattern, role, theme = "specs", "solution", "light"
        elif idx == n and len(lines) <= 2:
            pattern, role, theme = "closing", "closing", "dark"
        elif lines and lines[0].startswith(("“", '"')):
            pattern, role, theme = "quote", "quote", "light"
        elif re.search(r"week|phase|step|plan", low + " ".join(lines).lower()):
            pattern, role, theme = "process", "process", "light"
        else:
            pattern, role, theme = "cards", "problem", "light"
        out.append({"index": idx, "role": role, "pattern": pattern, "eyebrow": (role.replace("-", " ").title()),
                    "headline": title[:55] or "Thank you", "key_message": lines[0] if lines else title,
                    "key_facts": [],  # the heuristic cannot judge which facts carry the message; all stay supporting
                    "idea_a": "reveal items one by one with count-ups and a clickable spotlight",
                    "idea_b": "editorial grid, calm reveals", "theme": theme, "include": True})
    first = slides[0]["content"].get("title", "Deck") if slides else "Deck"
    return {"deck_title": first, "audience": "Business and technical decision makers", "tone": "Confident, evidence-led",
            "narrative": "Frames the problem, quantifies it, presents the HP solution and closes with a clear next step.", "slides": out}


def _chart_spec(c: dict, p: dict, variant: str) -> SlideSpec:
    ch = c["charts"][0]
    labels = ch.get("categories") or []
    vals = (ch.get("series") or [{"values": []}])[0]["values"]
    vals = [v or 0 for v in vals]
    side = _lines(c)[:3]
    meta = SpecMeta(pattern="chart", title=p["headline"], steps=2 if variant == "A" else 1, auto=variant != "A",
                    notes=[f"<b>{_esc(p['key_message'])}</b>"])
    side_html = "".join(f'<div class="card tint appear" data-step="2"><p class="body">{_esc(t)}</p></div>' for t in side) or ""
    html_ = (f'<div class="eyebrow">{_esc(p["eyebrow"])}</div><h1 class="title">{_esc(p["headline"])}</h1>'
             f'<div class="split wide-right body-area"><div class="stack vcenter">{side_html}</div>'
             f'<div class="stack"><div class="legend"><span><i></i>{_esc((ch.get("series") or [{"name": ""}])[0]["name"])}</span></div>'
             f'<div class="plot fill" data-plot></div></div></div>')
    js = (f"let chart;\nfunction mount(root){{ chart = H.chart.bars(H.$('[data-plot]', root), {{labels:{json.dumps(labels)}, values:{json.dumps(vals)}}}); }}\n"
          f"function go(root, step){{ chart.show(step >= 1 ? {len(vals)} : 0); H.$$('[data-step]', root).forEach(n => n.classList.toggle('in', step >= +n.dataset.step)); }}")
    return SlideSpec(meta=meta, html=html_, css="", js=js)


def _table_spec(c: dict, p: dict, variant: str) -> SlideSpec:
    rows = c["tables"][0]
    head, body = rows[0], rows[1:]
    th = "".join(f"<th>{_esc(h)}</th>" for h in head)
    trs = "".join(
        f'<tr class="{"hl " if i == len(body) - 1 else ""}appear">' + "".join(f"<td>{_esc(x)}</td>" for x in r) + "</tr>" for i, r in enumerate(body))
    meta = SpecMeta(pattern="compare", title=p["headline"], steps=len(body) if variant == "A" else 0, notes=[f"<b>{_esc(p['key_message'])}</b>"])
    html_ = (f'<div class="eyebrow">{_esc(p["eyebrow"])}</div><h1 class="title">{_esc(p["headline"])}</h1>'
             f'<div class="body-area"><table class="table"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>')
    css = "td{font-size:20px} .appear{transform:none}" if variant == "A" else "td{font-size:20px} .appear{opacity:1;transform:none}"
    return SlideSpec(meta=meta, html=html_, css=css, js="")


def spec(content: dict, plan_: dict, variant: str) -> SlideSpec:
    p = {"headline": content.get("title") or "Untitled", "eyebrow": "", "key_message": ""} | (plan_ or {})
    pattern = p.get("pattern", "cards")
    lines = _lines(content)
    notes = [f"<b>{_esc(p.get('key_message') or p['headline'])}</b>"]
    if content.get("speaker_notes"):
        notes.append(_esc(content["speaker_notes"]))
    if content.get("charts"):
        return _chart_spec(content, p, variant)
    if content.get("tables"):
        return _table_spec(content, p, variant)
    if pattern == "title":
        sub = "<br>".join(_esc(x) for x in lines[:3])
        return SlideSpec(meta=SpecMeta(pattern="title", title=p["headline"], steps=0, theme="light", notes=notes),
                         html=f'<div class="vcenter fill"><h1 class="title hero">{_esc(p["headline"])}</h1><div class="rule-bar"></div>'
                              f'<div class="sub">{sub}</div></div>', css=".fill{max-width:1100px}")
    if pattern == "closing":
        return SlideSpec(meta=SpecMeta(pattern="closing", title=p["headline"], steps=0, theme="navy", notes=notes),
                         html=f'<div class="center fill"><div class="big">{_esc(p["headline"])}</div></div>',
                         css=".big{font-size:140px;font-weight:800;letter-spacing:-.04em;color:#fff}")
    if pattern == "agenda":
        items = "".join(f"<li><div>{_esc(x)}</div></li>" for x in lines[:6])
        return SlideSpec(meta=SpecMeta(pattern="agenda", title=p["headline"], steps=0, theme="navy", notes=notes),
                         html=f'<div class="grid-2 fill" style="align-items:center"><div><div class="eyebrow">Agenda</div>'
                              f'<h1 class="title">{_esc(p["headline"])}</h1></div><ol class="nlist">{items}</ol></div>',
                         css=".nlist li{color:#fff}.nlist li::before{color:var(--sky)}")
    if pattern == "quote" and lines:
        cite = _esc(lines[1].lstrip("—- ")) if len(lines) > 1 else ""
        return SlideSpec(meta=SpecMeta(pattern="quote", title=p["headline"], steps=1 if variant == "A" else 0, notes=notes),
                         html=f'<div class="eyebrow">{_esc(p["eyebrow"])}</div><div class="vcenter fill"><div class="quote appear" data-anim="fade">'
                              f'{_esc(lines[0].strip(chr(8220) + chr(8221) + chr(34)))}</div><div class="cite">{cite}</div></div>', css="")
    items = lines[:6] or [p.get("key_message") or p["headline"]]
    n = len(items)
    grid = "grid-2" if n in (2, 4) else "grid-3"
    imgs = content.get("images") or []
    if pattern == "specs" and imgs:
        rows = "".join(f'<div class="card row appear"><i data-icon="{_icon(t, i)}" class="icon"></i><p class="body">{_esc(t)}</p></div>'
                       for i, t in enumerate(items[:5]))
        return SlideSpec(meta=SpecMeta(pattern="specs", title=p["headline"], steps=min(5, n) if variant == "A" else 0, notes=notes),
                         html=f'<div class="eyebrow">{_esc(p["eyebrow"])}</div><h1 class="title">{_esc(p["headline"])}</h1>'
                              f'<div class="split even body-area"><figure class="figure"><img src="asset:{imgs[0]["key"]}" alt="{_esc(imgs[0].get("alt", ""))}"></figure>'
                              f'<div class="stack">{rows}</div></div>',
                         css=".card.row{padding:16px 22px}.card p{font-size:18px;color:var(--ink)}" + ("" if variant == "A" else ".appear{opacity:1;transform:none}"))
    if variant == "A":
        cards = "".join(f'<button class="card appear"><i data-icon="{_icon(t, i)}" class="icon"></i><h3>{_esc(t)}</h3></button>'
                        for i, t in enumerate(items))
        return SlideSpec(meta=SpecMeta(pattern="cards", title=p["headline"], steps=n, notes=notes),
                         html=f'<div class="eyebrow">{_esc(p["eyebrow"])}</div><h1 class="title">{_esc(p["headline"])}</h1>'
                              f'<div class="{grid} body-area" data-cards style="display:grid">{cards}</div>',
                         css=".card{justify-content:center}", js="function mount(root){ H.spotlight(H.$('[data-cards]', root), '.card'); }")
    li = "".join(f"<li>{_esc(t)}</li>" for t in items)
    return SlideSpec(meta=SpecMeta(pattern="list", title=p["headline"], steps=0, notes=notes),
                     html=f'<div class="eyebrow">{_esc(p["eyebrow"])}</div><h1 class="title">{_esc(p["headline"])}</h1>'
                          f'<div class="split body-area"><ul class="list vcenter">{li}</ul><div class="callout vcenter">{_esc(p.get("key_message") or "")}</div></div>',
                     css=".list li{font-size:24px}.callout{font-size:26px;font-weight:700}")


def critic() -> dict:
    return {"scores": {"layout": 8, "hierarchy": 8, "brand": 8, "fidelity": 8, "craft": 7, "interaction": 7}, "issues": [], "verdict": "pass"}


def outline(brief: dict, count: int) -> dict:
    """Offline stand-in for the outline draft (LLM_MOCK=true).

    Deliberately dull and deterministic. It exists so the compose flow can be exercised end to end
    without the GB300; it is not a writing model and must never look like one, or a mock run would be
    mistaken for a real draft.
    """
    title = brief.get("deck_title") or "Untitled deck"
    about = (brief.get("about") or brief.get("narrative") or "").strip()
    slides = [{"title": title, "content": [brief.get("audience") or "Prepared for review"],
               "notes": "Title slide — drafted offline, not by the model."}]
    for i in range(2, max(2, count)):
        slides.append({
            "title": f"Point {i - 1}",
            "content": [f"Placeholder line {i - 1}.", "  Supporting detail."],
            "notes": "Offline placeholder. Replace this copy before generating.",
        })
    slides.append({"title": "Next steps", "content": ["Decide", "Schedule", "Review"],
                   "notes": "Closing slide — drafted offline."})
    return {"deck_title": title, "audience": brief.get("audience") or "Internal review",
            "tone": brief.get("tone") or "Plain and direct",
            "narrative": about or "An offline placeholder outline, written without the model.",
            "slides": slides[:count]}
