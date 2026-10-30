"""Full-text search over every library slide (SQLite FTS5).

The interface ingest and tagging call is fixed — `reindex`, `reindex_deck`, `drop` — and they never need to know
how the index works. Everything else here is the query language and `GET /search`.

Two FTS5 tables, written together, keyed by the same integer rowid (`lib_search_rid` maps it to the slide id):
  lib_fts   unicode61 words, prefix-indexed. Ranked with bm25 and per-column weights (`WEIGHTS`). This is the index
            that answers almost every query: FTS5 tokenises a quoted query string exactly as it tokenised the slide,
            so "ZGX-Fury", "$4.2M" and "Q3 2026" become phrases ("zgx fury", "4 2m", "q3 2026") and match.
  lib_tri   trigram, same columns. Finds what a word index cannot: a piece of a word ("station" in "Workstations",
            "Fury" in "ZGXFury", part of a part number). Needs 3+ characters.
How they combine (`_match`): a slide matches when *every* required term matches it in either index. Slides where
every term matched as a word (a word prefix, or its plural/singular) rank first, by weighted bm25 plus bonuses for
words on the slide itself rather than only on its deck, the exact word, and the terms side by side; slides that
needed a substring for some term rank after them, by trigram bm25. A whole-word hit is a stronger signal than a
hit mid-word, and union-then-tier keeps substring matches findable without letting "art" in "start" outrank a
slide about art. If nothing matches every term, the query is relaxed to any term (`relaxed: true` in the
response) rather than showing an empty page for a stray word. evals/library/ measures all of this.

Filters, facets, duplicate collapse and sorting run in Python over one narrow row per candidate slide, read from
a covering index (`lib_search_cover`). That keeps every facet exact (each counted with every filter but its own);
on 10k slides a query matching most of them takes ~50-100 ms, a selective one ~5-30 ms (test_library_search.py
prints the numbers).
"""
from __future__ import annotations

import html
import json
import logging
import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterator

from fastapi import APIRouter, Query
from sqlmodel import select

from ..store import db
from ..store.db import LibDeck, LibSlide, LibTag
from . import semantic
from .fingerprint import also_in_counts
from .schema import slide_out

log = logging.getLogger(__name__)
router = APIRouter()

# Indexed columns in table order (rowid = lib_search_rid.rid) and their bm25 weights.
COLUMNS = ("project", "deck_title", "filename", "title", "text", "notes", "summary", "tags", "entities")
WEIGHTS = {"title": 8, "project": 6, "tags": 5, "entities": 4, "summary": 3, "deck_title": 3,
           "text": 1, "notes": 0.5, "filename": 1}
_BM25_ARGS = ", ".join(str(WEIGHTS[c]) for c in COLUMNS)
# The slide's own columns (not its deck's) — an FTS5 column filter for the "on the slide itself" bonus.
_OWN = "{title text notes summary tags entities}"
SCHEMA = "1"   # bump when the tables or tokenizers change: the index is dropped and rebuilt on next use

MAX_Q = 500          # characters of q considered
MAX_TERMS = 16       # text terms considered
MAX_LIMIT = 200
FACET_TOP = 40       # values per facet (selected values are always kept)
SNIPPET_CHARS = 180

# Small words that would make an AND query fail for no reason ("risk of printers"). Dropped from the required
# terms when something else is left; kept inside "quoted phrases".
STOPWORDS = frozenset(
    "a an and are as at be by for from in into is it of on or our the their this to vs was we with your".split())

BY_MEANING = 1.5   # the tier of a slide found only by meaning (library/semantic.py): between "contains the words"
                   # (0, 1) and "shares one of them" (2, 3)

_ensured: set[int] = set()   # id(engine) for which the tables exist and the index has been reconciled
_lock = threading.Lock()


# ------------------------------------------------------------------ index maintenance

