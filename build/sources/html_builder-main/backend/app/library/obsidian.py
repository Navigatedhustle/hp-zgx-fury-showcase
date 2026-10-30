"""The library graph as an Obsidian vault: one note per slide, hub notes per project / tag / entity.

Same data as the Graph tab (`graph.build_graph`), rendered as Markdown so Obsidian's graph view shows the
same picture. Two ways out: a zip that is a vault (`GET /obsidian.zip`), or a sync into the user's own
vault (`OBSIDIAN_VAULT_DIR`, `POST /obsidian/sync`).

Layout (everything under one folder, so a sync can never reach the rest of a vault):
  HP Slide Library/Library index.md
  HP Slide Library/Slides/<Project>/<title> — <deck title> s<n>.md
  HP Slide Library/Projects/<Project>.md · Tags/<Tag>.md · Entities/<Entity>.md
  HP Slide Library/attachments/<slide id>.jpg      (the 1600 px render as JPEG q85)
  HP Slide Library/.hp-deck-builder.json            (sync manifest: attachments written, last sync; hidden)
  .obsidian/graph.json                              (colour groups — only into a folder that is not yet a vault)

Links are vault-root paths with an alias (`[[HP Slide Library/Tags/Security|Security]]`): Obsidian resolves a
bare `[[Security]]` by note name across the whole vault and picks one silently when two notes share it, so a
user's own "Security.md" elsewhere would capture the link. Note names are also unique (case-insensitively)
across the whole generated folder, so they read unambiguously in the graph.

Sync safety: a note is ours when its frontmatter says `generated_by: hp-deck-builder`; only those are ever
rewritten or removed. Attachments are ours when the manifest lists them. Files are rewritten only when their
bytes change; the index's "last updated" line moves only when something else did.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from ..config import settings
from ..downloads import disposition
from ..store.db import now
from . import common
from .graph import Graph, Node, Scope, build_graph

log = logging.getLogger(__name__)
router = APIRouter()

FOLDER = "HP Slide Library"
MARKER = "hp-deck-builder"
INDEX = "Library index"
MANIFEST = ".hp-deck-builder.json"
MAX_NAME = 120          # characters in a note's filename, ".md" included
HUB_NAME = 80           # hubs are also folder names (Slides/<Project>/): keep paths well inside Windows' 260
SLIDE_NAME = 100
JPEG_QUALITY = 85
DIRS = {"slide": "Slides", "project": "Projects", "tag": "Tags", "entity": "Entities"}
# Colour groups for graph.json: Obsidian packs a colour as (R << 16) | (G << 8) | B.
# The Graph tab's light-theme colours (frontend tokens --muted, --accent, --good, --warn), so both graphs read alike.
COLOURS = {"Slides": 0x5A6376, "Projects": 0x024AD8, "Tags": 0x0B8F5E, "Entities": 0xA8660A}
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_sync_lock = threading.Lock()


# ------------------------------------------------------------------ names
def safe_name(text: str, limit: int = MAX_NAME - 3) -> str:
    """A filename that works on Windows and inside a wikilink: no `\\/:*?"<>|` (Windows) and no `#^[]|` or `%%`
    (Obsidian link syntax), no control characters, no leading dots (hidden in Obsidian), no trailing dots or
    spaces (Windows drops them), not a reserved device name, at most `limit` characters."""
    s = re.sub(r'[\\/:*?"<>|#^\[\]\x00-\x1f\x7f]+', " ", text or "")
    while "%%" in s:
        s = s.replace("%%", "%")
    s = re.sub(r"\s+", " ", s).strip().lstrip(". ")
    s = s[:limit].rstrip(". ")
    if not s:
        s = "Untitled"
    if s.split(".")[0].strip().upper() in _RESERVED:
        s = f"{s}_"
    return s


class Names:
    """Unique note names across the whole generated folder, compared case-insensitively (Windows and macOS
    file systems, and Obsidian's own link matching, ignore case)."""

    def __init__(self) -> None:
        self.taken: set[str] = {INDEX.casefold()}

    def claim(self, base: str, kind: str, limit: int) -> str:
        base = safe_name(base, limit)
        tries = [base, f"{base} ({kind})", *(f"{base} ({kind} {n})" for n in range(2, 10_000))]
        for name in tries:
            if name.casefold() not in self.taken:
                self.taken.add(name.casefold())
                return name
        raise RuntimeError("no free note name")  # pragma: no cover — 10k collisions on one name


def obsidian_tag(slug: str) -> str:
    """Obsidian tag syntax (letters, digits, `_`, `-`, `/`; at least one non-digit), without the '#'."""
    t = re.sub(r"[^\w/-]+", "-", slug or "", flags=re.UNICODE).strip("-/") or "tag"
    return f"tag-{t}" if t.replace("/", "").isdigit() else t


# ------------------------------------------------------------------ YAML (no PyYAML in requirements)
def yaml_str(s: str) -> str:
    """A YAML double-quoted scalar. Everything outside YAML's printable set — and the characters some parsers
    treat as line breaks (NEL, LS, PS) — is escaped, so any slide text parses back exactly."""
    out = ['"']
    for ch in s or "":
        o = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif o < 0x20 or 0x7F <= o <= 0x9F or o in (0x2028, 0x2029, 0xFEFF, 0xFFFE, 0xFFFF) or 0xD800 <= o <= 0xDFFF:
            out.append(f"\\x{o:02x}" if o <= 0xFF else f"\\u{o:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def unlink(s: str) -> str:
    """Obsidian reads `[[...]]` inside a property value as a link: slide text in frontmatter must not make one."""
    return s.replace("[[", "[ [").replace("]]", "] ]")


def frontmatter(fields: dict[str, object]) -> str:
    """str → quoted; int/bool → plain; None → empty (null); list → block list of quoted strings (Obsidian
    wants `tags` as a list); a value already formatted (`Raw`) → as is."""
    lines = ["---"]
    for k, v in fields.items():
        if v is None:
            lines.append(f"{k}:")
        elif isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, int):
            lines.append(f"{k}: {v}")
        elif isinstance(v, Raw):
            lines.append(f"{k}: {v.text}")
        elif isinstance(v, list):
            lines.append(f"{k}:" if v else f"{k}: []")
            lines.extend(f"  - {yaml_str(unlink(str(x)))}" for x in v)
        else:
            lines.append(f"{k}: {yaml_str(unlink(str(v)))}")
    lines.append("---")
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class Raw:
    text: str


def is_generated(path: Path) -> bool:
    """True when the note's frontmatter carries our marker — the only notes a sync may rewrite or delete."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            head = f.read(8192)
    except OSError:
        return False
    m = re.match(r"\A﻿?---\r?\n(.*?)\r?\n---\s*(\r?\n|\Z)", head, re.S)
    return bool(m and re.search(rf'^generated_by:\s*"?{re.escape(MARKER)}"?\s*$', m.group(1), re.M))


# ------------------------------------------------------------------ Markdown
_MD_SPECIAL = re.compile(r"([\\`*_\[\]#<>|~=%^$])")


def md_escape(text: str) -> str:
    """Slide text is shown, never interpreted: no stray links, tags, comments, HTML or maths."""
    return _MD_SPECIAL.sub(r"\\\1", text or "")


def md_block(text: str) -> str:
    """Escaped, with a line break kept per source line and blank runs collapsed."""
    lines = [md_escape(x.rstrip()) for x in (text or "").replace("\r", "").split("\n")]
    out = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


@dataclass
class Vault:
    """Rendered notes (vault-relative POSIX path → text) and attachments (path → render to convert)."""
    notes: dict[str, str] = field(default_factory=dict)
    attachments: dict[str, Path] = field(default_factory=dict)
    index_path: str = f"{FOLDER}/{INDEX}.md"

    def paths(self) -> set[str]:
        return set(self.notes) | set(self.attachments)


def link(path: str, name: str) -> str:
    """`[[HP Slide Library/Tags/Security|Security]]` — `path` is the vault-relative note path."""
    return f"[[{path.removesuffix('.md')}|{name}]]"


def render_image(deck_id: str, index: int) -> Path | None:
    for p in (common.render_path(deck_id, index), common.render_path(deck_id, index, thumb=True)):
        if p.exists():
            return p
    return None


def jpeg_bytes(src: Path) -> bytes:
    from PIL import Image

    with Image.open(src) as im:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {'entities' if noun == 'entity' else noun + 's'}"


def _index_note(g: Graph, paths: dict[str, str], names: dict[str, str], updated: str) -> str:
    projects = [n for n in g.nodes if n.type == "project"]
    st = g.stats
    body = [frontmatter({"type": "index", "slides": st["slides"], "projects": st["projects"], "tags": st["tags"],
                         "entities": st["entities"], "generated_by": Raw(MARKER)}),
            "# HP Slide Library", "",
            "Slides from the HP Deck Builder slide library, written by the app. Notes in this folder that the app "
            "wrote carry `generated_by: hp-deck-builder` and are rewritten on every sync; notes you add here "
            "yourself are left alone.", "",
            " · ".join(_count(st[k], k[:-1] if k != "entities" else "entity") for k in st), "",
            "## Projects", "",
            *[f"- {link(paths[n.id], names[n.id])}" for n in projects], "",
            f"Last updated: {updated}", ""]
    return "\n".join(body)


def render(g: Graph, *, port: int | None = None, updated: str = "") -> Vault:
    """The whole vault for `g`. Deterministic except the index's `updated` line."""
    port = port or settings().port
    names: dict[str, str] = {}
    paths: dict[str, str] = {}
    taken = Names()
    hubs = [n for n in g.nodes if n.type != "slide"]
    slides = [n for n in g.nodes if n.type == "slide"]
    # hubs claim names first: they are the ones people read in the graph
    for kind in ("project", "tag", "entity"):
        for n in (h for h in hubs if h.type == kind):
            names[n.id] = taken.claim(n.label, kind, HUB_NAME)
            paths[n.id] = f"{FOLDER}/{DIRS[kind]}/{names[n.id]}.md"
    for n in slides:
        d = n.data
        base = f"{safe_name(n.label, 60)} — {safe_name(d['deck'], 30)} s{d['number']}"
        names[n.id] = taken.claim(base, "slide", SLIDE_NAME)
        paths[n.id] = f"{FOLDER}/{DIRS['slide']}/{names['p:' + d['project']]}/{names[n.id]}.md"

    by_id = g.by_id()
    out: dict[str, list[str]] = {n.id: [] for n in g.nodes}   # hub → linked slide ids
    nbs: dict[str, dict[str, list[Node]]] = {n.id: {"in": [], "tagged": [], "mentions": []} for n in slides}
    for e in g.edges:   # sorted, so each list comes out in id order
        out[e.target].append(e.source)
        nbs[e.source][e.type].append(by_id[e.target])
    v = Vault()
    for n in slides:
        sl = g.slides[n.data["slide_id"]]
        d = n.data
        nb = nbs[n.id]
        # frontmatter tags are every tag on the slide (Obsidian's tag pane), pruned or not; links follow min_shared
        tags = [obsidian_tag(t) for t in dict.fromkeys(sl.tags or []) if isinstance(t, str) and t]
        img = render_image(sl.deck_id, sl.index)
        lines = [frontmatter({
            "project": d["project"], "deck": d["deck"],
            "deck_date": Raw(d["deck_date"][:10]) if d["deck_date"] else None,
            "slide": int(d["number"]), "slide_type": sl.slide_type or "", "tags": tags, "summary": sl.summary or "",
            "library_id": sl.id, "generated_by": Raw(MARKER)}).rstrip("\n"), ""]
        lines += [f"# {md_escape(n.label)}", ""]
        if img is not None:
            att = f"{FOLDER}/attachments/{sl.id}.jpg"
            v.attachments[att] = img
            lines += [f"![[{att}]]", ""]
        if sl.summary:
            lines += [md_block(sl.summary), ""]
        lines.append("Project: " + " ".join(link(paths[p.id], names[p.id]) for p in nb["in"]))
        if nb["tagged"]:
            lines.append("Tags: " + " · ".join(link(paths[t.id], names[t.id]) for t in nb["tagged"]))
        if nb["mentions"]:
            lines.append("Mentions: " + " · ".join(link(paths[x.id], names[x.id]) for x in nb["mentions"]))
        lines.append("")
        if (sl.text or "").strip():
            lines += ["## Slide text", "", md_block(sl.text), ""]
        if (sl.notes or "").strip():
            lines += ["## Speaker notes", "", md_block(sl.notes), ""]
        lines += [f"[Open in HP Deck Builder](http://127.0.0.1:{port}/library?open={quote(sl.id)})", ""]
        v.notes[paths[n.id]] = "\n".join(lines)

    for n in hubs:
        linked = sorted(out[n.id], key=lambda i: names[i].casefold())
        count = len(linked)
        if n.type == "project":
            fm = {"type": "project", "project": n.data["project"], "slides": count, "decks": n.data["decks"]}
            desc = f"Project {md_escape(n.label)}: {count} slide{'s' * (count != 1)} from {n.data['decks']} " \
                   f"deck{'s' * (n.data['decks'] != 1)} in the slide library."
        elif n.type == "tag":
            fm = {"type": "tag", "tag": n.data["slug"], "facet": n.data["facet"], "slides": count,
                  "tags": [obsidian_tag(n.data["slug"])]}
            desc = f"Tag ({md_escape(n.data['facet'])}) on {count} slide{'s' * (count != 1)} in the slide library."
        else:
            fm = {"type": "entity", "entity": n.label, "entity_type": n.data["type"], "slides": count}
            kind = f" ({md_escape(n.data['type'])})" if n.data["type"] else ""
            desc = f"Mentioned{kind} on {count} slide{'s' * (count != 1)} in the slide library."
        lines = [frontmatter({**fm, "generated_by": Raw(MARKER)}).rstrip("\n"), "", f"# {md_escape(n.label)}", "",
                 desc, "", "## Slides", "", *[f"- {link(paths[i], names[i])}" for i in linked], ""]
        v.notes[paths[n.id]] = "\n".join(lines)

    v.notes[v.index_path] = _index_note(g, paths, names, updated)
    return v


def graph_json() -> str:
    """`.obsidian/graph.json` with one colour group per note kind. Obsidian fills in any key left out."""
    groups = [{"query": f'path:"{FOLDER}/{d}"', "color": {"a": 1, "rgb": COLOURS[d]}} for d in COLOURS]
    return json.dumps({"colorGroups": groups, "showTags": False, "showAttachments": False, "hideUnresolved": False,
                       "showOrphans": True, "showArrow": False, "textFadeMultiplier": 0, "nodeSizeMultiplier": 1,
                       "lineSizeMultiplier": 1}, indent=2) + "\n"


def _stamp() -> str:
    return now().strftime("%Y-%m-%d %H:%M UTC")


# ------------------------------------------------------------------ zip
def write_zip(g: Graph, out: Path) -> Path:
    v = render(g, updated=_stamp())
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(".obsidian/graph.json", graph_json())
        for p in sorted(v.notes):
            z.writestr(p, v.notes[p].encode("utf-8"))
        for p in sorted(v.attachments):
            try:
                z.writestr(p, jpeg_bytes(v.attachments[p]), compress_type=zipfile.ZIP_STORED)
            except Exception as e:  # noqa: BLE001 — one unreadable render must not lose the vault
                log.warning("obsidian zip: could not convert %s: %s", v.attachments[p], e)
    return out


# ------------------------------------------------------------------ sync
def vault_dir() -> Path | None:
    return settings().obsidian_vault_dir


def _manifest(root: Path) -> dict:
    try:
        return json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_if_changed(path: Path, data: bytes) -> bool:
    try:
        if path.read_bytes() == data:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-hpdb")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return True


def _inside(root: Path, rel: str) -> Path:
    p = (root.parent / rel).resolve()
    if p != root and root not in p.parents:  # names are sanitised; this is the belt to those braces
        raise RuntimeError(f"refusing to write outside {root}: {rel}")
    return p


def sync(g: Graph, vault: Path) -> dict:
    """Write `g` into `<vault>/HP Slide Library/`. Returns `{written, unchanged, removed, folder, open_uri}`."""
    with _sync_lock:
        root = (vault / FOLDER).resolve()
        new_vault = not (vault / ".obsidian").exists()
        old = _manifest(root)
        written = unchanged = removed = 0

        v = render(g, updated="")   # placeholder stamp; the real one is decided below
        index_rel = v.index_path
        notes = dict(v.notes)
        notes.pop(index_rel)
        for rel in sorted(notes):
            p = _inside(root, rel)
            if p.exists() and not is_generated(p):
                log.warning("obsidian sync: %s is a note of yours with the same name — left alone", p)
                unchanged += 1
                continue
            if _write_if_changed(p, notes[rel].encode("utf-8")):
                written += 1
            else:
                unchanged += 1
        for rel in sorted(v.attachments):
            p, src = _inside(root, rel), v.attachments[rel]
            if p.exists() and p.stat().st_mtime >= src.stat().st_mtime:
                unchanged += 1
                continue
            try:
                _write_if_changed(p, jpeg_bytes(src))
                written += 1
            except Exception as e:  # noqa: BLE001
                log.warning("obsidian sync: could not convert %s: %s", src, e)

        # stale notes we wrote earlier, and attachments the manifest says are ours
        keep = {_inside(root, r) for r in v.paths()}
        emptied: set[Path] = set()
        if root.exists():
            for p in sorted(root.rglob("*.md")):
                if p.resolve() not in keep and is_generated(p):
                    p.unlink()
                    removed += 1
                    emptied.add(p.parent)
        for rel in old.get("attachments") or []:
            if not isinstance(rel, str):
                continue
            try:
                p = _inside(root, rel)
            except RuntimeError:
                continue
            if p not in keep and p.is_file():
                p.unlink()
                removed += 1
                emptied.add(p.parent)
        for d in sorted(emptied, key=lambda x: len(x.parts), reverse=True):
            while d != root and root in d.parents:
                try:
                    d.rmdir()   # only when empty
                except OSError:
                    break
                d = d.parent

        # the index: its "Last updated" line moves only when something else changed (or it is missing / not ours)
        ip = _inside(root, index_rel)
        cur = ip.read_text(encoding="utf-8") if ip.exists() else None
        strip = lambda s: re.sub(r"^Last updated: .*$", "", s or "", flags=re.M)  # noqa: E731
        if cur is not None and not is_generated(ip):
            unchanged += 1
        elif cur is not None and not written and not removed and strip(cur) == strip(v.notes[index_rel]):
            unchanged += 1
        else:
            _write_if_changed(ip, render(g, updated=_stamp()).notes[index_rel].encode("utf-8"))
            written += 1

        if new_vault:   # a folder Obsidian has never opened: make the graph legible on first open
            _write_if_changed(vault / ".obsidian" / "graph.json", graph_json().encode("utf-8"))
        _write_if_changed(root / MANIFEST, (json.dumps(
            {"generated_by": MARKER, "last_sync": now().isoformat(), "attachments": sorted(v.attachments)},
            indent=1) + "\n").encode("utf-8"))
        return {"written": written, "unchanged": unchanged, "removed": removed, "folder": str(root),
                "open_uri": "obsidian://open?path=" + quote(str(ip), safe="")}


def status() -> dict:
    v = vault_dir()
    exists = bool(v and v.is_dir())
    return {"configured": v is not None, "vault_dir": str(v) if v else None, "exists": exists,
            "is_vault": bool(exists and (v / ".obsidian").is_dir()),
            "last_sync": _manifest(v / FOLDER).get("last_sync") if exists else None}


# ------------------------------------------------------------------ API
class SyncBody(BaseModel):
    scope: Scope = "favourites"
    project: str | None = None
    min_shared: int = 2


@router.get("/obsidian.zip")
async def obsidian_zip(scope: Scope = "favourites", project: str | None = None,
                       min_shared: int = Query(default=2, ge=1, le=1000)):
    """A zip that is an Obsidian vault: unzip it and "Open folder as vault"."""
    work = Path(tempfile.mkdtemp(prefix="libvault-"))
    try:
        g = await asyncio.to_thread(build_graph, scope, project or None, min_shared)
        out = await asyncio.to_thread(write_zip, g, work / "vault.zip")
    except Exception as e:
        shutil.rmtree(work, ignore_errors=True)
        log.exception("obsidian zip failed")
        raise HTTPException(500, f"Vault export failed: {e}") from e
    return FileResponse(out, media_type="application/zip", headers=disposition(FOLDER, "zip", fallback="vault", spaces=True),
                        background=BackgroundTask(shutil.rmtree, work, ignore_errors=True))


@router.get("/obsidian/status")
def obsidian_status() -> dict:
    """`{configured, vault_dir, exists, is_vault, last_sync}`."""
    return status()


@router.post("/obsidian/sync")
async def obsidian_sync(body: SyncBody) -> dict:
    """`{written, unchanged, removed, folder, open_uri}`; 400 when OBSIDIAN_VAULT_DIR is not set or missing."""
    v = vault_dir()
    if v is None:
        raise HTTPException(400, "No Obsidian vault configured: set OBSIDIAN_VAULT_DIR in .env and restart the app")
    if not v.is_dir():
        raise HTTPException(400, f"The Obsidian vault folder does not exist: {v}")
    g = await asyncio.to_thread(build_graph, body.scope, body.project or None, max(1, body.min_shared))
    return await asyncio.to_thread(sync, g, v)

