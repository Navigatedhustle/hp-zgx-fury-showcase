"""The HTTP surface: serializers, upload validation, exports, the SPA guard, and the reliability
fixes around them (SSE resync, the health cache, the killable PowerPoint export)."""
import asyncio
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import settings
from app.events import EventBus
from app.ingest import render
from app.ingest.pptx_parse import SlideContent
from app.qa import render_check
from app.spec import parse_spec
from app.store import db
from app.store.db import Project, Slide, Version

RAW = """<meta>{"pattern":"cards","title":"Spec title","steps":2,"notes":["say this"]}</meta>
<html><h1 class="title">Heading</h1><p>Body copy</p></html>
<css>.title{color:#000}</css>
<script>function go(root, step){}</script>"""


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def no_jobs(monkeypatch):
    """Never let a route start real background work (ingest, generation) during a test."""
    started: list[str] = []

    def spawn(project_id: str, coro):
        started.append(project_id)
        coro.close()
        return None

    monkeypatch.setattr(main.runner.jobs, "spawn", spawn)
    return started


def _project(**kw) -> Project:
    return db.save(Project(**{"name": "deck", "filename": "deck.pptx", "status": "ready", **kw}))


def _slide(p: Project, **kw) -> Slide:
    content = SlideContent(index=1, title="Source title",
                           texts=[{"kind": "body", "paragraphs": [{"text": "four little words here"}]}]).model_dump()
    return db.save(Slide(project_id=p.id, index=1, position=1, status="review", content=content, **kw))


def _version(p: Project, s: Slide, **kw) -> Version:
    spec, _ = parse_spec(RAW, s.id)
    qa = {"passed": True, "findings": [], "critic": {"score": 9}, "iterations": [], "steps": 2, "vision": True,
          "critic_status": "ok", "critic_error": "", "critic_warning": "", "critic_skipped_reason": ""}
    fields = {"lineage": "A", "number": 1, "status": "ready", "spec": spec.model_dump(), "qa": qa, "score": 9.0}
    return db.save(Version(slide_id=s.id, project_id=p.id, **{**fields, **kw}))


# ---------------------------------------------------------------- serializers
def test_project_out_shape(client):
    p = _project(deck_title="Q3 Review", warnings=["one"])
    s = _slide(p)
    _version(p, s)
    out = client.get(f"/api/projects/{p.id}").json()
    assert out["id"] == p.id and out["deck_title"] == "Q3 Review" and out["warnings"] == ["one"]
    assert out["counts"] == {"slides": 1, "included": 1, "approved": 0, "review": 1, "generating": 0, "error": 0, "removed": 0, "appendix": 0}
    assert out["cover_slide_index"] == 1 and out["busy"] is False
    assert out["created_at"].endswith("Z")
    assert len(out["slides"]) == 1
    assert {"id", "name", "filename", "status", "stage_note", "error", "brief", "renderer"} <= set(out)
    # the list route is the same serializer without slides
    assert "slides" not in next(x for x in client.get("/api/projects").json() if x["id"] == p.id)


def test_slide_out_carries_the_content_fields_the_plan_view_edits(client):
    p = _project()
    s = _slide(p)
    out = client.get(f"/api/projects/{p.id}").json()["slides"][0]
    assert out["word_count"] == 4 and out["source_title"] == "Source title"
    assert out["content"]["title"] == "Source title"
    assert out["content_edited"] is False
    assert out["content_original"] == out["content"]  # no override yet: the two agree
    assert {"has_chart", "has_table", "image_count", "notes", "warnings", "plan", "included"} <= set(out)

    r = client.patch(f"/api/slides/{s.id}", json={"content": {"title": "Edited title", "blocks": ["new copy"]}})
    assert r.status_code == 200
    out = client.get(f"/api/projects/{p.id}").json()["slides"][0]
    assert out["content_edited"] is True
    assert out["content"]["title"] == "Edited title"
    assert out["content_original"]["title"] == "Source title"  # the PowerPoint parse survives the edit

    client.patch(f"/api/slides/{s.id}", json={"reset_content": True})
    assert client.get(f"/api/projects/{p.id}").json()["slides"][0]["content_edited"] is False


