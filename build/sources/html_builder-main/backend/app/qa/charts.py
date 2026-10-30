"""Does each chart on the finished slide show the source PowerPoint chart's data?

`runtime/lib.js` records what every `H.chart.*` call was built from; the renderer reads those records at the final
step (`render_check.CHART_JS`). Here they are matched to the charts python-pptx read out of the source slide and
compared figure by figure. Severity follows the fact ledger's philosophy:

  chart-changed   a value differs in a category and series that match          fatal — never ships
  chart-missing   a category or series dropped, or the source chart is absent  error — forces a repair
  chart-scale     a forced axis maximum below the data (bars clipped)          error
  chart-hidden    part of the data is not visible at the final step            error
  chart-type      a different chart family (bars vs line vs part-of-whole)     warning
  chart-unverified a chart drawn without H.chart: nothing to check it against  warning

A chart the audience drives (a calculator's `set()`) is marked `live` and only checked for shape, never values.
Honest rescaling — $1,420,000 drawn as 1,420 on a "$K" axis, 0.25 drawn as 25% — is accepted.
"""
from __future__ import annotations

import re

from .render_check import Finding

_SCALES = (1.0, 1e3, 1e6, 1e9, 1e-3, 1e-6, 1e-9, 100.0, 0.01)
MATCH_MIN = 0.34      # share of a source chart's categories a rendered chart must share to be "that chart"


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9%$.]+", " ", str(s).lower()).strip()


def family(t: str) -> str:
    t = (t or "").lower()
    if "pie" in t or "doughnut" in t or t == "donut":
        return "part"
    if "line" in t or "area" in t or t == "sparkline":
        return "line"
    if "stack" in t:
        return "stacked"
    if "radar" in t or "scatter" in t or "bubble" in t:
        return "other"
    return "bars"   # column/bar clustered, bars, hbars, groupedBars


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.006 * abs(a), 0.051)


def _scale_of(src: list[float], got: list[float]) -> float | None:
    """The single factor that maps the source values onto the rendered ones, if there is one."""
    pairs = [(a, b) for a, b in zip(src, got) if a is not None and b is not None and a != 0]
    if not pairs:
        return 1.0
    for k in _SCALES:
        if all(_close(a / k, b) for a, b in pairs):
            return k
    return None


def _values_by_label(labels: list[str], values: list) -> dict[str, float | None]:
    return {_norm(lab): (None if v is None else float(v)) for lab, v in zip(labels, values)}


def _match(src: dict, rendered: list[dict]) -> tuple[dict | None, float]:
    cats = [_norm(c) for c in src.get("categories") or []]
    best, score = None, 0.0
    for r in rendered:
        got = {_norm(x) for x in r.get("labels") or []}
        if cats:
            s = sum(1 for c in cats if c in got) / len(cats)
        else:  # a chart with no categories (a single pie value): match on series names
            names = {_norm(x.get("name", "")) for x in src.get("series") or []}
            s = 1.0 if names & {_norm(x.get("name", "")) for x in r.get("series") or []} else 0.0
        if s > score:
            best, score = r, s
    return best, score


def chart_findings(source_charts: list[dict], rendered: list[dict], unverified: int = 0,
                   pattern: str = "") -> list[Finding]:
    out: list[Finding] = []
    used: set[int] = set()
    for src in source_charts or []:
        title = src.get("title") or "the source chart"
        cats = [str(c) for c in src.get("categories") or []]
        pool = [r for i, r in enumerate(rendered) if i not in used]
        r, score = _match(src, pool)
        if r is None or score < MATCH_MIN:
            if unverified:
                out.append(Finding(severity="warn", code="chart-unverified",
                                   message=f"{title}: drawn without H.chart, so its data can't be checked against the "
                                           f"source — rebuild it with H.chart.* from the source data"))
                continue
            sev = "error" if pattern == "chart" or not rendered else "warn"
            out.append(Finding(severity=sev, code="chart-missing",
                               message=f"{title} ({', '.join(cats[:6])}) from the source is not on the slide — "
                                       f"build it with H.chart from the source data"))
            continue
        used.add(rendered.index(r))
        got_labels = [str(x) for x in r.get("labels") or []]
        have = {_norm(x) for x in got_labels}
        dropped = [c for c in cats if _norm(c) not in have]
        if dropped:
            out.append(Finding(severity="error", code="chart-missing",
                               message=f"{title}: categories missing from the chart: {', '.join(dropped[:6])}"))
        if family(src.get("type", "")) != family(r.get("type", "")) and family(src.get("type", "")) != "other":
            out.append(Finding(severity="warn", code="chart-type",
                               message=f"{title} is a {src.get('type')} chart in the source but is drawn as "
                                       f"{r.get('type')} — keep the source's chart type unless the plan says otherwise"))
        if r.get("hidden"):
            out.append(Finding(severity="error", code="chart-hidden",
                               message=f"{title}: {r['hidden']} value(s) are not visible at the final step — "
                                       f"the last step must show every bar/point"))
        rser = r.get("series") or []
        if r.get("max") is not None:
            top = max((v for se in rser for v in se.get("values") or [] if v is not None), default=0)
            if r["max"] < top:
                out.append(Finding(severity="error", code="chart-scale",
                                   message=f"{title}: the axis maximum {r['max']:g} is below the largest value {top:g}, "
                                           f"so bars are clipped — drop `max` or raise it"))
        if r.get("live"):
            continue  # the audience's own numbers: shape is checked, values are theirs
        by_name = {_norm(x.get("name", "")): x for x in rser}
        changed: list[str] = []
        missing_series: list[str] = []
        for i, sse in enumerate(src.get("series") or []):
            name = sse.get("name", "") or f"series {i + 1}"
            rse = by_name.get(_norm(sse.get("name", ""))) or (rser[i] if i < len(rser) else None)
            if rse is None:
                missing_series.append(name)
                continue
            want = _values_by_label(cats, sse.get("values") or [])
            got = _values_by_label(got_labels, rse.get("values") or [])
            keys = [k for k in want if k in got and want[k] is not None and got[k] is not None]
            k = _scale_of([want[x] for x in keys], [got[x] for x in keys])
            if k is None:
                for key in keys:
                    if not _close(want[key], got[key]):
                        label = next((c for c in cats if _norm(c) == key), key)
                        changed.append(f"{name} · {label}: source {want[key]:g}, slide {got[key]:g}")
        if missing_series and len(src.get("series") or []) > 1:
            out.append(Finding(severity="error", code="chart-missing",
                               message=f"{title}: series missing from the chart: {', '.join(missing_series[:4])}"))
        if changed:
            out.append(Finding(severity="error", fatal=True, code="chart-changed",
                               message=f"{title}: the chart changes source values — " + "; ".join(changed[:4])))
    return out
