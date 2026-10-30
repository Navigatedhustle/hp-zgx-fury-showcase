"""Library search: the query language, the two indexes, filters, facets, collapse, and speed at 10k slides."""
import random
import string
import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlmodel import SQLModel

from app.library import search as S
from app.store import db
from app.store.db import LibDeck, LibSlide, LibTag


@pytest.fixture()
def lib(tmp_path):
    """A fresh, empty database for each test: the rest of the suite shares one, and these assert exact counts."""
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
        S._ensured.discard(id(eng))
        eng.dispose()


_t0 = datetime(2026, 1, 1)


def deck(project="Contoso", title="Deck", n=0, **kw) -> LibDeck:
    d = LibDeck(project=project, title=title, filename=f"{title}.pptx", status="ready",
                created_at=_t0 + timedelta(days=n), **kw)
    with db.session() as s:
        s.add(d)
        s.commit()
    return d


def slide(d: LibDeck, index=1, title="", text="", **kw) -> LibSlide:
    x = LibSlide(deck_id=d.id, index=index, title=title, text=text, created_at=d.created_at, **kw)
    with db.session() as s:
        s.add(x)
        s.commit()
    S.reindex([x.id])
    return x


def ids(res) -> list[str]:
    return [i["id"] for i in res["items"]]


# ------------------------------------------------------------------ parser

def test_parse_phrases_fields_negation():
    p = S.parse('"cloud spend" project:"Contoso GenAI" tag:genai type:chart deck:ld1 is:fav -egress -"old plan" gpu')
    assert [(t.text, t.phrase) for t in p.terms] == [("cloud spend", True), ("gpu", False)]
    assert [t.text for t in p.negated] == ["egress", "old plan"]
    assert ("project", "Contoso GenAI", False) in p.filters
    assert {f[0] for f in p.filters} == {"project", "tag", "type", "deck", "fav"}


def test_parse_unknown_key_is_text_and_negated_filter():
    p = S.parse("10:30 http://x -project:old")
    assert [t.text for t in p.terms] == ["10:30", "http://x"]
    assert p.filters == [("project", "old", True)]


def test_parse_stopwords_and_prefix():
    p = S.parse("risk of printers")
    assert [t.text for t in p.terms] == ["risk", "printers"] and [t.text for t in p.optional] == ["of"]
    assert S.parse("the").terms[0].text == "the"
    p = S.parse("z cl")
    assert not p.terms[0].prefix and p.terms[1].prefix  # one letter: no prefix, except the last word


def test_parse_unbalanced_and_junk():
    assert [t.text for t in S.parse('"unterminated phrase').terms] == ["unterminated phrase"]
    assert S.parse('- -- " "" $ — ***').terms == []
    assert S.parse("").terms == []


def test_fuzz_never_raises(lib):
    d = deck()
    slide(d, title='Weird "quotes" AND (parens) * NEAR/2 col:on', text="a-b c_d 1.5% $4.2M")
    rnd = random.Random(7)
    alphabet = string.ascii_letters + string.digits + ' "\'-*:()^+.$%&|\\/{}[]<>!?#@~`,;=_' + "éüß中文—…"
    cases = ['"', '""', '"*"', "*", "-", "^", "NEAR(a b)", "a OR", "AND", "NOT x", "col:", ":", "tag:", 'tag:"',
             "-\"\"", "\x00", "a\x00b", "'); DROP TABLE libslide; --", "{a b}", "x" * 2000]
    cases += ["".join(rnd.choice(alphabet) for _ in range(rnd.randint(1, 40))) for _ in range(400)]
    for q in cases:
        res = S.search(q)
        assert isinstance(res["total"], int)
    assert S.search("4.2M")["total"] == 1   # the table survived


def test_endpoint_rejects_nothing(lib):
    from app.main import app
    d = deck()
    slide(d, title="Cloud GPU spend")
    c = TestClient(app)
    for q in ['"', "NEAR(", "*", "-", "a:b:c", "tag:"]:
        r = c.get("/api/library/search", params={"q": q})
        assert r.status_code == 200, (q, r.text)
    r = c.get("/api/library/search", params={"q": "cloud"})
    assert r.json()["total"] == 1 and set(r.json()["facets"]) == {"project", "tag", "type", "entity", "deck", "origin"}


