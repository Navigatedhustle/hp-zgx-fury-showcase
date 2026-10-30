"""The library as an Obsidian vault: notes, frontmatter, links that resolve, names, the zip, and the sync."""
import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, event
from sqlmodel import SQLModel

from app import main
from app.config import settings
from app.library import common
from app.library import obsidian as O
from app.library.graph import build_graph
from app.store import db
from app.store.db import LibDeck, LibSlide, LibTag

yaml = pytest.importorskip("yaml")   # installed with the test tooling; the app itself writes YAML by hand

WIN_BAD = re.compile(r'[\\:*?"<>|\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
LINK = re.compile(r"(?<!\\)(!?)\[\[([^\]|#^]+)(?:\|([^\]]*))?\]\]")


@pytest.fixture()
def lib(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'lib.db'}", connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _wal(conn, _):  # noqa: ANN001
        conn.execute("PRAGMA journal_mode=WAL")

    SQLModel.metadata.create_all(eng)
    old = db._engine
    db._engine = eng
    try:
        yield eng
    finally:
        db._engine = old
        eng.dispose()


def _png(deck_id: str, index: int, colour=(200, 30, 30)) -> Path:
    p = common.render_path(deck_id, index)
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (160, 90), colour).save(p)
    return p


@pytest.fixture()
def corpus(lib):
    db.save(LibTag(slug="generative-ai", label="Generative AI"))
    db.save(LibTag(slug="security", label="Security"))
    db.save(LibTag(slug="2025", label="2025"))
    a = db.save(LibDeck(project='Con:toso "AI"', title="AI pitch", filename="a.pptx", status="ready",
                        deck_date=datetime(2025, 6, 1)))
    b = db.save(LibDeck(project="Security", title="CON", filename="b.pptx", status="ready"))
    nasty = 'Edge [[AI]] #win | 50%% "q" \\ back sep \U0001F680 é'
    x = {
        "a1": db.save(LibSlide(deck_id=a.id, index=1, title="Spend: 2026?", favourite=True,
                               tags=["generative-ai", "security", "2025"], summary=nasty,
                               text="Line one [[not a link]]\n# not a heading\n%%hidden%%", notes="Say <b>this</b>",
                               entities=[{"name": "ZGX Fury", "type": "product"}, {"name": "Security", "type": "team"}])),
        "a2": db.save(LibSlide(deck_id=a.id, index=2, title="Spend: 2026?", favourite=True,
                               tags=["generative-ai", "security", "2025"],
                               entities=[{"name": "zgx fury", "type": "product"}, {"name": "Security", "type": "team"}])),
        "b1": db.save(LibSlide(deck_id=b.id, index=1, title="...", favourite=True, tags=["generative-ai"],
                               entities=[{"name": "ZGX Fury", "type": "product"}])),
    }
    _png(a.id, 1)
    _png(b.id, 1)
    return a, b, x


def _frontmatter(text: str) -> dict:
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    assert m, text[:200]
    return yaml.safe_load(m.group(1))


def _check_vault(files: dict[str, bytes]) -> None:
    """Every note's frontmatter parses; every link resolves; every name is Windows-safe and unique."""
    notes = {p: b.decode("utf-8") for p, b in files.items() if p.endswith(".md")}
    stems = [PurePosixPath(p).stem.casefold() for p in notes]
    assert len(stems) == len(set(stems)), "duplicate note names make Obsidian links ambiguous"
    for p in files:
        for part in PurePosixPath(p).parts:
            assert not WIN_BAD.search(part), p
            assert part == part.rstrip(". ") and not part.startswith(" "), p
            assert part.split(".")[0].upper() not in RESERVED, p
            if part != ".obsidian":
                assert not part.startswith("."), p
        if p.endswith(".md"):
            assert len(PurePosixPath(p).name) <= 120
    for p, text in notes.items():
        fm = _frontmatter(text)
        assert fm["generated_by"] == "hp-deck-builder"
        for embed, target, alias in LINK.findall(text):
            if embed:
                assert target in files, (p, target)
            else:
                assert f"{target}.md" in notes, (p, target)
                assert alias == PurePosixPath(target).name
                # also unambiguous by name alone, as Obsidian would resolve a bare [[name]]
                assert stems.count(PurePosixPath(target).name.casefold()) == 1


