"""OpenAI-compatible client for vLLM on the GB300, with concurrency limits, retries and a vision probe."""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from PIL import Image

from .. import usage
from ..config import Endpoint, Role, settings

log = logging.getLogger(__name__)

# Image sizing. Screenshots of the 1600x900 stage are what the critic judges for typography, alignment,
# spacing and clipping, so they go out at native width and lossless; the original PowerPoint render is
# "content reference only" (skill/critic.md) and is downscaled to keep the token cost of every call down.
# Overridable per environment (SHOT_IMAGE_MAX_W / SOURCE_IMAGE_MAX_W) or via config, if fields are added there.
_SHOT_MAX_W_DEFAULT = 1600
_SOURCE_MAX_W_DEFAULT = 1024
VISION_RETRY_S = 60.0  # a failed vision probe is re-tried after this long (a cold GB300 must not stick text-only)


class ContextLengthError(RuntimeError):
    """The prompt did not fit in the served context window.

    vLLM answers this with a plain HTTP 400, which is indistinguishable from "the request was malformed" at the
    transport level and is fatal by design (retrying the same oversized prompt can only fail again). Callers that
    can make the prompt smaller — the plan pass, generation, repair — catch this specifically, trim and retry once.
    """

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


# Substrings vLLM (and OpenAI-compatible servers generally) use when a prompt exceeds max_model_len. Matched
# case-insensitively against the 400's body; anything that matches is a size problem, not a malformed request.
_CONTEXT_MARKERS = (
    "maximum context length",
    "max_model_len",
    "maximum model length",
    "context length",
    "context window",
    "longer than the maximum",
    "please reduce the length",
    "reduce the length of the messages",
    "too long",
    "prompt is too long",
    "decoder prompt",
)


def is_context_error(message: str) -> bool:
    low = (message or "").lower()
    return any(m in low for m in _CONTEXT_MARKERS)


# Substrings that mean "this server does not do guided/structured decoding" rather than "your request was wrong".
# vLLM supports `guided_json` in extra_body; llama.cpp, LM Studio, Ollama's OpenAI shim and older vLLM builds do
# not, and answer with a validation error naming the field or the structured-output backend. Anything matching
# turns guided decoding off for the process (see `_S.guided`) — the JSON stages then fall back to extract_json,
# which is exactly how they worked before.
_GUIDED_MARKERS = (
    "guided_json", "guided json", "guided decoding", "guided_decoding", "structured output", "structured_output",
    "json_schema", "response_format", "xgrammar", "outlines", "lm-format-enforcer",
    "extra inputs are not permitted", "additional properties", "unexpected keyword", "unknown field",
    "unrecognized request argument", "not supported",
)


def is_guided_error(status_code: int, message: str) -> bool:
    low = (message or "").lower()
    return status_code in (400, 404, 422, 500, 501) and any(m in low for m in _GUIDED_MARKERS)


# Substrings that mean "this request carried more images than the server was launched to accept".
# vLLM fixes that ceiling at startup (--limit-mm-per-prompt) and it cannot be negotiated per request; the
# refusal is a plain 400 that matches neither _CONTEXT_MARKERS nor _GUIDED_MARKERS, so it is fatal where a
# context error would have been trimmed and retried. Used only to explain the failure, never to recover.
_IMAGE_LIMIT_MARKERS = (
    "limit_mm_per_prompt", "limit-mm-per-prompt", "may be provided in one request", "at most",
    "too many images", "number of images", "image input", "multimodal", "mm_processor",
)


def is_image_limit_error(message: str) -> bool:
    low = (message or "").lower()
    return any(m in low for m in _IMAGE_LIMIT_MARKERS)


@dataclass
class LLMResult:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0
    reasoning: str = ""
    finish_reason: str = ""