# ------------------------------------------------------------------ matching and ranking

def test_title_beats_body(lib):
    d = deck()
    body = slide(d, 1, title="Agenda", text="Deployment plan, cost comparison, product lineup")
    title = slide(d, 2, title="Deployment plan", text="Week 1: site survey")
    assert ids(S.search("deployment plan"))[:2] == [title.id, body.id]


def test_project_and_tags_weigh_more_than_text(lib):
    d1 = deck("Fabrikam", "Print", 1)
    d2 = deck("Other", "Other", 2)
    t = LibTag(slug="print-security", label="Print security", aliases=["printsec"])
    with db.session() as s:
        s.add(t)
        s.commit()
    tagged = slide(d2, 1, title="Device layers", tags=["print-security"])
    mention = slide(d2, 2, title="Misc", text="something about print security somewhere in a long body")
    assert ids(S.search("printsec")) == [tagged.id]           # aliases are indexed
    assert ids(S.search("print security"))[0] == tagged.id
    assert mention.id in ids(S.search("print security"))
    assert ids(S.search("fabrikam")) == [] and S.search("fabrikam")["total"] == 0  # deck has no slides yet
    x = slide(d1, 1, title="Anything")
    assert ids(S.search("fabrikam")) == [x.id]


def test_prefix_and_exact_outranks_prefix(lib):
    d = deck()
    a = slide(d, 1, title="Cloudy outlook")
    b = slide(d, 2, title="Cloud outlook")
    assert ids(S.search("cloud")) == [b.id, a.id]
    assert ids(S.search("clo")) and set(ids(S.search("clo"))) == {a.id, b.id}


def test_plural_and_singular(lib):
    d = deck()
    a = slide(d, 1, title="Printer fleet")
    b = slide(d, 2, title="HP Z Workstations")
    c = slide(d, 3, title="Policies and reports")
    assert ids(S.search("printers")) == [a.id]
    assert ids(S.search("workstation")) == [b.id]
    assert ids(S.search("policy")) == [c.id]
    assert "<mark>Printer</mark>" in S.search("printers")["items"][0]["snippet"]
    assert ids(S.search("-printers")) and a.id not in ids(S.search("-printers"))
    assert S.parse("deploym").terms[0].prefix and ids(S.search("work")) == [b.id]  # still a prefix search


def test_slide_words_beat_deck_words(lib):
    """Project and deck title are on every slide of the deck: the slide that also says it comes first."""
    d = deck("Contoso AI", "Contoso pitch")
    others = [slide(d, i, title=t) for i, t in enumerate(["Thank you", "Agenda", "Next steps"], 1)]
    named = slide(d, 9, title="HP Z Workstations for AI", text="Prepared for Contoso Engineering, Q3 2026, with a "
                  "long subtitle that makes this slide much longer than the others")
    res = ids(S.search("contoso"))
    assert res[0] == named.id and set(res) == {named.id, *(o.id for o in others)}


def test_terms_side_by_side_rank_first(lib):
    d = deck()
    apart = slide(d, 1, title="Spend review", text="Quarterly figures: Q3 2025, Q4 2025, Q1 2026, Q2 2026")
    together = slide(d, 2, title="Kickoff", text="Prepared for the engineering team, Q3 2026, long text body here")
    assert ids(S.search("Q3 2026")) == [together.id, apart.id]


def test_schema_change_rebuilds_index(lib):
    d = deck()
    x = slide(d, 1, title="Rebuild me")
    with S._conn() as c:
        c.execute("UPDATE lib_search_meta SET v = 'old' WHERE k = 'schema'")
    S._ensured.clear()
    assert ids(S.search("rebuild")) == [x.id]
    with S._conn() as c:
        assert c.execute("SELECT v FROM lib_search_meta").fetchone()[0] == S.SCHEMA


