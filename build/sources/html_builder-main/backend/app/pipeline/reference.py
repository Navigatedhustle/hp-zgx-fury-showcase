"""Reference documents in the pipeline: the digest job, what the planner, the generator and the outline draft are
shown, and the gate a figure from a document must pass before it joins a slide's fact ledger. See app/docs.py
for parsing, sections and chunks.

Nothing of a document is dropped for being far into it: every section is digested, the planner reads all of
those digests and can point a slide at the sections it draws on, and the generator is given passages from them.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .. import docs, facts
from ..config import settings
from ..llm import client as llm
from ..llm import embed
from ..skillpack import read
from ..store import db
from ..store.db import Project, ProjectDoc, Slide
from . import prompts

log = logging.getLogger(__name__)

DIGEST_INPUT_CHARS = 60_000   # ~15k tokens: a document this size is digested whole; a longer one from its sections
DIGEST_TOKENS = 1200
SECTION_TOKENS = 500
PLANNER_CHARS = 28_000        # ~7k tokens of digests and section notes in the planner's message, all documents together
FULL_SECTIONS = 8             # in a scoped (per-batch) planner message, the sections shown with their figures
EXCERPTS_PER_SLIDE = 4
EXCERPT_CHARS = 6500
SEMANTIC_FLOOR = 0.35         # cosine below this is "about something else" for retrieval models; such a chunk is not a hit
_RRF = 60


def _done(pid: str) -> None:
    from .runner import emit
    emit(pid, "slides")


# ------------------------------------------------------------------ digest
async def _ask(template: str, name: str, body: str, max_tokens: int, **fill: str) -> str:
    msg = read(template).replace("{{NAME}}", name).replace("{{TEXT}}", body)
    for k, v in fill.items():
        msg = msg.replace("{{" + k + "}}", v)
    r = await llm.chat([prompts._system(), prompts._user(msg)], temperature=0.2, max_tokens=max_tokens, stage="doc_digest")
    return r.text.strip()


async def _section_digest(name: str, sec: docs.Section, total: int) -> str:
    try:
        return await _ask("doc_section.md", name, sec.text, SECTION_TOKENS,
                          WHERE=f"section {sec.n} of {total}" + (f", {sec.where}" if sec.where else ""))
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 - one unread section must not cost the whole document
        log.warning("section %d of %s was not digested: %s", sec.n, name, e)
        return ""


def _section_notes(secs: list[docs.Section], digests: list[str]) -> str:
    return "\n\n".join(f"### Section {s.n}{f' ({s.where})' if s.where else ''}: {s.title}\n{d}"
                       for s, d in zip(secs, digests) if d)


def index_doc(pdir: Path, doc_id: str, text: docs.DocText) -> bool:
    """Embed the document's chunks and store the vectors. False (and nothing written) when embeddings are off or
    the server did not answer — retrieval then ranks this document by words."""
    name = embed.model()
    cs = docs.chunks(text)
    if not name or not cs:
        return False
    vecs = embed.embed([f"{c.heading}\n{c.text}" if c.heading else c.text for c in cs])
    if vecs is None:
        return False
    docs.save_vectors(pdir, doc_id, name, [list(v) for v in vecs])
    return True


async def digest_doc(doc_id: str) -> None:
    """Read one document for the planner: a digest of every section (one author-model call each, when there is
    more than one), then the document's own ≤600-word digest — from the whole text when that fits one call,
    otherwise from the section digests, so the end of a long document counts as much as its start."""
    d = await asyncio.to_thread(db.get, ProjectDoc, doc_id)
    if d is None:
        return
    pdir = db.project_dir(d.project_id)
    text = await asyncio.to_thread(docs.load_text, pdir, doc_id)
    try:
        if text is None:
            raise ValueError("the document's text is missing")
        secs = docs.sections(text)
        many = len(secs) > 1
        if settings().llm_mock:
            notes = [s.text[:300] for s in secs] if many else []
            digest = "PURPOSE: (offline mock — the start of the document)\n" + text.text[:2000]
        else:
            notes = list(await asyncio.gather(*(_section_digest(d.name, s, len(secs)) for s in secs))) if many else []
            if len(text.text) <= DIGEST_INPUT_CHARS:
                digest = await _ask("doc_digest.md", d.name, text.text, DIGEST_TOKENS)
            elif not any(notes):
                raise ValueError("none of the document's sections could be read")
            else:
                body = ("[The document is too long to show whole. These are notes on each of its sections, in "
                        "order; every figure in them is copied exactly from the document.]\n\n" + _section_notes(secs, notes))
                digest = await _ask("doc_digest.md", d.name, body, DIGEST_TOKENS)
        await asyncio.to_thread(docs.save_section_digests, pdir, doc_id, notes)
        await asyncio.to_thread(index_doc, pdir, doc_id, text)
        await asyncio.to_thread(db.update, ProjectDoc, doc_id, digest=digest[:6000], status="ready", error="")
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("digest failed for %s", doc_id)
        await asyncio.to_thread(db.update, ProjectDoc, doc_id, status="error", error=str(e)[:300])
    _done(d.project_id)


# ------------------------------------------------------------------ what each stage reads
@dataclass
class Indexed:
    """One ready document as the pipeline addresses it: `D<k>` to the planner, its id everywhere it is stored."""
    k: int
    doc: ProjectDoc
    text: docs.DocText

    @property
    def handle(self) -> str:
        return f"D{self.k}"


@lru_cache(maxsize=64)
def _parsed(path: str, mtime_ns: int) -> tuple[docs.DocText, tuple[docs.Section, ...], tuple[docs.Chunk, ...]]:
    """A document's text, sections and chunks, parsed once per file version — every slide of a deck asks for them."""
    text = docs.DocText(pages=Path(path).read_text(encoding="utf-8").split(docs.PAGE_BREAK))
    return text, tuple(docs.sections(text)), tuple(docs.chunks(text))