@dataclass
class _Server:
    """Everything learned about one served model, keyed by `Endpoint.key` (base URL + model).

    Per-model and not global because the author and review roles may be two different models with
    different checkpoints, context windows, image ceilings and structured-output support. A single flat state
    would let the review server's 32k window trim the author's prompts, or one server's guided-decoding
    refusal disable it on the other.
    """

    client: AsyncOpenAI | None = None
    vision: bool | None = None
    vision_at: float = 0.0  # monotonic time of the last probe (only meaningful when vision is False)
    models: list[str] = field(default_factory=list)
    max_model_len: int | None = None
    last_error: str = ""
    guided: bool | None = None  # None = never tried, True = the server honoured guided_json, False = it refused


@dataclass
class _State:
    servers: dict[str, _Server] = field(default_factory=dict)
    sem: asyncio.Semaphore | None = None
    sem_loop: asyncio.AbstractEventLoop | None = None

    def server(self, key: str) -> _Server:
        srv = self.servers.get(key)
        if srv is None:
            srv = self.servers[key] = _Server()
        return srv

    # --- single-server views, kept so existing callers and tests read the endpoint they mean ---
    @property
    def author(self) -> _Server:
        return self.server(settings().endpoint(Role.author).key)

    @property
    def review(self) -> _Server:
        return self.server(settings().endpoint(Role.review).key)


_S = _State()


def endpoint(role: Role | str = Role.author) -> Endpoint:
    return settings().endpoint(role)


def _client(ep: Endpoint | None = None) -> AsyncOpenAI:
    ep = ep or endpoint(Role.author)
    srv = _S.server(ep.key)
    if srv.client is None:
        s = settings()
        srv.client = AsyncOpenAI(base_url=ep.base_url, api_key=ep.api_key, timeout=s.llm_timeout_s, max_retries=0)
    return srv.client


def _sem() -> asyncio.Semaphore:
    """Per-event-loop semaphore: a Semaphore binds to the loop that first awaits it, and the CLI/evals
    call asyncio.run() more than once per process."""
    loop = asyncio.get_running_loop()
    if _S.sem is None or _S.sem_loop is not loop:
        _S.sem = asyncio.Semaphore(settings().llm_max_concurrency)
        _S.sem_loop = loop
    return _S.sem


def _bool_setting(name: str, default: bool) -> bool:
    v = getattr(settings(), name, None)
    if v is None:
        v = os.getenv(name.upper())
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def guided_json_enabled(role: Role | str = Role.review) -> bool:
    """Whether the next JSON-stage call may ask for guided decoding, on that role's server.

    Off once *that* server has refused it and off entirely when GUIDED_JSON=false. Per-server because the
    author and review roles can be two different vLLM builds: one refusing guided decoding says nothing
    about the other, and disabling it globally would cost the working server its schema for nothing.
    """
    return _S.server(endpoint(role).key).guided is not False and _bool_setting("guided_json", True)


def guided_json_state(role: Role | str = Role.review) -> bool | None:
    """None = never attempted, True = honoured, False = the server refused and we fell back."""
    return _S.server(endpoint(role).key).guided


def _int_setting(name: str, default: int) -> int:
    v = getattr(settings(), name, None) or os.getenv(name.upper())
    try:
        return max(64, int(v))
    except (TypeError, ValueError):
        return default