def test_version_out_keeps_origin_and_the_critic_keys(client):
    p = _project()
    s = _slide(p)
    v = _version(p, s, origin="edit", comment="Edited by hand: 1 text change")
    out = client.get(f"/api/projects/{p.id}").json()["slides"][0]["versions"][0]
    assert out["id"] == v.id and out["origin"] == "edit" and out["lineage"] == "A" and out["number"] == 1
    assert out["title"] == "Spec title" and out["steps"] == 2 and out["notes"] == ["say this"]
    assert out["qa"]["passed"] is True and out["qa"]["critic"] == {"score": 9}
    assert {"critic_status", "critic_error", "critic_warning", "critic_skipped_reason", "vision",
            "findings", "iterations"} <= set(out["qa"])
    assert out["qa"]["critic_status"] == "ok"


def test_version_out_reports_the_new_judge_fields(client):
    p = _project()
    s = _slide(p)
    ab = {"status": "ok", "winner": "A", "recommended": True, "confidence": 0.8, "reason": "Clearer hierarchy.",
          "order": "AB", "versions": {"A": "v1", "B": "v2"}}
    best = {"n": 3, "requested": 3, "returned": 3, "picked": 1, "clean": 2,
            "drafts": [{"draft": 0, "errors": 1, "warns": 0, "note": ""}, {"draft": 1, "errors": 0, "warns": 1, "note": ""}]}
    v = _version(p, s)
    db.update(Version, v.id, qa={**v.qa, "ab": ab, "best_of": best})
    out = client.get(f"/api/projects/{p.id}").json()["slides"][0]["versions"][0]["qa"]
    assert out["ab"]["recommended"] is True and out["ab"]["reason"] == "Clearer hierarchy."
    assert out["best_of"]["picked"] == 1 and len(out["best_of"]["drafts"]) == 2


def test_a_qa_payload_that_no_longer_fits_is_served_anyway(client, caplog):
    """The pipeline owns this dict. A field that changes shape must be reported here, not become a 500."""
    p = _project()
    s = _slide(p)
    v = _version(p, s)
    db.update(Version, v.id, qa={"passed": "maybe", "findings": [], "brand_new_key": 7})
    out = client.get(f"/api/projects/{p.id}").json()["slides"][0]["versions"][0]
    assert out["qa"]["passed"] == "maybe"  # served as stored rather than dropped
    assert any("does not fit QaReport" in r.getMessage() for r in caplog.records)


def test_unknown_qa_keys_survive_the_model():
    r = db.QaReport.of({"passed": True, "something_the_pipeline_added": {"x": 1}})
    assert r.passed is True and r.model_extra["something_the_pipeline_added"] == {"x": 1}


def test_version_out_defaults_origin_for_rows_written_before_the_column(client):
    p = _project()
    s = _slide(p)
    v = _version(p, s)
    db.update(Version, v.id, origin="")
    assert client.get(f"/api/projects/{p.id}").json()["slides"][0]["versions"][0]["origin"] == "llm"


# ---------------------------------------------------------------- the slim polling payload
def test_slim_is_a_strict_subset_of_the_full_payload(client):
    """The client lays slim over the full payload it already holds, so every key slim sends must be
    one full sends too — otherwise a merge would invent a field or clobber a real one."""
    p = _project()
    s = _slide(p)
    _version(p, s)
    full = client.get(f"/api/projects/{p.id}").json()
    slim = client.get(f"/api/projects/{p.id}?slim=true").json()
    assert full["slim"] is False and slim["slim"] is True
    assert set(slim) <= set(full)
    fs, ss = full["slides"][0], slim["slides"][0]
    assert set(ss) <= set(fs)
    fv, sv = fs["versions"][0], ss["versions"][0]
    assert set(sv) <= set(fv)
    assert set(sv["qa"]) <= set(fv["qa"])
    for k, v in sv.items():
        if k != "qa":
            assert fv[k] == v, k
    for k, v in sv["qa"].items():
        assert fv["qa"][k] == v, k


