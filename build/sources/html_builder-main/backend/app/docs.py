"""Reference documents: a PDF, Word file or text the user adds to a deck for context.

Testers said a deck plans better when the planner can read the brief behind it — the whitepaper, the proposal,
the customer's RFP — not only the slides. A document is *reference*, never the deck itself:

- it is cut into **sections** (`sections`), each digested by the author model and then merged into one **digest**
  (`pipeline/reference.digest_doc`). The planner reads the digest and the section list, so every page of a
  200-page PDF is represented — not only the part that fits one call;
- its **chunks** (`chunks`: paragraph-aligned, overlapping, each knowing its section, heading and page) are
  searched per slide and the best few go to the generator as background. The planner can name the sections a
  slide draws on (`doc_refs`); keyword overlap and, when an embedding model is configured, meaning rank the rest;
- a figure from it reaches a slide only through the fact ledger (`Fact.origin == "doc"`), and only when the
  planner quoted it exactly and it really is in the text (`contains`). Nothing unverifiable gets on a slide.

Parsing is local (pypdf, python-docx) — the GB300 only ever sees text. A PDF page is read in layout order
(`pdf_layout`: columns down, tables marked), and the pictures in a document become deck images (`pictures`).
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import unicodedata
from array import array
from dataclasses import dataclass, field
from pathlib import Path

DOC_TYPES = {".pdf", ".docx", ".txt", ".md"}
MAX_BYTES = 50 * 1024 * 1024
MAX_CHARS = 300_000     # ~75k tokens: far more than any brief; a longer file is cut, and says so
SECTION_CHARS = 16_000  # ~4k tokens: one section-digest call each, and the unit the planner points at
CHUNK_CHARS = 1600      # what the generator is shown: big enough to hold an argument, or a table with its lead-in
OVERLAP_CHARS = 300     # a chunk starts with the previous one's last paragraph when that is short
_WORD = re.compile(r"[a-z0-9][a-z0-9.%$-]{2,}")
_STOP = frozenset("the and for with that this from are was were have has will into their our your its not but "
                  "can all any more most than then also such each which what when where who how".split())


class DocRefused(ValueError):
    """The file cannot be used as a reference document. The message is safe to show the user."""


def safe_extract(path):
    """Application boundary: actual document decoding stays in a bounded worker."""
    import base64
    from showcase_app.document_parser import run_parser
    try:
        result = run_parser('presentation', path)
        return DocText(pages=result['pages'], truncated=result['truncated']), [base64.b64decode(p, validate=True) for p in result['pictures']]
    except (ValueError, KeyError, OSError) as error:
        raise DocRefused("That document couldn't be read safely within the local parser limits.") from error


@dataclass
class DocText:
    pages: list[str]                 # one entry per PDF page; one entry for a Word or text file
    truncated: bool = False

    @property
    def text(self) -> str:
        return "\n\n".join(self.pages)


@dataclass
class Section:
    n: int                           # 1-based, in document order
    title: str                       # its first heading, else its first words
    page_from: int                   # 1-based; 0 when the source has no pages
    page_to: int
    paras: list[tuple[int, str]]     # (page, paragraph)

    @property
    def text(self) -> str:
        return "\n\n".join(p for _, p in self.paras)

    @property
    def where(self) -> str:
        if not self.page_from:
            return ""
        return f"p. {self.page_from}" if self.page_from == self.page_to else f"pp. {self.page_from}–{self.page_to}"


@dataclass
class Chunk:
    page: int                        # 1-based; 0 when the source has no pages
    text: str
    words: set[str] = field(default_factory=set)
    section: int = 0                 # the Section.n it came from
    heading: str = ""                # the nearest heading above it, when the document has any


def _pdf(path: Path) -> list[str]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                if not reader.decrypt(""):
                    raise DocRefused("That PDF is password-protected — save an unprotected copy first.")
            except DocRefused:
                raise
            except Exception as e:  # noqa: BLE001
                raise DocRefused("That PDF is password-protected — save an unprotected copy first.") from e
        from .pdf_layout import page_text
        return [page_text(p) for p in reader.pages]
    except DocRefused:
        raise
    except (PdfReadError, OSError, ValueError) as e:
        raise DocRefused("That PDF couldn't be read. Is it damaged?") from e


def _docx(path: Path) -> list[str]:
    import docx
    from docx.opc.exceptions import PackageNotFoundError
    from docx.table import Table

    try:
        d = docx.Document(str(path))
    except (PackageNotFoundError, KeyError, ValueError, OSError) as e:
        raise DocRefused("That Word file couldn't be read. Save it as .docx (not .doc) and try again.") from e
    # In document order: a table stays under the paragraph that introduces it, and a heading keeps its level
    # of emphasis ("# …") so sections and chunks can be named after it.
    lines: list[str] = []
    for item in d.iter_inner_content():
        if isinstance(item, Table):
            rows = [" | ".join(c.text.strip().replace("\n", " ") for c in row.cells) for row in item.rows]
            rows = [f"| {r} |" for r in rows if r.replace("|", "").strip()]
            if rows:
                lines.append("\n".join(rows))
            continue
        text = item.text.strip()
        if not text:
            continue
        style = (item.style.name or "") if item.style is not None else ""
        lines.append(f"# {text}" if style.startswith(("Heading", "Title")) else text)
    return ["\n\n".join(lines)]


def extract(path: Path) -> DocText:
    """The document's text, page by page. Raises DocRefused with a readable reason."""
    ext = path.suffix.lower()
    if ext not in DOC_TYPES:
        raise DocRefused("Please add a PDF, Word (.docx), .txt or .md file.")
    if ext == ".pdf":
        pages = _pdf(path)
    elif ext == ".docx":
        pages = _docx(path)
    else:
        pages = [path.read_text(encoding="utf-8", errors="replace")]
    pages = [re.sub(r"[ \t]+", " ", p) for p in pages]
    if not any(p.strip() for p in pages):
        raise DocRefused("No text found in that file. A scanned PDF needs OCR before it can be used.")
    out, used, truncated = [], 0, False
    for p in pages:
        if used + len(p) > MAX_CHARS:
            out.append(p[: max(0, MAX_CHARS - used)])
            truncated = True
            break
        out.append(p)
        used += len(p)
    return DocText(pages=out, truncated=truncated)


