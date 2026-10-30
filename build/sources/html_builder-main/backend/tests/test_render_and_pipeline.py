"""Slower tests: headless Chromium renders and the full mock pipeline."""
import asyncio
import shutil

from conftest import DECKS, ROOT

from app import main
from app.assemble import DeckInput, DeckSlide, assemble
from app.config import RUNTIME_DIR
from app.ingest.pptx_parse import Paragraph, SlideContent, TextBlock
from app.pipeline import prompts, runner
from app.qa.render_check import check_spec
from app.skillpack import examples
from app.spec import parse_spec
from app.store import db
from app.store.db import Project, Slide


def test_gold_examples_render_without_errors(tmp_path):
    assets = {p.stem: p for p in (RUNTIME_DIR / "img").iterdir()}

    async def run():
        reps = []
        for i, ex in enumerate(examples()):
            spec, _ = parse_spec(ex.output, f"g{i}")
            reps.append((ex.name, await check_spec(spec, f"g{i}", assets, tmp_path / str(i))))
        return reps

    for name, rep in asyncio.run(run()):
        assert not rep.errors, (name, [e.message for e in rep.errors])
        assert (tmp_path / str(examples().index(next(e for e in examples() if e.name == name))) / "shot_final.png").exists()


def test_broken_spec_is_caught(tmp_path):
    bad = ('<meta>{"steps":1}</meta><html><p style="position:absolute;left:1500px;width:500px">wide text</p>'
           '<img src="asset:missing" alt="gone"></html><script>function go(r,s){ if(s) nope(); }</script>')
    spec, _ = parse_spec(bad, "b")
    rep = asyncio.run(check_spec(spec, "b", {}, tmp_path))
    codes = {f.code for f in rep.errors}
    assert {"overflow", "image", "js"} <= codes


def test_assembled_deck_is_self_contained():
    spec, _ = parse_spec(examples()[5].output, "s")
    html = assemble(DeckInput(title="t", slides=[DeckSlide(id="s", spec=spec)], assets={p.stem: p for p in (RUNTIME_DIR / "img").iterdir()}))
    assert "data:image/png;base64" in html and "data:font/woff2;base64" in html
    assert "https://" not in html.split("<template")[0]  # no external resources in head/runtime


def _slide_with_content() -> Slide:
    p = db.save(Project(name="edit", filename="edit.pptx"))
    sc = SlideContent(index=1, title="Parsed title", texts=[
        TextBlock(kind="title", paragraphs=[Paragraph(text="Parsed title")], box=[100, 60, 1400, 120]),
        TextBlock(kind="body", paragraphs=[Paragraph(text="Parsed point one"),
                                           Paragraph(text="Parsed detail", level=1)], box=[100, 240, 700, 300]),
    ])
    return db.save(Slide(project_id=p.id, index=1, position=1, content=sc.model_dump()))


def test_content_edit_overrides_the_parse_and_reverts():
    s = _slide_with_content()
    parsed = runner._content(s)
    assert parsed == runner.parsed_content(s).for_prompt()  # no override: the parse is the copy

    edit = runner.content_edit(s, blocks=["Approved point one\n  **Approved detail**"])
    s = db.update(Slide, s.id, content_edit=edit)

    merged = runner._content(s)
    assert merged["text"][0]["lines"] == ["Approved point one", "  **Approved detail**"]
    assert merged["text"][0]["kind"] == parsed["text"][0]["kind"]          # kind survives the edit
    assert merged["text"][0]["position"] == parsed["text"][0]["position"]  # so does where it sat
    assert merged["title"] == "Parsed title"                              # untouched fields come from the parse
    assert runner.parsed_content(s).for_prompt() == parsed                # the PPTX parse is never overwritten
    ctx = runner.Ctx(s)
    assert ctx.content == merged and ctx.verbatim  # generation, repair, revision and the critic all read Ctx.content
    assert "Approved point one" in ctx.source_text and "Parsed point one" not in ctx.source_text  # QA fidelity too

    # an emptied block disappears, an extra one lands as body text
    s = db.update(Slide, s.id, content_edit=runner.content_edit(s, blocks=["", "Added block"]))
    assert [b["lines"] for b in runner._content(s)["text"]] == [["Added block"]]

    s = db.update(Slide, s.id, content_edit=None)
    assert runner._content(s) == parsed and not runner.Ctx(s).verbatim


