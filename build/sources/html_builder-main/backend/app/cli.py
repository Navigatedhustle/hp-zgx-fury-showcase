"""Command line: probe the GB300, run the pipeline headless, build the gold-examples deck.

  python -m app.cli probe
  python -m app.cli run ../evals/decks/hp_z_workstations_genai.pptx [--slides 3,4] [--out deck.html]
  python -m app.cli examples
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import time
from pathlib import Path

from .config import ROOT_DIR, RUNTIME_DIR, settings


def _print(*a):
    print(*a, flush=True)


CRITIC_IMAGES = 3   # step 0, final step, original slide render


async def probe_image_limit(h: dict) -> None:
    """Report the server's real per-request image ceiling, and what it costs if it is too low.

    No endpoint exposes it: it is fixed when the server starts and the refusal is an ordinary 400, so the
    only way to know is to send images and see. Worth doing before a deck rather than during one — a plan
    batch that exceeds the limit fails outright instead of being trimmed and retried.
    """
    from .llm import client as llm
    from .pipeline.runner import PLAN_MAX_IMAGES

    if not h.get("vision"):
        _print("\nimages    vision is off — the critic and the A/B judge will be skipped, and the planner sends text only")
        return
    _print("\nimages per request (fixed when the server starts; nothing can raise it from here)")
    highest, refused_at = 0, 0
    for n in (1, CRITIC_IMAGES, PLAN_MAX_IMAGES):
        ok, err = await llm.probe_image_count(n)
        if ok:
            highest = n
            _print(f"  {n:>2}  ok")
        else:
            refused_at = n
            _print(f"  {n:>2}  refused — {'over the image limit' if llm.is_image_limit_error(err) else err}")
            break
    if refused_at:
        # The ladder only proves the rungs it stood on: a server that stops at 4 refuses 16 and would be
        # reported as "3" — and then advised to drop to 3, losing a slide per batch for nothing. Bisect
        # for the real ceiling, which is the number the advice below tells the user to act on.
        lo, hi = highest, refused_at
        while hi - lo > 1:
            mid = (lo + hi) // 2
            ok, _ = await llm.probe_image_count(mid)
            _print(f"  {mid:>2}  {'ok' if ok else 'refused'}")
            lo, hi = (mid, hi) if ok else (lo, mid)
        highest = lo
    _print(f"  limit = {highest} image(s) per request")
    if highest >= PLAN_MAX_IMAGES:
        _print(f"  → planning ({PLAN_MAX_IMAGES} thumbnails) and the critic ({CRITIC_IMAGES}) both fit. Nothing to change.")
    elif highest >= CRITIC_IMAGES:
        _print(f"  → the critic fits, planning does not: a batch may carry up to {PLAN_MAX_IMAGES} thumbnails and would\n"
               f"    be refused. Either raise the server's limit to {PLAN_MAX_IMAGES}, or set PLAN_MAX_IMAGES = {highest} in\n"
               "    backend/app/pipeline/runner.py (smaller batches, more planning calls, same result).")
    else:
        _print(f"  → only {highest} image(s) per request: the critic needs {CRITIC_IMAGES} and would fail on every slide —\n"
               "    which now shows up as critic_status=failed rather than a silent pass. Raise the server's limit,\n"
               "    or set VISION=off to run text-only deliberately.")


def _endpoint_report(label: str, ep, h: dict) -> None:
    """One server's line in `probe`: is it up, what is it serving, and what can it do."""
    mark = "ok" if h.get("ok") else "XX"
    _print(f"\n{mark}  {label:<7} {ep.model}\n    {'':<7} {ep.base_url}")
    bits: list[str] = []
    if h.get("ok"):
        if h.get("max_model_len"):
            bits.append(f"{h['max_model_len'] // 1000}k context")
        if h.get("vision") is not None:
            bits.append("vision on" if h["vision"] else "TEXT ONLY")
    else:
        bits.append(h.get("error") or "no response")
    if bits:
        _print(f"    {'':<7} " + " / ".join(bits))