@contextmanager
def _conn() -> Iterator[Any]:
    """A raw sqlite3 connection from the app's pool, committed on success."""
    raw = db.engine().raw_connection()
    try:
        yield raw.driver_connection
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def _ensure() -> None:
    """Create the FTS tables once per engine, and bring the index in line with the slide table: a restore, a crash
    between a write and its reindex, or a database from before search existed all heal on first use."""
    eng = db.engine()
    if id(eng) in _ensured:
        return
    with _lock:
        if id(eng) in _ensured:
            return
        cols = ", ".join(COLUMNS)
        with _conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS lib_search_meta (k TEXT PRIMARY KEY, v TEXT)")
            v = c.execute("SELECT v FROM lib_search_meta WHERE k = 'schema'").fetchone()
            if v is None or v[0] != SCHEMA:
                for t in ("lib_fts", "lib_tri", "lib_search_rid"):
                    c.execute(f"DROP TABLE IF EXISTS {t}")
                c.execute("INSERT OR REPLACE INTO lib_search_meta (k, v) VALUES ('schema', ?)", (SCHEMA,))
            c.execute("CREATE TABLE IF NOT EXISTS lib_search_rid (rid INTEGER PRIMARY KEY, slide_id TEXT NOT NULL UNIQUE)")
            c.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS lib_fts USING fts5({cols}, "
                      "tokenize='unicode61 remove_diacritics 2', prefix='2 3')")
            c.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS lib_tri USING fts5({cols}, tokenize='trigram')")
            c.execute(semantic.TABLE)
            c.execute('CREATE INDEX IF NOT EXISTS lib_search_cover ON libslide '
                      '(id, deck_id, "index", slide_type, favourite, phash, text_sha, created_at, tags, entities)')
            have = {r[0] for r in c.execute("SELECT slide_id FROM lib_search_rid")}
            want = {r[0] for r in c.execute("SELECT id FROM libslide")}
        _ensured.add(id(eng))
        if have - want:
            drop(sorted(have - want))
        if want - have:
            log.info("library search: indexing %d slides", len(want - have))
            reindex(sorted(want - have))


def _tag_text(slugs: list[str], tags: dict[str, LibTag]) -> str:
    out: list[str] = []
    for slug in slugs or []:
        t = tags.get(slug)
        out += [t.label, slug, *(t.aliases or [])] if t else [slug]
    return " ".join(out)


def _entity_text(entities: list[Any]) -> str:
    return " ".join(str(e.get("name", "")) if isinstance(e, dict) else str(e) for e in entities or [])


def reindex(slide_ids: list[str]) -> None:
    """(Re)write the index rows for these slides from their current LibSlide + LibDeck rows. Idempotent.
    An id with no LibSlide row is dropped from the index."""
    ids = list(dict.fromkeys(i for i in slide_ids if i))
    if not ids:
        return
    _ensure()
    with db.session() as s:
        slides = list(s.exec(select(LibSlide).where(LibSlide.id.in_(ids))))
        decks = {d.id: d for d in s.exec(select(LibDeck).where(LibDeck.id.in_({x.deck_id for x in slides})))}
        slugs = {t for x in slides for t in (x.tags or [])}
        tags = {t.slug: t for t in s.exec(select(LibTag).where(LibTag.slug.in_(slugs)))} if slugs else {}
    found = {x.id for x in slides}
    rows = []
    for x in slides:
        d = decks.get(x.deck_id)
        rows.append((x.id, (d.project if d else "", d.title if d else "", d.filename if d else "",
                            x.title, x.text, x.notes, x.summary, _tag_text(x.tags, tags), _entity_text(x.entities))))
    ph = ", ".join("?" * len(COLUMNS))
    with _conn() as c:
        for sid, values in rows:
            c.execute("INSERT OR IGNORE INTO lib_search_rid (slide_id) VALUES (?)", (sid,))
            rid = c.execute("SELECT rid FROM lib_search_rid WHERE slide_id = ?", (sid,)).fetchone()[0]
            for table in ("lib_fts", "lib_tri"):
                c.execute(f"DELETE FROM {table} WHERE rowid = ?", (rid,))
                c.execute(f"INSERT INTO {table} (rowid, {', '.join(COLUMNS)}) VALUES (?, {ph})", (rid, *values))
    gone = [i for i in ids if i not in found]
    if gone:
        drop(gone)


def reindex_deck(deck_id: str) -> None:
    """Every slide of one deck — after a rename, a re-date, or supersede."""
    with db.session() as s:
        ids = list(s.exec(select(LibSlide.id).where(LibSlide.deck_id == deck_id)))
    reindex(ids)


def reindex_all() -> None:
    """Every slide — after a tag's label or aliases change, or a restore."""
    with db.session() as s:
        ids = list(s.exec(select(LibSlide.id)))
    reindex(ids)


def drop(slide_ids: list[str]) -> None:
    """Remove these slides from the index (called before their rows are deleted)."""
    ids = [i for i in slide_ids if i]
    if not ids:
        return
    _ensure()
    with _conn() as c:
        for sid in ids:
            r = c.execute("SELECT rid FROM lib_search_rid WHERE slide_id = ?", (sid,)).fetchone()
            if r is None:
                continue
            c.execute("DELETE FROM lib_fts WHERE rowid = ?", (r[0],))
            c.execute("DELETE FROM lib_tri WHERE rowid = ?", (r[0],))
            c.execute("DELETE FROM lib_search_rid WHERE rid = ?", (r[0],))
    semantic.forget(ids)