def test_patch_slide_edits_and_resets_content():
    s = _slide_with_content()
    asyncio.run(main.patch_slide(s.id, main.SlidePatch(content=main.ContentEdit(title="New title", blocks=["Only this"]))))
    out = main.slide_out(db.get(Slide, s.id), [])
    assert out["content_edited"] and out["content"]["title"] == "New title"
    assert out["content"]["text"][0]["lines"] == ["Only this"]
    assert out["content_original"]["title"] == "Parsed title"
    assert out["source_title"] == "Parsed title"  # the row still shows what the PowerPoint said

    asyncio.run(main.patch_slide(s.id, main.SlidePatch(reset_content=True)))
    out = main.slide_out(db.get(Slide, s.id), [])
    assert not out["content_edited"] and out["content"] == out["content_original"]
    assert out["content"]["text"][0]["lines"] == ["Parsed point one", "  Parsed detail"]


def test_verbatim_rule_is_user_side_only():
    """The system prompt is the shared prefix vLLM caches — it must not vary with a content edit."""
    kw = dict(variant="A", position=1, total=2, brief={}, plan={}, content={"title": "t"},
              prev_plan=None, next_plan=None, source_png=None, vision=False)
    spec, _ = parse_spec(examples()[0].output, "x")
    calls = [
        (prompts.generate_messages, kw),
        (prompts.repair_messages, dict(variant="A", position=1, plan={}, content={"title": "t"}, spec=spec,
                                       slide_id="x", issues=["[overflow] too tall"], shot=None, vision=False)),
        (prompts.revise_messages, dict(variant="A", position=1, plan={}, content={"title": "t"}, spec=spec,
                                       slide_id="x", comment="tighter", other=None, other_id=None, shot=None, vision=False)),
    ]
    for build, args in calls:
        plain, edited = build(**args), build(**args, verbatim=True)
        assert plain[0]["content"] == edited[0]["content"], build.__name__  # byte-identical system prefix
        assert prompts.VERBATIM_RULE not in plain[0]["content"] + plain[1]["content"]
        assert prompts.VERBATIM_RULE in edited[1]["content"], build.__name__


def test_replan_preserves_content_edits():
    async def run():
        p = db.save(Project(name="t", filename="t.pptx"))
        shutil.copy2(DECKS / "hp_wolf_print_security.pptx", db.project_dir(p.id) / "source.pptx")
        await runner.ingest(p.id)
        s = next(x for x in db.slides_of(p.id) if runner._content(x).get("text"))
        db.update(Slide, s.id, content_edit=runner.content_edit(s, blocks=["Copy the user approved"]))
        await runner.plan(p.id)
        after = db.get(Slide, s.id)
        assert after.content_edit and after.content == s.content  # the parse and the edit both survive
        assert runner._content(after)["text"][0]["lines"] == ["Copy the user approved"]

    asyncio.run(run())


def test_full_mock_pipeline(tmp_path):
    async def run():
        p = db.save(Project(name="t", filename="t.pptx"))
        shutil.copy2(DECKS / "hp_wolf_print_security.pptx", db.project_dir(p.id) / "source.pptx")
        await runner.ingest(p.id)
        assert db.get(Project, p.id).status == "ready"
        await runner.generate_project(p.id)
        slides = db.slides_of(p.id)
        for s in slides:
            vs = db.versions_of_slide(s.id)
            assert {v.lineage for v in vs} == {"A", "B"}
            assert all(v.status == "ready" for v in vs), [(v.lineage, v.error, v.qa) for v in vs]
        await runner.revise(slides[1].id, db.versions_of_slide(slides[1].id)[0].id, "shorter title")
        assert len(db.versions_of_slide(slides[1].id)) == 3
        for s in slides:
            runner.choose(s.id, db.versions_of_slide(s.id)[-1].id)
        assert db.get(Project, p.id).status == "complete"
        html, stats = runner.build_deck(p.id, fill_unapproved=False)
        assert stats["approved"] == len(slides) and html.count("\"hasScript\"") == len(slides)

    asyncio.run(run())