def _probe_embeddings() -> None:
    """Optional third model: say whether it answers /v1/embeddings, and what it returns."""
    from .llm import embed
    s = settings()
    if not s.embed_model:
        _print("\nembed     off (EMBED_MODEL is empty) — reference documents are searched by shared words only")
        return
    t0 = time.perf_counter()
    got = embed.embed(["GPU queues delay experiments", "Owning the fleet lowers lifetime cost"])
    if got is None:
        _print(f"\n!  embed   {s.embed_model} did not answer /v1/embeddings at {s.embed_base_url or s.llm_base_url}.\n"
               "           It must be served as an embedding model (vLLM: --runner pooling --convert embed), not as a\n"
               "           chat model. Until then document search falls back to shared words; nothing else is affected.")
        return
    _print(f"\n✓  embed   {s.embed_model}\n           {len(got[0])} dimensions"
           f"{f' (cut to EMBED_DIM={s.embed_dim})' if s.embed_dim else ''}, 2 texts in {time.perf_counter() - t0:.2f}s")


async def probe() -> int:
    from .config import Role
    from .llm import client as llm
    from .pipeline import prompts
    from .skillpack import examples
    from .spec import parse_spec

    s = settings()
    _print(f"mock      {s.llm_mock}\nrenderer  {s.renderer}   vision {s.vision}   guided_json {s.guided_json}")
    _print("stages    " + "  ".join(
        f"{name}(think={'y' if st.thinking else 'n'}" + (f",temp={st.temperature})" if st.temperature is not None else ")")
        for name, st in s.stages.items()))

    author, review = s.endpoint(Role.author), s.endpoint(Role.review)
    if s.split_endpoints:
        _print("\ntwo models: authoring and review are separate engines, so each keeps its own hot prefix cache")
    else:
        _print("\none model: authoring and review share it, so their two system prefixes compete for one KV cache.\n"
               "Set VLM_MODEL (and VLM_BASE_URL if it is on another server) to split them.")

    hs = await llm.health_all()
    _endpoint_report("author", author, hs["author"])
    if s.split_endpoints:
        _endpoint_report("review", review, hs["review"])

    h = hs["author"]
    if not h["ok"]:
        _print("\n✗ Authoring endpoint not usable. Check Tailscale (`tailscale status`), the vLLM server "
               "and LLM_MODEL in .env.")
        return 1
    if s.split_endpoints and not hs["review"]["ok"]:
        _print("\n! The review endpoint is down. Slides still generate, but with no critic, no repair loop driven by\n"
               "  it and no A/B verdict — every deck ships unreviewed. Check VLM_MODEL is served.")
    if h.get("mock"):
        # health() answers ok for the mock, but everything below this point is a live call: probing the
        # template generator would measure nothing and fail on the first connection attempt.
        _print("\n! LLM_MOCK is on, so there is nothing to probe. Unset it (or drop --mock) to test the GB300.")
        return 0
    if h.get("max_model_len") and h["max_model_len"] < 48000:
        _print(f"! author max_model_len={h['max_model_len']} is small: the system prompt is ~17k tokens and replies "
               f"up to {s.llm_max_tokens}. Use ≥ 64k.")
    rl = hs["review"].get("max_model_len")
    if s.split_endpoints and rl and rl < 24000:
        _print(f"! review max_model_len={rl} is small for a critic carrying three 1600x900 screenshots. Use ≥ 32k.")
    # The image ceiling that matters is the one on the server that actually sends images.
    await probe_image_limit(hs["review"] if s.split_endpoints else h)
    _probe_embeddings()
    ex = examples()[1]
    msgs = prompts.generate_messages(variant=ex.variant, position=2, total=10, brief={"deck_title": "Probe"}, plan={"pattern": "cards", "headline": "Probe"},
                                     content=ex.input["source"], prev_plan=None, next_plan=None, source_png=None, vision=False)
    for label in ("cold", "warm (prefix cache)"):
        t0 = time.perf_counter()
        r = await llm.chat(msgs, temperature=0.5, thinking=False, max_tokens=4000, stage="probe")
        dt = time.perf_counter() - t0
        tps = r.completion_tokens / dt if dt else 0
        try:
            spec, issues = parse_spec(r.text, "probe")
            ok = f"parsed ✓ (steps={spec.meta.steps}, {len(spec.html)} chars html, {len(issues)} issues)"
        except ValueError as e:
            ok = f"parse ✗ {e}"
        _print(f"{label:<22} {dt:6.1f}s  prompt={r.prompt_tokens} out={r.completion_tokens} ({tps:.0f} tok/s)  {ok}")
    return 0


