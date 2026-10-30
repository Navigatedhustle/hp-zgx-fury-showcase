"""The fact ledger: what a source slide actually claims, and whether the designed slide still claims it.

The pipeline's original fidelity check (`qa/render_check.fidelity_findings`) compared two bags of bare
digit strings. That could not tell `$4.2M` from `4.2%` from `4.2GB`, ignored single digits entirely,
counted any `40` anywhere on the slide as proof that a different `40` survived, and never looked for
numbers the model had *invented*. It also let speaker notes stand in for the slide, which is how a deck
can score a clean fidelity pass while the audience sees none of the figures.

This module replaces the bag of digits with a ledger:

  extract(content)                -> the facts a source slide asserts, with units and labels
  check(facts, rendered, notes)   -> per fact: present / in notes only / missing / CHANGED

Extraction is deterministic. Tables and charts come out of python-pptx exactly, so those facts involve
no reading and no guessing at all; prose figures and proper nouns are found by regex. An LLM pass adds
what prose states but regex cannot see (`pipeline/runner.py::fill_facts`) and assigns tiers — it only
ever *adds* to and annotates this list, so a hallucinated ledger entry cannot invent a requirement out
of nothing that the deterministic pass did not find.

The distinction the whole module exists to draw is **missing vs changed**. A supporting figure that did
not fit is a shortfall; a figure whose value moved is a lie, and they must not share a severity.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Literal, Sequence

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- units
# A fact's unit decides what a match *means*, so it is part of the identity of the fact and not
# decoration on it. "40" surviving is meaningless; "40%" surviving is the claim.
#
# Classes rather than exact strings: a source that writes "40 percent" and a slide that writes "40%"
# assert the same thing, while "$4.2M" and "4.2GB" never do however similar the digits look.
UnitClass = Literal["percent", "currency", "multiplier", "bytes", "duration", "plain"]

_SCALES: dict[str, float] = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mn": 1e6, "million": 1e6, "millions": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9, "billions": 1e9,
    "t": 1e12, "trillion": 1e12,
}
# Byte scales are powers of two in spirit but nobody writes them that way on a slide; what matters is
# that TB and GB are a thousand apart, not whether it is 1000 or 1024.
_BYTE_UNITS = {"b": 1.0, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12, "pb": 1e15}
_DURATION_UNITS = {
    "ms": 0.001, "s": 1.0, "sec": 1.0, "secs": 1.0, "second": 1.0, "seconds": 1.0,
    "min": 60.0, "mins": 60.0, "minute": 60.0, "minutes": 60.0,
    "h": 3600.0, "hr": 3600.0, "hrs": 3600.0, "hour": 3600.0, "hours": 3600.0,
    "day": 86400.0, "days": 86400.0, "week": 604800.0, "weeks": 604800.0,
    "month": 2629800.0, "months": 2629800.0, "year": 31557600.0, "years": 31557600.0,
}
_CURRENCY = "$£€¥₹"
_MULTIPLIER = {"x", "×", "fold"}
_PERCENT = {"%", "percent", "pct", "percentage"}


class Fact(BaseModel):
    """One checkable assertion from a source slide."""

    id: str
    # claim: a statement with no figure or name to check it by ("Full backward compatibility with legacy
    # firmware"), quoted from a reference document. Checked by its wording, not by a value.
    kind: Literal["number", "name", "claim"] = "number"
    raw: str = ""                       # as the source wrote it: "$4.2M", "40%", "Z8 Fury G5"
    label: str = ""                     # the words around it, for reporting and for spotting a changed value
    origin: Literal["title", "text", "table", "chart", "notes", "llm", "doc"] = "text"  # doc: from a reference document
    tier: Literal["key", "supporting"] = "supporting"
    # numbers only
    value: float | None = None          # magnitude after scale words are applied ("$4.2M" -> 4200000.0)
    unit: UnitClass = "plain"
    unit_raw: str = ""                  # "%", "$", "GB", "x" — for display, never for matching
    # origin == "doc" only: the reference document it came from and how to cite it ("Whitepaper.pdf, p. 4"),
    # so removing that document can take exactly its facts back out.
    doc: str = ""
    cite: str = ""

    @property
    def visible_required(self) -> bool:
        """Key facts must be on the slide itself; supporting ones may live in the speaker notes.

        This is the loophole the old check left open — notes counted as kept for everything, so a deck
        could pass fidelity with every figure hidden behind the presenter view.
        """
        return self.tier == "key"


Status = Literal["present", "notes", "missing", "changed"]


class FactCheck(BaseModel):
    """What became of one fact on the finished slide."""

    id: str
    status: Status
    fact: Fact
    found: str = ""       # what was on the slide instead, when status is "changed"
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "present" or (self.status == "notes" and not self.fact.visible_required)

    @property
    def fatal(self) -> bool:
        """A value that moved is never shippable; a value that did not fit is a shortfall, not a lie."""
        return self.status == "changed"


# ---------------------------------------------------------------- parsing numbers
def _norm(s: str) -> str:
    """NFKC so ﬁ, ×, ½ and full-width digits compare as themselves, with whitespace flattened."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s or "")).strip()