def test_slim_keeps_everything_that_moves_during_a_run(client):
    p = _project(status="generating", stage_note="Designing slide 1")
    s = _slide(p)
    _version(p, s, status="qa", stage_note="Rendering and checking", score=None)
    slim = client.get(f"/api/projects/{p.id}?slim=true").json()
    assert slim["status"] == "generating" and slim["stage_note"] == "Designing slide 1"
    assert slim["counts"]["review"] == 1 and "busy" in slim
    v = slim["slides"][0]["versions"][0]
    assert v["status"] == "qa" and v["stage_note"] == "Rendering and checking"
    assert v["qa"]["critic_status"] == "ok"  # the QA summary is there; the detail behind it is not
    assert "findings" not in v["qa"] and "critic" not in v["qa"]
    assert slim["slides"][0]["status"] == "review" and "approved_version_id" in slim["slides"][0]


def test_slim_drops_the_bulk(client):
    p = _project()
    s = _slide(p)
    _version(p, s)
    v = client.get(f"/api/projects/{p.id}?slim=true").json()["slides"][0]["versions"][0]
    assert {"notes", "title", "llm"}.isdisjoint(v)
    assert "content" not in client.get(f"/api/projects/{p.id}?slim=true").json()["slides"][0]
    full = client.get(f"/api/projects/{p.id}").content
    slim = client.get(f"/api/projects/{p.id}?slim=true").content
    assert len(slim) < len(full)


def test_the_slim_query_never_reads_the_fat_columns(client):
    p = _project()
    s = _slide(p)
    _version(p, s)
    lite = db.versions_of_project(p.id, slim=True)
    full = db.versions_of_project(p.id)
    assert [v.id for v in lite] == [v.id for v in full]
    assert lite[0].spec == {} and lite[0].llm == {}   # left in the database
    assert lite[0].status == full[0].status and lite[0].score == full[0].score
    assert full[0].spec["meta"]["title"] == "Spec title"  # ... and still there for the full payload


def test_missing_ids_are_404(client):
    assert client.get("/api/projects/nope").status_code == 404
    assert client.get("/api/versions/nope/spec").status_code == 404
    assert client.patch("/api/slides/nope", json={"included": False}).status_code == 404


# ---------------------------------------------------------------- upload validation
def _upload(client, name="deck.pptx", body=b"PK\x03\x04data"):
    return client.post("/api/projects", files={"file": (name, body, "application/vnd.ms-powerpoint")})


def test_upload_rejects_anything_but_pptx(client, no_jobs):
    r = _upload(client, name="deck.ppt")
    assert r.status_code == 400 and ".pptx" in r.json()["detail"]
    assert not no_jobs


def test_upload_accepts_a_pptx_and_starts_the_ingest(client, no_jobs):
    r = _upload(client)
    assert r.status_code == 200
    out = r.json()
    assert out["name"] == "deck" and out["filename"] == "deck.pptx"
    assert no_jobs == [out["id"]]
    assert (db.project_dir(out["id"]) / "source.pptx").read_bytes() == b"PK\x03\x04data"


def test_oversize_upload_leaves_no_project_and_no_bytes(client, no_jobs, monkeypatch):
    monkeypatch.setattr(main, "MAX_UPLOAD", 16)
    before = {p.id for p in db.projects()}
    r = _upload(client, body=b"x" * 4096)
    assert r.status_code == 413
    after = {p.id for p in db.projects()}
    assert after == before  # the row is gone
    leaked = [d for d in settings().projects_dir.iterdir() if d.is_dir() and d.name not in before]
    assert leaked == []  # ... and so is the partial source.pptx
    assert not no_jobs


def test_empty_upload_is_refused(client, no_jobs):
    before = {p.id for p in db.projects()}
    r = _upload(client, body=b"")
    assert r.status_code == 400
    assert {p.id for p in db.projects()} == before
    assert not no_jobs


# ---------------------------------------------------------------- choose / revise validation
def test_choose_refuses_a_version_from_another_slide(client):
    p = _project()
    s1, s2 = _slide(p), db.save(Slide(project_id=p.id, index=2, position=2, content={"index": 2}))
    v = _version(p, s1)
    assert client.post(f"/api/slides/{s2.id}/choose", json={"version_id": v.id}).status_code == 400
    assert client.post(f"/api/slides/{s1.id}/choose", json={"version_id": "missing"}).status_code == 404
    assert client.post(f"/api/slides/{s1.id}/choose", json={"version_id": v.id}).status_code == 200
    assert db.get(Slide, s1.id).approved_version_id == v.id