# ------------------------------------------------------------------ the query language

FIELDS = {"project", "tag", "type", "deck", "entity", "origin", "is"}
_WORD = re.compile(r"\w", re.UNICODE)


@dataclass
class Term:
    text: str              # as typed (no quotes)
    phrase: bool = False   # came from "quotes"
    prefix: bool = True    # also match words starting with it


@dataclass
class Parsed:
    terms: list[Term] = field(default_factory=list)       # required (AND)
    optional: list[Term] = field(default_factory=list)    # stopwords dropped from the AND; used when relaxing
    negated: list[Term] = field(default_factory=list)
    filters: list[tuple[str, str, bool]] = field(default_factory=list)  # (field, value, negated)
    typed: list[Term] = field(default_factory=list)       # terms + optional, in the order typed

    @property
    def highlight(self) -> list[Term]:
        return self.terms + self.optional


def _scan(q: str) -> Iterator[tuple[bool, str | None, str, bool]]:
    """Yield (negated, field, value, quoted) from q. Never raises: an unmatched quote runs to the end."""
    i, n = 0, len(q)
    while i < n:
        if q[i].isspace():
            i += 1
            continue
        neg = False
        if q[i] == "-" and i + 1 < n and not q[i + 1].isspace():
            neg, i = True, i + 1
        key = None
        m = re.match(r"([A-Za-z]+):(?=\S)", q[i:])
        if m and m.group(1).lower() in FIELDS:
            key, i = m.group(1).lower(), i + m.end()
        if i < n and q[i] == '"':
            j = q.find('"', i + 1)
            j = n if j < 0 else j
            yield neg, key, q[i + 1:j], True
            i = j + 1
        else:
            j = i
            while j < n and not q[j].isspace():
                j += 1
            yield neg, key, q[i:j], False
            i = j


def parse(q: str) -> Parsed:
    """`"exact phrase"`, `project:x` / `tag:x` / `type:x` / `deck:x` / `entity:x` / `origin:x` (quotes allowed in
    the value), `is:fav`, and `-` before any of them to exclude. Unknown `key:value` is plain text (so "10:30"
    and "http://..." search as typed). Any string parses."""
    p = Parsed()
    raw: list[tuple[bool, str, bool]] = []
    for neg, key, value, quoted in _scan((q or "")[:MAX_Q]):
        value = value.strip()
        if not value:
            continue
        if key == "is":
            if value.lower() in ("fav", "favs", "favourite", "favorite", "starred"):
                p.filters.append(("fav", "true", neg))
            continue
        if key:
            p.filters.append((key, value, neg))
            continue
        if not _WORD.search(value):
            continue  # "-", "—", "$" alone: nothing to search for
        raw.append((neg, value, quoted))
    for neg, value, quoted in raw:
        t = Term(value, phrase=quoted)
        if neg:
            p.negated.append(t)
        elif not quoted and value.lower() in STOPWORDS:
            p.optional.append(t)
            p.typed.append(t)
        else:
            p.terms.append(t)
            p.typed.append(t)
    if not p.terms and p.optional:          # "the" alone, or only stopwords: they are the query
        p.terms, p.optional = p.optional, []
    p.terms = p.terms[:MAX_TERMS]
    p.negated = p.negated[:MAX_TERMS]
    for t in p.terms:
        # A one-letter prefix matches half the dictionary; it is only worth it while typing the last word.
        t.prefix = not t.phrase and len(t.text) >= 2
    if p.terms and not p.terms[-1].phrase:
        p.terms[-1].prefix = True
    return p


def _quote(s: str) -> str:
    """One FTS5 string literal. Inside double quotes FTS5 treats everything as text (AND, NEAR, *, :, ( ...);
    the only special character is the quote itself, escaped by doubling."""
    return '"' + s.replace('"', '""') + '"'


def _forms(t: Term) -> list[str]:
    """The term and its plural/singular, for plain words: "printers" also finds "printer", "workstation" finds
    "workstations". Query-side only, so the index keeps exact words and prefix search keeps working (a stemming
    tokenizer breaks "deploy*" against "deployment")."""
    w = t.text
    if t.phrase or len(w) < 3 or not w.isalpha():
        return [w]
    low = w.lower()
    out = [w]
    if low.endswith("ies") and len(low) > 4:
        out.append(w[:-3] + "y")
    elif low.endswith(("ses", "xes", "ches", "shes")):
        out.append(w[:-2])
    elif low.endswith("s") and not low.endswith("ss"):
        out.append(w[:-1])
    if low.endswith("y") and len(low) > 3 and low[-2] not in "aeiou":
        out.append(w[:-1] + "ies")
    elif low.endswith(("s", "x", "ch", "sh")):
        out.append(w + "es")
    else:
        out.append(w + "s")
    return out