@lru_cache(maxsize=64)
def _image_data_uri(path: str, mtime: float, size: int, max_w: int, lossless: bool) -> str:
    """Encode one image to a data URI. Cached on (path, mtime, size, encoding): the same source render and the
    same screenshot are otherwise re-decoded and re-encoded for generate A, generate B and every critic call."""
    with Image.open(path) as im:
        if lossless and im.width <= max_w and Path(path).suffix.lower() == ".png":
            return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()
        im = im.convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        if lossless:
            im.save(buf, "PNG", optimize=True)
            return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        im.save(buf, "JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _is_shot(path: Path) -> bool:
    return path.name.startswith("shot_")


def image_part(path: Path, max_w: int | None = None, *, readable: bool | None = None) -> dict:
    """A chat image part for `path`, cached on (path, mtime, width, encoding).

    `readable` says the model has to read small text in this picture, not merely recognise its shape. Those
    go at native width without lossy re-encoding: minimum-legal 13px body text survives that and does not
    survive 1024px JPEG. Slide screenshots are readable by default.

    The original PowerPoint render defaults to the cheaper treatment, because the planner only needs its
    *shape* — is this a diagram, a photo, a wall of bullets. Grounding is the exception and passes
    `readable=True`: checking whether a figure survived means reading the figure, and a dense source table
    downscaled to 1024px wide is illegible to any model. Getting that wrong is silent — the critic answers
    confidently about numbers it cannot actually see.
    """
    path = Path(path)
    lossless = _is_shot(path) if readable is None else readable
    if max_w is None:
        max_w = _int_setting("shot_image_max_w", _SHOT_MAX_W_DEFAULT) if lossless else _int_setting("source_image_max_w", _SOURCE_MAX_W_DEFAULT)
    st = path.stat()
    return {"type": "image_url", "image_url": {"url": _image_data_uri(str(path), st.st_mtime, st.st_size, max_w, lossless)}}


async def chat(messages: list[dict], *, role: Role | str = Role.author, model: str | None = None,
               temperature: float = 0.6, max_tokens: int | None = None,
               thinking: bool = False, retries: int = 0, guided_json: dict | None = None,
               stage: str = "", response_format: dict | None = None) -> LLMResult:
    """One chat completion.

    `guided_json` asks vLLM to constrain the reply to a JSON schema (`extra_body={"guided_json": ...}`). It is only
    ever passed by the three stages that emit pure JSON — plan, critic, judge — never by spec generation, where
    format restriction would fight the free-form reasoning the slide code needs. The schema travels in the request
    body, not in the system prompt, so the cached prefix is untouched.

    A server that does not implement it must not break the pipeline: the first refusal turns guided decoding off
    for that server, the same call is re-sent unconstrained, and the caller's existing extract_json path takes
    over. That fallback costs one wasted request per server, once.

    `role` picks which of the two servers the call goes to (author or review); `model` overrides the model name
    on that server, which only the probes need. `stage` only labels the call in the usage ledger (app/usage.py),
    which every successful call is written to.
    """
    s = settings()
    ep = endpoint(role)
    model = model or ep.model
    srv = _S.server(ep.key)
    body = {"chat_template_kwargs": {"enable_thinking": thinking}}
    if thinking:
        body["top_k"] = 20
    if guided_json is not None and guided_json_enabled(ep.role):
        body["guided_json"] = guided_json
    delay = 3.0
    attempt = 0
    while True:
        # the semaphore covers the call only — a backing-off attempt must not hold a concurrency slot asleep
        async with _sem():
            t0 = time.perf_counter()
            try:
                r = await _client(ep).chat.completions.create(
                    model=model, messages=messages, temperature=temperature, top_p=0.95,
                    max_tokens=max_tokens or s.llm_max_tokens, extra_body=body,
                    **({"response_format":response_format} if response_format is not None else {}),
                    extra_headers={"X-Fury-Role":str(ep.role)+":"+stage},
                )
                if "guided_json" in body:
                    srv.guided = True
                ch = r.choices[0]
                msg = ch.message
                reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None) or ""
                u = r.usage
                res = LLMResult(text=msg.content or "", model=model, prompt_tokens=u.prompt_tokens if u else 0,
                                completion_tokens=u.completion_tokens if u else 0, seconds=time.perf_counter() - t0,
                                reasoning=reasoning, finish_reason=ch.finish_reason or "")
                details = getattr(u, "prompt_tokens_details", None) if u else None
                await usage.record(role=str(ep.role), model=model, stage=stage, prompt_tokens=res.prompt_tokens,
                                   completion_tokens=res.completion_tokens,
                                   cached_tokens=getattr(details, "cached_tokens", None),
                                   system_tokens=estimate_tokens([m for m in messages if m.get("role") == "system"]),
                                   images=_count_images(messages), seconds=res.seconds, usage_known=u is not None)
                return res
            except (APIConnectionError, APITimeoutError) as e:
                srv.last_error = f"{type(e).__name__}: {e}"
                if attempt >= retries:
                    raise
            except APIStatusError as e:
                srv.last_error = f"HTTP {e.status_code}: {e.message}"
                detail = f"{e.message} {getattr(e, 'body', '') or ''}"
                if e.status_code == 400 and is_context_error(detail):
                    # never retried as-is: the same prompt cannot start fitting. The caller trims and rebuilds.
                    raise ContextLengthError(srv.last_error, e.status_code) from e
                if "guided_json" in body and is_guided_error(e.status_code, detail):
                    srv.guided = False
                    body.pop("guided_json")
                    log.warning("server refused guided_json (%s) — structured decoding is off for this process, "
                                "JSON replies fall back to best-effort parsing", srv.last_error)
                    continue  # same attempt, unconstrained
                if e.status_code < 500 or attempt >= retries:
                    raise
        attempt += 1
        log.warning("LLM call failed (attempt %d): %s — retrying", attempt, srv.last_error)
        await asyncio.sleep(delay)
        delay *= 2