def test_punctuated_tokens_and_numbers(lib):
    d = deck()
    fury = slide(d, 1, title="HP ZGX-Fury", text="748 GB coherent memory")
    money = slide(d, 2, title="Savings", text="Total $4.2M over three years; 1,576,000 vs 417,000", notes="Savings: $1.16M")
    q3 = slide(d, 3, title="Prepared for Q3 2026")
    assert ids(S.search("ZGX")) == [fury.id]
    assert ids(S.search("zgx-fury")) == [fury.id]
    assert ids(S.search("4.2M")) == [money.id]
    assert ids(S.search("$4.2M")) == [money.id]
    assert ids(S.search("1,576,000")) == [money.id]
    assert ids(S.search("1.16M")) == [money.id]
    assert ids(S.search('"Q3 2026"')) == [q3.id]


def test_trigram_substring_ranks_after_words(lib):
    d = deck()
    sub = slide(d, 1, title="HP Z Workstations", text="Part ZGXFury-748")
    word = slide(d, 2, title="Fury of the storm")
    assert ids(S.search("station")) == [sub.id]       # mid-word: only the trigram index finds it
    assert ids(S.search("fury")) == [word.id, sub.id]  # whole word first, substring after
    assert ids(S.search("Fury 748")) == [sub.id]       # one term by substring, one by word
    r = S.search("station")["items"][0]
    assert "<mark>station</mark>" in r["snippet"].lower() or "<mark>" in r["snippet"]


def test_and_then_relaxed(lib):
    d = deck()
    a = slide(d, 1, title="What customers say", text="Quote from an aerospace director")
    assert S.search("customers aerospace")["relaxed"] is False
    res = S.search("customers testimonial")
    assert res["relaxed"] is True and ids(res) == [a.id]
    assert S.search("zzzz qqqq")["total"] == 0


def test_negation(lib):
    d = deck()
    a = slide(d, 1, title="Cloud GPU spend")
    b = slide(d, 2, title="Cloud egress fees")
    assert ids(S.search("cloud -egress")) == [a.id]
    assert ids(S.search('cloud -"egress fees"')) == [a.id]
    assert set(ids(S.search("-egress"))) == {a.id}   # negation alone filters a browse


def test_snippet_escapes_and_marks(lib):
    d = deck()
    slide(d, 1, title="T", text="Use <script>alert(1)</script> & enjoy cloud savings of $4.2M today")
    snip = S.search("cloud")["items"][0]["snippet"]
    assert "<script>" not in snip and "&lt;script&gt;" in snip and "&amp;" in snip
    assert "<mark>cloud</mark>" in snip
    snip = S.search("4.2M")["items"][0]["snippet"]
    assert "<mark>4.2M</mark>" in snip
    assert S.search("")["items"][0]["snippet"] == ""


def test_snippet_prefers_field_with_most_terms():
    t = [S.Term("gpu"), S.Term("spend")]
    snip = S.snippet(["gpu only here", "summary on gpu spend", "", ""], t)
    assert snip == "summary on <mark>gpu</mark> <mark>spend</mark>"
    long = "word " * 100 + "needle " + "word " * 100
    s = S.snippet([long], [S.Term("needle")])
    assert s.startswith("…") and s.endswith("…") and "<mark>needle</mark>" in s and len(s) < 260


# ------------------------------------------------------------------ filters, facets, sort, paging

@pytest.fixture()
def corpus(lib):
    with db.session() as s:
        s.add(LibTag(slug="generative-ai", label="Generative AI", aliases=["genai"]))
        s.add(LibTag(slug="security", label="Security"))
        s.commit()
    a = deck("Contoso", "AI pitch", 1, deck_date=datetime(2025, 6, 1))
    b = deck("Fabrikam", "Print pitch", 2, deck_date=datetime(2026, 3, 1), origin="converted")
    out = {
        "a1": slide(a, 1, "Cloud GPU spend", tags=["generative-ai"], slide_type="chart", favourite=True,
                    entities=[{"name": "Contoso", "type": "customer"}]),
        "a2": slide(a, 2, "Cloud cost table", slide_type="table"),
        "b1": slide(b, 1, "Cloud print security", tags=["security"], slide_type="chart"),
        "b2": slide(b, 2, "Rollout", text="cloud reports", tags=["security", "generative-ai"]),
    }
    return a, b, out


