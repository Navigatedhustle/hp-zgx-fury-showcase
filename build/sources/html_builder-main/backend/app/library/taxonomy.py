"""The library's controlled vocabulary: seed tags, slide types, facets, entity types, and how a spelling becomes a slug.

Tags are `LibTag` rows. The seed below is written once per slug (`seed()`); after that the user owns the vocabulary —
a renamed, merged or deleted seed tag stays that way, because the slugs already seeded are remembered in
`library/taxonomy_seeded.json` and never re-added. A later release that adds seed tags still gets them.
"""
from __future__ import annotations

import json
import logging
import re
import threading

from sqlmodel import select

from ..store import db
from ..store.db import LibTag
from . import common

log = logging.getLogger(__name__)

SLIDE_TYPES = ("title", "agenda", "section-divider", "data-chart", "table", "comparison", "timeline-roadmap",
               "architecture-diagram", "process", "quote", "team", "product-showcase", "summary", "closing", "other")
FACETS = ("topic", "product", "customer", "project")
ENTITY_TYPES = ("product", "customer", "partner", "technology", "metric", "person", "team")

# (slug, label, facet, aliases). Aliases are spellings, not synonyms of taste: each one is run through normalise()
# before it is stored, so "Gen AI" and "gen-ai" are the same alias.
SEED: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    # AI and data
    ("generative-ai", "Generative AI", "topic", ("genai", "gen-ai", "gen ai", "llm", "large language model")),
    ("ai-inference", "AI inference", "topic", ("inference", "inferencing")),
    ("ai-training", "AI training", "topic", ("model training", "fine-tuning", "fine tuning")),
    ("machine-learning", "Machine learning", "topic", ("ml",)),
    ("agentic-ai", "Agentic AI", "topic", ("ai agent", "agents")),
    ("ai-pc", "AI PC", "topic", ("ai pcs", "npu")),
    ("data-science", "Data science", "topic", ()),
    ("analytics", "Analytics", "topic", ("business intelligence", "bi")),
    ("data-management", "Data management", "topic", ("data platform", "data governance")),
    ("computer-vision", "Computer vision", "topic", ()),
    ("gpu", "GPU", "topic", ("gpus", "accelerator", "accelerated computing")),
    # computing and infrastructure
    ("workstations", "Workstations", "topic", ("workstation",)),
    ("pcs-and-laptops", "PCs and laptops", "topic", ("pc", "laptop", "notebook", "desktop")),
    ("edge-computing", "Edge computing", "topic", ("edge", "edge ai")),
    ("cloud", "Cloud", "topic", ("cloud computing", "public cloud")),
    ("hybrid-cloud", "Hybrid cloud", "topic", ("multicloud", "multi-cloud")),
    ("data-center", "Data center", "topic", ("datacenter", "data centre")),
    ("hpc", "High-performance computing", "topic", ("high performance computing", "supercomputing")),
    ("storage", "Storage", "topic", ()),
    ("networking", "Networking", "topic", ("network",)),
    ("virtualization", "Virtualization", "topic", ("vdi", "virtual desktop")),
    ("printing", "Printing", "topic", ("print", "printer", "3d printing")),
    ("peripherals", "Peripherals", "topic", ("monitor", "display", "accessories")),
    ("hybrid-work", "Hybrid work", "topic", ("remote work", "future of work", "collaboration")),
    ("device-management", "Device management", "topic", ("fleet management", "endpoint management")),
    ("software", "Software", "topic", ()),
    ("open-source", "Open source", "topic", ("oss",)),
    ("developer-tools", "Developer tools", "topic", ("devops", "mlops", "sdk")),
    ("performance", "Performance", "topic", ("benchmark",)),
    ("architecture", "Architecture", "topic", ("reference architecture", "system design")),
    # security and trust
    ("security", "Security", "topic", ("cybersecurity", "cyber security")),
    ("zero-trust", "Zero trust", "topic", ()),
    ("privacy", "Privacy", "topic", ("data privacy",)),
    ("compliance", "Compliance", "topic", ("regulation", "regulatory", "governance")),
    ("risk", "Risk", "topic", ("risk management",)),
    ("responsible-ai", "Responsible AI", "topic", ("ai ethics", "trustworthy ai")),
    # sustainability and operations
    ("sustainability", "Sustainability", "topic", ("esg", "carbon", "net zero", "climate")),
    ("energy-efficiency", "Energy efficiency", "topic", ("power efficiency", "power consumption")),
    ("circular-economy", "Circular economy", "topic", ("recycling", "refurbished")),
    ("supply-chain", "Supply chain", "topic", ("logistics",)),
    ("manufacturing", "Manufacturing", "topic", ()),
    ("operations", "Operations", "topic", ("operational excellence",)),
    ("services", "Services", "topic", ("managed services",)),
    ("lifecycle", "Lifecycle", "topic", ("product lifecycle",)),
    # strategy and business
    ("strategy", "Strategy", "topic", ("strategic",)),
    ("roadmap", "Roadmap", "topic", ("product roadmap",)),
    ("go-to-market", "Go-to-market", "topic", ("gtm",)),
    ("pricing", "Pricing", "topic", ("price", "price list")),
    ("licensing", "Licensing", "topic", ("license", "subscription")),
    ("sales", "Sales", "topic", ("sales enablement", "pipeline")),
    ("marketing", "Marketing", "topic", ("campaign",)),
    ("channel-partners", "Channel partners", "topic", ("channel", "reseller", "partner program")),
    ("partnerships", "Partnerships", "topic", ("alliance", "ecosystem")),
    ("customer-case-study", "Customer case study", "topic", ("case study", "customer story", "reference customer")),
    ("customer-experience", "Customer experience", "topic", ("cx", "user experience", "ux")),
    ("competitive", "Competitive", "topic", ("competition", "competitor", "competitive landscape")),
    ("market-analysis", "Market analysis", "topic", ("market", "market size", "tam", "industry trends")),
    ("financials", "Financials", "topic", ("revenue", "earnings", "financial results", "p&l")),
    ("budget", "Budget", "topic", ("forecast",)),
    ("roi", "ROI and TCO", "topic", ("tco", "total cost of ownership", "return on investment", "cost savings")),
    ("business-case", "Business case", "topic", ("value proposition",)),
    ("kpi", "KPIs and metrics", "topic", ("kpis", "okr", "okrs", "metrics", "scorecard")),
    ("growth", "Growth", "topic", ("expansion",)),
    ("innovation", "Innovation", "topic", ("research", "r&d")),
    ("digital-transformation", "Digital transformation", "topic", ("transformation", "modernization")),
    ("product-launch", "Product launch", "topic", ("launch", "announcement", "new product")),
    ("product-overview", "Product overview", "topic", ("portfolio", "product line", "lineup")),
    ("specifications", "Specifications", "topic", ("specs", "spec sheet", "tech specs")),
    ("use-cases", "Use cases", "topic", ("use case",)),
    ("industry-solutions", "Industry solutions", "topic", ("vertical", "verticals")),
    ("healthcare", "Healthcare", "topic", ("life sciences", "medical")),
    ("financial-services", "Financial services", "topic", ("banking", "fsi", "insurance")),
    ("public-sector", "Public sector", "topic", ("government", "education")),
    ("media-entertainment", "Media and entertainment", "topic", ("m&e", "content creation", "creative")),
    ("engineering-design", "Engineering and design", "topic", ("cad", "simulation", "product design")),
    ("retail", "Retail", "topic", ()),
    # people and programme
    ("organization", "Organization", "topic", ("org chart", "team structure", "leadership")),
    ("hiring", "Hiring", "topic", ("talent", "recruiting")),
    ("training", "Training", "topic", ("enablement", "skills")),
    ("culture", "Culture", "topic", ("diversity", "inclusion")),
    ("project-status", "Project status", "topic", ("status update", "milestones")),
    ("program-management", "Program management", "topic", ("project management", "governance model", "raci")),
    ("timeline", "Timeline", "topic", ("schedule",)),
    ("risks-and-issues", "Risks and issues", "topic", ("issues", "blockers", "mitigation")),
    ("decision", "Decision", "topic", ("approval", "recommendation")),
    ("next-steps", "Next steps", "topic", ("action items", "call to action")),
    ("executive-summary", "Executive summary", "topic", ("exec summary", "overview", "key takeaways")),
    ("lessons-learned", "Lessons learned", "topic", ("retrospective", "postmortem")),
    ("survey-results", "Survey results", "topic", ("survey", "research findings", "insights")),
)