def test_choose_refuses_a_version_that_is_not_ready(client):
    p = _project()
    s = _slide(p)
    v = _version(p, s, status="generating")
    assert client.post(f"/api/slides/{s.id}/choose", json={"version_id": v.id}).status_code == 400


def test_revise_needs_a_ready_base_and_a_comment(client, no_jobs):
    p = _project()
    s = _slide(p)
    v = _version(p, s)
    empty = _version(p, s, lineage="B", spec={})
    assert client.post(f"/api/slides/{s.id}/revise", json={"base_version_id": empty.id, "comment": "x"}).status_code == 400
    assert client.post(f"/api/slides/{s.id}/revise", json={"base_version_id": v.id, "comment": "  "}).status_code == 400
    assert client.post(f"/api/slides/{s.id}/revise", json={"base_version_id": v.id}).status_code == 422
    assert not no_jobs
    assert client.post(f"/api/slides/{s.id}/revise", json={"base_version_id": v.id, "comment": "bigger"}).status_code == 200
    assert no_jobs == [p.id]


def test_generate_is_refused_while_the_deck_is_still_importing(client, no_jobs):
    p = _project(status="ingesting")
    assert client.post(f"/api/projects/{p.id}/generate", json={}).status_code == 409
    assert not no_jobs


# ---------------------------------------------------------------- export
JP = "日本語 デッキ"


def test_export_html_with_a_non_ascii_title(client):
    """Starlette encodes headers as latin-1: a CJK title in `filename=` used to 500 the export."""
    p = _project(deck_title=JP)
    r = client.get(f"/api/projects/{p.id}/export.html")
    assert r.status_code == 200
    cd = r.headers["content-disposition"]
    cd.encode("latin-1")  # would raise before the fix
    assert "filename*=UTF-8''%E6%97%A5%E6%9C%AC%E8%AA%9E_%E3%83%87%E3%83%83%E3%82%AD.html" in cd
    assert 'filename="deck.html"' in cd  # ASCII fallback, never empty
    assert r.text.lstrip().startswith("<!")


def test_export_html_ascii_title_keeps_a_readable_fallback(client):
    p = _project(deck_title="Café Q3 Review!")
    cd = client.get(f"/api/projects/{p.id}/export.html").headers["content-disposition"]
    cd.encode("latin-1")
    assert 'filename="Cafe_Q3_Review.html"' in cd
    assert "filename*=UTF-8''Caf%C3%A9_Q3_Review.html" in cd