# A number with whatever sits against it: a leading currency sign, a trailing %/x/unit/scale word.
_NUM_RE = re.compile(
    rf"""
    (?P<cur>[{_CURRENCY}])?\s*
    (?P<num>\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+(?:\.\d+)?)
    \s*
    (?P<suf>%|percent|pct|percentage|[x×]\b|fold\b|
            k\b|m\b|bn?\b|t\b|thousand|millions?|billions?|trillion|
            [kmgtp]?b\b|ms\b|s\b|secs?\b|seconds?\b|mins?\b|minutes?\b|hrs?\b|h\b|hours?\b|
            days?\b|weeks?\b|months?\b|years?\b)?
    """,
    re.X | re.I,
)


def _classify(cur: str, suf: str) -> tuple[UnitClass, str, float]:
    """-> (unit class, unit as written, multiplier to apply to the digits)."""
    s = (suf or "").strip().lower()
    if s in _PERCENT:
        return "percent", "%", 1.0
    if s in _MULTIPLIER:
        return "multiplier", "x", 1.0
    if cur:
        return "currency", cur, _SCALES.get(s, 1.0)
    # "MB" before "M": the byte units overlap the scale words and the longer reading wins.
    if s in _BYTE_UNITS and (len(s) > 1 or s == "b"):
        return "bytes", s.upper(), _BYTE_UNITS[s]
    if s in _DURATION_UNITS:
        return "duration", s, _DURATION_UNITS[s]
    if s in _SCALES:
        return "plain", "", _SCALES[s]
    return "plain", "", 1.0


class _Num(BaseModel):
    value: float
    unit: UnitClass
    unit_raw: str
    raw: str
    start: int = 0
    end: int = 0


def parse_numbers(text: str) -> list[_Num]:
    """Every number in `text`, with its unit resolved and its scale word applied."""
    out: list[_Num] = []
    s = _norm(text)
    for m in _NUM_RE.finditer(s):
        digits = m.group("num").replace(",", "")
        try:
            base = float(digits)
        except ValueError:
            continue
        unit, unit_raw, mult = _classify(m.group("cur") or "", m.group("suf") or "")
        # A bare single digit is list numbering, a step count or a slide number far more often than a
        # claim. One that carries a unit ("3 TB", "5x", "2%") is a claim, so only the naked ones go.
        if unit == "plain" and mult == 1.0 and len(digits.replace(".", "").lstrip("0")) < 2:
            continue
        out.append(_Num(value=base * mult, unit=unit, unit_raw=unit_raw, raw=_norm(m.group(0)),
                        start=m.start(), end=m.end()))
    return out


def _close(a: float, b: float) -> bool:
    """Same magnitude allowing for rounding on the slide ("41.8%" shown as "42%")."""
    if a == b:
        return True
    scale = max(abs(a), abs(b))
    return scale > 0 and abs(a - b) <= max(scale * 0.005, 1e-9)