PICTURE_MIN_SIDE = 240   # smaller than this is a logo, a bullet or a rule, not a figure worth a slide
PICTURE_MAX_ASPECT = 6.0
PICTURES_PER_DOC = 24


def pictures(path: Path) -> list[bytes]:
    """The figures embedded in a document — diagrams, charts, photos — as PNG bytes, largest first.

    Raster pictures only: a diagram drawn with vector strokes in a PDF is not an image the file contains, and is
    not found here. Small or sliver-shaped pictures (logos, bullets, rules) are skipped, and one repeated on
    every page counts once. Never raises: a document whose pictures cannot be read still has its text.
    """
    from PIL import Image

    blobs: list[bytes] = []
    try:
        ext = path.suffix.lower()
        if ext == ".pdf":
            from pypdf import PdfReader
            for page in PdfReader(str(path)).pages:
                try:
                    blobs += [im.data for im in page.images]
                except Exception:  # noqa: BLE001, S112 - one page's unusual image encoding
                    continue
        elif ext == ".docx":
            import docx
            blobs = [part.blob for part in docx.Document(str(path)).part.related_parts.values()
                     if str(getattr(part, "content_type", "")).startswith("image/")]
    except Exception:  # noqa: BLE001
        return []
    out: list[tuple[int, bytes]] = []
    seen: set[str] = set()
    for blob in blobs:
        sha = hashlib.sha1(blob).hexdigest()  # noqa: S324 - identity of a picture, not security
        if sha in seen:
            continue
        seen.add(sha)
        try:
            im = Image.open(io.BytesIO(blob))
            im.load()
            w, h = im.size
            if min(w, h) < PICTURE_MIN_SIDE or max(w, h) / max(1, min(w, h)) > PICTURE_MAX_ASPECT:
                continue
            buf = io.BytesIO()
            im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB").save(buf, "PNG")
            out.append((w * h, buf.getvalue()))
        except Exception:  # noqa: BLE001, S112 - EMF/WMF and anything else Pillow cannot decode
            continue
    return [b for _, b in sorted(out, key=lambda x: -x[0])[:PICTURES_PER_DOC]]