def test_export_pdf_uses_a_private_working_directory(client, monkeypatch):
    seen: list[Path] = []

    async def fake_pdf(html_path: Path, out: Path) -> Path:
        seen.append(out)
        out.write_bytes(b"%PDF-1.4 fake")
        return out

    monkeypatch.setattr(main, "export_pdf", fake_pdf)
    p = _project(deck_title=JP)
    r = client.get(f"/api/projects/{p.id}/export.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    r.headers["content-disposition"].encode("latin-1")
    assert "filename*=UTF-8''%E6%97%A5" in r.headers["content-disposition"]
    # per-request directory, cleaned up once the response has been sent
    assert seen and seen[0].parent.name.startswith("pdf-")
    assert not seen[0].parent.exists()


def test_two_pdf_exports_do_not_share_paths(client, monkeypatch):
    seen: list[Path] = []

    async def fake_pdf(html_path: Path, out: Path) -> Path:
        seen.append(out)
        out.write_bytes(b"%PDF-1.4 " + out.parent.name.encode())
        return out

    monkeypatch.setattr(main, "export_pdf", fake_pdf)
    p = _project()
    a = client.get(f"/api/projects/{p.id}/export.pdf").content
    b = client.get(f"/api/projects/{p.id}/export.pdf").content
    assert len({s.parent for s in seen}) == 2
    assert a != b  # each response is the file that request produced


def test_export_stats(client):
    p = _project()
    out = client.get(f"/api/projects/{p.id}/export/stats").json()
    assert out["bytes"] > 0 and out["approved"] == 0


# ---------------------------------------------------------------- SPA / static
@pytest.mark.skipif(not hasattr(main, "spa"), reason="frontend not built")
def test_spa_refuses_to_serve_files_outside_the_dist_folder():
    index = (main.FRONTEND_DIST / "index.html").resolve()
    for path in ("../../README.md", "../../backend/app/main.py", "..%2f..%2f.env", "/etc/passwd"):
        r = asyncio.run(main.spa(path))
        assert Path(r.path).resolve() == index, path
    assert Path(asyncio.run(main.spa("index.html")).path).resolve() == index


# ---------------------------------------------------------------- health cache
def test_health_is_cached(client, monkeypatch):
    calls = []

    async def fake_health(role=None):
        calls.append(role)
        return {"ok": True, "mock": True}

    monkeypatch.setattr(main.llm, "health", fake_health)
    main._health.update(value=None, at=0.0)
    first = client.get("/api/health").json()
    assert first["llm"]["ok"] is True and "renderer" in first and "qa_max_repairs" in first
    # Author and review share one base URL here, so the route reports both roles off a single probe.
    assert first["split"] is False and first["review"]["ok"] is True
    for _ in range(5):
        client.get("/api/health")
    assert len(calls) == 1
    main._health.update(at=time.monotonic() - main.HEALTH_TTL_S - 1)
    client.get("/api/health")
    assert len(calls) == 2
    main._health.update(value=None, at=0.0)


# ---------------------------------------------------------------- SSE backpressure
def test_a_full_subscriber_queue_is_drained_down_to_one_resync():
    async def run():
        bus = EventBus()
        q = bus.subscribe("p1")
        for i in range(q.maxsize + 5):
            bus.publish("p1", {"type": "slides", "n": i})
        # the backlog is gone, replaced by one sentinel; the events after it were delivered normally
        assert q.qsize() == 5
        ev = q.get_nowait()
        assert ev["type"] == "resync" and ev["channel"] == "p1" and ev["dropped"] == q.maxsize
        assert [q.get_nowait()["n"] for _ in range(4)] == [q.maxsize + 1, q.maxsize + 2, q.maxsize + 3, q.maxsize + 4]
        bus.publish("p1", {"type": "slides", "n": 999})
        assert q.get_nowait()["n"] == 999

    asyncio.run(run())


def test_publish_reaches_every_subscriber_including_the_wildcard():
    async def run():
        bus = EventBus()
        a, b, star = bus.subscribe("p1"), bus.subscribe("p1"), bus.subscribe("*")
        bus.publish("p1", {"type": "project", "status": "ready"})
        for q in (a, b, star):
            assert q.get_nowait() == {"channel": "p1", "type": "project", "status": "ready"}
        bus.unsubscribe("p1", a)
        bus.publish("p1", {"type": "project"})
        assert a.empty() and not b.empty()

    asyncio.run(run())


# ---------------------------------------------------------------- PowerPoint export subprocess
def test_a_hung_powerpoint_export_is_killed_and_the_lock_released(tmp_path, monkeypatch):
    """The COM export must be killable: in-process it held _com_lock for the life of the server."""
    hang = tmp_path / "hang.py"
    hang.write_text("import sys, time\n"
                    "(sys.argv[3:4] or [''])[0]\n"
                    "open(sys.argv[2] + '/started.txt', 'w').write(str(__import__('os').getpid()))\n"
                    "time.sleep(600)\n", encoding="utf-8")
    out = tmp_path / "renders"
    out.mkdir()
    monkeypatch.setattr(render, "_WORKER", hang)
    monkeypatch.setattr(render, "COM_TIMEOUT_BASE_S", 3.0)
    monkeypatch.setattr(render, "COM_TIMEOUT_PER_SLIDE_S", 0.0)

    t0 = time.monotonic()
    with pytest.raises(RuntimeError, match="did not respond"):
        render._powerpoint(tmp_path / "deck.pptx", out, expected=3)
    assert time.monotonic() - t0 < 30

    pid = int((out / "started.txt").read_text())
    assert not _alive(pid), "the hung worker process survived the timeout"
    assert render._com_lock.acquire(blocking=False), "_com_lock was not released"
    render._com_lock.release()


def _alive(pid: int) -> bool:
    if sys.platform != "win32":
        try:
            import os
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                         capture_output=True, text=True, timeout=30).stdout
    return str(pid) in out