def _word_expr(t: Term) -> str:
    """Matches the term as a word: its forms, and words starting with it when it is a prefix term."""
    parts = [_quote(f) for f in _forms(t)]
    if t.prefix:
        parts[0] += "*"
    return parts[0] if len(parts) == 1 else "(" + " OR ".join(parts) + ")"


def _exact_expr(t: Term) -> str:
    """The term as a whole word (or one of its forms) — no prefix. Used for the exact-word bonus and for `-word`."""
    parts = [_quote(f) for f in _forms(t)]
    return parts[0] if len(parts) == 1 else "(" + " OR ".join(parts) + ")"


def _tri_ok(t: Term) -> bool:
    return len(t.text) >= 3


# ------------------------------------------------------------------ matching

def _rowids(c, table: str, expr: str) -> set[int]:  # noqa: ANN001
    try:
        return {r[0] for r in c.execute(f"SELECT rowid FROM {table} WHERE {table} MATCH ?", (expr,))}
    except Exception as e:  # noqa: BLE001 — a query FTS5 rejects matches nothing, never a 500
        log.warning("library search: %s rejected %r: %s", table, expr, e)
        return set()


def _scored(c, table: str, expr: str) -> dict[int, float]:  # noqa: ANN001
    try:
        return {r[0]: r[1] for r in c.execute(
            f"SELECT rowid, bm25({table}, {_BM25_ARGS}) FROM {table} WHERE {table} MATCH ?", (expr,))}
    except Exception as e:  # noqa: BLE001
        log.warning("library search: %s rejected %r: %s", table, expr, e)
        return {}


def _term_set(c, t: Term, words: set[int] | None = None) -> set[int]:  # noqa: ANN001
    """Slides matching one term in either index. `words`: its word matches, when already known."""
    found = set(words) if words is not None else _rowids(c, "lib_fts", _word_expr(t))
    if _tri_ok(t):
        found |= _rowids(c, "lib_tri", _quote(t.text))
    return found


def _bonus(c, table: str, expr: str, base: dict[int, float]) -> None:  # noqa: ANN001
    """Add the bm25 of a narrower query to rows already matched (bm25 is negative: lower is better)."""
    for r, s in _scored(c, table, expr).items():
        if r in base:
            base[r] += s


def _match(c, p: Parsed) -> tuple[dict[int, tuple[int, float]], bool]:  # noqa: ANN001
    """rowid → (tier, score) for the slides the text part of the query matches; lower sorts first.
    tier 0: every term as a word; 1: some term only as a substring; 2/3: relaxed (any term). Score = weighted bm25
    of the whole query, plus bonuses (more negative) for: the words on the slide itself, not only on its deck —
    project and deck title are on every slide of a deck, so they say which deck but never which slide; the exact
    word rather than a longer one; and the terms side by side, in the order typed. Second value: whether relaxed to OR."""
    out: dict[int, tuple[int, float]] = {}
    if p.terms:
        words = _scored(c, "lib_fts", " AND ".join(_word_expr(t) for t in p.terms))
        if words:
            _bonus(c, "lib_fts", f"{_OWN} : (" + " AND ".join(_exact_expr(t) for t in p.terms) + ")", words)
            if len(p.typed) > 1:  # the words as typed, side by side (stopwords too): a rare phrase, so a large bonus
                _bonus(c, "lib_fts", _quote(" ".join(t.text for t in p.typed)) + ("*" if p.typed[-1].prefix else ""),
                       words)
        out = {r: (0, s) for r, s in words.items()}
        both: set[int] | None = None
        for t in p.terms:
            got = _term_set(c, t, set(words) if len(p.terms) == 1 else None)
            both = got if both is None else both & got
            if not both:
                break
        extra = (both or set()) - out.keys()
        tri_terms = [t for t in p.terms if _tri_ok(t)]
        if extra and tri_terms:
            any_tri = " OR ".join(_quote(t.text) for t in tri_terms)
            tri = {r: s for r, s in _scored(c, "lib_tri", any_tri).items() if r in extra}
            _bonus(c, "lib_tri", f"{_OWN} : ({any_tri})", tri)
            out.update({r: (1, tri.get(r, 0.0)) for r in extra})
        elif extra:
            out.update({r: (1, 0.0) for r in extra})
    relaxed = False
    if not out and len(p.terms) + len(p.optional) > 1:
        relaxed = True
        for t in p.terms + p.optional:
            for r, s in _scored(c, "lib_fts", _word_expr(t)).items():
                out[r] = (2, out.get(r, (2, 0.0))[1] + s)
            if _tri_ok(t):
                for r in _rowids(c, "lib_tri", _quote(t.text)) - out.keys():
                    out[r] = (3, 0.0)
    if p.negated and out:
        for r in _negated_only(c, p):
            out.pop(r, None)
    return out, relaxed