def _facet(res, name):
    return {f["value"]: (f["label"], f["count"]) for f in res["facets"][name]}


def test_filters_url_and_query(corpus):
    a, b, x = corpus
    assert set(ids(S.search("cloud", project=["Contoso"]))) == {x["a1"].id, x["a2"].id}
    assert set(ids(S.search("cloud project:fab"))) == {x["b1"].id, x["b2"].id}
    assert set(ids(S.search("cloud -project:fab"))) == {x["a1"].id, x["a2"].id}
    assert set(ids(S.search("", tag=["security"]))) == {x["b1"].id, x["b2"].id}
    assert set(ids(S.search("tag:genai"))) == {x["a1"].id, x["b2"].id}      # alias
    assert set(ids(S.search('tag:"Generative AI"'))) == {x["a1"].id, x["b2"].id}  # label
    assert set(ids(S.search("type:chart"))) == {x["a1"].id, x["b1"].id}
    assert ids(S.search("is:fav")) == [x["a1"].id] == ids(S.search("", fav=True))
    assert set(ids(S.search("", deck=[b.id]))) == {x["b1"].id, x["b2"].id}
    assert set(ids(S.search("deck:print"))) == {x["b1"].id, x["b2"].id}
    assert set(ids(S.search("", origin=["converted"]))) == {x["b1"].id, x["b2"].id}
    assert ids(S.search("", entity=["contoso"])) == [x["a1"].id]
    assert set(ids(S.search("", date_from="2026-01"))) == {x["b1"].id, x["b2"].id}
    assert set(ids(S.search("", date_to="2025-12-31"))) == {x["a1"].id, x["a2"].id}
    assert S.search("", date_from="garbage")["total"] == 4
    assert set(ids(S.search("", project=["Contoso", "Fabrikam"]))) == {v.id for v in x.values()}  # OR within


def test_facets_exclude_their_own_filter(corpus):
    a, b, x = corpus
    res = S.search("cloud", project=["Contoso"])
    assert _facet(res, "project") == {"Contoso": ("Contoso", 2), "Fabrikam": ("Fabrikam", 2)}
    assert _facet(res, "tag") == {"generative-ai": ("Generative AI", 1)}
    assert _facet(res, "type") == {"chart": ("chart", 1), "table": ("table", 1)}
    assert _facet(res, "deck") == {a.id: ("AI pitch", 2)}       # other facets do honour the project filter
    assert _facet(res, "entity") == {"contoso": ("Contoso", 1)}
    assert _facet(res, "origin") == {"upload": ("upload", 2)}
    res = S.search("", tag=["security"], project=["Fabrikam"])
    assert _facet(res, "tag") == {"security": ("Security", 2), "generative-ai": ("Generative AI", 1)}


def test_sort_and_paging(corpus):
    a, b, x = corpus
    assert ids(S.search("", sort="added")) == [x["b1"].id, x["b2"].id, x["a1"].id, x["a2"].id]
    assert ids(S.search("", sort="deck_date"))[:2] == [x["b1"].id, x["b2"].id]
    assert ids(S.search("", sort="project")) == [x["a1"].id, x["a2"].id, x["b1"].id, x["b2"].id]
    full = ids(S.search("cloud"))
    assert len(full) == 4 and full[:2] != full[2:]
    assert ids(S.search("cloud", limit=2)) + ids(S.search("cloud", limit=2, offset=2)) == full
    assert S.search("cloud", limit=2, offset=2)["total"] == 4
    assert S.search("cloud", offset=99)["items"] == []


def test_project_sort_and_groups(corpus):
    a, b, x = corpus
    c = deck("contoso", "Newer pitch", 5)   # same project but for its case, added later: sorts before `a`
    c1 = slide(c, 1, "Cloud roadmap")
    assert ids(S.search("", sort="project")) == [c1.id, x["a1"].id, x["a2"].id, x["b1"].id, x["b2"].id]
    res = S.search("", sort="project", groups=True, limit=0)
    assert res["items"] == [] and res["total"] == 5
    assert res["groups"] == [{"project": "contoso", "deck": c.id, "count": 1},
                             {"project": "Contoso", "deck": a.id, "count": 2},
                             {"project": "Fabrikam", "deck": b.id, "count": 2}]
    # The outline is of the result: filters apply, and a deck with no matching slide is not in it.
    assert S.search("", tag=["security"], groups=True)["groups"] == [{"project": "Fabrikam", "deck": b.id, "count": 2}]
    assert "groups" not in S.search("")