def words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


_PARA = re.compile(r"\n\s*\n|\n(?=[A-Z0-9•\-#])")
_NUMBERED = re.compile(r"^\d+(\.\d+)*\.?\s+\S")


def is_heading(para: str) -> bool:
    """A line that names what follows: marked ("# …"), numbered ("3.2 Results"), ALL CAPS or Title Case — short,
    one line, and not a sentence. PDFs carry no structure, so this reads the text the way a person skims it."""
    if "\n" in para:
        return False
    if para.startswith("#"):
        return True
    if not 3 <= len(para) <= 80 or para[-1] in ".!?:;," or para.startswith(("|", "•", "-")):
        return False
    ws = para.split()
    if len(ws) > 12 or not any(c.isalpha() for c in para):
        return False
    if _NUMBERED.match(para):
        return True
    alpha = [w for w in ws if w[0].isalpha() and len(w) > 3]  # "and", "of", "the" stay lower case in a title
    return bool(alpha) and (para.isupper() or (len(ws) >= 2 and all(w[0].isupper() for w in alpha)))


def _paras(doc: DocText) -> list[tuple[int, str]]:
    paged = len(doc.pages) > 1
    return [(n if paged else 0, para.strip()) for n, page in enumerate(doc.pages, 1)
            for para in _PARA.split(page) if para.strip()]