_SEEDED_FILE = "taxonomy_seeded.json"
_seed_lock = threading.Lock()
_seeded_for: str | None = None   # the data dir seed() last ran against (tests swap DATA_DIR per process only)

# A trailing "s" that is not a plural: kept as is so "analytics" never becomes "analytic".
_KEEP_S = {"analytics", "sales", "news", "economics", "logistics", "series", "species", "kubernetes", "windows",
           "os", "status", "bus", "campus", "always", "aws", "ops", "devops", "mlops", "aiops", "finops", "bias",
           "chassis", "gas", "lens", "plus", "this", "its", "was", "has", "virus", "focus", "corpus", "nexus",
           "radius", "bonus", "census", "consensus", "stimulus", "syllabus", "apparatus", "prospectus", "campus"}


def _singular(word: str) -> str:
    if len(word) <= 2 or word in _KEEP_S or word.endswith(("ss", "is", "ics", "ous")):
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "xes", "sses", "zes")):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def slugify(text: str) -> str:
    """Lowercase, '&' → 'and', anything else not a letter or digit → one hyphen."""
    s = (text or "").strip().lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def base_form(text: str) -> str:
    """The comparison key for a spelling: the slug with each word singularised. Never used as a stored slug
    by itself — two spellings are the same tag when their base forms are equal."""
    return "-".join(_singular(w) for w in slugify(text).split("-") if w)