def _negated_only(c, p: Parsed) -> set[int]:  # noqa: ANN001
    ids: set[int] = set()
    for t in p.negated:
        ids |= _rowids(c, "lib_fts", _exact_expr(t))
    return ids


# ------------------------------------------------------------------ candidates, filters, facets

@dataclass(slots=True)
class DeckInfo:
    project: str
    title: str
    filename: str
    origin: str
    date: str             # deck_date, else the deck's created_at — what from/to and sort=deck_date use
    created: str
    superseded: bool


@dataclass(slots=True)
class Row:
    rid: int | None
    id: str
    deck_id: str
    d: DeckInfo
    index: int
    slide_type: str
    tags: list[str]
    entities: list[str]   # lowercased names
    entity_labels: dict[str, str]
    favourite: bool
    key: str              # duplicate key: phash, else text_sha, else the slide id
    created: str
    score: tuple[int, float] = (0, 0.0)


def _json_list(raw: str | None) -> list[Any]:
    if not raw or raw == "[]":
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else []
    except ValueError:
        return []


_NO_DECK = DeckInfo("", "", "", "", "", "", False)


def _rows(c, rids: set[int] | None) -> list[Row]:  # noqa: ANN001
    """One narrow row per candidate slide; `rids` None = every slide (browse). Reads `lib_search_cover`, an index
    holding just these columns, so a scan never touches the wide rows (text, parsed content, facts) — on 10k
    slides that is the difference between ~15 and ~45 ms. Decks (few) are joined here rather than in SQL."""
    decks = {i: DeckInfo(p or "", t or "", f or "", o or "", str(dd or ""), str(dc or ""), bool(sup))
             for i, p, t, f, o, dd, dc, sup in c.execute(
                 "SELECT id, project, title, filename, origin, COALESCE(deck_date, created_at), created_at, "
                 "superseded_by FROM libdeck")}
    if rids is not None and not rids:
        return []
    out = []
    for (rid, sid, deck_id, idx, stype, tags, ents, fav, phash, tsha, created) in c.execute(
            'SELECT m.rid, s.id, s.deck_id, s."index", s.slide_type, s.tags, s.entities, s.favourite, s.phash, '
            "s.text_sha, s.created_at FROM libslide s LEFT JOIN lib_search_rid m ON m.slide_id = s.id"):
        if rids is not None and rid not in rids:
            continue
        labels: dict[str, str] = {}
        for e in _json_list(ents):
            name = (e.get("name") if isinstance(e, dict) else e) or ""
            if isinstance(name, str) and name.strip():
                labels.setdefault(name.strip().lower(), name.strip())
        out.append(Row(rid, sid, deck_id, decks.get(deck_id, _NO_DECK), idx or 0, (stype or "").lower(),
                       [t for t in _json_list(tags) if isinstance(t, str)], list(labels), labels,
                       bool(fav), phash or tsha or sid, str(created or "")))
    return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _slugish(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _norm(s)).strip("-")


def _tag_resolver(tags: list[LibTag]):  # noqa: ANN202
    """A typed tag (`tag:genai`, `tag:"Generative AI"`) → the slugs it can mean: slug, label or alias."""
    index: dict[str, set[str]] = {}
    for t in tags:
        for k in (t.slug, t.label, *(t.aliases or [])):
            for form in {_norm(k), _slugish(k)}:
                if form:
                    index.setdefault(form, set()).add(t.slug)

    def resolve(v: str) -> set[str]:
        return index.get(_norm(v), set()) | index.get(_slugish(v), set()) | {_slugish(v), v}
    return resolve


def _q_filter(key: str, value: str, resolve_tag) -> Any:  # noqa: ANN001, ANN401
    """A filter typed into q: forgiving (substring, case-insensitive) where the URL filters are exact."""
    v = _norm(value)
    if key == "project":
        return lambda r: v in r.d.project.lower()
    if key == "deck":
        return lambda r: r.deck_id == value or v in r.d.title.lower() or v in r.d.filename.lower()
    if key == "tag":
        slugs = resolve_tag(value)
        return lambda r: any(t in slugs for t in r.tags)
    if key == "type":
        return lambda r: r.slide_type == v or _slugish(r.slide_type) == _slugish(v)
    if key == "entity":
        return lambda r: any(v in e for e in r.entities)
    if key == "origin":
        return lambda r: r.d.origin == v
    if key == "fav":
        return lambda r: r.favourite
    return lambda r: True


