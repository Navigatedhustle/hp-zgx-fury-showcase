"""Reference documents: parsing, search, the digest job, and the gate a document figure passes to reach a slide."""
import asyncio
import io

import pytest
from fastapi.testclient import TestClient

from app import compose, docs, facts, main
from app.pipeline import prompts, reference, runner
from app.store import db
from app.store.db import Project, ProjectDoc, Slide


def pdf_bytes(pages: list[str]) -> bytes:
    """A minimal valid PDF with one line of Helvetica text per page — enough for pypdf to extract."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream.decode()}\nendstream")
        content_no = len(objs)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_no} 0 R "
                    f"/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(len(objs))
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n{body}\nendobj\n".encode())
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def docx_bytes() -> bytes:
    import docx
    d = docx.Document()
    d.add_paragraph("Proposal for Contoso Engineering")
    d.add_paragraph("The pilot saved $4.2M in the first year across 12 sites.")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Metric", "Value"
    t.cell(1, 0).text, t.cell(1, 1).text = "Uptime", "99.95%"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- parsing
def test_a_pdf_is_read_page_by_page(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(pdf_bytes(["GPU queues delay experiments by 3.4 days", "Egress fees add 12% to every run"]))
    d = docs.extract(f)
    assert len(d.pages) == 2 and "3.4 days" in d.pages[0] and "12%" in d.pages[1]
    assert docs.page_of(d, "Egress fees add 12%") == 2


def test_a_word_file_keeps_paragraphs_and_tables(tmp_path):
    f = tmp_path / "a.docx"
    f.write_bytes(docx_bytes())
    text = docs.extract(f).text
    assert "$4.2M" in text and "Uptime | 99.95%" in text


@pytest.mark.parametrize("name,blob,why", [
    ("a.doc", b"x", "PDF, Word"),
    ("a.pdf", b"not a pdf", "couldn't be read"),
    ("a.docx", b"not a zip", "couldn't be read"),
    ("a.txt", b"   \n  ", "No text"),
])
def test_unusable_files_are_refused_with_a_reason(tmp_path, name, blob, why):
    f = tmp_path / name
    f.write_bytes(blob)
    with pytest.raises(docs.DocRefused, match=why):
        docs.extract(f)


def test_a_huge_document_is_cut_and_says_so(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("word " * (docs.MAX_CHARS // 4))
    d = docs.extract(f)
    assert d.truncated and len(d.text) <= docs.MAX_CHARS


def test_search_finds_the_passage_about_the_slide():
    d = docs.DocText(pages=["Cloud egress fees are rising.\n\nThe Z8 Fury G5 carries 2TB of memory for large models.",
                            "Our office furniture policy is unrelated to anything."])
    pool = [("a.pdf", c) for c in docs.chunks(d)]
    hits = docs.relevant(pool, "Z8 Fury memory for models")
    assert hits and "Z8 Fury" in hits[0][1].text


def test_a_quote_counts_only_if_it_is_really_in_the_document():
    text = "The pilot saved $4.2M in the first   year."
    assert docs.contains(text, "saved $4.2M in the first year")
    assert not docs.contains(text, "saved $5.1M")


# ---------------------------------------------------------------- the HTTP surface and the digest
@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


def _deck() -> Project:
    p = db.save(Project(name="docs", filename="d.pptx", status="ready"))
    c = compose.blank(1, title="Savings", lines=["The pilot cut costs"])
    db.save(Slide(project_id=p.id, index=1, position=1, content=c.model_dump(), facts=[],
                  plan={"pattern": "cards", "headline": "Savings", runner.PART_KEY: [0, 1]}))
    return p


def _wait_ready(client, pid):
    for _ in range(100):
        got = client.get(f"/api/projects/{pid}/docs").json()
        if got and all(d["status"] != "digesting" for d in got):
            return got
        asyncio.run(asyncio.sleep(0.02))
    raise AssertionError("digest never finished")


def test_upload_then_digest_then_delete(client):
    p = _deck()
    r = client.post(f"/api/projects/{p.id}/docs", files={"file": ("proposal.docx", docx_bytes())})
    assert r.status_code == 200, r.text
    got = _wait_ready(client, p.id)
    assert got[0]["status"] == "ready" and got[0]["digest"]
    assert "proposal.docx" in reference.planner_reference(p.id)
    assert client.delete(f"/api/docs/{got[0]['id']}").status_code == 200
    assert client.get(f"/api/projects/{p.id}/docs").json() == []


def test_upload_refusal_is_readable(client):
    p = _deck()
    r = client.post(f"/api/projects/{p.id}/docs", files={"file": ("scan.pdf", b"%PDF-1.4 junk")})
    assert r.status_code == 400 and "couldn't be read" in r.json()["detail"]


# ---------------------------------------------------------------- into the pipeline
def _with_doc(p) -> ProjectDoc:
    d = db.save(ProjectDoc(project_id=p.id, name="proposal.pdf", status="ready", digest="PURPOSE: savings"))
    docs.save_text(db.project_dir(p.id), d.id,
                   docs.DocText(pages=["intro", "The pilot saved $4.2M in the first year across 12 sites."]))
    return d


def test_a_doc_figure_joins_the_ledger_only_when_it_is_verbatim(client):
    p = _deck()
    _with_doc(p)
    got, cites = reference.doc_facts(p.id, ["$4.2M", "$9.9M", "saved $4.2M in the first year"], "s1d0_")
    raws = {f.raw for f in got}
    assert "$4.2M" in raws and "$9.9M" not in raws, "a figure no document contains never reaches a slide"
    assert all(f.origin == "doc" and f.tier == "key" for f in got)
    assert cites == ["proposal.pdf, p. 2"]


def test_the_planner_sees_digests_in_the_user_message_and_the_prefix_is_unchanged():
    base = prompts.plan_messages([{"index": 1, "content": {"title": "x"}}])
    withref = prompts.plan_messages([{"index": 1, "content": {"title": "x"}}], reference="### proposal.pdf\nPURPOSE: savings")
    assert base[0] == withref[0], "the system prefix must stay byte-stable"
    assert "PURPOSE: savings" in withref[1]["content"] and "PURPOSE: savings" not in base[1]["content"]


def test_a_replan_brings_doc_facts_in_and_cites_them(monkeypatch, client):
    from app.config import settings
    p = _deck()
    _with_doc(p)

    async def fake_call(batch, **kw):
        assert "PURPOSE: savings" in kw.get("reference", "")
        return {"deck_title": "D", "audience": "a", "tone": "t", "narrative": "n",
                "slides": [{"index": b["index"], "role": "evidence", "pattern": "cards", "eyebrow": "e", "headline": "h",
                            "key_message": "m", "idea_a": "a", "idea_b": "b", "theme": "light", "include": True,
                            "key_facts": [], "doc_facts": ["$4.2M", "$7M"]} for b in batch]}

    monkeypatch.setattr(runner, "_plan_call", fake_call)
    monkeypatch.setattr(runner.llm, "vision_enabled", lambda: asyncio.sleep(0, result=False))
    monkeypatch.setenv("LLM_MOCK", "false")
    settings.cache_clear()
    try:
        asyncio.run(runner.plan(p.id))
        asyncio.run(runner.plan(p.id))  # twice: doc facts are re-derived, never piled up
    finally:
        monkeypatch.setenv("LLM_MOCK", "true")
        settings.cache_clear()
    s = db.slides_of(p.id)[0]
    doc = [f for f in runner.slide_facts(s) if f.origin == "doc"]
    assert [f.raw for f in doc] == ["$4.2M"]
    assert s.plan[runner.DOC_SOURCES_KEY] == ["proposal.pdf, p. 2"]
    ctx = runner.Ctx(s)
    msgs = prompts.generate_messages(variant="A", position=1, total=1, brief=ctx.brief, plan=ctx.plan, content=ctx.content,
                                     prev_plan=None, next_plan=None, source_png=None, vision=False, ledger=ctx.facts,
                                     reference=ctx.reference, doc_sources=ctx.plan.get(runner.DOC_SOURCES_KEY))
    assert "proposal.pdf, p. 2" in msgs[1]["content"]


def test_documents_added_with_the_upload_are_read_before_the_first_plan(client, monkeypatch):
    from conftest import DECKS
    seen = {}
    real_plan = runner.plan

    async def spy(pid):
        seen["reference"] = reference.planner_reference(pid)  # what the first plan will be shown
        await real_plan(pid)

    monkeypatch.setattr(runner, "plan", spy)
    deck = DECKS / "hp_wolf_print_security.pptx"
    r = client.post("/api/projects", files=[("file", (deck.name, deck.read_bytes())),
                                            ("context", ("brief.docx", docx_bytes())),
                                            ("context", ("junk.pdf", b"not a pdf"))])
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    for _ in range(300):
        if client.get(f"/api/projects/{pid}").json()["status"] == "ready":
            break
        asyncio.run(asyncio.sleep(0.05))
    assert "brief.docx" in seen["reference"], "the first plan already has the document"
    docs_now = client.get(f"/api/projects/{pid}/docs").json()
    assert [d["name"] for d in docs_now] == ["brief.docx"]
    assert any("junk.pdf" in w for w in client.get(f"/api/projects/{pid}").json()["warnings"]), \
        "an unreadable document is reported, and does not stop the deck"


def test_a_composed_deck_drafts_from_its_documents(client, monkeypatch):
    p = client.post("/api/projects/blank", json={"name": "From a doc", "slides": 1}).json()
    client.post(f"/api/projects/{p['id']}/docs", files={"file": ("brief.docx", docx_bytes())})
    seen = {}

    async def fake(pid, count, about, source):
        seen["source"] = source

    monkeypatch.setattr(runner, "draft_outline", fake)
    client.post(f"/api/projects/{p['id']}/outline", json={"about": "", "slides": 5})
    for _ in range(50):
        if seen:
            break
        asyncio.run(asyncio.sleep(0.02))
    assert "$4.2M" in seen["source"]


# ---------------------------------------------------------------- structure: sections, chunks, the tolerant gate
def test_a_word_table_stays_under_the_paragraph_that_introduces_it(tmp_path):
    import docx
    d = docx.Document()
    d.add_heading("Results", level=1)
    d.add_paragraph("The table below shows uptime by site.")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Site", "Uptime"
    t.cell(1, 0).text, t.cell(1, 1).text = "Austin", "99.95%"
    d.add_paragraph("Everything after the table.")
    f = tmp_path / "t.docx"
    d.save(str(f))
    text = docs.extract(f).text
    assert text.index("uptime by site") < text.index("| Austin | 99.95% |") < text.index("Everything after")
    assert "# Results" in text
    c = docs.chunks(docs.extract(f))[0]
    assert c.heading == "Results" and "| Site | Uptime |\n| Austin | 99.95% |" in c.text, "a table is never split from its header"


def _long_doc() -> docs.DocText:
    """Three pages, each a headed part bigger than half a section, with one figure only on the last page."""
    filler = "The programme continued as planned across every region without incident. "
    pages = [f"Executive Summary\n\n{filler * 150}", f"Market Analysis\n\n{filler * 150}",
             f"Financial Appendix\n\n{filler * 150}\n\nThe retrofit paid back in 14 months at the Leipzig plant."]
    return docs.DocText(pages=pages)


def test_sections_cover_the_whole_document_and_break_at_headings():
    d = _long_doc()
    secs = docs.sections(d)
    assert [s.title for s in secs] == ["Executive Summary", "Market Analysis", "Financial Appendix"]
    assert [s.where for s in secs] == ["p. 1", "p. 2", "p. 3"]
    assert all(len(s.text) <= docs.SECTION_CHARS for s in secs)
    assert "14 months" in secs[-1].text, "the end of the document is in a section like the start"
    assert docs.sections(d)[1].text == secs[1].text, "deterministic: a stored digest still matches its section"


def test_chunks_know_their_section_and_heading_and_overlap():
    d = docs.DocText(pages=["Cooling Options\n\n" + "Liquid cooling removes heat at the rack. " * 30
                            + "\n\nThis cut energy use by 12%.\n\n" + "Air handling was kept as a fallback. " * 40])
    cs = docs.chunks(d)
    assert len(cs) >= 2 and all(c.section == 1 and c.heading == "Cooling Options" for c in cs)
    assert all(len(c.text) <= docs.CHUNK_CHARS * 2 for c in cs)
    assert sum("This cut energy use by 12%." in c.text for c in cs) == 2, "a short paragraph opens the next chunk too"


def test_an_oversized_table_is_cut_by_rows_with_its_header_repeated():
    table = "| Site | Uptime |\n" + "\n".join(f"| Site number {i} | 99.{i:02d}% |" for i in range(200))
    cs = docs.chunks(docs.DocText(pages=[table]))
    assert len(cs) > 1 and all(c.text.startswith("| Site | Uptime |") for c in cs)


def test_a_line_break_in_the_pdf_does_not_cost_a_real_figure():
    text = "The pilot saved $4.2\nM in its first year and improved infor-\nmation flow — a “step change”."
    assert docs.contains(text, "$4.2M") and docs.contains(text, "information flow")
    assert docs.contains(text, 'a "step change"'), "typographic quotes and dashes are the same characters"
    assert not docs.contains(text, "$4.3M") and not docs.contains("saved 12 sites", "212")


# ---------------------------------------------------------------- a long document is read to the end
class _Reply:
    def __init__(self, text):
        self.text = text


def _real_llm(monkeypatch):
    from app.config import settings
    monkeypatch.setenv("LLM_MOCK", "false")
    settings.cache_clear()
    return settings


def test_a_long_document_is_digested_section_by_section(monkeypatch, client):
    p = _deck()
    d = db.save(ProjectDoc(project_id=p.id, name="report.pdf", pages=3))
    docs.save_text(db.project_dir(p.id), d.id, _long_doc())
    assert len(_long_doc().text) < reference.DIGEST_INPUT_CHARS
    monkeypatch.setattr(reference, "DIGEST_INPUT_CHARS", 20_000)  # so this document counts as too long for one call
    calls = []

    async def fake_chat(msgs, **kw):
        body = msgs[1]["content"]
        calls.append(body)
        if "take notes on one section" in body:
            return _Reply("SUMMARY: payback.\nFIGURES:\n- 14 months — payback, Leipzig" if "14 months" in body
                          else "SUMMARY: steady progress.\nFIGURES: none")
        assert "notes on each of its sections" in body and "14 months — payback" in body, \
            "the document digest is written from every section, the last included"
        return _Reply("PURPOSE: report\nFIGURES:\n- 14 months — payback")

    monkeypatch.setattr(reference.llm, "chat", fake_chat)
    settings = _real_llm(monkeypatch)
    try:
        asyncio.run(reference.digest_doc(d.id))
    finally:
        monkeypatch.setenv("LLM_MOCK", "true")
        settings.cache_clear()
    assert len(calls) == 4, "three sections, then the merge"
    assert "section 3 of 3, p. 3" in calls[2]
    got = db.get(ProjectDoc, d.id)
    assert got.status == "ready" and "14 months" in got.digest
    assert len(docs.load_section_digests(db.project_dir(p.id), d.id)) == 3
    ref = reference.planner_reference(p.id)
    assert "### D1 — report.pdf" in ref and "D1.S3 (p. 3) “Financial Appendix”" in ref and "14 months — payback, Leipzig" in ref
    assert client.get(f"/api/projects/{p.id}/docs").json()[0]["sections"] == 3


def test_the_planner_reference_shrinks_before_it_is_cut(monkeypatch):
    p = _deck()
    d = db.save(ProjectDoc(project_id=p.id, name="report.pdf", status="ready", digest="PURPOSE: report"))
    docs.save_text(db.project_dir(p.id), d.id, _long_doc())
    docs.save_section_digests(db.project_dir(p.id), d.id, ["SUMMARY: about cooling.\nFIGURES:\n" + "- 1 — x\n" * 200] * 3)
    monkeypatch.setattr(reference, "PLANNER_CHARS", 1500)
    ref = reference.planner_reference(p.id)
    assert len(ref) <= 1600 and ref.count("about cooling.") == 3 and "- 1 — x" not in ref


# ---------------------------------------------------------------- retrieval: named sections, words, meaning
def _two_part_doc(p) -> ProjectDoc:
    d = db.save(ProjectDoc(project_id=p.id, name="report.pdf", status="ready", digest="PURPOSE: report"))
    filler = "Nothing in this paragraph concerns the matter at hand. "
    docs.save_text(db.project_dir(p.id), d.id, docs.DocText(pages=[
        f"Cost Savings\n\nThe pilot cut costs sharply across sites.\n\n{filler * 200}",
        f"Total Cost of Ownership\n\nOwning the fleet outright lowers lifetime expenditure versus leasing.\n\n{filler * 200}"]))
    return d


def test_the_planner_can_point_a_slide_at_a_section():
    p = _deck()
    d = _two_part_doc(p)
    s = db.slides_of(p.id)[0]
    content = runner._content(s)
    assert "pilot cut costs" in reference.slide_reference(p.id, s.plan, content)
    assert "lifetime expenditure" not in reference.slide_reference(p.id, s.plan, content), "no shared words, so not found"
    assert reference.resolve_refs(p.id, ["D1.S2", "d1.s2", "D9.S1", "D1.S7", "nonsense"]) == [f"{d.id}:2"]
    named = reference.slide_reference(p.id, {**s.plan, "doc_refs": [f"{d.id}:2"]}, content)
    assert named.startswith("[report.pdf, p. 2 — Total Cost of Ownership]") and "lifetime expenditure" in named
    assert "pilot cut costs" in named, "a named section leads; it does not replace what the words find"


def test_meaning_finds_a_passage_that_shares_no_words(monkeypatch):
    p = _deck()
    d = _two_part_doc(p)
    s = db.slides_of(p.id)[0]
    asked = []

    def fake_embed(texts, *, query=False):
        asked.append((len(texts), query))
        # Two directions: "ownership / expenditure" passages and the slide's query point one way, the rest the other.
        return [[1.0, 0.0] if query or "lifetime expenditure" in t else [0.0, 1.0] for t in texts]

    monkeypatch.setattr(reference.embed, "model", lambda: "fake-embed")
    monkeypatch.setattr(reference.embed, "embed", fake_embed)
    got = reference.slide_reference(p.id, s.plan, runner._content(s))
    assert "lifetime expenditure" in got and "pilot cut costs" in got, "meaning and words are fused, not swapped"
    pdir = db.project_dir(p.id)
    n = len(docs.chunks(docs.load_text(pdir, d.id)))
    assert asked[0] == (n, False) and asked[1] == (1, True), "the document is indexed once, on first use"
    reference.slide_reference(p.id, s.plan, runner._content(s))
    assert [a for a in asked if not a[1]] == [(n, False)], "and its vectors are reused"
    assert docs.load_vectors(pdir, d.id, "another-model", n) is None, "vectors from another model are stale, not wrong"
    docs.remove(pdir, d.id)
    assert not docs.vectors_path(pdir, d.id).exists() and not docs.text_path(pdir, d.id).exists()


def test_without_an_embedding_model_nothing_is_called(monkeypatch):
    p = _deck()
    _two_part_doc(p)
    monkeypatch.setattr(reference.embed, "embed", lambda *a, **k: pytest.fail("embeddings are off"))
    s = db.slides_of(p.id)[0]
    assert "pilot cut costs" in reference.slide_reference(p.id, s.plan, runner._content(s))


def test_embeddings_are_unit_length_and_failures_degrade(monkeypatch):
    from app.llm import embed

    class Data:
        def __init__(self, i, v):
            self.index, self.embedding = i, v

    class Fake:
        class embeddings:  # noqa: N801
            @staticmethod
            def create(model, input):  # noqa: A002
                assert input[0].startswith("Q: ")
                return type("R", (), {"data": [Data(1, [0.0, 2.0, 9.0]), Data(0, [3.0, 4.0, 9.0])][: len(input)]})

    settings = _real_llm(monkeypatch)
    monkeypatch.setenv("EMBED_MODEL", "model4")
    monkeypatch.setenv("EMBED_DIM", "2")
    monkeypatch.setenv("EMBED_QUERY_PREFIX", "Q: ")
    settings.cache_clear()
    monkeypatch.setattr(embed, "RETRIES", ())
    monkeypatch.setattr(embed, "_down_until", 0.0)
    try:
        monkeypatch.setattr(embed, "_client", lambda: Fake)
        a, b = embed.embed(["x", "y"], query=True)
        assert [round(v, 2) for v in a] == [0.6, 0.8] and list(b) == [0.0, 1.0], "cut to EMBED_DIM, scaled, in input order"
        assert round(embed.cosine(a, b), 2) == 0.8 and embed.cosine(a, [1.0]) == 0.0
        monkeypatch.setattr(embed, "_client", lambda: (_ for _ in ()).throw(RuntimeError("down")))
        assert embed.embed(["x"]) is None, "a dead embedding server is a missing signal, never an error"
    finally:
        monkeypatch.setenv("LLM_MOCK", "true")
        monkeypatch.delenv("EMBED_MODEL")
        settings.cache_clear()
    assert embed.embed(["x"]) is None and not embed.enabled()


# ---------------------------------------------------------------- revise, outline, and telling the user
def test_a_revision_gets_passages_chosen_with_the_comment():
    from app.spec import SlideSpec
    p = _deck()
    _two_part_doc(p)
    s = db.slides_of(p.id)[0]
    content = runner._content(s)
    passages = reference.slide_reference(p.id, s.plan, content, "add the ownership versus leasing expenditure point")
    assert "lifetime expenditure" in passages
    spec = SlideSpec(html="<section></section>", steps=1)
    kw = dict(variant="A", position=1, plan=s.plan, content=content, spec=spec, slide_id=s.id, comment="c",
              other=None, other_id=None, shot=None, vision=False)
    plain, withref = prompts.revise_messages(**kw), prompts.revise_messages(**kw, reference=passages)
    assert plain[0] == withref[0], "the system prefix must stay byte-stable"
    assert "lifetime expenditure" in withref[1]["content"] and "presenter's comment already gives it" in withref[1]["content"]
    assert "{{REFERENCE}}" not in plain[1]["content"] and "reference documents" not in plain[1]["content"]


def test_an_outline_draws_on_the_whole_of_a_long_document():
    p = _deck()
    long = db.save(ProjectDoc(project_id=p.id, name="long.pdf", status="ready", digest="PURPOSE: the long one"))
    docs.save_text(db.project_dir(p.id), long.id, _long_doc())
    docs.save_section_digests(db.project_dir(p.id), long.id, ["SUMMARY: a", "SUMMARY: b", "SUMMARY: payback\nFIGURES:\n- 14 months"])
    short = db.save(ProjectDoc(project_id=p.id, name="memo.txt", status="ready", digest="PURPOSE: memo"))
    docs.save_text(db.project_dir(p.id), short.id, docs.DocText(pages=["The board approved $2M for phase two."]))
    src = reference.compose_source(p.id, 6000)
    assert len(src) <= 6100
    assert "The board approved $2M for phase two." in src, "a document that fits goes in whole"
    assert "PURPOSE: the long one" in src and "14 months" in src and "Section 3 (p. 3): Financial Appendix" in src
    assert src.index("# long.pdf") < src.index("# memo.txt"), "in the order the user added them"
    whole = reference.compose_source(p.id, 200_000)
    assert "paid back in 14 months at the Leipzig plant" in whole and "summarised" not in whole


def test_a_replan_keeps_section_references_and_reports_rejected_figures(monkeypatch, client):
    p = _deck()
    d = _with_doc(p)

    async def fake_call(batch, **kw):
        return {"deck_title": "D", "audience": "a", "tone": "t", "narrative": "n",
                "slides": [{"index": b["index"], "role": "evidence", "pattern": "cards", "eyebrow": "e", "headline": "h",
                            "key_message": "m", "idea_a": "a", "idea_b": "b", "theme": "light", "include": True,
                            "key_facts": [], "doc_facts": ["$4.2M", "$7M"], "doc_refs": ["D1", "D4.S2"]} for b in batch]}

    monkeypatch.setattr(runner, "_plan_call", fake_call)
    monkeypatch.setattr(runner.llm, "vision_enabled", lambda: asyncio.sleep(0, result=False))
    settings = _real_llm(monkeypatch)
    try:
        asyncio.run(runner.plan(p.id))
        asyncio.run(runner.plan(p.id))
    finally:
        monkeypatch.setenv("LLM_MOCK", "true")
        settings.cache_clear()
    s = db.slides_of(p.id)[0]
    assert s.plan[runner.DOC_REFS_KEY] == [f"{d.id}:0"]
    notes = [w for w in db.get(Project, p.id).warnings if "word for word" in w]
    assert len(notes) == 1 and "“$7M”" in notes[0] and "$4.2M" not in notes[0], "said once, however often the deck is re-planned"


# ---------------------------------------------------------------- what a document may put on a slide
def test_a_statement_with_no_figure_joins_the_ledger_as_a_claim():
    p = _deck()
    d = db.save(ProjectDoc(project_id=p.id, name="spec.pdf", status="ready", digest="x"))
    docs.save_text(db.project_dir(p.id), d.id, docs.DocText(pages=[
        "intro", "The platform offers full backward compatibility with legacy firmware across every region."]))
    quote = "full backward compatibility with legacy firmware"
    rejected: list[str] = []
    got, cites = reference.doc_facts(p.id, [quote, "it works well everywhere today", "ok"], "s1d0_", rejected=rejected)
    assert [(f.kind, f.raw, f.tier, f.doc, f.cite) for f in got] == [("claim", quote, "key", d.id, "spec.pdf, p. 2")]
    assert cites == ["spec.pdf, p. 2"] and rejected == ["it works well everywhere today", "ok"], "said, not dropped in silence"
    kept = facts.check(got, "Fully backward compatible: legacy firmware keeps its compatibility")
    lost = facts.check(got, "A modern platform for every region")
    assert [c.status for c in kept] == ["present"] and [c.status for c in lost] == ["missing"]
    assert [c.status for c in facts.check(got, "", "Full backward compatibility with legacy firmware.")] == ["notes"]
    assert "a statement: keep its meaning" in facts.for_prompt(got)["must_be_visible"][0]
    iso = [facts.Fact(id="c", kind="claim", raw="ISO 27001 Type II certified across all regions")]
    assert facts.check(iso, "Certified to ISO 9001 Type II in all regions")[0].status == "missing", "the term with a digit must be there"


def test_a_figure_quoted_in_other_words_is_held_to_the_documents_own(client):
    p = _deck()
    _with_doc(p)  # says "$4.2M … across 12 sites"
    rejected: list[str] = []
    adopted: list[str] = []
    got, cites = reference.doc_facts(p.id, ["saved $4.2 million", "saved $4.3 million", "12 locations"], "s1d0_",
                                     rejected=rejected, adopted=adopted)
    assert [f.raw for f in got if f.kind == "number"] == ["$4.2M"], "the ledger holds what the document wrote"
    assert cites == ["proposal.pdf, p. 2"]
    assert rejected == ["saved $4.3 million", "12 locations"], "another value, or a bare number, is still nowhere"
    assert adopted == ["“saved $4.2 million” → “saved $4.2M” (proposal.pdf)"]


def _figures_doc(p, name: str, value: str, **kw) -> ProjectDoc:
    d = db.save(ProjectDoc(project_id=p.id, name=name, status="ready",
                           digest=f"PURPOSE: terms\nFIGURES:\n- {value} — first-year savings, EMEA pilot\n- 12 — sites", **kw))
    docs.save_text(db.project_dir(p.id), d.id, docs.DocText(pages=[f"The pilot saved {value} and reached 40% of users."]))
    return d


def test_documents_that_disagree_are_named_and_the_primary_one_wins(client):
    p = _deck()
    rfp = _figures_doc(p, "rfp.pdf", "$4.2M")
    add = _figures_doc(p, "addendum.pdf", "$4.8M")
    clash = client.get(f"/api/projects/{p.id}/docs/conflicts").json()
    assert len(clash) == 1 and clash[0]["use"] == ""
    assert {v["doc"]: v["value"] for v in clash[0]["values"]} == {"rfp.pdf": "$4.2M", "addendum.pdf": "$4.8M"}
    ref = reference.planner_reference(p.id)
    assert "Where the documents disagree" in ref and "$4.2M (rfp.pdf) vs $4.8M (addendum.pdf)" in ref
    # Unmarked, the newer document is the one cited for what both state …
    assert reference.doc_facts(p.id, ["40%"], "x")[1] == ["addendum.pdf"]
    # … and the user's mark outranks recency.
    r = client.patch(f"/api/docs/{rfp.id}", json={"primary": True})
    assert r.status_code == 200 and r.json()["primary"] is True
    assert reference.doc_facts(p.id, ["40%"], "x")[1] == ["rfp.pdf"]
    ref = reference.planner_reference(p.id)
    assert ref.index("rfp.pdf — PRIMARY") < ref.index("### D2 — addendum.pdf"), "handles keep upload order; the primary reads first"
    assert "— use rfp.pdf" in ref and client.get(f"/api/projects/{p.id}/docs/conflicts").json()[0]["use"] == "rfp.pdf"
    assert add.id != rfp.id


def test_removing_a_document_takes_its_figures_back_out(client):
    from app.pipeline import deckreview
    from app.spec import SlideSpec
    from app.store.db import Version
    p = _deck()
    d = _with_doc(p)
    other = _two_part_doc(p)
    s = db.slides_of(p.id)[0]
    got, cites = reference.doc_facts(p.id, ["$4.2M"], "s1d0_")
    own = facts.Fact(id="own", kind="number", raw="12%", value=12, unit="percent")
    db.update(Slide, s.id, facts=facts.dump([own, *got]),
              plan={**s.plan, runner.DOC_SOURCES_KEY: cites, runner.DOC_REFS_KEY: [f"{d.id}:0", f"{other.id}:2"]})
    spec = SlideSpec(html="<section></section>", steps=1)
    db.save(Version(slide_id=s.id, project_id=p.id, lineage="A", number=1, status="ready", spec=spec.model_dump()))

    r = client.delete(f"/api/docs/{d.id}")
    assert r.json()["slides_affected"] == [s.id]
    s = db.slides_of(p.id)[0]
    assert [f.id for f in facts.load(s.facts)] == ["own"], "the slide's own figures are untouched"
    assert runner.DOC_SOURCES_KEY not in s.plan and s.plan[runner.DOC_REFS_KEY] == [f"{other.id}:2"]
    assert s.plan[runner.DOC_STALE_KEY]["figures"] == ["$4.2M"]
    assert any("“proposal.pdf” was removed" in w for w in db.get(Project, p.id).warnings)
    blocks = [i for i in deckreview.readiness(p.id)["items"] if i["severity"] == "block"]
    assert any("has since been" in i["message"] and "$4.2M" in i["message"] for i in blocks)
    # A design made after the removal answers it.
    db.save(Version(slide_id=s.id, project_id=p.id, lineage="A", number=2, status="ready", spec=spec.model_dump(), score=99))
    assert not [i for i in deckreview.readiness(p.id)["items"] if "has since been" in i["message"]]
    # A document nothing was taken from leaves no mark.
    assert client.delete(f"/api/docs/{other.id}").json()["slides_affected"] == []
    assert runner.DOC_REFS_KEY not in db.slides_of(p.id)[0].plan


def test_a_slide_cites_its_documents_whatever_the_model_wrote():
    from app.spec import SlideSpec
    spec = SlideSpec(html="<section></section>", steps=1)
    spec.meta.sources = "Internal analysis."
    plan = {runner.DOC_SOURCES_KEY: ["Whitepaper.pdf, p. 4", "Brief.docx"]}
    assert runner.ensure_citations(spec, plan) == ["Whitepaper.pdf, p. 4", "Brief.docx"]
    assert spec.meta.sources == "Internal analysis; Whitepaper.pdf, p. 4; Brief.docx"
    assert runner.ensure_citations(spec, plan) == [], "once"
    named = SlideSpec(html="<section></section>", steps=1)
    named.meta.sources = "Source: whitepaper.pdf"
    assert runner.ensure_citations(named, {runner.DOC_SOURCES_KEY: ["Whitepaper.pdf, p. 4"]}) == [], "named is cited"


def test_a_planning_batch_reads_in_full_only_the_sections_its_slides_bear_on():
    p = _deck()
    d = db.save(ProjectDoc(project_id=p.id, name="long.pdf", status="ready", digest="PURPOSE: long"))
    filler = "The programme continued as planned across every region without incident. "
    topics = ["cooling", "networking", "storage", "security", "licensing", "staffing", "logistics", "training",
              "warranty", "recycling", "telemetry", "firmware"]
    docs.save_text(db.project_dir(p.id), d.id, docs.DocText(pages=[f"{t.title()} Overview Chapter\n\n{filler * 150}" for t in topics]))
    docs.save_section_digests(db.project_dir(p.id), d.id,
                              [f"SUMMARY: all about {t}.\nFIGURES:\n- {i + 10}% — {t} improvement" for i, t in enumerate(topics)])
    whole = reference.planner_reference(p.id)
    assert all(f"{t} improvement" in whole for t in topics), "one batch: everything"
    scoped = reference.planner_reference(p.id, "this slide is about firmware and telemetry")
    assert "firmware improvement" in scoped and "telemetry improvement" in scoped
    assert scoped.count("improvement") == reference.FULL_SECTIONS
    assert all(f"all about {t}." in scoped for t in topics), "every section is still listed, so it can still be named"
    assert len(scoped) < len(whole)


def test_embedding_requests_are_retried_then_the_server_is_left_alone(monkeypatch):
    from app.llm import embed

    calls = {"n": 0}

    class Flaky:
        class embeddings:  # noqa: N801
            @staticmethod
            def create(model, input):  # noqa: A002
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("busy")
                return type("R", (), {"data": [type("D", (), {"index": 0, "embedding": [1.0, 0.0]})()]})

    settings = _real_llm(monkeypatch)
    monkeypatch.setenv("EMBED_MODEL", "model4")
    settings.cache_clear()
    monkeypatch.setattr(embed, "RETRIES", (0.0,))
    monkeypatch.setattr(embed, "_down_until", 0.0)
    try:
        monkeypatch.setattr(embed, "_client", lambda: Flaky)
        assert embed.embed(["x"]) is not None and calls["n"] == 2, "a busy server gets a second try"
        calls["n"] = -10  # now it fails for good
        monkeypatch.setattr(Flaky.embeddings, "create", staticmethod(lambda model, input: (_ for _ in ()).throw(RuntimeError("down"))))  # noqa: A006
        assert embed.embed(["x"]) is None
        monkeypatch.setattr(embed, "_client", lambda: pytest.fail("the server is cooling off; nobody should call it"))
        assert embed.embed(["x"]) is None
    finally:
        monkeypatch.setenv("LLM_MOCK", "true")
        monkeypatch.delenv("EMBED_MODEL")
        settings.cache_clear()


# ---------------------------------------------------------------- PDF layout, tables and pictures
def pdf_at(pages: list[list[tuple]]) -> bytes:
    """A PDF whose text runs sit where they are told: each page is a list of (x, y, text[, size])."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for frags in pages:
        ops = []
        for f in frags:
            safe = f[2].replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"BT /F1 {f[3] if len(f) > 3 else 10} Tf {f[0]} {f[1]} Td ({safe}) Tj ET")
        stream = "\n".join(ops)
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {len(objs)} 0 R "
                    f"/Resources << /Font << /F1 3 0 R >> >> >>")
        kids.append(len(objs))
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n{body}\nendobj\n".encode())
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def _whitepaper_page() -> list[tuple]:
    left = ["Cloud egress fees are rising quickly across", "every region and the trend is not slowing.",
            "Customers report that budgets are overrun", "within the first two quarters of the year."]
    right = ["On-premises workstations avoid those fees", "entirely because data never leaves the site.",
             "The Z8 Fury G5 carries 2TB of memory for", "large models and local fine-tuning work."]
    frags: list[tuple] = [(72, 740, "Executive Summary of the Whitepaper", 14)]
    for i, (a, b) in enumerate(zip(left, right)):   # written row by row, as a two-column page often is
        frags += [(72, 700 - i * 14, a), (320, 700 - i * 14, b)]
    frags += [(72, 620, "Results by site"), (72, 600, "Site"), (250, 600, "Uptime"), (400, 600, "Savings"),
              (72, 586, "Austin"), (250, 586, "99.95%"), (400, 586, "$4.2M"),
              (72, 572, "Leipzig"), (250, 572, "99.90%"), (400, 572, "$1.1M"),
              (72, 540, "A closing paragraph that runs the full width of the page and so belongs to neither column at all.")]
    return frags


