"""SQLite persistence (SQLModel). Projects -> Slides -> Versions (A/B lineages)."""
from __future__ import annotations

import logging
import secrets
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import JSON, Column, event
from sqlalchemy import select as sa_select
from sqlmodel import Field, Session, SQLModel, create_engine, select

from ..config import settings

log = logging.getLogger(__name__)


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return prefix + secrets.token_hex(4)


class Project(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("p"), primary_key=True)
    name: str
    filename: str
    # Where the deck's content came from. "pptx" is the converter: a PowerPoint is parsed, rendered and
    # planned. "composed" is a deck written here — the same pipeline from planning onwards, but the slide
    # content is typed (or drafted from a brief) instead of extracted, so there is no source render and
    # nothing to ingest. Rows written before this column exist read back as NULL, which means "pptx".
    source: str = "pptx"    # pptx | composed
    status: str = "uploaded"  # uploaded|composing|ingesting|planning|ready|generating|reviewing|complete|error
    stage_note: str = ""
    error: str = ""
    deck_title: str = ""
    brief: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))  # audience, tone, narrative
    renderer: str = ""
    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # Deck-level LLM rollup, refreshed by runner.roll_up_stats(): the sum of every version's `llm` dict plus the
    # wall-clock of the last generation run. Answers "what did this deck cost and how long did it take", which
    # nothing could answer while the numbers only existed per version. Rows written before this column exist read
    # back as NULL — treat a falsy value as "not measured yet".
    llm: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Slide(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("s"), primary_key=True)
    project_id: str = Field(index=True)
    index: int  # 1-based position in the source PPTX; also names its render (renders/{index:03d}.png)
    # Which part of that source slide this is, 0-based. A dense PowerPoint slide can carry more facts than
    # the density limits allow on one designed slide, and the two constraints cannot both be met — the model
    # resolved that by dropping facts. The planner may now split one source slide into two or three output
    # slides instead, which all share `index` (and its render) and differ by `part`.
    part: int = 0
    position: int  # order in the output deck
    included: bool = True
    content: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))  # the PPTX parse, never overwritten
    # The user's approved copy, holding only the SlideContent fields they changed. None = untouched parse.
    # Laid over `content` by runner.merged_content(), so a slide can always be reverted to the PowerPoint.
    content_edit: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    plan: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # The fact ledger: what this source slide asserts, as `app.facts.Fact` dicts. Written by ingest
    # (deterministic) and annotated by the tier pass; read by generation, QA and the review UI. Null on
    # rows created before it existed — `facts.load()` treats that as an empty ledger, which is exactly
    # the position the pipeline was in before there was one.
    facts: list[Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    # The user's corrections to the ledger, whole-list (a fact can be added, retiered or struck out).
    # None = the extracted ledger stands.
    facts_edit: list[Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    status: str = "pending"  # pending|generating|review|revising|approved|error
    error: str = ""
    approved_version_id: str | None = None
    updated_at: datetime = Field(default_factory=now)


# ------------------------------------------------------------------ the shape of Version.qa
# `Version.qa` is a JSON column written by the pipeline (app/pipeline/runner.py) and by the edit
# re-check in app/main.py, and read by main.py, the frontend, evals/run_eval.py and app/cli.py. It
# was an untyped dict with an implicit schema that grew a field at a time, so a producer-side rename
# only showed up as a crash in the browser.
#
# These models describe it *without* owning it. Every field is optional and every model allows extra
# keys, because the writer is free to add one and this reader must not be the thing that breaks when
# it does. What they buy is a typed, documented boundary: the API layer reads attributes instead of
# guessing at `.get()` chains, and a field that changes type is reported here (see `QaReport.of`)
# with the version id, instead of reaching the UI as `undefined`.
_LOOSE = ConfigDict(extra="allow")


class AbVerdict(BaseModel):
    """The pairwise A-vs-B judgement, written identically onto both versions of a slide.

    It is advice, not a gate: `recommended` says the judge preferred *this* version, and nothing in
    the pipeline acts on it. `status` is ok | skipped | failed — only "ok" carries a real winner.
    """

    model_config = _LOOSE
    status: str = ""                            # ok | skipped | failed
    winner: str = ""                            # A | B | tie ("" unless status == "ok")
    recommended: bool = False                   # the winner is this version's lineage
    confidence: float | None = None             # 0..1, the judge's own certainty
    reason: str = ""                            # one sentence, shown to the user
    order: str = ""                             # AB | BA — which variant the judge saw first
    versions: dict[str, str] = Field(default_factory=dict)  # lineage -> version id
    note: str = ""                              # why it was skipped
    error: str = ""                             # why it failed


class BestOfDraft(BaseModel):
    model_config = _LOOSE
    draft: int = 0
    errors: int = 0
    warns: int = 0
    note: str = ""


class BestOf(BaseModel):
    """Best-of-n sampling for variant A: n drafts DOM-checked, the cleanest kept. Off by default."""

    model_config = _LOOSE
    n: int = 0
    requested: int = 0
    returned: int = 0        # drafts the model actually returned (a draft may fail outright)
    picked: int = 0          # index into `drafts`
    clean: int = 0           # drafts with no error-severity findings
    drafts: list[BestOfDraft] = Field(default_factory=list)


class EditCheck(BaseModel):
    """Set when the version came out of the direct editor: what was changed and whether QA re-ran."""

    model_config = _LOOSE
    parent: str | None = None
    reasons: list[str] = Field(default_factory=list)
    checked: bool = False
    error: str = ""


class QaReport(BaseModel):
    model_config = _LOOSE
    passed: bool | None = None
    findings: list[dict[str, Any]] = Field(default_factory=list)
    critic: dict[str, Any] | None = None
    steps: int | None = None
    shots: list[str] = Field(default_factory=list)
    iterations: list[dict[str, Any]] = Field(default_factory=list)
    vision: bool | None = None
    critic_status: str = ""                     # ok | skipped | failed
    critic_error: str = ""
    critic_warning: str = ""
    critic_skipped_reason: str = ""
    edit: EditCheck | None = None
    ab: AbVerdict | None = None
    best_of: BestOf | None = None
    diff: dict[str, Any] | None = None          # qa/pixels.VisualDiff against the previous iteration

    @classmethod
    def of(cls, raw: dict[str, Any] | None, *, version_id: str = "") -> "QaReport":
        """Validate a stored payload. Drift is logged, never raised: a report that no longer fits is
        still better shown loosely than turned into a 500 on the project route."""
        try:
            return cls.model_validate(raw or {})
        except ValidationError as e:
            log.warning("version %s: qa payload does not fit QaReport (%s)", version_id or "?", e.errors()[:3])
            return cls.model_construct(**(raw or {}))


class Version(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("v"), primary_key=True)
    slide_id: str = Field(index=True)
    project_id: str = Field(index=True)
    lineage: str  # A | B
    number: int = 1  # 1, 2, 3 within lineage
    parent_id: str | None = None
    # How this version came to exist. "llm" is a generation/revision/repair; "edit" is a batch of
    # deterministic direct-manipulation ops (app/edit.py) applied to its parent. Kept apart from
    # `comment` because the two answer different questions: comment is what the user asked the model
    # for, origin is whether a model was involved at all. Rows written before this column exist read
    # back as NULL — treat a falsy value as "llm".
    origin: str = "llm"  # llm | edit
    comment: str = ""
    status: str = "queued"  # queued|generating|qa|repairing|ready|failed|cancelled
    stage_note: str = ""
    spec: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    qa: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    score: float | None = None
    repairs: int = 0
    llm: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error: str = ""
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Choice(SQLModel, table=True):
    """Append-only record of one human A/B decision. Never updated, never deleted.

    This is the single most valuable signal the product produces: a person looked at two finished renderings of
    the same slide, with both QA reports and both scores available, and said which one was better. It is what
    tells you whether the LLM judge should be believed (evals/run_eval.py computes judge-human agreement from
    these rows) and it is the seed corpus for any later fine-tune.

    Everything the calibration needs is denormalized into the row — lineages, scores, the judge's verdict — so a
    record stays readable after its project, slides and versions have been deleted.
    """

    id: str = Field(default_factory=lambda: new_id("ch"), primary_key=True)
    project_id: str = Field(index=True)
    slide_id: str = Field(index=True)
    slide_index: int = 0
    deck: str = ""      # project/deck title at the time of the choice
    pattern: str = ""   # the planned pattern, so agreement can be sliced by slide kind
    chosen_version_id: str = ""
    chosen_lineage: str = ""
    chosen_score: float | None = None
    chosen_critic: float | None = None
    rejected_version_id: str = ""
    rejected_lineage: str = ""
    rejected_score: float | None = None
    rejected_critic: float | None = None
    judge_winner: str = ""              # Version.qa["ab"]["winner"]: A | B | tie | "" when never judged
    judge_confidence: float | None = None
    judge_agrees: bool | None = None    # judge picked what the human picked (None: no judgement, or a tie)
    score_agrees: bool | None = None    # the pointwise score picked what the human picked (the baseline to beat)
    comment: str = ""                   # the revise comment behind the chosen version, if any
    candidates: int = 0                 # ready versions the slide had when the pick was made
    source: str = "user"                # user | edit | auto
    created_at: datetime = Field(default_factory=now)


class Feedback(SQLModel, table=True):
    """Append-only: why a user threw designs away ("too dense", "wrong layout", their own words). Beside `Choice`
    (which of two designs won) this is the other half of the human signal — what keeps going wrong, by pattern."""

    id: str = Field(default_factory=lambda: new_id("fb"), primary_key=True)
    project_id: str = Field(index=True)
    slide_id: str = Field(index=True)
    pattern: str = ""
    kind: str = "redesign"
    reasons: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    note: str = ""
    rejected: list[str] = Field(default_factory=list, sa_column=Column(JSON))  # the version ids replaced
    created_at: datetime = Field(default_factory=now)


class LlmCall(SQLModel, table=True):
    """Append-only ledger of one successful model call — what the usage dashboard (app/usage.py) reads.

    Written by `llm.chat()`, the single choke point every model call passes through, so nothing escapes it.
    Deliberately not keyed to a Version: plan, outline and pairwise calls belong to no version, and a deck's
    savings must not vanish from the dashboard when the deck is deleted. `project_id` is a plain column, not a
    foreign key, for the same reason.
    """

    id: int | None = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=now, index=True)
    project_id: str = Field(default="", index=True)   # "" for calls outside any deck (probe, eval)
    stage: str = ""             # outline | plan | generate | repair | critic | ab | judge | probe
    role: str = ""              # author | review
    model: str = ""             # the name sent on the wire (a ZRT label, or the HF id)
    usage_known: bool = True
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int | None = None   # what the server reported as prefix-cache hits; None = not reported
    system_tokens: int = 0      # estimated size of the byte-stable system prefix a cloud API would cache
    images: int = 0
    seconds: float = 0.0


class ProjectDoc(SQLModel, table=True):
    """A reference document the user added to a deck (app/docs.py). The text lives on disk at
    `projects/<pid>/docs/<id>.txt`; the row carries what the UI lists and the digest the planner reads."""

    id: str = Field(default_factory=lambda: new_id("d"), primary_key=True)
    project_id: str = Field(index=True)
    name: str
    pages: int = 0
    chars: int = 0
    truncated: bool = False
    # The user's word on which document is right when two disagree (an addendum over the RFP it amends).
    primary: bool = False
    status: str = "digesting"   # digesting | ready | error
    error: str = ""
    # ≤600 words from the author model: purpose, audience, claims, and figures copied verbatim. What the
    # planner reads — never the whole text, so a long PDF costs the planner no more than a memo.
    digest: str = ""
    created_at: datetime = Field(default_factory=now)


# ------------------------------------------------------------------ the slide library (app/library/)
# A personal store of finished decks, apart from the conversion pipeline: a library deck is never planned or
# generated, and deleting a project never touches it (its files are copies under `data/library/<deck id>/`).
# Search runs over every slide; the model only tags and summarises the ones the user favourites.
class LibDeck(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("ld"), primary_key=True)
    project: str = Field(default="", index=True)   # the user's project name — what search finds first
    title: str = ""                 # the deck's own title (core properties, else the first slide's title)
    filename: str = ""
    file_sha: str = Field(default="", index=True)  # sha256 of the uploaded file: the same file twice is a duplicate
    deck_date: datetime | None = None              # when the deck was written (core properties; user-editable)
    # Where it came from: an uploaded PowerPoint, the source slides of a converted deck, or the approved
    # slides of a deck made here. `origin_project_id` points back for the last two.
    origin: str = "upload"          # upload | converted | generated
    origin_project_id: str = ""
    supersedes_id: str = ""         # the older deck this one replaces
    superseded_by: str = ""         # set on the older deck; its slides read as superseded
    status: str = "ingesting"       # ingesting | ready | error
    stage_note: str = ""
    error: str = ""
    renderer: str = ""
    slide_count: int = 0
    # Project slide ids starred (library/reuse.py) while this deck was still being copied from its project: the
    # slides to favourite once they exist. Emptied when applied. Null on rows written before it existed = none.
    pending_favourites: list[str] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class LibSlide(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("ls"), primary_key=True)
    deck_id: str = Field(index=True)
    index: int                      # 1-based; names the render (library/<deck>/renders/{index:03d}.png)
    title: str = ""
    text: str = ""                  # every word on the slide, flattened: body, table cells, chart labels
    notes: str = ""
    content: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))  # SlideContent, as parsed
    facts: list[Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    phash: str = Field(default="", index=True)    # 64-bit dHash of the render, hex — finds the same slide in other decks
    text_sha: str = Field(default="", index=True)  # fallback fingerprint when there is no render
    favourite: bool = Field(default=False, index=True)
    favourited_at: datetime | None = None
    # What the review model said about it. Only favourites are tagged unless the user asks for a whole deck.
    ai_status: str = "none"         # none | pending | done | error
    ai_error: str = ""
    summary: str = ""
    slide_type: str = ""            # an enum from library/taxonomy.py
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))       # LibTag slugs
    entities: list[Any] = Field(default_factory=list, sa_column=Column(JSON))   # [{name, type}]
    suggested: list[str] = Field(default_factory=list, sa_column=Column(JSON))  # new tags the model proposed
    # The user's edits are never overwritten by a re-tag.
    tags_user: bool = False
    summary_user: bool = False
    slide_type_user: bool = False
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class LibTag(SQLModel, table=True):
    slug: str = Field(primary_key=True)   # "generative-ai"
    label: str                            # "Generative AI"
    facet: str = "topic"                  # topic | product | customer | project
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSON))  # normalised spellings that map here
    approved: bool = True                 # False = a model suggestion waiting for the user
    created_at: datetime = Field(default_factory=now)


