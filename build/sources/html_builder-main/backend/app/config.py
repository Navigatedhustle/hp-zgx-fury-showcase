"""Settings, read from `.env` only (see `.env.example`).

The flat field names *are* the documented contract: pydantic-settings maps `LLM_BASE_URL` to
`llm_base_url`, and renaming a field renames an environment variable someone has in a file. So the
tidying here is grouping, validation and structured *views* — never a rename.
"""
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Renderer(StrEnum):
    """How the source PowerPoint is turned into per-slide pictures.

    An enum rather than a string because `RENDERER=powerpont` used to be accepted here and then blow
    up as a bare `KeyError` inside `ingest/render.py`, halfway through an import, with nothing to say
    what had been mistyped. It now fails at startup, naming the four values.
    """

    auto = "auto"               # PowerPoint if it answers, LibreOffice if not
    powerpoint = "powerpoint"
    libreoffice = "libreoffice"
    none = "none"               # no source renders: no thumbnails, and the critic works blind


class Vision(StrEnum):
    """Whether the served model is asked to look at images (the design critic and the A/B judge)."""

    auto = "auto"               # probe once with a tiny image and believe the answer
    on = "on"
    off = "off"


class Role(StrEnum):
    """Which of the two served models a call is for.

    The pipeline has always had two byte-stable system prefixes — `skillpack.system_prompt()` for
    authoring and `review_system_prompt()` for judgement — and they are now allowed to live on two
    different vLLM servers. Splitting them is not only about using a better critic: one server means
    the two prefixes evict each other from the same KV cache, so neither stays hot. Two servers give
    each prefix a cache of its own.
    """

    author = "author"           # plan, generate, repair, revise — the long-context, long-output work
    review = "review"           # critic, pairwise A/B, eval judge, grounding — vision + short JSON


class Endpoint(BaseModel):
    """One OpenAI-compatible server and the model it serves."""

    model_config = {"frozen": True}
    role: Role
    base_url: str
    api_key: str
    model: str

    @property
    def key(self) -> str:
        """What the client caches its AsyncOpenAI and per-model state under.

        URL *and* model: a multi-model gateway (ZRT) serves several models behind one URL, routed by the
        `model` field, and each has its own context window, vision and guided-decoding support.
        """
        return f"{self.base_url}#{self.model}"


