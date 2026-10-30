"""Existing slide call ledger and selected-price scenarios.
Only API-reported usage is measured. Missing token/cache data stays unknown.
The shared Fury gateway extends this database with prompt-free aggregate events.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

from sqlmodel import select

from .store import db
from .store.db import LlmCall, Project

log = logging.getLogger(__name__)

PRICING = Path(__file__).with_name("pricing.json")
SAME_SIZE = "same_size"

# Which deck the running job belongs to. Set by `runner.jobs.spawn`, inherited by every task the job starts,
# so no call site has to thread a project id through to the client.
current_project: ContextVar[str] = ContextVar("current_project", default="")


def pricing() -> dict:
    """Re-read on every request: the file is meant to be edited while the app runs."""
    try:
        return json.loads(PRICING.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("pricing.json unreadable (%s) — cloud comparison disabled", e)
        return {"as_of": "", "frontier": [], "same_size": []}


def _insert(row: LlmCall) -> None:
    with db.session() as s:
        s.add(row)
        s.commit()


async def record(*, role: str, model: str, stage: str, prompt_tokens: int, completion_tokens: int,
                 cached_tokens: int | None, system_tokens: int, images: int, seconds: float, usage_known: bool = True) -> None:
    """Log one call. Never raises: losing a ledger row must not fail a generation."""
    row = LlmCall(usage_known=usage_known, project_id=current_project.get(), stage=stage, role=role, model=model,
                  prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, cached_tokens=cached_tokens,
                  system_tokens=system_tokens, images=images, seconds=round(seconds, 3))
    try:
        await asyncio.to_thread(_insert, row)
    except Exception as e:  # noqa: BLE001
        log.warning("usage ledger write failed: %s", e)


# ------------------------------------------------------------------ pricing
def _match(model: str, same_size: list[dict]) -> dict | None:
    m = model.lower()
    for entry in same_size:
        if any(k.lower() == m or k.lower() in m for k in entry.get("match", [])):
            return entry
    return None


def _cached(c: LlmCall) -> int:
    n = c.cached_tokens if c.cached_tokens is not None else 0
    return max(0, min(n, c.prompt_tokens))


def _cost(c: LlmCall, price: dict) -> float:
    hit = _cached(c)
    return ((c.prompt_tokens - hit) * price["input"] + hit * price.get("cached", price["input"])
            + c.completion_tokens * price["output"]) / 1e6


def _costs(c: LlmCall, p: dict) -> dict[str, float]:
    out = {f["id"]: _cost(c, f) for f in p.get("frontier", [])}
    same = _match(c.model, p.get("same_size", []))
    out[SAME_SIZE] = _cost(c, same) if same else 0.0
    return out


# ------------------------------------------------------------------ rollup
def _bucket() -> dict[str, Any]:
    return {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "images": 0, "seconds": 0.0,
            "costs": defaultdict(float)}


def _add(b: dict, c: LlmCall, costs: dict[str, float]) -> None:
    b["calls"] += 1
    b["prompt_tokens"] += c.prompt_tokens
    b["completion_tokens"] += c.completion_tokens
    b["images"] += c.images
    b["seconds"] += c.seconds
    for k, v in costs.items():
        b["costs"][k] += v


def _out(b: dict) -> dict:
    return {**b, "seconds": round(b["seconds"], 1), "total_tokens": b["prompt_tokens"] + b["completion_tokens"],
            "costs": {k: round(v, 4) for k, v in b["costs"].items()}}


def summary(days: int | None = None) -> dict:
    """Everything the dashboard shows, for the last `days` days (None = all time)."""
    p = pricing()
    # SQLite hands datetimes back naive; they were written in UTC, so compare in naive UTC
    since = (db.now() - timedelta(days=days)).replace(tzinfo=None) if days else None
    with db.session() as s:
        q = select(LlmCall).order_by(LlmCall.at)
        if since is not None:
            q = q.where(LlmCall.at >= since)
        calls = list(s.exec(q))
        titles = {pr.id: pr.deck_title or pr.name for pr in s.exec(select(Project))}

    total = _bucket()
    models: dict[str, dict] = {}
    stages: dict[str, dict] = defaultdict(_bucket)
    decks: dict[str, dict] = defaultdict(_bucket)
    daily: dict[str, dict] = defaultdict(_bucket)
    latencies: dict[str, list[float]] = defaultdict(list)
    cached_reported = cached = 0
    unpriced = 0
    unknown_usage_calls = sum(not c.usage_known for c in calls)
    for c in calls:
        if not c.usage_known:
            continue
        costs = _costs(c, p)
        _add(total, c, costs)
        if c.model not in models:
            same = _match(c.model, p.get("same_size", []))
            models[c.model] = {**_bucket(), "roles": set(), "name": same["name"] if same else c.model,
                               "hf": same.get("hf", "") if same else ""}
        m = models[c.model]
        _add(m, c, costs)
        m["roles"].add(c.role)
        latencies[c.model].append(c.seconds)
        _add(stages[c.stage or "other"], c, costs)
        if c.project_id:
            _add(decks[c.project_id], c, costs)
            decks[c.project_id]["last_at"] = c.at
        _add(daily[_day(c.at)], c, costs)
        cached += _cached(c)
        cached_reported += c.cached_tokens is not None
        if not _match(c.model, p.get("same_size", [])):
            unpriced += c.prompt_tokens + c.completion_tokens

    def model_row(name: str, b: dict) -> dict:
        out = _out(b)
        out["model"] = name
        out["roles"] = sorted(b["roles"])
        out["tok_s"] = round(b["completion_tokens"] / b["seconds"], 1) if b["seconds"] else None
        out["p50_s"] = round(median(latencies[name]), 1) if latencies[name] else None
        return out

    return {
        "unknown_usage_calls": unknown_usage_calls,
        "as_of": p.get("as_of", ""),
        "days": days,
        "frontier": [{k: f[k] for k in ("id", "name", "vendor", "input", "cached", "output", "source") if k in f}
                     for f in p.get("frontier", [])],
        "same_size": [{k: e[k] for k in ("name", "hf", "input", "cached", "output", "source") if k in e}
                      for e in p.get("same_size", [])],
        "same_size_unpriced_tokens": unpriced,
        "totals": {**_out(total), "decks": len(decks),
                   "cached_tokens": cached, "cache_reported": bool(calls) and cached_reported == len(calls)},
        "models": sorted((model_row(k, v) for k, v in models.items()), key=lambda r: -r["total_tokens"]),
        "stages": sorted(({"stage": k, **_out(v)} for k, v in stages.items()), key=lambda r: -r["total_tokens"]),
        "decks": sorted(({"project_id": k, "title": titles.get(k, ""), "deleted": k not in titles,
                          "last_at": _utc(v.pop("last_at")), **_out(v)} for k, v in decks.items()),
                        key=lambda r: r["last_at"], reverse=True),
        "daily": [{"day": k, **_out(v)} for k, v in sorted(daily.items())],
    }


def _utc(at: datetime) -> str:
    return (at if at.tzinfo else at.replace(tzinfo=timezone.utc)).isoformat()


def _day(at: datetime) -> str:
    """The local calendar day of a UTC timestamp, which is the day the user remembers the work on."""
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return at.astimezone().strftime("%Y-%m-%d")