def _vault_files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_zip_is_a_vault(corpus, tmp_path):
    a, b, x = corpus
    with TestClient(main.app) as c:
        r = c.get("/api/library/obsidian.zip", params={"min_shared": 2})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert "HP%20Slide%20Library.zip" in r.headers["content-disposition"]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    files = {n: z.read(n) for n in z.namelist()}
    _check_vault(files)
    groups = json.loads(files[".obsidian/graph.json"])["colorGroups"]
    assert {g["query"] for g in groups} == {f'path:"HP Slide Library/{d}"' for d in ("Slides", "Projects", "Tags", "Entities")}
    assert all(isinstance(g["color"]["rgb"], int) and g["color"]["a"] == 1 for g in groups)

    notes = {p: v.decode() for p, v in files.items() if p.endswith(".md")}
    a1 = next(t for t in notes.values() if f"library_id: \"{x['a1'].id}\"" in t)
    fm = _frontmatter(a1)
    # escaping round-trips (emoji, U+2028, quotes, backslashes); only "[[" is broken up, so it is no link
    assert fm["summary"] == x["a1"].summary.replace("[[", "[ [").replace("]]", "] ]")
    assert fm["project"] == 'Con:toso "AI"' and fm["deck"] == "AI pitch" and fm["slide"] == 1
    assert str(fm["deck_date"]) == "2025-06-01"
    assert fm["tags"] == ["generative-ai", "security", "tag-2025"]   # Obsidian tags: no '#', not all digits
    assert "[[not a link]]" not in a1 and "\n# not a heading" not in a1 and "%%hidden" not in a1
    assert f"![[HP Slide Library/attachments/{x['a1'].id}.jpg]]" in a1
    assert f"/library?open={x['a1'].id}" in a1
    assert "Speaker notes" in a1 and "Mentions: " in a1 and "Tags: " in a1
    with Image.open(io.BytesIO(files[f"HP Slide Library/attachments/{x['a1'].id}.jpg"])) as im:
        assert im.format == "JPEG"
    # a slide without a render gets no embed (and no dangling attachment)
    a2 = next(t for t in notes.values() if f"library_id: \"{x['a2'].id}\"" in t)
    assert "![[" not in a2
    # hubs: project "Security", tag "Security" and entity "Security" are three distinct notes
    assert {"HP Slide Library/Projects/Security.md", "HP Slide Library/Tags/Security (tag).md",
            "HP Slide Library/Entities/Security (entity).md"} <= set(notes)
    assert "HP Slide Library/Library index.md" in notes
    assert "HP Slide Library/Entities/ZGX Fury.md" in notes
    # deck titled "CON" → a reserved-name-free slide note; title "..." → Untitled
    assert any(PurePosixPath(p).name == "Untitled — CON_ s1.md" for p in notes)


def test_names():
    assert O.safe_name('a/b\\c:d*e?f"g<h>i|j#k^l[m]n') == "a b c d e f g h i j k l m n"
    assert O.safe_name("  ..hidden. ") == "hidden"
    assert O.safe_name("CON") == "CON_" and O.safe_name("lpt1.txt") == "lpt1.txt_"
    assert O.safe_name("") == "Untitled" and O.safe_name("...") == "Untitled"
    assert len(O.safe_name("x" * 500)) == 117
    n = O.Names()
    assert [n.claim("A", "tag", 80), n.claim("a", "tag", 80), n.claim("A", "tag", 80)] == ["A", "a (tag)", "A (tag 2)"]
    assert n.claim("Library index", "project", 80) == "Library index (project)"


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    v = tmp_path / "My Vault"
    v.mkdir()
    monkeypatch.setenv("OBSIDIAN_VAULT_DIR", str(v))
    settings.cache_clear()
    yield v
    monkeypatch.delenv("OBSIDIAN_VAULT_DIR")
    settings.cache_clear()