def _of(pdir: Path, doc_id: str) -> tuple[docs.DocText, tuple[docs.Section, ...], tuple[docs.Chunk, ...]] | None:
    p = docs.text_path(pdir, doc_id)
    try:
        return _parsed(str(p), p.stat().st_mtime_ns)
    except OSError:
        return None


@lru_cache(maxsize=64)
def _numbers(path: str, mtime_ns: int) -> tuple:
    """Every figure the document states — what a reworded quote is aligned against."""
    return tuple(facts.parse_numbers(Path(path).read_text(encoding="utf-8")))


def by_authority(items: list[Indexed]) -> list[Indexed]:
    """Primary documents first, then the most recently added: where two state a figure, that is whose it is."""
    return sorted(items, key=lambda x: (not x.doc.primary, -x.k))


def indexed(project_id: str) -> list[Indexed]:
    """The project's documents that have text, numbered in the order the user added them."""
    pdir = db.project_dir(project_id)
    out = []
    for k, d in enumerate(db.docs_of(project_id), 1):
        got = _of(pdir, d.id)
        if got is not None:
            out.append(Indexed(k=k, doc=d, text=got[0]))
    return out


def _summary_only(note: str) -> str:
    """A section note without its FIGURES list — what is left when the planner's message is running out of room."""
    head = note.split("FIGURES:")[0].replace("SUMMARY:", "").strip()
    return head[:300]


def _figures(project_id: str) -> list[tuple[Indexed, facts.Fact]]:
    """Each document's figures as its digest and section notes list them: one labelled fact per FIGURES line."""
    pdir = db.project_dir(project_id)
    out = []
    for x in indexed(project_id):
        text = "\n".join([x.doc.digest or "", *docs.load_section_digests(pdir, x.doc.id)])
        lines = [ln.strip("-• ").strip() for ln in text.splitlines() if ln.lstrip().startswith(("-", "•")) and "—" in ln]
        for f in facts.extract({"text": [{"lines": lines}]}):
            if f.kind == "number" and f.value is not None and f.unit != "plain":
                out.append((x, f))
    return out