def alias_map(tags: list[LibTag] | None = None) -> dict[str, str]:
    """base form → slug, for every tag's slug, label and aliases. Seed aliases first, then the database, so a
    user's alias always wins over a built-in one."""
    out: dict[str, str] = {}
    for slug, label, _facet, aliases in SEED:
        for spelling in (slug, label, *aliases):
            out.setdefault(base_form(spelling), slug)
    rows = tags if tags is not None else all_tags()
    known = {t.slug for t in rows}
    # a seed slug the user merged away or deleted must not keep resolving to a tag that no longer exists
    out = {k: v for k, v in out.items() if v in known}
    for t in rows:
        for spelling in (*(t.aliases or []), t.label):
            out[base_form(spelling)] = t.slug
    for t in rows:  # a tag's own slug is the strongest claim on its spelling
        out[base_form(t.slug)] = t.slug
    return out


def normalise(text: str, aliases: dict[str, str] | None = None) -> str:
    """A spelling → the slug it means: lowercase, trimmed, slugged, simple plurals singularised, then looked up in
    the alias table ("GenAI", "gen-ai" → "generative-ai"). Unknown spellings come back as their own clean slug
    (without singularising, so "Analytics Pipelines" stays readable as "analytics-pipelines")."""
    slug = slugify(text)
    if not slug:
        return ""
    table = aliases if aliases is not None else alias_map()
    return table.get(base_form(slug), slug)


def all_tags() -> list[LibTag]:
    ensure_seeded()
    with db.session() as s:
        return list(s.exec(select(LibTag).order_by(LibTag.facet, LibTag.label)))


def approved_slugs(tags: list[LibTag] | None = None) -> list[str]:
    return sorted(t.slug for t in (tags if tags is not None else all_tags()) if t.approved)


def _seeded_path():
    return common.library_dir() / _SEEDED_FILE


def seed() -> int:
    """Write every seed tag that was never seeded before (approved=True). Idempotent; returns how many were added.
    A seed slug that is already a row is only recorded, never rewritten — the user may have relabelled it."""
    path = _seeded_path()
    try:
        done = set(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        done = set()
    added = 0
    with db.session() as s:
        have = {t.slug for t in s.exec(select(LibTag))}
        for slug, label, facet, aliases in SEED:
            if slug in done:
                continue
            if slug not in have:
                clean = sorted({base_form(a) for a in aliases} - {base_form(slug)})
                s.add(LibTag(slug=slug, label=label, facet=facet, aliases=clean, approved=True))
                added += 1
            done.add(slug)
        s.commit()
    try:
        path.write_text(json.dumps(sorted(done), indent=0), encoding="utf-8")
    except OSError as e:
        log.warning("could not record the seeded taxonomy (%s) — seed tags may be re-added after a delete", e)
    if added:
        log.info("library taxonomy: seeded %d tags", added)
    return added


def ensure_seeded() -> None:
    """seed() once per process (per data dir). Cheap to call from every vocabulary read."""
    global _seeded_for
    key = str(common.library_dir())
    if _seeded_for == key:
        return
    with _seed_lock:
        if _seeded_for != key:
            seed()
            _seeded_for = key


def taxonomy() -> dict:
    return {"slide_types": list(SLIDE_TYPES), "facets": list(FACETS), "entity_types": list(ENTITY_TYPES)}