def test_a_two_column_pdf_is_read_down_each_column(tmp_path):
    from pypdf import PdfReader
    f = tmp_path / "wp.pdf"
    f.write_bytes(pdf_at([_whitepaper_page()]))
    stored = PdfReader(str(f)).pages[0].extract_text()
    assert "rising quickly across On-premises workstations" in stored, "as stored, the columns are interleaved"
    text = docs.extract(f).text
    assert text.index("within the first two quarters") < text.index("On-premises workstations avoid"), "left column first"
    assert docs.contains(text, "the trend is not slowing. Customers report that budgets are overrun"), \
        "a sentence that runs down a column can be quoted"
    assert not docs.contains(stored, "the trend is not slowing. Customers report that budgets are overrun")
    assert text.index("Executive Summary") < text.index("Cloud egress") < text.index("Results by site") < text.index("A closing paragraph")


def test_a_pdf_table_is_marked_so_it_is_kept_whole(tmp_path):
    f = tmp_path / "wp.pdf"
    f.write_bytes(pdf_at([_whitepaper_page()]))
    d = docs.extract(f)
    assert "| Site | Uptime | Savings |\n| Austin | 99.95% | $4.2M |\n| Leipzig | 99.90% | $1.1M |" in d.text
    table = next(c for c in docs.chunks(d) if "| Austin |" in c.text)
    assert "| Site | Uptime | Savings |" in table.text and "| Leipzig |" in table.text
    rows = [(72, 740, "Site"), (300, 740, "Uptime")] + [x for i in range(150) for x in
                                                           ((72, 726 - i * 4, f"Site number {i}"), (300, 726 - i * 4, f"99.{i % 100:02d}%"))]
    big = tmp_path / "big.pdf"
    big.write_bytes(pdf_at([rows]))
    cs = docs.chunks(docs.extract(big))
    assert len(cs) > 1 and all(c.text.startswith("| Site | Uptime |") for c in cs), "the header row rides with every piece"