def sections(doc: DocText) -> list[Section]:
    """The document in order, in pieces of at most ~SECTION_CHARS that break at a heading when one is near.
    Deterministic, so a stored section digest still belongs to the same text when this is computed again."""
    out: list[Section] = []
    cur: list[tuple[int, str]] = []
    size = 0

    def flush() -> None:
        nonlocal cur, size
        if not cur:
            return
        head = next((p for _, p in cur if is_heading(p)), cur[0][1].split("\n")[0])
        out.append(Section(n=len(out) + 1, title=head.lstrip("# ").strip()[:80], page_from=cur[0][0],
                           page_to=cur[-1][0], paras=cur))
        cur, size = [], 0

    for page, para in _paras(doc):
        if cur and (size + len(para) > SECTION_CHARS or (size > SECTION_CHARS // 2 and is_heading(para))):
            flush()
        cur.append((page, para))
        size += len(para)
    flush()
    return out


def _pieces(para: str) -> list[str]:
    """A paragraph as it is, unless it is far too long for one chunk (a big table, a wall of text): then by
    lines, a table's header row repeated on each piece so every one still says what its columns are."""
    if len(para) <= CHUNK_CHARS * 2:
        return [para]
    lines = para.split("\n")
    if len(lines) == 1:
        return [para[i:i + CHUNK_CHARS] for i in range(0, len(para), CHUNK_CHARS)]
    head = lines[0] if lines[0].startswith("|") else ""
    out, buf = [], ""
    for ln in lines:
        if buf and len(buf) + len(ln) > CHUNK_CHARS:
            out.append(buf)
            buf = head if head and ln != head else ""
        buf = f"{buf}\n{ln}" if buf else ln
    if buf:
        out.append(buf)
    return out


def chunks(doc: DocText) -> list[Chunk]:
    """~CHUNK_CHARS pieces on paragraph boundaries. Each remembers its page, its section and the heading it sits
    under, and opens with the previous piece's last paragraph when that is short — so a sentence that refers
    back ("this cut costs by 12%") still arrives with what "this" was."""
    out: list[Chunk] = []
    for sec in sections(doc):
        heading = ""
        buf: list[tuple[int, str]] = []
        buf_heading = ""

        def flush(carry: bool) -> None:
            nonlocal buf, buf_heading
            if not buf:
                return
            out.append(Chunk(page=buf[0][0], text="\n".join(p for _, p in buf), section=sec.n, heading=buf_heading))
            last = buf[-1]
            buf = [last] if carry and len(buf) > 1 and len(last[1]) <= OVERLAP_CHARS and not is_heading(last[1]) else []
            buf_heading = heading

        for page, para in sec.paras:
            if is_heading(para):
                heading = para.lstrip("# ").strip()
                if sum(len(p) for _, p in buf) >= CHUNK_CHARS // 3:
                    flush(carry=False)  # a heading opens the chunk about it rather than trailing the one before
            for piece in _pieces(para):
                if buf and sum(len(p) for _, p in buf) + len(piece) > CHUNK_CHARS:
                    flush(carry=True)
                if not buf:
                    buf_heading = heading
                buf.append((page, piece))
        # A carried paragraph alone is already in the previous chunk: only flush what is new.
        if buf and not (len(buf) == 1 and out and out[-1].section == sec.n and out[-1].text.endswith(buf[0][1])):
            flush(carry=False)
    for c in out:
        c.words = words(f"{c.heading} {c.text}")
    return out


def lexical(pool: list[tuple[str, Chunk]], query: str, min_hits: int = 2) -> dict[int, float]:
    """pool index → how many (rarity-weighted) words that chunk shares with `query`. A chunk sharing fewer than
    `min_hits` is absent: one common word in a long slide is a coincidence, not a match."""
    q = words(query)
    if not q or not pool:
        return {}
    df: dict[str, int] = {}
    for _, c in pool:
        for w in c.words & q:
            df[w] = df.get(w, 0) + 1
    return {i: sum(1.0 / df[w] for w in hit) for i, (_, c) in enumerate(pool) if len(hit := c.words & q) >= min_hits}


def relevant(pool: list[tuple[str, Chunk]], query: str, k: int = 3, max_chars: int = 6500) -> list[tuple[str, Chunk]]:
    """The `k` chunks sharing the most (rarity-weighted) words with `query`. `pool` is (doc name, chunk)."""
    score = lexical(pool, query)
    best = sorted(score, key=lambda i: -score[i])
    out, used = [], 0
    for i in best[:k]:
        if used + len(pool[i][1].text) > max_chars:
            break
        out.append(pool[i])
        used += len(pool[i][1].text)
    return out


_PUNCT = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-", "‘": "'", "’": "'",
                        "“": '"', "”": '"', "\u00ad": "", "\u00a0": " "})


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s).translate(_PUNCT)).strip().lower()


def _forms(text: str) -> tuple[str, str, str]:
    """A text three ways: spacing collapsed; spacing removed; and with words rejoined that a line break hyphenated.
    PDF extraction breaks lines (and sometimes "$4.2 M") wherever the page did, and the quote gate must not
    mistake that for a different figure. Characters are never changed — only the white space between them."""
    n = unicodedata.normalize("NFKC", text).translate(_PUNCT).lower()
    return re.sub(r"\s+", " ", n).strip(), re.sub(r"\s+", "", n), re.sub(r"\s+", "", re.sub(r"-\s*\n\s*", "", n))


def _within(forms: tuple[str, str, str], quote: str) -> bool:
    q = _norm(quote)
    if len(q) < 2:
        return False
    if q in forms[0]:
        return True
    tight = q.replace(" ", "")
    return len(tight) >= 4 and (tight in forms[1] or tight in forms[2])


def contains(doc_text: str, quote: str) -> bool:
    """Is `quote` really in the document (case, spacing and line breaks aside)? The gate a doc fact must pass."""
    return _within(_forms(doc_text), quote)