# ------------------------------------------------------------------ superseded, duplicates

def test_superseded_hidden_by_default(lib):
    old = deck("P", "v1", 1)
    new = deck("P", "v2", 2, supersedes_id=old.id)
    o = slide(old, 1, "Pricing")
    n = slide(new, 1, "Pricing update")
    db.update(LibDeck, old.id, superseded_by=new.id)
    S.reindex_deck(old.id)
    assert ids(S.search("pricing")) == [n.id]
    assert set(ids(S.search("pricing", superseded=True))) == {o.id, n.id}
    assert ids(S.search("", deck=[old.id])) == [o.id]   # picking the old deck shows it
    item = S.search("pricing", superseded=True, sort="added")["items"][1]
    assert item["superseded"] is True


def test_duplicates_collapse_to_newest(lib):
    d1, d2, d3 = deck("A", "a", 1), deck("B", "b", 2), deck("C", "c", 3)
    s1 = slide(d1, 1, "Company overview", phash="ab" * 8)
    s2 = slide(d2, 4, "Company overview", phash="ab" * 8)
    s3 = slide(d3, 2, "Company overview", phash="ab" * 8)
    other = slide(d1, 2, "Company overview v2", phash="cd" * 8)
    res = S.search("company overview")
    assert set(ids(res)) == {s3.id, other.id} and res["total"] == 2
    item = next(i for i in res["items"] if i["id"] == s3.id)
    assert item["also_in"] == 2
    assert _facet(res, "project")["A"][1] == 2 and _facet(res, "project")["B"][1] == 1
    assert set(ids(S.search("company overview", dupes=True))) == {s1.id, s2.id, s3.id, other.id}
    assert ids(S.search("overview", project=["B"])) == [s2.id]  # the filtered set keeps its own copy
    # no render: identical words collapse instead (text_sha), but two empty slides never do
    e1 = slide(d1, 3, "", text_sha="")
    e2 = slide(d2, 5, "", text_sha="")
    assert {e1.id, e2.id} <= set(ids(S.search("")))


# ------------------------------------------------------------------ reindex / drop

def test_reindex_after_edits_and_drop(lib):
    d = deck("Old name", "Deck")
    x = slide(d, 1, "Roadmap")
    assert ids(S.search("roadmap")) == [x.id]
    db.update(LibSlide, x.id, summary="Quarterly milestones for Contoso", tags=["milestones"])
    assert S.search("quarterly")["total"] == 0         # not yet reindexed
    S.reindex([x.id])
    assert ids(S.search("quarterly")) == [x.id] and ids(S.search("milestones")) == [x.id]
    db.update(LibDeck, d.id, project="Fabrikam")
    S.reindex_deck(d.id)
    assert ids(S.search("fabrikam")) == [x.id] and S.search('"old name"')["total"] == 0
    S.reindex([x.id])
    S.reindex([x.id, x.id])                            # idempotent
    with S._conn() as c:
        assert c.execute("SELECT count(*) FROM lib_fts").fetchone()[0] == 1
        assert c.execute("SELECT count(*) FROM lib_tri").fetchone()[0] == 1
    S.drop([x.id])
    S.drop([x.id, "nope"])
    assert S.search("roadmap")["total"] == 0
    with S._conn() as c:
        assert c.execute("SELECT count(*) FROM lib_fts").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM lib_search_rid").fetchone()[0] == 0


def test_reindex_of_deleted_row_drops_it_and_ensure_heals(lib):
    d = deck()
    x = slide(d, 1, "Ghost")
    with db.session() as s:
        s.delete(s.get(LibSlide, x.id))
        s.commit()
    S.reindex([x.id])
    assert S.search("ghost")["total"] == 0
    # rows written without a reindex are picked up the first time a fresh process searches
    y = LibSlide(deck_id=d.id, index=2, title="Unindexed orphan")
    with db.session() as s:
        s.add(y)
        s.commit()
    S._ensured.clear()
    assert ids(S.search("orphan")) == [y.id]