# ---------------------------------------------------------------- parsing names
_WORD = r"[A-Z][A-Za-z0-9&+.\-]*"
_JOIN = r"(?:of|for|de|&)"
_NAME_RE = re.compile(rf"\b{_WORD}(?:\s+(?:{_WORD}|{_JOIN}))*\b")
# Capitalised words that identify nothing on their own: a span of only these is not a name.
_GENERIC = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "de", "do", "for", "from", "how", "if", "in", "is", "it",
    "of", "on", "or", "our", "so", "the", "to", "up", "us", "we", "what", "when", "where", "which", "who", "why",
    "will", "with", "you", "your", "all", "any", "best", "better", "big", "both", "each", "every", "first", "full",
    "good", "great", "high", "key", "last", "less", "low", "main", "many", "more", "most", "much", "new", "next",
    "no", "not", "now", "one", "only", "other", "own", "part", "per", "real", "right", "same", "few", "small",
    "some", "such", "than", "that", "their", "them", "then", "there", "these", "they", "those", "three",
    "top", "total", "two", "very", "was", "way", "while", "year", "years", "yes", "agenda", "overview",
    "summary", "thank", "thanks", "today", "tomorrow", "questions", "steps", "step", "appendix", "before",
    "after", "about", "across", "against", "between", "during", "into", "over", "under", "within", "without",
    "prepared", "presented", "confidential", "internal", "draft",
}
# A single capitalised word is a name in two situations, and the two need different evidence:
#   shape    — ALLCAPS or inner-capital tokens are products and acronyms wherever they sit ("NVFP4",
#              "ZBook", "EMEA"), including at the start of a table cell.
#   position — an ordinary capitalised word that is *not* opening a sentence is a name ("...by Zscaler"),
#              because prose only capitalises mid-line for proper nouns.
# Shape alone missed "Zscaler"; position alone would make a name of every sentence opener.
_SHAPE_RE = re.compile(r"^(?:[A-Z]{2,}[0-9]*|[A-Z][a-z0-9]*[A-Z][A-Za-z0-9]*)$")
_SENTENCE_END = ".!?:;|•-–—"

# Unit tokens are never names, however they are capitalised: "GB", "TB", "MB" are the units of a fact
# that has already been recorded as a number, not separate claims.
_UNIT_WORDS = {u.lower() for u in _BYTE_UNITS} | set(_DURATION_UNITS) | set(_SCALES) | _PERCENT | _MULTIPLIER


def _ident(span: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-z0-9&+.\-]+", span)
            if len(t) > 1 and t.lower() not in _GENERIC and t.lower() not in _UNIT_WORDS]


def _opens_a_sentence(line: str, at: int) -> bool:
    before = line[:at].rstrip()
    return not before or before[-1] in _SENTENCE_END


def parse_names(text: str) -> list[str]:
    """Product, company and person names: multi-word capitalised spans, plus qualifying single words."""
    out: list[str] = []
    seen: set[str] = set()
    for raw_line in (text or "").splitlines():
        line = _norm(raw_line)
        for m in _NAME_RE.finditer(line):
            words = m.group(0).split(" ")
            dropped = 0
            while words and words[0].lower().strip(".,") in _GENERIC:
                dropped += len(words.pop(0)) + 1
            while words and words[-1].lower().strip(".,") in _GENERIC:
                words.pop()
            span = " ".join(words).strip(" .-")
            if not span:
                continue
            toks = _ident(span)
            ok = len(toks) >= 2 and len(span) >= 5
            if not ok and len(toks) == 1:
                tok = toks[0]
                if _SHAPE_RE.match(tok) or not _opens_a_sentence(line, m.start() + dropped):
                    span, ok = tok, True
            if ok and span.lower() not in seen:
                seen.add(span.lower())
                out.append(span)
    return out


def has_name(span: str, haystack: str) -> bool:
    """Present if the span survived whole, or if every identifying token of it did — a slide may
    legitimately split a product name across an eyebrow, a heading and a label."""
    low = _norm(haystack).lower()
    if span.lower() in low:
        return True
    toks = _ident(span)
    if not toks:
        return False
    words = set(re.findall(r"[a-z0-9&+.\-]+", low))
    return all(t.lower() in words for t in toks)


# ---------------------------------------------------------------- extraction
_MAX_FACTS = 60  # a ledger longer than this is a slide that must be split, not a slide to check harder


def _label_for(text: str, num: _Num) -> str:
    """The words on either side of a number, which is what makes a changed value recognisable as the
    *same* claim with a different figure rather than simply another number on the slide."""
    s = _norm(text)
    before = re.findall(r"[A-Za-z%][A-Za-z%\-]*", s[max(0, num.start - 60):num.start])[-4:]
    after = re.findall(r"[A-Za-z%][A-Za-z%\-]*", s[num.end:num.end + 40])[:3]
    return " ".join(before + after).strip()