def docs_of(project_id: str) -> list[ProjectDoc]:
    with session() as s:
        return list(s.exec(select(ProjectDoc).where(ProjectDoc.project_id == project_id).order_by(ProjectDoc.created_at)))


_engine = None


def _add_missing_columns(conn) -> None:  # noqa: ANN001
    """`create_all` only ever creates whole tables, so a column added to the model after a database
    already exists would silently never appear. Nullable additions are applied here instead."""
    for table in SQLModel.metadata.sorted_tables:
        have = {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info('{table.name}')")}
        if not have:
            continue  # brand-new table: create_all already built it in full
        for col in table.columns:
            if col.name in have:
                continue
            try:
                conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type.compile(conn.dialect)}')
                log.info("migrated %s: added column %s", table.name, col.name)
            except Exception as e:  # noqa: BLE001
                log.error("could not add column %s.%s: %s", table.name, col.name, e)


def engine():
    global _engine
    if _engine is None:
        s = settings()
        s.data_dir.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(f"sqlite:///{s.data_dir / 'app.db'}", connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(_engine, "connect")
        def _pragmas(conn, _):  # noqa: ANN001
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

        SQLModel.metadata.create_all(_engine)
        with _engine.begin() as conn:
            _add_missing_columns(conn)
    return _engine


@contextmanager
def session() -> Iterator[Session]:
    with Session(engine(), expire_on_commit=False) as s:
        yield s


def get(model, id_: str):
    with session() as s:
        return s.get(model, id_)


def save(obj):
    if hasattr(obj, "updated_at"):
        obj.updated_at = now()
    with session() as s:
        s.add(obj)
        s.commit()
        s.refresh(obj)
    return obj


def update(model, id_: str, *, touch: bool = True, **fields):
    """Write `fields` to one row. `touch=False` leaves `updated_at` alone, for writes that change
    nothing the user can see — the UI uses that timestamp as a cache key, so bumping it would reload
    a preview iframe (and throw away an editing session) for a no-op."""
    with session() as s:
        obj = s.get(model, id_)
        if obj is None:
            return None
        for k, v in fields.items():
            setattr(obj, k, v)
        if touch and hasattr(obj, "updated_at"):
            obj.updated_at = now()
        s.add(obj)
        s.commit()
        s.refresh(obj)
        return obj


def slides_of(project_id: str) -> list[Slide]:
    with session() as s:
        return list(s.exec(select(Slide).where(Slide.project_id == project_id).order_by(Slide.position)))


def versions_of_slide(slide_id: str) -> list[Version]:
    with session() as s:
        return list(s.exec(select(Version).where(Version.slide_id == slide_id).order_by(Version.created_at)))


# The three JSON columns the project route does not need in full. `spec` is by far the largest thing
# in the database — the whole HTML/CSS/JS of a slide, tens of kilobytes per version — and only three
# values out of its `meta` ever reach the API. `llm` is a per-version token ledger that nothing on
# the review board reads. Loading and JSON-decoding all of it on every SSE-driven refetch, dozens of
# times during one generation, was the single largest avoidable cost in a run.
_FAT_COLUMNS = ("spec", "llm")
# `qa` is small next to `spec` but it is still two thirds of what the project route sends, and almost
# all of that is detail only the quality dialog ever renders. The slim payload keeps the summary keys
# and drops these — see `main.version_out`.
QA_DETAIL_KEYS = ("findings", "critic", "iterations", "diff")


def _versions_lite(project_id: str) -> list[Version]:
    """`versions_of_project` with the fat columns left in the database.

    The rows come back as ordinary `Version` objects with `spec` and `llm` empty, so nothing
    downstream needs to know about the projection — but nothing may write one back either.
    """
    table = Version.__table__
    cols = [c for c in table.c if c.name not in _FAT_COLUMNS]
    with session() as s:
        rows = s.execute(sa_select(*cols)
                         .where(table.c.project_id == project_id)
                         .order_by(table.c.created_at)).all()
    return [Version(**dict(row._mapping), spec={}, llm={}) for row in rows]


def versions_of_project(project_id: str, *, slim: bool = False) -> list[Version]:
    """Every version of a project, oldest first.

    `slim=True` leaves `spec` and `llm` in the database (see `_versions_lite`). The returned rows are
    read-only projections: never hand one to `save()`, or the fat columns would be written back empty.
    """
    if slim:
        return _versions_lite(project_id)
    with session() as s:
        return list(s.exec(select(Version).where(Version.project_id == project_id).order_by(Version.created_at)))


def log_choice(**fields) -> Choice:
    """Append one human decision. Insert-only by design — there is no update_choice and there must not be."""
    return save(Choice(**fields))


def choices(project_id: str | None = None) -> list[Choice]:
    with session() as s:
        q = select(Choice).order_by(Choice.created_at)
        if project_id:
            q = q.where(Choice.project_id == project_id)
        return list(s.exec(q))


def projects() -> list[Project]:
    with session() as s:
        return list(s.exec(select(Project).order_by(Project.updated_at.desc())))


def delete_slide(slide_id: str) -> None:
    """Delete one slide and every version of it.

    Used when a re-plan splits a source slide into fewer parts than the previous plan did: the orphaned
    parts are that slide's own, and nothing outside them refers to them.
    """
    with session() as s:
        for v in s.exec(select(Version).where(Version.slide_id == slide_id)):
            s.delete(v)
        sl = s.get(Slide, slide_id)
        if sl:
            s.delete(sl)
        s.commit()


def delete_project(project_id: str) -> None:
    """Deletes the project, its slides and its versions. `Choice` rows are deliberately left behind: they are
    the calibration corpus, they carry no content of their own, and they are self-contained."""
    with session() as s:
        for v in s.exec(select(Version).where(Version.project_id == project_id)):
            s.delete(v)
        for sl in s.exec(select(Slide).where(Slide.project_id == project_id)):
            s.delete(sl)
        for d in s.exec(select(ProjectDoc).where(ProjectDoc.project_id == project_id)):
            s.delete(d)
        p = s.get(Project, project_id)
        if p:
            s.delete(p)
        s.commit()


def project_dir(project_id: str) -> Path:
    d = settings().projects_dir / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def version_dir(project_id: str, version_id: str) -> Path:
    d = project_dir(project_id) / "versions" / version_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def asset_files(project_id: str) -> dict[str, Path]:
    d = project_dir(project_id) / "assets"
    return {p.stem: p for p in d.glob("*.*")} if d.exists() else {}