class Stage(BaseModel):
    """One pipeline stage's model knobs.

    `temperature` is None for the stages whose temperature is fixed in the pipeline and has never
    been configurable (planning, critique) — better an explicit gap than a setting that looks live
    and is not.
    """

    model_config = {"frozen": True}
    thinking: bool = False
    temperature: float | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    # ---------------------------------------------------------------- model endpoint
    llm_base_url: str = "http://127.0.0.1:8001/slides/v1"
    llm_api_key: str = "none"
    llm_model: str = "unsloth/Qwen3.6-27B-NVFP4"
    # The review model (critic, pairwise A/B, eval judge, grounding). Every field falls back to its
    # LLM_* counterpart when empty, so a single-server setup needs no new settings at all.
    vlm_base_url: str = ""          # empty -> same as llm_base_url
    vlm_api_key: str = ""           # empty -> same as llm_api_key
    vlm_model: str = ""             # empty -> same as llm_model
    # The embedding model (app/llm/embed.py): optional. Empty EMBED_MODEL = off, and reference-document search
    # ranks by words alone. Like VLM_*, the URL and key fall back to LLM_*; the model is its ZRT label.
    embed_base_url: str = ""
    embed_api_key: str = ""
    embed_model: str = ""
    embed_dim: int = Field(default=0, ge=0)   # keep the first N dimensions (Matryoshka models only); 0 = all
    # What a retrieval model expects in front of the asking side. This is Qwen3-Embedding's format; set it
    # empty for a model trained without instructions. "\n" is written literally in .env.
    embed_query_prefix: str = ("Instruct: Given a topic or a question, retrieve the document passages and "
                               "presentation slides that address it\\nQuery: ")
    embed_timeout_s: float = Field(default=60, gt=0)
    vision: Vision = Vision.auto
    llm_mock: bool = False          # offline mode: deterministic template output, no GB300 calls
    mock_delay_s: float = Field(default=0.4, ge=0)

    # ---------------------------------------------------------------- throughput
    llm_timeout_s: float = Field(default=600, gt=0)
    llm_max_concurrency: int = Field(default=8, ge=1)
    llm_max_tokens: int = Field(default=16000, ge=256)
    # Constrain the JSON-only stages (plan, critic, pairwise, judge) with extra_body={"guided_json": …}.
    # Never spec generation — restricting the decoder there fights the reasoning the slide code needs.
    # Disables itself for the process if the server refuses it.
    guided_json: bool = True

    # ---------------------------------------------------------------- per-stage model knobs
    # Six flat names for three stages' thinking mode and three sampling temperatures. Read them as a
    # structure through `stages` / `stage()`; they stay flat here because both `.env` and the
    # pipeline address them by these names.
    thinking_plan: bool = True
    thinking_generate: bool = False
    thinking_critic: bool = False
    temp_a: float = Field(default=0.8, ge=0, le=2)
    temp_b: float = Field(default=0.5, ge=0, le=2)
    temp_repair: float = Field(default=0.3, ge=0, le=2)

    # ---------------------------------------------------------------- quality loop
    qa_max_repairs: int = Field(default=2, ge=0)
    qa_concurrency: int = Field(default=3, ge=1)
    critic_min_score: float = Field(default=7.0, ge=0, le=10)
    # Variant-A drafts to sample and filter by DOM check before QA. 1 = off. Costs n renders per slide.
    generate_best_of_a: int = Field(default=1, ge=1, le=8)

    # ---------------------------------------------------------------- local machine
    renderer: Renderer = Renderer.auto
    data_dir: Path = ROOT / "data"
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)
    # An Obsidian vault the library syncs into (`<vault>/HP Slide Library/`, library/obsidian.py). None = off.
    obsidian_vault_dir: Path | None = None

    @field_validator("data_dir")
    @classmethod
    def _abs(cls, v: Path) -> Path:
        return (v if v.is_absolute() else (ROOT / v)).resolve()

    @field_validator("obsidian_vault_dir", mode="before")
    @classmethod
    def _vault(cls, v: object) -> Path | None:
        """`OBSIDIAN_VAULT_DIR=` (the .env.example default) means off — not the current directory."""
        if v is None or not str(v).strip():
            return None
        p = Path(str(v).strip().strip('"')).expanduser()
        return (p if p.is_absolute() else (ROOT / p)).resolve()

    @property
    def vision_model(self) -> str:
        return self.vlm_model or self.llm_model

    @property
    def endpoints(self) -> dict[Role, Endpoint]:
        return {
            Role.author: Endpoint(role=Role.author, base_url=self.llm_base_url, api_key=self.llm_api_key,
                                  model=self.llm_model),
            Role.review: Endpoint(role=Role.review, base_url=self.vlm_base_url or self.llm_base_url,
                                  api_key=self.vlm_api_key or self.llm_api_key, model=self.vision_model),
        }

    def endpoint(self, role: Role | str = Role.author) -> Endpoint:
        return self.endpoints[Role(role)]

    @property
    def split_endpoints(self) -> bool:
        """True when review runs on its own model — a second server, or a second model behind the same URL."""
        e = self.endpoints
        return e[Role.author].key != e[Role.review].key

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def stages(self) -> dict[str, Stage]:
        """The per-stage knobs as one structure, keyed by the stage the pipeline runs.

        A read-only view over the six flat fields, for anything that wants to report or compare the
        configuration rather than pull one number out of it (`cli probe`, the eval harness).
        """
        return {
            "plan": Stage(thinking=self.thinking_plan),
            "variant_a": Stage(thinking=self.thinking_generate, temperature=self.temp_a),
            "variant_b": Stage(thinking=self.thinking_generate, temperature=self.temp_b),
            "repair": Stage(thinking=self.thinking_generate, temperature=self.temp_repair),
            "critic": Stage(thinking=self.thinking_critic),
        }

    def stage(self, name: str) -> Stage:
        return self.stages.get(name, Stage())


ROOT_DIR = ROOT
RUNTIME_DIR = ROOT / "runtime"
SKILL_DIR = ROOT / "skill"
BRAND_DIR = ROOT / "brand"
FRONTEND_DIST = ROOT / "frontend" / "dist"


@lru_cache
def settings() -> Settings:
    s = Settings()
    s.projects_dir.mkdir(parents=True, exist_ok=True)
    return s