def _lines_of(content: dict) -> list[tuple[str, str]]:
    """(origin, line) for every piece of text a source slide carries."""
    out: list[tuple[str, str]] = []
    if content.get("title"):
        out.append(("title", str(content["title"])))
    for block in content.get("text") or []:
        for line in block.get("lines") or []:
            if str(line).strip():
                out.append(("text", str(line)))
    for rows in content.get("tables") or []:
        for row in rows or []:
            out.append(("table", " | ".join(str(c) for c in row)))
    for chart in content.get("charts") or []:
        if chart.get("title"):
            out.append(("chart", str(chart["title"])))
        cats = [str(c) for c in chart.get("categories") or []]
        for series in chart.get("series") or []:
            name = str(series.get("name") or "")
            for i, v in enumerate(series.get("values") or []):
                if v is None:
                    continue
                cat = cats[i] if i < len(cats) else ""
                # Rendered as text so one code path extracts it, but the value came from python-pptx
                # exactly — no reading, no rounding, no chance of a misread axis.
                out.append(("chart", f"{name} {cat} {_fmt(v)}".strip()))
    return out


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def extract(content: dict, *, prefix: str = "f") -> list[Fact]:
    """The facts a source slide asserts. Deterministic: same content in, same ledger out.

    `content` is `SlideContent.for_prompt()` — the same view the model is given, so the ledger can never
    demand something the generator was never shown.
    """
    facts: list[Fact] = []
    seen: set[tuple] = set()
    n = 0

    def add(f: Fact, key: tuple) -> None:
        nonlocal n
        if key in seen or len(facts) >= _MAX_FACTS:
            return
        seen.add(key)
        n += 1
        f.id = f"{prefix}{n}"
        facts.append(f)

    lines = _lines_of(content)
    for origin, line in lines:
        for num in parse_numbers(line):
            add(Fact(id="", kind="number", raw=num.raw, label=_label_for(line, num), origin=origin,
                     value=num.value, unit=num.unit, unit_raw=num.unit_raw),
                ("n", round(num.value, 6), num.unit))
    for origin, line in lines:
        if origin == "chart":
            continue  # series names repeat per point; they are covered by the chart's title and categories
        for span in parse_names(line):
            add(Fact(id="", kind="name", raw=span, label=span, origin=origin), ("s", span.lower()))
    return facts


# ---------------------------------------------------------------- checking
def _find(num_list: Sequence[_Num], fact: Fact) -> _Num | None:
    for c in num_list:
        if c.unit == fact.unit and _close(c.value, fact.value or 0.0):
            return c
    return None


def _label_hit(fact: Fact, text: str) -> bool:
    """Does the slide still talk about this claim? Two identifying words from the label is enough."""
    words = [w for w in re.findall(r"[a-z]{3,}", fact.label.lower()) if w not in _GENERIC]
    if not words:
        return False
    low = _norm(text).lower()
    return sum(1 for w in set(words) if w in low) >= min(2, len(set(words)))


def _changed_to(fact: Fact, nums: Sequence[_Num], text: str) -> _Num | None:
    """A number of the same unit sitting in the same claim, with a different magnitude.

    Deliberately narrow. Reporting every unmatched number as "changed" would make the fatal status
    meaningless, so it fires only when the slide still makes this claim and has put a different figure
    on it — a units slip or a transcription error, not a figure that was dropped.
    """
    if fact.value is None or not _label_hit(fact, text):
        return None
    same_unit = [c for c in nums if c.unit == fact.unit and not _close(c.value, fact.value)]
    return same_unit[0] if len(same_unit) == 1 else None


def _claim_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9][a-z0-9.\-]{2,}", _norm(text).lower()) if w not in _GENERIC}


def has_claim(claim: str, text: str) -> bool:
    """Is this statement still made? A designer tightens wording, so not word for word — but every term that
    carries a digit ("27001") must be there, and at least three quarters of the rest."""
    want = _claim_words(claim)
    if not want:
        return False
    have = _claim_words(text)
    coded = {w for w in want if any(c.isdigit() for c in w)}
    return coded <= have and len(want & have) >= 0.75 * len(want)


def align_numbers(quote: str, document: Sequence[_Num]) -> str | None:
    """`quote` rewritten with each of its figures in the document's own wording, when the document states every
    one of them — the same value in the same unit, written differently ("$4.2 million" for "$4.2M", "40 percent"
    for "40%"). None when the quote has no unit-bearing figure, or the document lacks any of them: a bare "12"
    matches too much to mean anything."""
    nums = [n for n in parse_numbers(quote) if n.unit != "plain"]
    if not nums:
        return None
    out = quote
    for n in nums:
        hit = next((d for d in document if d.unit == n.unit and abs(d.value - n.value) <= 1e-9 * max(1.0, abs(n.value))), None)
        if hit is None:
            return None
        out = out.replace(n.raw, hit.raw, 1)
    return out