def _count_images(messages: list[dict]) -> int:
    return sum(1 for m in messages if not isinstance(m.get("content"), str)
               for part in m.get("content") or [] if part.get("type") == "image_url")


def estimate_tokens(messages: list[dict]) -> int:
    """Rough prompt size, good enough to decide whether to split a batch before sending it.

    Text is counted at ~3.6 chars/token (conservative for English prose mixed with JSON); each image part is
    counted at IMAGE_TOKENS, the cost of one ~480px thumbnail in a Qwen-VL-class model. It is an estimate, never
    a guarantee — the real limit is still enforced by the server, and ContextLengthError is the backstop.
    """
    total = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            total += len(c) // 3.6 + 4
            continue
        for part in c or []:
            if part.get("type") == "image_url":
                total += IMAGE_TOKENS
            else:
                total += len(part.get("text", "")) // 3.6 + 4
    return int(total)


IMAGE_TOKENS = 300  # one 480px thumbnail, rounded up


async def context_limit(role: Role | str = Role.author) -> int | None:
    """max_model_len of that role's served model, or None if the server never told us.

    health() caches it; this fills it in for processes (CLI, evals, the pipeline before any health check) that
    never called health, and never raises — an unknown limit simply means "do not pre-trim". Per role because
    the review model is typically served with a much smaller window than the author model, and trimming an
    authoring prompt to the critic's 32k would throw away context that fits perfectly well.
    """
    srv = _S.server(endpoint(role).key)
    if srv.max_model_len or settings().llm_mock:
        return srv.max_model_len
    try:
        await health(role)
    except Exception as e:  # noqa: BLE001
        log.debug("context_limit probe failed: %s", e)
    return srv.max_model_len


async def health(role: Role | str = Role.author) -> dict:
    """Is that role's server up and serving the model we expect?

    `vision` is only ever reported for the review role: it is the critic, the pairwise judge and the grounding
    pass that need to see, and asking the author model whether it can read a picture answers a question the
    pipeline no longer poses.
    """
    s = settings()
    ep = endpoint(role)
    if s.llm_mock:
        return {"ok": True, "mock": True, "models": ["mock"], "model": "mock", "vision": True,
                "base_url": ep.base_url, "role": str(ep.role)}
    srv = _S.server(ep.key)
    try:
        models = await _client(ep).models.list()
        data = list(models.data)
        srv.models = [m.id for m in data]
        for m in data:
            if m.id == ep.model:
                srv.max_model_len = getattr(m, "max_model_len", None) or (m.model_extra or {}).get("max_model_len")
        ok = ep.model in srv.models
        return {"ok": ok, "mock": False, "models": srv.models, "model": ep.model, "max_model_len": srv.max_model_len,
                "vision": await vision_enabled() if ep.role is Role.review else None,
                "base_url": ep.base_url, "role": str(ep.role), "guided_json": srv.guided,
                "error": "" if ok else f"model {ep.model} not served (available: {', '.join(srv.models)})"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "mock": False, "models": [], "model": ep.model, "vision": False,
                "base_url": ep.base_url, "role": str(ep.role), "error": f"{type(e).__name__}: {e}"}