def conflicts(project_id: str) -> list[dict]:
    """One quantity, two values, in two documents — an RFP and the addendum that amends it. Found the way the
    deck's own consistency check finds it across slides: same unit, the same identifying words around the figure,
    a different magnitude. `use` names the document to believe when the user marked one as primary."""
    seen: dict[tuple, tuple[Indexed, facts.Fact]] = {}
    out: list[dict] = []
    for x, f in _figures(project_id):
        words = " ".join(sorted(set(re.findall(r"[a-z]{4,}", f.label.lower()))))
        if len(words.split()) < 2:
            continue
        key = (words, f.unit)
        first = seen.setdefault(key, (x, f))
        if first[0].k != x.k and abs(first[1].value - f.value) > 1e-9 * max(1.0, abs(f.value)):
            a, b = by_authority([first[0], x])
            item = {"label": f.label.strip(), "values": [{"doc": first[0].doc.name, "value": first[1].raw},
                                                           {"doc": x.doc.name, "value": f.raw}],
                    "use": a.doc.name if a.doc.primary and not b.doc.primary else ""}
            if item not in out:
                out.append(item)
    return out[:8]


def planner_reference(project_id: str, focus: str = "") -> str:
    """Every document's digest and, for a long one, a line per section the planner can point a slide at
    (`doc_refs`). For the planner's user message; empty when the deck has no reference documents.

    `focus` is the text of the slides one planning batch covers. With it, only the sections that bear on those
    slides carry their full notes and figures; the rest are a line each. A deck planned in four batches then
    reads each section's detail once, where it is needed, instead of four times.
    """
    pdir = db.project_dir(project_id)
    ready = [x for x in indexed(project_id) if x.doc.status == "ready" and x.doc.digest]
    entries = [(x, s, n) for x in ready
               for s, n in zip(_of(pdir, x.doc.id)[1], docs.load_section_digests(pdir, x.doc.id) or [])
               if len(_of(pdir, x.doc.id)[1]) > 1]
    full: set[tuple[int, int]] | None = None
    if focus and len(entries) > FULL_SECTIONS:
        pool = [("", docs.Chunk(page=0, text=n, words=docs.words(f"{s.title} {n}"))) for _, s, n in entries]
        score = docs.lexical(pool, focus, min_hits=1)
        full = {(entries[i][0].k, entries[i][1].n) for i in sorted(score, key=lambda i: -score[i])[:FULL_SECTIONS]}

    def render(brief: bool) -> str:
        parts = []
        for x in by_authority(ready):
            tag = " — PRIMARY: where documents disagree, this one is right" if x.doc.primary else ""
            block = f"### {x.handle} — {x.doc.name}{tag}\n{x.doc.digest.strip()}"
            lines = []
            for y, s, n in entries:
                if y.k != x.k:
                    continue
                short = brief or (full is not None and (x.k, s.n) not in full)
                body = (_summary_only(n) if short else n.strip()).replace("\n", "\n  ")
                lines.append(f"- {x.handle}.S{s.n}{f' ({s.where})' if s.where else ''} “{s.title}”\n  {body}".rstrip())
            if lines:
                block += f"\n\nSections of {x.handle} — name the ones a slide draws on in its `doc_refs`:\n" + "\n".join(lines)
            parts.append(block)
        clash = conflicts(project_id)
        if clash:
            rows = [f"- {c['label']}: " + " vs ".join(f"{v['value']} ({v['doc']})" for v in c["values"])
                    + (f" — use {c['use']}" if c["use"] else "") for c in clash]
            parts.append("### Where the documents disagree\nDo not put either figure of a pair in `doc_facts` unless one "
                         "document is marked PRIMARY — then use its figure.\n" + "\n".join(rows))
        return "\n\n".join(parts)

    out = render(brief=False)
    if len(out) > PLANNER_CHARS:
        out = render(brief=True)
    if len(out) > PLANNER_CHARS:
        out = out[:PLANNER_CHARS].rstrip() + "\n[… the remaining section notes are not shown …]"
    return out