def check(facts: Iterable[Fact], rendered_text: str, notes_text: str = "") -> list[FactCheck]:
    """Where each fact ended up on the finished slide."""
    slide_nums = parse_numbers(rendered_text)
    notes_nums = parse_numbers(notes_text)
    out: list[FactCheck] = []
    for f in facts:
        if f.kind == "claim":
            st = "present" if has_claim(f.raw, rendered_text) else "notes" if has_claim(f.raw, notes_text) else "missing"
            out.append(FactCheck(id=f.id, status=st, fact=f))
            continue
        if f.kind == "name":
            if has_name(f.raw, rendered_text):
                st, found = "present", ""
            elif has_name(f.raw, notes_text):
                st, found = "notes", ""
            else:
                st, found = "missing", ""
            out.append(FactCheck(id=f.id, status=st, fact=f, found=found))
            continue
        hit = _find(slide_nums, f)
        if hit:
            out.append(FactCheck(id=f.id, status="present", fact=f, found=hit.raw))
            continue
        moved = _changed_to(f, slide_nums, rendered_text)
        if moved:
            out.append(FactCheck(id=f.id, status="changed", fact=f, found=moved.raw,
                                 detail=f"the source says {f.raw}, the slide says {moved.raw}"))
            continue
        if _find(notes_nums, f):
            out.append(FactCheck(id=f.id, status="notes", fact=f))
            continue
        out.append(FactCheck(id=f.id, status="missing", fact=f))
    return out


def invented(facts: Iterable[Fact], rendered_text: str) -> list[str]:
    """Numbers on the slide that no source fact accounts for.

    The old check only ever looked for omissions, so a fabricated figure — the failure that actually
    misleads an audience — passed in silence. Plain unitless numbers are excluded: step counters, "1 of
    6", axis ticks and years are all legitimately introduced by the design.
    """
    known = [f for f in facts if f.kind == "number" and f.value is not None]
    out: list[str] = []
    for c in parse_numbers(rendered_text):
        if c.unit == "plain":
            continue
        if not any(f.unit == c.unit and _close(f.value or 0.0, c.value) for f in known):
            out.append(c.raw)
    return out


# ---------------------------------------------------------------- reporting
class Ledger(BaseModel):
    """A slide's facts and, once it has been rendered, what became of them."""

    facts: list[Fact] = Field(default_factory=list)
    checks: list[FactCheck] = Field(default_factory=list)
    invented: list[str] = Field(default_factory=list)

    @property
    def changed(self) -> list[FactCheck]:
        return [c for c in self.checks if c.status == "changed"]

    @property
    def missing(self) -> list[FactCheck]:
        return [c for c in self.checks if c.status == "missing"]

    @property
    def hidden(self) -> list[FactCheck]:
        """Key facts that reached only the speaker notes — present, but not where they were needed."""
        return [c for c in self.checks if c.status == "notes" and c.fact.visible_required]

    @property
    def ok(self) -> bool:
        return not self.changed and not self.missing and not self.hidden and not self.invented


def ledger(facts: Sequence[Fact], rendered_text: str, notes_text: str = "") -> Ledger:
    return Ledger(facts=list(facts), checks=check(facts, rendered_text, notes_text),
                  invented=invented(facts, rendered_text))


def load(raw: Any) -> list[Fact]:
    """Facts out of the database column, skipping anything that no longer parses.

    A ledger stored by an older build must never take a project down: a fact that cannot be read is a
    fact that cannot be checked, which is the same position the pipeline was in before it existed.
    """
    out: list[Fact] = []
    for item in raw or []:
        try:
            out.append(Fact.model_validate(item))
        except Exception:  # noqa: BLE001, S110 - a stored fact that no longer validates is simply dropped
            continue
    return out


def dump(facts: Sequence[Fact]) -> list[dict]:
    return [f.model_dump() for f in facts]


def for_prompt(facts: Sequence[Fact]) -> dict:
    """The ledger as the generator is shown it: what must be on the slide, and what merely must survive."""
    def line(f: Fact) -> str:
        if f.kind == "claim":
            return f"“{f.raw}” — a statement: keep its meaning and every term in it; the wording may be tightened"
        return f"{f.raw} ({f.label})" if f.label and f.kind == "number" else f.raw

    return {"must_be_visible": [line(f) for f in facts if f.tier == "key"],
            "must_survive": [line(f) for f in facts if f.tier != "key"]}