def test_an_ordinary_page_and_an_odd_one_are_left_as_pypdf_reads_them(tmp_path, monkeypatch):
    from pypdf import PdfReader

    from app import pdf_layout
    lines = [(72, 740 - i * 14, f"Line number {i} of an ordinary paragraph that runs along the page.") for i in range(4)]
    f = tmp_path / "plain.pdf"
    f.write_bytes(pdf_at([lines + [(72, 660, "A new paragraph after a gap.")]]))
    text = docs.extract(f).text
    assert "|" not in text and text.count("Line number") == 4 and "\n\nA new paragraph" in text
    page = PdfReader(str(f)).pages[0]
    monkeypatch.setattr(pdf_layout, "_rows", lambda p: [pdf_layout.Row(y=1, cells=[pdf_layout.Cell(0, "only this", 10)])])
    assert pdf_layout.page_text(page) == page.extract_text().strip(), "a layout that lost text is not used"
    monkeypatch.setattr(pdf_layout, "_rows", lambda p: 1 / 0)
    assert pdf_layout.page_text(page) == page.extract_text().strip(), "nor one that could not be worked out"


def _png(w: int, h: int, colour=(20, 90, 200)) -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), "white")
    ImageDraw.Draw(im).rectangle([w // 8, h // 8, w - w // 8, h - h // 8], fill=colour)  # content to the edge would be trimmed
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _docx_with_pictures() -> bytes:
    import docx
    d = docx.Document()
    d.add_paragraph("Architecture overview: the pilot saved $4.2M.")
    d.add_picture(io.BytesIO(_png(800, 500)))
    d.add_picture(io.BytesIO(_png(60, 60)))      # a logo
    d.add_picture(io.BytesIO(_png(1200, 40)))    # a rule
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_figures_in_a_document_become_deck_images(client, tmp_path):
    f = tmp_path / "arch.docx"
    f.write_bytes(_docx_with_pictures())
    assert len(docs.pictures(f)) == 1, "the diagram, not the logo or the rule"
    from PIL import Image
    pdf = tmp_path / "scan.pdf"
    Image.open(io.BytesIO(_png(900, 600, (200, 60, 20)))).save(pdf, "PDF")
    assert len(docs.pictures(pdf)) == 1
    assert docs.pictures(tmp_path / "missing.pdf") == []

    p = _deck()
    r = client.post(f"/api/projects/{p.id}/docs", files={"file": ("arch.docx", _docx_with_pictures())})
    assert r.status_code == 200 and r.json()["pictures"] == 1
    assets = [a for a in client.get(f"/api/projects/{p.id}/assets").json() if a["doc"]]
    assert len(assets) == 1 and assets[0]["doc"] == "arch.docx" and assets[0]["upload"] is True, "pickable like any upload"
    key = assets[0]["key"]
    _wait_ready(client, p.id)
    # Removing the document takes an unused picture with it …
    doc_id = client.get(f"/api/projects/{p.id}/docs").json()[0]["id"]
    client.delete(f"/api/docs/{doc_id}")
    assert key not in {a["key"] for a in client.get(f"/api/projects/{p.id}/assets").json()}
    # … but not one a slide is showing.
    client.post(f"/api/projects/{p.id}/docs", files={"file": ("arch.docx", _docx_with_pictures())})
    _wait_ready(client, p.id)
    s = db.slides_of(p.id)[0]
    assert client.post(f"/api/slides/{s.id}/images", json={"key": key}).status_code == 200
    client.delete(f"/api/docs/{client.get(f'/api/projects/{p.id}/docs').json()[0]['id']}")
    assert key in {a["key"] for a in client.get(f"/api/projects/{p.id}/assets").json()}


# ---------------------------------------------------------------- steering an outline drafted from documents
def test_an_outline_can_be_drafted_from_chosen_sections_and_an_angle(client, monkeypatch):
    p = client.post("/api/projects/blank", json={"name": "Steered", "slides": 1}).json()
    pid = p["id"]
    long = db.save(ProjectDoc(project_id=pid, name="long.pdf", status="ready", digest="PURPOSE: the long one"))
    docs.save_text(db.project_dir(pid), long.id, _long_doc())
    memo = db.save(ProjectDoc(project_id=pid, name="memo.txt", status="ready", digest="PURPOSE: memo"))
    docs.save_text(db.project_dir(pid), memo.id, docs.DocText(pages=["The board approved $2M for phase two."]))

    listed = client.get(f"/api/projects/{pid}/docs/sections").json()
    assert [d["name"] for d in listed] == ["long.pdf", "memo.txt"]
    assert [s["title"] for s in listed[0]["sections"]] == ["Executive Summary", "Market Analysis", "Financial Appendix"]
    appendix = listed[0]["sections"][2]
    assert appendix["ref"] == f"{long.id}:3" and appendix["where"] == "p. 3" and appendix["summary"]

    src = reference.compose_source(pid, 200_000, {appendix["ref"]})
    assert "# long.pdf (selected sections)" in src and "paid back in 14 months" in src
    assert "Executive Summary" not in src and "memo.txt" not in src, "what was not chosen is not there"
    assert "Market Analysis" in reference.compose_source(pid, 200_000), "no choice means everything"

    seen = {}

    async def fake(pid_, count, about, source, **kw):
        seen.update(source=source, kw=kw)

    monkeypatch.setattr(runner, "draft_outline", fake)
    client.post(f"/api/projects/{pid}/outline", json={"slides": 5, "sections": [appendix["ref"]], "angle": " Financial case "})
    for _ in range(50):
        if seen:
            break
        asyncio.run(asyncio.sleep(0.02))
    assert "paid back in 14 months" in seen["source"] and "Executive Summary" not in seen["source"]
    assert seen["kw"] == {"angle": "Financial case"}
    msgs = compose.outline_messages({"deck_title": "T", "angle": "Financial case"}, 5, "material")
    assert '"angle": "Financial case"' in msgs[1]["content"]
    assert '"angle"' not in compose.outline_messages({"deck_title": "T"}, 5, "material")[1]["content"]