def resolve_refs(project_id: str, raw: list | None) -> list[str]:
    """The planner's `doc_refs` ("D2.S3", or "D2" for a whole short document) as stored references `<doc id>:<n>`
    (n = 0 for the whole document). Stored by id so removing another document cannot repoint them; anything
    that names no real section is dropped."""
    by_handle = {x.handle: x for x in indexed(project_id)}
    pdir = db.project_dir(project_id)
    out: list[str] = []
    for item in raw or []:
        doc_part, _, sec_part = str(item).strip().upper().partition(".")
        x = by_handle.get(doc_part)
        if x is None:
            continue
        n = int(sec_part[1:]) if sec_part.startswith("S") and sec_part[1:].isdigit() else 0
        if n > len(_of(pdir, x.doc.id)[1]):
            continue
        ref = f"{x.doc.id}:{n}"
        if ref not in out:
            out.append(ref)
    return out[:4]


def _vectors(pdir: Path, doc_id: str, text: docs.DocText, n: int) -> list | None:
    """This document's chunk vectors — indexing it now if an embedding model was configured after it was added."""
    name = embed.model()
    if not name:
        return None
    got = docs.load_vectors(pdir, doc_id, name, n)
    if got is None and index_doc(pdir, doc_id, text):
        got = docs.load_vectors(pdir, doc_id, name, n)
    return got


def slide_reference(project_id: str, plan: dict, content: dict, extra: str = "") -> str:
    """The few document passages that bear on one slide, for its generation or revision prompt.

    Three signals, fused by rank: the sections the planner named for this slide (`plan.doc_refs`), words shared
    with the slide, and — when an embedding model is configured — closeness in meaning. `extra` is anything else
    that says what is wanted, such as the presenter's comment on a revision.
    """
    pdir = db.project_dir(project_id)
    pool: list[tuple[str, docs.Chunk]] = []
    owner: list[str] = []
    vectors: list = []
    for x in indexed(project_id):
        cs = _of(pdir, x.doc.id)[2]
        vs = _vectors(pdir, x.doc.id, x.text, len(cs))
        pool += [(x.doc.name, c) for c in cs]
        owner += [x.doc.id] * len(cs)
        vectors += vs if vs is not None else [None] * len(cs)
    if not pool:
        return ""
    asked = " ".join(str(v) for v in (plan.get("headline", ""), plan.get("key_message", ""), extra) if v)
    query = f"{asked} {prompts._dump(content)}"
    refs = {str(r) for r in plan.get("doc_refs") or []}
    preferred = {i for i, (_, c) in enumerate(pool) if f"{owner[i]}:{c.section}" in refs or f"{owner[i]}:0" in refs}

    score: dict[int, float] = {}

    def add(ranked: list[int]) -> None:
        for rank, i in enumerate(ranked):
            score[i] = score.get(i, 0.0) + 1.0 / (_RRF + rank)

    strict = docs.lexical(pool, query, min_hits=2)
    add(sorted(strict, key=lambda i: -strict[i]))
    if any(v is not None for v in vectors):
        qv = embed.embed([f"{asked} {content.get('title', '')}".strip()[:1000] or query[:1000]], query=True)
        if qv:
            sims = {i: embed.cosine(qv[0], v) for i, v in enumerate(vectors) if v is not None}
            add(sorted((i for i, c in sims.items() if c >= SEMANTIC_FLOOR), key=lambda i: -sims[i])[:20])
    sem = set(score) - set(strict)
    if preferred:
        # A named section leads — the planner read its notes and chose it — but through its best passages, not
        # all of them: the two that share most with the slide (one shared word is enough here), or its opening
        # when none shares anything.
        loose = docs.lexical(pool, query, min_hits=1)
        by_ref: dict[str, list[int]] = {}
        for i in sorted(preferred):
            by_ref.setdefault(f"{owner[i]}:{pool[i][1].section}", []).append(i)
        lead: set[int] = set()
        for members in by_ref.values():
            hit = sorted((i for i in members if i in loose or i in sem), key=lambda i: (-loose.get(i, 0.0), i))
            lead.update(hit[:2] or members[:1])
        for i in lead:
            score[i] = score.get(i, 0.0) + 1.0 / 30
        preferred = lead

    ranked = sorted(score, key=lambda i: (-score[i], i))
    # Named sections never take every place: the last one is kept for what the open search found.
    head = ranked[:EXCERPTS_PER_SLIDE - 1]
    rest = [i for i in ranked if i not in head]
    tail = next((i for i in rest if i not in preferred), None) if all(i in preferred for i in head) else None
    order = head + ([tail] if tail is not None else []) + [i for i in rest if i != tail]

    out, used = [], 0
    for i in order:
        name, c = pool[i]
        if len(out) >= EXCERPTS_PER_SLIDE:
            break
        if used + len(c.text) > EXCERPT_CHARS:
            continue
        where = ", ".join(x for x in (name, f"p. {c.page}" if c.page else "") if x)
        out.append(f"[{where}{f' — {c.heading}' if c.heading else ''}]\n{c.text}")
        used += len(c.text)
    return "\n\n".join(out)