async def run(pptx: Path, slides: str | None, out: Path | None) -> int:
    from .pipeline import runner
    from .store import db
    from .store.db import Project

    p = db.save(Project(name=pptx.stem, filename=pptx.name))
    shutil.copy2(pptx, db.project_dir(p.id) / "source.pptx")
    t0 = time.perf_counter()
    _print(f"project {p.id}: importing {pptx.name}")
    await runner.ingest(p.id)
    p = db.get(Project, p.id)
    if p.status == "error":
        _print("import failed:", p.error)
        return 1
    all_slides = db.slides_of(p.id)
    _print(f"planned {len(all_slides)} slides in {time.perf_counter() - t0:.0f}s — {p.brief.get('narrative', '')[:120]}")
    ids = None
    if slides:
        want = {int(x) for x in slides.split(",")}
        ids = [s.id for s in all_slides if s.index in want]
    await runner.generate_project(p.id, ids)
    for s in db.slides_of(p.id):
        for v in db.versions_of_slide(s.id):
            # Read the payload through the model rather than by hand: it is the pipeline's dict, and a
            # field that has changed shape should be reported once, not become a KeyError here.
            qa = db.QaReport.of(v.qa, version_id=v.id)
            errs = sum(1 for f in qa.findings if f.get("severity") == "error")
            pick = " *judge" if qa.ab and qa.ab.recommended else ""
            _print(f"  slide {s.index:>2} {v.lineage}  {v.status:<7} score={v.score}  errors={errs}  "
                   f"repairs={v.repairs}  llm={v.llm.get('seconds')}s{pick}")
    html, stats = runner.build_deck(p.id, fill_unapproved=True)
    out = out or (ROOT_DIR / "data" / f"{pptx.stem}.html")
    out.write_text(html, encoding="utf-8")
    _print(f"deck → {out} ({len(html) // 1024} KB, {stats}) in {time.perf_counter() - t0:.0f}s")
    return 0


def examples_deck() -> int:
    from .assemble import DeckInput, DeckSlide, assemble
    from .skillpack import examples
    from .spec import parse_spec

    slides = [DeckSlide(id=f"ex{i + 1}", spec=parse_spec(e.output, f"ex{i + 1}")[0]) for i, e in enumerate(examples())]
    html = assemble(DeckInput(title="HP Deck Skill — gold examples", slides=slides, assets={p.stem: p for p in (RUNTIME_DIR / "img").iterdir()}))
    out = ROOT_DIR / "data" / "gold_examples.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    _print(f"→ {out}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe", help="check the GB300 endpoint, vision, output format and speed")
    r = sub.add_parser("run", help="run the whole pipeline on a .pptx without the UI")
    r.add_argument("pptx", type=Path)
    r.add_argument("--slides", help="comma-separated 1-based slide numbers")
    r.add_argument("--out", type=Path)
    sub.add_parser("examples", help="build a deck from the gold examples in skill/examples")
    a = ap.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "probe":
        sys.exit(asyncio.run(probe()))
    if a.cmd == "run":
        sys.exit(asyncio.run(run(a.pptx.resolve(), a.slides, a.out)))
    sys.exit(examples_deck())


if __name__ == "__main__":
    main()