def test_sync_idempotent_and_safe(corpus, vault):
    a, b, x = corpus
    root = vault / "HP Slide Library"
    (root / "Tags").mkdir(parents=True)
    (root / "Tags" / "My own note.md").write_text("---\ntags: [mine]\n---\nmine\n", encoding="utf-8")
    (root / "Plain.md").write_text("no frontmatter at all\n", encoding="utf-8")
    with TestClient(main.app) as c:
        st = c.get("/api/library/obsidian/status").json()
        assert st == {"configured": True, "vault_dir": str(vault.resolve()), "exists": True, "is_vault": False,
                      "last_sync": None}
        first = c.post("/api/library/obsidian/sync", json={"scope": "favourites", "min_shared": 2}).json()
        assert first["written"] > 0 and first["removed"] == 0 and first["folder"] == str(root.resolve())
        assert first["open_uri"].startswith("obsidian://open?path=")
        assert Path(unquote(first["open_uri"].split("=", 1)[1])) == (root / "Library index.md").resolve()
        assert (vault / ".obsidian" / "graph.json").exists()   # a new vault gets colour groups
        files = _vault_files(vault)
        _check_vault({p: v for p, v in files.items()
                      if p.startswith(".obsidian/") or (p.startswith("HP Slide Library/") and p.endswith((".md", ".jpg"))
                                                      and "My own note" not in p and "Plain" not in p)})

        second = c.post("/api/library/obsidian/sync", json={"scope": "favourites", "min_shared": 2}).json()
        assert second["written"] == 0 and second["removed"] == 0
        assert second["unchanged"] == first["written"] + first["unchanged"]
        assert _vault_files(vault) == {**files, "HP Slide Library/.hp-deck-builder.json":
                                       (root / ".hp-deck-builder.json").read_bytes()}
        st = c.get("/api/library/obsidian/status").json()
        assert st["is_vault"] and st["last_sync"]

        # the user customises the graph; a later sync never overwrites it
        (vault / ".obsidian" / "graph.json").write_text("{}", encoding="utf-8")
        # unfavourite b1 and raise min_shared: its note, its project hub, its attachment go; user notes stay
        x["b1"].favourite = False
        db.save(x["b1"])
        third = c.post("/api/library/obsidian/sync", json={"scope": "favourites", "min_shared": 3}).json()
        assert third["removed"] > 0
        after = _vault_files(vault)
        assert not any(x["b1"].id in p for p in after)
        assert not any(p.startswith("HP Slide Library/Projects/Security") for p in after)
        assert not (root / "Slides" / "Security").exists()      # emptied folder removed
        assert (root / "Tags" / "My own note.md").exists() and (root / "Plain.md").exists()
        assert (vault / ".obsidian" / "graph.json").read_text(encoding="utf-8") == "{}"
        assert c.post("/api/library/obsidian/sync", json={"min_shared": 3}).json()["written"] == 0


def test_user_note_with_a_generated_name_is_kept(corpus, vault):
    root = vault / "HP Slide Library" / "Projects"
    root.mkdir(parents=True)
    (vault / ".obsidian").mkdir()
    mine = root / "Security.md"
    mine.write_text("my project notes\n", encoding="utf-8")
    O.sync(build_graph("favourites", None, 2), vault)
    assert mine.read_text(encoding="utf-8") == "my project notes\n"
    assert not (vault / ".obsidian" / "graph.json").exists()   # an existing vault: never written


def test_sync_400_when_not_configured(corpus, tmp_path, monkeypatch):
    with TestClient(main.app) as c:
        monkeypatch.setenv("OBSIDIAN_VAULT_DIR", "")
        settings.cache_clear()
        try:
            assert c.get("/api/library/obsidian/status").json() == {
                "configured": False, "vault_dir": None, "exists": False, "is_vault": False, "last_sync": None}
            assert c.post("/api/library/obsidian/sync", json={}).status_code == 400
            monkeypatch.setenv("OBSIDIAN_VAULT_DIR", str(tmp_path / "missing"))
            settings.cache_clear()
            assert c.get("/api/library/obsidian/status").json()["exists"] is False
            assert c.post("/api/library/obsidian/sync", json={}).status_code == 400
        finally:
            monkeypatch.delenv("OBSIDIAN_VAULT_DIR")
            settings.cache_clear()


def test_yaml_escaping_round_trips():
    for s in ['plain', 'a "quote" and \\ slash', "tab\there\nnew", "\x00\x07\x1b\x7f\x85", "  ﻿",
              "emoji \U0001F680 é ü 日本", ": - # [ ] { } & * ! | > ' % @ `", ""]:
        assert yaml.safe_load(f"k: {O.yaml_str(s)}")["k"] == s