def _day(s: str | None, *, end: bool = False) -> str | None:
    """'2026-03' / '2026-03-04' / full ISO → a string comparable with SQLite's stored datetimes. Bad input → None."""
    if not s:
        return None
    s = s.strip()
    try:
        if re.fullmatch(r"\d{4}", s):
            d = datetime(int(s) + (1 if end else 0), 1, 1)
        elif re.fullmatch(r"\d{4}-\d{2}", s):
            y, m = map(int, s.split("-"))
            d = datetime(y, m, 1)
            if end:
                d = datetime(y + (m == 12), m % 12 + 1, 1)
        else:
            d = datetime.fromisoformat(s[:10])
            if end:
                d += timedelta(days=1)
    except ValueError:
        return None
    return d.strftime("%Y-%m-%d")


# facet name → the row's values for it
_FACET_VALUES = {
    "project": lambda r: [r.d.project] if r.d.project else [],
    "tag": lambda r: r.tags,
    "type": lambda r: [r.slide_type] if r.slide_type else [],
    "entity": lambda r: r.entities,
    "deck": lambda r: [r.deck_id],
    "origin": lambda r: [r.d.origin] if r.d.origin else [],
}


def _collapse(rows: list[Row]) -> list[Row]:
    """Keep the newest slide of each duplicate group; the group's best score goes with it. (The copies folded away
    are what `also_in` counts on the kept one.)"""
    best: dict[str, Row] = {}
    score: dict[str, tuple[int, float]] = {}
    for r in rows:
        k = r.key
        cur = best.get(k)
        if cur is None:
            best[k], score[k] = r, r.score
            continue
        if r.score < score[k]:
            score[k] = r.score
        if (r.d.created, r.created) > (cur.d.created, cur.created):
            best[k] = r
    for k, r in best.items():
        r.score = score[k]
    return list(best.values())


def _sort(rows: list[Row], sort: str, has_text: bool) -> None:
    by_deck = lambda r: (r.deck_id, r.index)  # noqa: E731
    rows.sort(key=by_deck)
    if sort == "relevance" and has_text:
        rows.sort(key=lambda r: r.d.created, reverse=True)
        rows.sort(key=lambda r: r.score)
    elif sort == "deck_date":
        rows.sort(key=lambda r: r.d.date, reverse=True)
    elif sort == "project":  # projects A–Z, the newest deck first within each, each deck in slide order
        rows.sort(key=lambda r: r.d.created, reverse=True)
        rows.sort(key=lambda r: r.d.project.lower())
    else:  # added (and browse with relevance): newest deck first, each deck in slide order
        rows.sort(key=lambda r: r.d.created, reverse=True)


# ------------------------------------------------------------------ snippets

def _patterns(terms: list[Term]) -> tuple[list[re.Pattern], list[re.Pattern]]:
    """Per term: a word-start pattern (how the word index matched) and a substring one (how the trigram did)."""
    word, sub = [], []
    for t in terms:
        parts = [re.escape(w) for w in re.findall(r"\w+", t.text)]
        if not parts:
            continue
        forms = _forms(t)
        body = r"\W+".join(parts) if len(forms) == 1 else "(?:" + "|".join(re.escape(f) for f in forms) + ")"
        tail = r"\w*" if t.prefix else r"(?!\w)"
        word.append(re.compile(r"(?<!\w)" + body + tail, re.IGNORECASE))
        sub.append(re.compile(re.escape(t.text), re.IGNORECASE))
    return word, sub