def section_list(project_id: str) -> list[dict]:
    """Every document's sections with a line on each — what the user picks from before drafting an outline."""
    pdir = db.project_dir(project_id)
    out = []
    for x in indexed(project_id):
        secs = _of(pdir, x.doc.id)[1]
        notes = docs.load_section_digests(pdir, x.doc.id)
        notes = notes if len(notes) == len(secs) else [""] * len(secs)
        out.append({"doc_id": x.doc.id, "name": x.doc.name, "primary": bool(x.doc.primary),
                    "sections": [{"ref": f"{x.doc.id}:{s.n}", "n": s.n, "title": s.title, "where": s.where, "chars": len(s.text),
                                  "summary": _summary_only(n) or " ".join(s.text.split())[:200]} for s, n in zip(secs, notes)]})
    return out


def compose_source(project_id: str, limit: int, only: set[str] | None = None) -> str:
    """What an outline is drafted from when the user pasted nothing: the documents themselves while they fit
    `limit`, and for a document that does not, its digest and section notes — the whole of it, summarised,
    rather than the start of it, verbatim.

    `only` narrows it to the sections the user chose (`<doc id>:<n>`): a ten-slide deck from a hundred-page
    brief is about some of it, and the user knows which part. A document with no chosen section is left out.
    The budget goes to the shortest first and what it does not use passes on, so a two-page summary never
    takes room from an eighty-page appendix.
    """
    pdir = db.project_dir(project_id)
    picked: list[tuple[Indexed, list[docs.Section], list[str], bool]] = []
    for x in indexed(project_id):
        secs = list(_of(pdir, x.doc.id)[1])
        notes = docs.load_section_digests(pdir, x.doc.id)
        notes = notes if len(notes) == len(secs) else [""] * len(secs)
        keep = [i for i, s in enumerate(secs) if only is None or f"{x.doc.id}:{s.n}" in only]
        if keep:
            picked.append((x, [secs[i] for i in keep], [notes[i] for i in keep], len(keep) == len(secs)))
    picked.sort(key=lambda t: sum(len(s.text) for s in t[1]))
    parts: dict[int, str] = {}
    left = limit
    for n, (x, secs, notes, whole) in enumerate(picked):
        share = left // (len(picked) - n)
        raw = x.text.text if whole else "\n\n".join(f"## {s.title}{f' ({s.where})' if s.where else ''}\n{s.text}" for s in secs)
        if len(raw) <= share:
            body = raw
        else:
            summary = "\n\n".join(p for p in (x.doc.digest.strip() if whole else "", _section_notes(secs, notes)) if p)
            body = (("[Too long to include whole — summarised section by section; figures are copied exactly.]\n\n" + summary)[:share]
                    if summary else raw[:share])
        parts[x.k] = f"# {x.doc.name}{'' if whole else ' (selected sections)'}\n{body}"
        left -= len(body)
    return "\n\n".join(parts[k] for k in sorted(parts))