def test_a_failed_powerpoint_export_reports_the_workers_error(tmp_path, monkeypatch):
    boom = tmp_path / "boom.py"
    boom.write_text("import sys; print('Com error: dialog', file=sys.stderr); sys.exit(1)\n", encoding="utf-8")
    monkeypatch.setattr(render, "_WORKER", boom)
    with pytest.raises(RuntimeError, match="Com error: dialog"):
        render._powerpoint(tmp_path / "deck.pptx", tmp_path, expected=1)


def test_the_powerpoint_worker_reports_its_slide_count(tmp_path, monkeypatch):
    ok = tmp_path / "ok.py"
    ok.write_text("print('chatter'); print('RESULT {\"count\": 7}')\n", encoding="utf-8")
    monkeypatch.setattr(render, "_WORKER", ok)
    assert render._powerpoint(tmp_path / "deck.pptx", tmp_path, expected=7) == 7


def test_render_slides_falls_through_to_libreoffice_when_powerpoint_hangs(tmp_path, monkeypatch):
    calls: list[str] = []

    def powerpoint(pptx, out_dir, expected=None):
        calls.append("powerpoint")
        raise RuntimeError("PowerPoint did not respond within 3s")

    def libreoffice(pptx, out_dir):
        calls.append("libreoffice")
        (out_dir / "001.png").write_bytes(_PNG)
        return 1

    monkeypatch.setattr(render, "_powerpoint", powerpoint)
    monkeypatch.setattr(render, "_libreoffice", libreoffice)
    monkeypatch.setattr(render, "visible_slide_count", lambda p: 1)
    assert render.render_slides(tmp_path / "deck.pptx", tmp_path / "out", "auto") == "libreoffice"
    assert calls == ["powerpoint", "libreoffice"]


# ---------------------------------------------------------------- QA renderer recovery
def test_a_failed_chromium_start_is_retried_instead_of_blocking_for_60s(monkeypatch):
    r = render_check._Renderer()
    attempts: list[str] = []

    async def boom(self):
        attempts.append("boom")
        raise RuntimeError("chromium missing")

    monkeypatch.setattr(render_check._Renderer, "_start", boom)
    for _ in range(2):
        t0 = time.monotonic()
        with pytest.raises(RuntimeError, match="chromium missing"):
            r.ensure()
        assert time.monotonic() - t0 < 10  # used to wait the full 60s ready-timeout, every call
    assert len(attempts) == 2  # ... and the dead thread is replaced rather than reused

    async def ok(self):
        self._sem = asyncio.Semaphore(1)
        self._relaunching = asyncio.Lock()

    monkeypatch.setattr(render_check._Renderer, "_start", ok)
    r.ensure()  # the renderer comes back without restarting the server
    assert r._thread is not None and r._thread.is_alive()
    r._loop.call_soon_threadsafe(r._loop.stop)


def test_a_browser_that_died_mid_run_is_relaunched():
    class FakeBrowser:
        def __init__(self) -> None:
            self.connected = True
            self.contexts = 0

        def is_connected(self) -> bool:
            return self.connected

        async def new_context(self, **kw):
            if not self.connected:
                raise RuntimeError("Target page, context or browser has been closed")
            self.contexts += 1
            return f"ctx{self.contexts}"

        async def close(self) -> None:
            self.connected = False

    async def run():
        r = render_check._Renderer()
        r._relaunching = asyncio.Lock()
        launched = [FakeBrowser()]
        r._browser = launched[0]

        class Chromium:
            async def launch(self, **kw):
                launched.append(FakeBrowser())
                return launched[-1]

        r._pw = type("PW", (), {"chromium": Chromium()})()
        assert await r._context(viewport={}) == "ctx1"
        launched[0].connected = False  # Chromium crashes mid-run
        assert await r._context(viewport={}) == "ctx1"  # a fresh browser, not a `render` finding for ever
        assert len(launched) == 2 and r._browser is launched[1]

    asyncio.run(run())


_PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82")