def page_of(doc: DocText, quote: str) -> int:
    """1-based page the quote is on, or 0 when the document has no pages or it isn't found."""
    if len(doc.pages) < 2:
        return 0
    return next((i for i, p in enumerate(doc.pages, 1) if _within(_forms(p), quote)), 0)


# ------------------------------------------------------------------ storage
def text_path(project_dir: Path, doc_id: str) -> Path:
    d = project_dir / "docs"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{doc_id}.txt"


PAGE_BREAK = "\n\f\n"  # pages survive the round trip through the .txt file


def save_text(project_dir: Path, doc_id: str, doc: DocText) -> None:
    text_path(project_dir, doc_id).write_text(PAGE_BREAK.join(doc.pages), encoding="utf-8")


def load_text(project_dir: Path, doc_id: str) -> DocText | None:
    p = text_path(project_dir, doc_id)
    if not p.exists():
        return None
    return DocText(pages=p.read_text(encoding="utf-8").split(PAGE_BREAK))


# What the digest job learned about a document, next to its text: one digest per section (the planner's map of
# the document) and, when an embedding model is configured, one vector per chunk.
def meta_path(project_dir: Path, doc_id: str) -> Path:
    return project_dir / "docs" / f"{doc_id}.sections.json"


def vectors_path(project_dir: Path, doc_id: str) -> Path:
    return project_dir / "docs" / f"{doc_id}.emb"


def save_section_digests(project_dir: Path, doc_id: str, digests: list[str]) -> None:
    meta_path(project_dir, doc_id).write_text(json.dumps({"digests": digests}, ensure_ascii=False), encoding="utf-8")


def load_section_digests(project_dir: Path, doc_id: str) -> list[str]:
    """One digest per `sections()` entry, in order; [] when the document was never digested by section."""
    try:
        got = json.loads(meta_path(project_dir, doc_id).read_text(encoding="utf-8")).get("digests")
        return [str(x) for x in got] if isinstance(got, list) else []
    except (OSError, ValueError, AttributeError):
        return []


def save_vectors(project_dir: Path, doc_id: str, model: str, vectors: list[list[float]]) -> None:
    """Unit vectors as float32, behind a one-line JSON header naming the model and the shape they belong to."""
    dim = len(vectors[0]) if vectors else 0
    head = json.dumps({"model": model, "n": len(vectors), "dim": dim}).encode() + b"\n"
    flat = array("f", (x for v in vectors for x in v))
    vectors_path(project_dir, doc_id).write_bytes(head + flat.tobytes())


def load_vectors(project_dir: Path, doc_id: str, model: str, n: int) -> list[array] | None:
    """The stored vectors, only if they are this model's and match today's `n` chunks — anything else is stale."""
    try:
        raw = vectors_path(project_dir, doc_id).read_bytes()
        head, _, body = raw.partition(b"\n")
        meta = json.loads(head)
        dim = int(meta["dim"])
        if meta.get("model") != model or meta.get("n") != n or not dim or len(body) != n * dim * 4:
            return None
        flat = array("f")
        flat.frombytes(body)
        return [flat[i * dim:(i + 1) * dim] for i in range(n)]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def pictures_path(project_dir: Path, doc_id: str) -> Path:
    return project_dir / "docs" / f"{doc_id}.images.json"


def save_picture_keys(project_dir: Path, doc_id: str, keys: list[str]) -> None:
    pictures_path(project_dir, doc_id).write_text(json.dumps(keys), encoding="utf-8")


def picture_keys(project_dir: Path, doc_id: str) -> list[str]:
    """The asset keys of the pictures this document brought into the deck."""
    try:
        got = json.loads(pictures_path(project_dir, doc_id).read_text(encoding="utf-8"))
        return [str(k) for k in got] if isinstance(got, list) else []
    except (OSError, ValueError):
        return []


def remove(project_dir: Path, doc_id: str) -> None:
    for p in (text_path(project_dir, doc_id), meta_path(project_dir, doc_id), vectors_path(project_dir, doc_id),
              pictures_path(project_dir, doc_id)):
        p.unlink(missing_ok=True)