# ------------------------------------------------------------------ speed

WORDS = ("cloud gpu spend security print firmware deployment plan pilot customer revenue margin roadmap "
         "workstation network memory storage latency throughput agenda pricing forecast quarter growth risk "
         "compliance identity endpoint fleet rollout partner channel retail europe americas asia").split()


def test_10k_slides_typical_queries_fast(lib):
    rnd = random.Random(1)
    with db.session() as s:
        s.add(LibTag(slug="generative-ai", label="Generative AI"))
        decks = [LibDeck(project=f"Project {i % 40}", title=f"Deck {i}", filename=f"deck_{i}.pptx",
                         created_at=_t0 + timedelta(hours=i), origin="upload") for i in range(400)]
        s.add_all(decks)
        s.commit()
        slides = []
        for i in range(10_000):
            d = decks[i % 400]
            title = " ".join(rnd.choice(WORDS) for _ in range(4)).capitalize()
            text = " ".join(rnd.choice(WORDS) for _ in range(60)) + f" ${rnd.randint(1, 99)}.{rnd.randint(0, 9)}M " \
                f"SKU-{rnd.randint(1000, 9999)}"
            slides.append(LibSlide(deck_id=d.id, index=i // 400 + 1, title=title, text=text,
                                   notes=" ".join(rnd.choice(WORDS) for _ in range(20)),
                                   tags=["generative-ai"] if i % 7 == 0 else [], slide_type=rnd.choice(["chart", "table", "bullets"]),
                                   favourite=i % 13 == 0, phash=f"{rnd.randint(0, 3000):016x}",
                                   created_at=d.created_at))
        s.add_all(slides)
        s.commit()
    t = time.perf_counter()
    S._ensure()                                   # indexes all 10k
    build = time.perf_counter() - t
    queries = [dict(q="cloud gpu"), dict(q="security"), dict(q="deployment plan pilot"), dict(q="SKU-12"),
               dict(q="4.5M"), dict(q="orkstat"), dict(q="cloud", project=["Project 3"]), dict(q="", sort="added"),
               dict(q="tag:generative-ai roadmap"), dict(q='"cloud gpu" -security'), dict(q="", fav=True),
               dict(q="nothingmatches zzz")]
    S.search("warm up")
    times = {}
    for kw in queries:
        best = min(_timed(kw) for _ in range(3))
        times[kw["q"] or f"<browse {kw}>"] = round(best * 1000, 1)
    print(f"\n10k index build {build:.1f}s; query ms: {times}")
    # Target is <100 ms typical (measured ~35-90 ms on a laptop for this corpus, where every common word is on most
    # slides — a worst case); the bounds here leave room for a slow CI machine.
    typical = sorted(times.values())[len(times) // 2]
    assert typical < 250, times
    assert max(times.values()) < 500, times


def _timed(kw) -> float:
    t = time.perf_counter()
    S.search(**kw)
    return time.perf_counter() - t


# ------------------------------------------------------------------ by meaning (library/semantic.py)

@pytest.fixture()
def meaning(monkeypatch):
    """An embedding model that knows two subjects: money saved by owning hardware, and everything else."""
    from array import array

    from app.library import semantic
    from app.llm import embed

    calls = {"docs": 0, "queries": 0}

    def fake(texts, *, query=False, timeout=None):
        calls["queries" if query else "docs"] += len(texts)
        return [array("f", [1.0, 0.0, 0.0, 0.0]) if any(w in t.lower() for w in ("tco", "cost savings", "lifetime expenditure"))
                else array("f", [0.0, 1.0, 0.0, 0.0]) for t in texts]

    monkeypatch.setattr(embed, "model", lambda: "fake-embed")
    monkeypatch.setattr(embed, "embed", fake)
    monkeypatch.setattr(semantic, "kick", lambda: None)   # tests index on purpose, not in a background thread
    monkeypatch.setattr(semantic, "_index", None)
    semantic._query.cache_clear()
    yield calls
    semantic._query.cache_clear()


def test_meaning_finds_a_slide_the_words_miss(corpus, meaning):
    from app.library import semantic
    a, b, x = corpus
    before = ids(S.search("cloud"))
    tco = slide(a, 3, "TCO reduction", text="Owning the fleet lowers lifetime expenditure")
    assert tco.id not in ids(S.search("cost savings")), "not indexed yet: words only, and it shares none"
    assert semantic.sync() == 5 and semantic.sync() == 0, "every slide once"
    res = S.search("cost savings")
    assert ids(res)[0] == tco.id and res["items"][0]["by_meaning"] is True
    assert x["a2"].id in ids(res) and "by_meaning" not in res["items"][ids(res).index(x["a2"].id)], \
        "a slide that merely shares a word comes after one that means it"
    # Slides that contain the words keep their order; meaning only adds to the end.
    assert ids(S.search("cloud"))[:4] == before
    assert tco.id not in ids(S.search("cost savings -lifetime")), "a negated word still excludes"
    assert ids(S.search("")) and meaning["queries"] <= 3, "browsing asks the model nothing, and a query is asked once"


def test_the_meaning_index_follows_the_slides(corpus, meaning):
    from app.library import semantic
    a, b, x = corpus
    tco = slide(a, 3, "TCO reduction", text="Owning the fleet lowers lifetime expenditure")
    semantic.sync()
    assert [sid for sid, _ in semantic.pending()] == []
    with db.session() as s:
        row = s.get(LibSlide, tco.id)
        row.summary = "Now about something else entirely"
        s.add(row)
        s.commit()
    assert [sid for sid, _ in semantic.pending()] == [tco.id], "changed words are embedded again"
    S.drop([tco.id])
    with S._conn() as c:
        assert c.execute("SELECT COUNT(*) FROM lib_vec WHERE slide_id = ?", (tco.id,)).fetchone()[0] == 0
    assert S.search("cost savings")["items"] == [] or tco.id not in ids(S.search("cost savings"))


def test_the_bit_filter_agrees_with_the_exact_ranking(lib, monkeypatch):
    import math
    import random
    from array import array

    from app.library import semantic
    from app.llm import embed

    rnd = random.Random(7)

    def unit(v):
        n = math.sqrt(sum(x * x for x in v))
        return array("f", (x / n for x in v))

    dim = 256
    topic = [rnd.gauss(0, 1) for _ in range(dim)]
    vecs = {f"s{i}": unit([rnd.gauss(0, 1) for _ in range(dim)]) for i in range(600)}
    # Five slides on the query's subject, each a little further from it than the last; 600 about other things.
    near = {f"n{k}": unit([x + rnd.gauss(0, 0.25 * (k + 1)) for x in topic]) for k in range(5)}
    vecs.update(near)
    S._ensure()
    with S._conn() as c:
        for sid, v in vecs.items():
            c.execute("INSERT INTO lib_vec VALUES (?, 'fake-embed', 'x', ?, ?, ?)",
                      (sid, dim, semantic._bits(v).to_bytes(dim // 8, "big"), v.tobytes()))
    monkeypatch.setattr(embed, "model", lambda: "fake-embed")
    monkeypatch.setattr(semantic, "_index", None)
    monkeypatch.setattr(semantic, "CANDIDATES", 30)   # 5% of the library goes on to the exact comparison
    q = unit(topic)
    exact = sorted(vecs, key=lambda sid: -embed.cosine(q, vecs[sid]))[:5]
    got = [sid for sid, _ in semantic.nearest(q, k=5, floor=-1.0)]
    assert exact == ["n0", "n1", "n2", "n3", "n4"]
    assert got == exact, "the cheap comparison lost none of the best five, and the exact one put them in order"
    assert [sid for sid, _ in semantic.nearest(q)] == exact, "the floor keeps out the 600 that are about other things"


def test_without_an_embedding_model_search_asks_for_nothing(corpus, monkeypatch):
    from app.llm import embed
    monkeypatch.setattr(embed, "embed", lambda *a, **k: pytest.fail("meaning is off"))
    assert len(ids(S.search("cloud"))) == 4