def _spans(text: str, pats: list[re.Pattern]) -> list[tuple[int, int]]:
    spans = sorted((m.start(), m.end()) for p in pats for m in p.finditer(text) if m.end() > m.start())
    merged: list[tuple[int, int]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged


def snippet(fields: list[str], terms: list[Term]) -> str:
    """HTML: a window of the field with the most matched terms, matches in <mark>, everything else escaped."""
    if not terms:
        return ""
    word, sub = _patterns(terms)
    best: tuple[int, str, list[tuple[int, int]]] | None = None
    for pats in (word, sub):
        for text in fields:
            text = re.sub(r"\s+", " ", text or "").strip()
            if not text:
                continue
            spans = _spans(text, pats)
            hits = sum(1 for p in pats if p.search(text))
            if spans and (best is None or hits > best[0]):
                best = (hits, text, spans)
        if best:
            break
    if best is None:
        return ""
    _, text, spans = best
    start = max(0, spans[0][0] - SNIPPET_CHARS // 4)
    if start:
        sp = text.rfind(" ", 0, start)
        start = sp + 1 if sp >= 0 and start - sp < 20 else start
    end = min(len(text), start + SNIPPET_CHARS)
    if end < len(text):
        sp = text.find(" ", end)
        end = sp if 0 <= sp < end + 20 else end
    out, pos = ["…" if start else ""], start
    for a, b in spans:
        if b <= start or a >= end:
            continue
        a, b = max(a, start), min(b, end)
        out += [html.escape(text[pos:a]), "<mark>", html.escape(text[a:b]), "</mark>"]
        pos = b
    out.append(html.escape(text[pos:end]))
    if end < len(text):
        out.append("…")
    return "".join(out)


# ------------------------------------------------------------------ the endpoint

def search(q: str = "", *, project: list[str] | None = None, tag: list[str] | None = None,
           type: list[str] | None = None, entity: list[str] | None = None, deck: list[str] | None = None,  # noqa: A002
           origin: list[str] | None = None, fav: bool = False, superseded: bool = False,
           date_from: str | None = None, date_to: str | None = None, sort: str = "relevance",
           limit: int = 60, offset: int = 0, dupes: bool = False, groups: bool = False) -> dict:
    """The whole search, callable without HTTP (the eval and tests use it). `groups` adds the result's outline —
    how many of its slides each deck holds, in `sort="project"` order — which with `limit=0` is all a grouped view
    needs to draw its headers before any deck is opened."""
    _ensure()
    p = parse(q)
    limit = max(0, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))
    has_text = bool(p.terms)
    with db.session() as s:
        all_tags = list(s.exec(select(LibTag)))
    resolve_tag = _tag_resolver(all_tags)

    relaxed = False
    # Meaning is asked for before the connection is taken: it is a network call, and it must not hold one.
    meant = semantic.matches(" ".join(t.text for t in (p.typed or p.terms))) if has_text else {}
    with _conn() as c:
        if has_text:
            scores, relaxed = _match(c, p)
            if meant:
                # Slides that say it in other words. After every slide that contains the words — or, when none
                # contains them all, before the ones that merely share a word.
                marks = ",".join("?" * len(meant))
                gone = _negated_only(c, p) if p.negated else set()
                for rid, sid in c.execute(f"SELECT rid, slide_id FROM lib_search_rid WHERE slide_id IN ({marks})", tuple(meant)):  # noqa: S608
                    if rid not in gone and (rid not in scores or scores[rid][0] >= 2):
                        scores[rid] = (BY_MEANING, -meant[sid])
            rows = _rows(c, set(scores))
            for r in rows:
                r.score = scores.get(r.rid, (9, 0.0))
        else:
            rows = _rows(c, None)
            if p.negated:
                gone = _negated_only(c, p)
                rows = [r for r in rows if r.rid not in gone]

    # Base filters: everything that is not a facet.
    lo, hi = _day(date_from), _day(date_to, end=True)
    q_filters = [(_q_filter(k, v, resolve_tag), neg) for k, v, neg in p.filters]
    # Superseded slides stay hidden unless asked for — or unless the user picked that very deck.
    explicit_decks = set(deck or [])
    for k, v, neg in p.filters:
        if k == "deck" and not neg:
            f = _q_filter(k, v, resolve_tag)
            explicit_decks |= {r.deck_id for r in rows if f(r)}

    def base(r: Row) -> bool:
        if r.d.superseded and not superseded and r.deck_id not in explicit_decks:
            return False
        if fav and not r.favourite:
            return False
        if lo and r.d.date[:10] < lo:
            return False
        if hi and r.d.date[:10] >= hi:
            return False
        return all(f(r) != neg for f, neg in q_filters)

    rows = [r for r in rows if base(r)]

    # Facet filters (URL params, exact; OR within a facet, AND across facets). Each facet is counted with every
    # filter but its own, so picking one value never hides the others: a row counts towards every facet when it
    # passes all of them, towards the one facet it fails when it fails exactly one, and towards none otherwise.
    selected = {"project": set(project or []), "tag": set(tag or []), "type": {_norm(t) for t in type or []},
                "entity": {_norm(e) for e in entity or []}, "deck": set(deck or []), "origin": set(origin or [])}
    active = [(k, v, _FACET_VALUES[k]) for k, v in selected.items() if v]
    keys: dict[str, dict[str, set[str]]] = {name: {} for name in _FACET_VALUES}
    labels: dict[str, dict[str, str]] = {"deck": {}, "entity": {}}
    result: list[Row] = []
    every = list(_FACET_VALUES.items())
    for r in rows:
        failed = [k for k, vals, values_of in active if not any(x in vals for x in values_of(r))]
        if not failed:
            result.append(r)
            counts_in = every
        elif len(failed) == 1:
            counts_in = [(failed[0], _FACET_VALUES[failed[0]])]
        else:
            continue
        k = r.id if dupes else r.key
        for name, values_of in counts_in:
            bucket = keys[name]
            for v in values_of(r):
                got = bucket.get(v)
                if got is None:
                    bucket[v] = got = set()
                    if name == "deck":
                        labels["deck"][v] = r.d.title or r.d.filename or v
                    elif name == "entity":
                        labels["entity"][v] = r.entity_labels.get(v, v)
                got.add(k)

    tag_label = {t.slug: t.label for t in all_tags}
    facets: dict[str, list[dict]] = {}
    for name, bucket in keys.items():
        items = sorted(bucket.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        keep = items[:FACET_TOP] + [kv for kv in items[FACET_TOP:] if kv[0] in selected[name]]
        names = tag_label if name == "tag" else labels.get(name, {})
        facets[name] = [{"value": v, "label": names.get(v, v), "count": len(ks)} for v, ks in keep]

    if not dupes:
        result = _collapse(result)
    _sort(result, sort, has_text)
    total = len(result)
    page = result[offset:offset + limit]

    items = _items(page, p)
    by_meaning = {r.id for r in page if r.score[0] == BY_MEANING}
    for it in items:
        if it["id"] in by_meaning:
            it["by_meaning"] = True  # found by what it says, not by the words typed
    out = {"total": total, "items": items, "facets": facets, "relaxed": relaxed}
    if groups:
        out["groups"] = _groups(result)
    return out


def _groups(result: list[Row]) -> list[dict]:
    """`[{project, deck, count}]`: one entry per deck with slides in the result, ordered as `sort="project"` is."""
    count: dict[str, int] = {}
    info: dict[str, DeckInfo] = {}
    for r in result:
        count[r.deck_id] = count.get(r.deck_id, 0) + 1
        info[r.deck_id] = r.d
    order = sorted(count, key=lambda i: info[i].created, reverse=True)
    order.sort(key=lambda i: info[i].project.lower())
    return [{"project": info[i].project, "deck": i, "count": count[i]} for i in order]


def _items(page: list[Row], p: Parsed) -> list[dict]:
    if not page:
        return []
    ids = [r.id for r in page]
    with db.session() as s:
        slides = {x.id: x for x in s.exec(select(LibSlide).where(LibSlide.id.in_(ids)))}
        decks = {d.id: d for d in s.exec(select(LibDeck).where(LibDeck.id.in_({r.deck_id for r in page})))}
    also = also_in_counts([slides[i] for i in ids if i in slides])
    terms = p.highlight
    out = []
    for r in page:
        x = slides.get(r.id)
        if x is None:
            continue  # deleted between the two queries
        snip = snippet([x.text, x.summary, x.title, x.notes], terms) if terms else ""
        out.append(slide_out(x, decks.get(x.deck_id), also_in=also.get(x.id, 0), snippet=snip))
    return out


@router.get("/search")
def search_endpoint(
    q: str = "", project: list[str] = Query(default=[]), tag: list[str] = Query(default=[]),
    type: list[str] = Query(default=[]), entity: list[str] = Query(default=[]),  # noqa: A002
    deck: list[str] = Query(default=[]), origin: list[str] = Query(default=[]),
    fav: bool = False, superseded: bool = False,
    date_from: str | None = Query(default=None, alias="from"), date_to: str | None = Query(default=None, alias="to"),
    sort: str = Query(default="relevance", pattern="^(relevance|added|deck_date|project)$"),
    limit: int = Query(default=60, ge=0, le=MAX_LIMIT), offset: int = Query(default=0, ge=0),
    dupes: bool = False, groups: bool = False,
) -> dict:
    """`{total, items: slide_out[], facets: {project, tag, type, entity, deck, origin: [{value, label, count}]},
    relaxed}` — `relaxed` is true when no slide matched every word and the results match some of them.
    `groups=true` adds `groups: [{project, deck, count}]`."""
    return search(q, project=project, tag=tag, type=type, entity=entity, deck=deck, origin=origin, fav=fav,
                  superseded=superseded, date_from=date_from, date_to=date_to, sort=sort, limit=limit,
                  offset=offset, dupes=dupes, groups=groups)