# ------------------------------------------------------------------ the gate
def doc_facts(project_id: str, quotes: list, prefix: str, rejected: list[str] | None = None,
              adopted: list[str] | None = None) -> tuple[list[facts.Fact], list[str]]:
    """Turn the planner's `doc_facts` into key ledger facts, keeping only what a document really states.

    Returns the facts and the source lines to cite ("Whitepaper.pdf, p. 4"). Three ways in, tried in order:

    - the quote is in a document word for word (case, spacing and line breaks aside);
    - its figures are — the same values in the same units, written differently ("$4.2 million" for "$4.2M").
      The ledger then takes the *document's* wording, and the swap is appended to `adopted`;
    - neither: dropped, and appended to `rejected`. The planner may bring a figure in from the reference, but
      it may not bring one in from nowhere.

    A verbatim quote with no figure or name in it joins the ledger as a claim, checked by its wording.
    Where two documents state it, the primary one (else the newest) is the one cited.
    """
    pdir = db.project_dir(project_id)
    order = by_authority(indexed(project_id))
    out: list[facts.Fact] = []
    cites: list[str] = []
    for i, q in enumerate(str(x).strip() for x in quotes or []):
        if not q:
            continue
        home = next((x for x in order if docs.contains(x.text.text, q)), None)
        line = q
        if home is None:
            for x in order:
                p = docs.text_path(pdir, x.doc.id)
                line = facts.align_numbers(q, _numbers(str(p), p.stat().st_mtime_ns)) or ""
                if line:
                    home = x
                    if adopted is not None and line != q:
                        adopted.append(f"“{q[:60]}” → “{line[:60]}” ({x.doc.name})")
                    break
        if home is None:
            if rejected is not None:
                rejected.append(q)
            continue
        found = facts.extract({"text": [{"lines": [line]}]}, prefix=f"{prefix}{i}_")
        if not found and line == q and len(q.split()) >= 3:
            found = [facts.Fact(id=f"{prefix}{i}_c", kind="claim", raw=q[:240], label=q[:240])]
        if not found:
            if rejected is not None:
                rejected.append(q)
            continue
        anchor = found[0].raw if line != q else q
        page = docs.page_of(home.text, anchor)
        cite = f"{home.doc.name}{f', p. {page}' if page else ''}"
        for f in found:
            f.origin = "doc"
            f.tier = "key"
            f.label = f.label or q
            f.doc, f.cite = home.doc.id, cite
        out += found
        if cite not in cites:
            cites.append(cite)
    return out, cites


def forget_doc(project_id: str, doc_id: str, name: str) -> list[Slide]:
    """A document has been removed: take what it gave the deck back out. Its figures leave every slide's ledger,
    its citation and section references leave the plans — and a slide that had a design is marked, because that
    design may still show a figure nothing now stands behind. Returns the slides so marked."""
    from .runner import DOC_REFS_KEY, DOC_SOURCES_KEY, DOC_STALE_KEY

    left = [x for x in indexed(project_id) if x.doc.id != doc_id]
    marked: list[Slide] = []
    for s in db.slides_of(project_id):
        ledger = facts.load(s.facts)
        # A fact stored before facts carried their document: it goes unless another document still states it.
        gone = [f for f in ledger if f.origin == "doc"
                and (f.doc == doc_id or (not f.doc and not any(docs.contains(x.text.text, f.raw) for x in left)))]
        plan = dict(s.plan or {})
        refs = [r for r in plan.get(DOC_REFS_KEY) or [] if not str(r).startswith(f"{doc_id}:")]
        cited = [c for c in plan.get(DOC_SOURCES_KEY) or [] if not (c == name or str(c).startswith(f"{name}, p."))]
        if not gone and refs == (plan.get(DOC_REFS_KEY) or []) and cited == (plan.get(DOC_SOURCES_KEY) or []):
            continue
        for key, value in ((DOC_REFS_KEY, refs), (DOC_SOURCES_KEY, cited)):
            if value:
                plan[key] = value
            else:
                plan.pop(key, None)
        fields: dict = {"plan": plan}
        if gone:
            fields["facts"] = facts.dump([f for f in ledger if f not in gone])
            if db.versions_of_slide(s.id):
                plan[DOC_STALE_KEY] = {"at": db.now().isoformat(), "doc": name, "figures": [f.raw for f in gone][:6]}
                marked.append(s)
        db.update(Slide, s.id, **fields)
    if marked:
        p = db.get(Project, project_id)
        which = ", ".join(str(s.position) for s in marked[:12]) + ("…" if len(marked) > 12 else "")
        note = (f"“{name}” was removed, and {len(marked)} slide(s) had figures from it (slides {which}). Their "
                "designs may still show those figures — redesign them, or add the document back.")
        db.update(Project, project_id, warnings=[*((p.warnings if p else None) or []), note])
    return marked