async def health_all() -> dict[str, dict]:
    """Both roles, asking each distinct server exactly once.

    When the two roles resolve to the same URL and model there is only one thing to probe, so the author's answer
    is reused rather than re-requested — the frontend polls this every 30s per open tab, and a single-server
    setup should not pay two round trips over Tailscale to learn the same thing twice. Only `vision` is filled
    in separately, because it is its own probe and it belongs to whichever model does the reviewing.
    """
    s = settings()
    author = await health(Role.author)
    if s.split_endpoints:
        return {"author": author, "review": await health(Role.review)}
    review = {**author, "role": str(Role.review), "model": s.endpoint(Role.review).model,
              "vision": await vision_enabled() if author.get("ok") else False}
    return {"author": author, "review": review}


def _tiny_image_part(rgb: tuple[int, int, int] = (2, 74, 216)) -> dict:
    """A 64x64 solid-colour PNG part. Small enough that a request carrying sixteen of them is still a
    negligible prompt, so a refusal is about the image *count* and not about the context window."""
    img = Image.new("RGB", (64, 64), rgb)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}}


async def probe_image_count(n: int) -> tuple[bool, str]:
    """Send one request carrying `n` tiny images. Returns (accepted, error).

    The only way to learn the server's real per-request image ceiling: it is fixed at launch, no endpoint
    reports it, and how the server was started (raw vLLM flags, a wrapper, a proxy) does not change what a
    request is allowed to carry. The pipeline needs 3 for the critic and up to PLAN_MAX_IMAGES for a plan batch.
    """
    parts = [_tiny_image_part() for _ in range(n)]
    parts.append({"type": "text", "text": "Reply with the single word: ok"})
    try:
        await chat([{"role": "user", "content": parts}], role=Role.review, temperature=0, max_tokens=8, retries=0,
                   stage="probe")
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


async def vision_enabled() -> bool:
    """vision=auto: probe the *review* server with a tiny image. A positive answer is cached for the process; a
    negative one is cached for VISION_RETRY_S only, so one transient blip (a cold GB300 on the first generation)
    cannot pin the whole run into text-only mode — which silently costs the source image at generate time and
    the critic entirely."""
    s = settings()
    if s.llm_mock:
        return True
    if s.vision in ("on", "off"):
        return s.vision == "on"
    srv = _S.review
    if srv.vision is True:
        return True
    if srv.vision is False and (time.monotonic() - srv.vision_at) < VISION_RETRY_S:
        return False
    part = _tiny_image_part()
    try:
        r = await chat([{"role": "user", "content": [part, {"type": "text", "text": "What colour is this image? One word."}]}],
                       role=Role.review, temperature=0, max_tokens=20, retries=0, stage="probe")
        srv.vision = "blue" in r.text.lower()
        if not srv.vision:
            log.warning("vision probe answered %r — treating the review model as text-only (re-probing in %.0fs)",
                        r.text, VISION_RETRY_S)
    except Exception as e:  # noqa: BLE001
        log.warning("vision probe failed (%s) — text-only mode, re-probing in %.0fs", e, VISION_RETRY_S)
        srv.vision = False
    srv.vision_at = time.monotonic()
    return srv.vision


def reset() -> None:
    """Forget every server: clients, probes and capability flags. Called when settings change under us."""
    _S.servers.clear()
    _S.sem = None
    _S.sem_loop = None
    _image_data_uri.cache_clear()
