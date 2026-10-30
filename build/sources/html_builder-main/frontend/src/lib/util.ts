import clsx, { type ClassValue } from "clsx";
import { ApiError, isRemoved, type AbVerdict, type BestOf, type Critic, type CriticIssue, type CriticStatus, type EditFailure, type EditOp, type ElementInfo, type Fact, type Finding, type Project, type ProjectStatus, type Slide, type SlideStatus, type Version } from "./api";

export const cn = (...v: ClassValue[]) => clsx(v);

export const projectStatusText: Record<ProjectStatus, string> = {
  uploaded: "Uploaded",
  composing: "Drafting",
  ingesting: "Importing",
  planning: "Planning",
  ready: "Plan ready",
  generating: "Designing slides",
  reviewing: "In review",
  complete: "Ready to export",
  error: "Needs attention",
};

export const slideStatusText: Record<SlideStatus, string> = {
  pending: "Not started",
  generating: "Designing",
  review: "Pick a design",
  revising: "Revising",
  approved: "Approved",
  error: "Failed",
};

export const lineageName = { A: "Cinematic", B: "Refined" } as const;
export const lineageBlurb = { A: "Highly interactive", B: "Minimal interaction" } as const;

export function slideTone(s: SlideStatus): "good" | "warn" | "bad" | "busy" | "idle" {
  if (s === "approved") return "good";
  if (s === "review") return "warn";
  if (s === "error") return "bad";
  if (s === "generating" || s === "revising") return "busy";
  return "idle";
}

export function timeAgo(iso: string): string {
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.floor(d / 60)} min ago`;
  if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** Latest version per lineage (the one shown on the review board by default). */
export function latestByLineage(slide: Slide): { A?: Version; B?: Version } {
  const out: { A?: Version; B?: Version } = {};
  for (const v of slide.versions) out[v.lineage] = v;
  return out;
}

export const isBusyVersion = (v?: Version | null) => !!v && ["queued", "generating", "qa", "repairing"].includes(v.status);

export const isBusySlide = (s: Slide) =>
  s.status === "generating" || s.status === "revising" || s.versions.some(isBusyVersion);

/** True while anything on the project is still being produced, whatever the project status says. */
export const hasWorkInFlight = (p?: Project) =>
  !!p && (p.busy || ["uploaded", "composing", "ingesting", "planning", "generating"].includes(p.status) || (p.slides ?? []).some(isBusySlide));

/* --------------------------------------------------------- QA payload accessors
 * The backend's `qa` dict is shared with other tooling and gains fields over
 * time. Nothing in the UI may assume a shape: read it only through these. */

export function qaFindings(v?: Version | null): Finding[] {
  const f = v?.qa?.findings;
  return Array.isArray(f) ? f : [];
}

export function qaCritic(v?: Version | null): Critic | null {
  const c = v?.qa?.critic;
  return c && typeof c === "object" ? c : null;
}

export function criticScores(c: Critic | null): [string, number][] {
  const s = c?.scores;
  if (!s || typeof s !== "object") return [];
  return Object.entries(s).filter((e): e is [string, number] => typeof e[1] === "number");
}

export function criticIssues(c: Critic | null): CriticIssue[] {
  const i = c?.issues;
  return Array.isArray(i) ? i.filter(x => !!x && typeof x === "object") : [];
}

/** Why a design does or doesn't carry a review, so a score is never read as more than it is.
 *  `failed` matters most: the critique never ran, so the score is a floor, not a verdict. */
export function criticState(v?: Version | null): { status: CriticStatus; label: string; detail: string } | null {
  const raw = v?.qa?.critic_status;
  const status: CriticStatus | null =
    raw === "ok" || raw === "skipped" || raw === "failed" ? raw
      : qaCritic(v) ? "ok" : null;  // pre-existing versions predate the field
  if (!status || status === "ok") {
    const warning = typeof v?.qa?.critic_warning === "string" ? v.qa.critic_warning : "";
    if (!status) return null;
    return { status, label: "Reviewed", detail: warning };
  }
  const detail = String(
    (status === "failed" ? v?.qa?.critic_error : v?.qa?.critic_skipped_reason) ?? "",
  );
  return status === "failed"
    ? { status, label: "Not reviewed", detail: detail || "The design critique failed to run." }
    : { status, label: "Review skipped", detail };
}

/** The pairwise A-vs-B judgement, and only when it actually ran. */
export function qaAb(v?: Version | null): AbVerdict | null {
  const ab = v?.qa?.ab;
  if (!ab || typeof ab !== "object") return null;
  return ab.status === "ok" && (ab.winner === "A" || ab.winner === "B" || ab.winner === "tie") ? ab : null;
}

/** What to tell the user about a version, or null when there is nothing worth saying.
 *  `preferred` is the judge's pick; a tie is reported as a tie, never as a win. */
export function abAdvice(v?: Version | null): { preferred: boolean; tie: boolean; reason: string; confidence: number | null } | null {
  const ab = qaAb(v);
  if (!ab) return null;
  return {
    preferred: ab.recommended === true,
    tie: ab.winner === "tie",
    reason: typeof ab.reason === "string" ? ab.reason : "",
    confidence: typeof ab.confidence === "number" ? ab.confidence : null,
  };
}

/** Best-of-n sampling, present only when it was switched on for this generation. */
export function qaBestOf(v?: Version | null): BestOf | null {
  const b = v?.qa?.best_of;
  if (!b || typeof b !== "object") return null;
  return typeof b.n === "number" && b.n > 1 ? b : null;
}

/** `n drafts, m clean` — the one line the best-of record is worth in the UI. */
export function bestOfSummary(b: BestOf): string {
  const drafts = Array.isArray(b.drafts) ? b.drafts.length : (b.returned ?? 0);
  const clean = b.clean ?? 0;
  return `${drafts} draft${drafts === 1 ? "" : "s"} sampled · ${clean} passed the layout check · kept #${(b.picked ?? 0) + 1}`;
}

/** Counts are derived from slides on the server; recompute them after a local patch. */
export function recount(p: Project): Project {
  if (!p.slides) return p;
  const slides = p.slides.filter(s => !isRemoved(s));  // mirrors project_out: removed slides are out of the deck
  return {
    ...p,
    counts: {
      removed: p.slides.length - slides.length,
      appendix: slides.filter(s => s.included && s.plan?.appendix).length,
      slides: slides.length,
      included: slides.filter(s => s.included).length,
      approved: slides.filter(s => s.included && s.status === "approved").length,
      review: slides.filter(s => s.included && s.status === "review").length,
      generating: slides.filter(s => s.status === "generating" || s.status === "revising").length,
      error: slides.filter(s => s.status === "error").length,
    },
  };
}

export function formatBytes(n: number): string {
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${Math.round(n / 1e3)} KB`;
}

export const patterns = [
  "title", "agenda", "section", "stat-hook", "cards", "problem-solution", "specs", "chart", "compare", "calculator",
  "explorer", "process", "timeline", "roadmap", "quote", "table", "references", "closing", "image-focus",
];

/* --------------------------------------------------------- direct editing */

/** The structured body of a 400 from the edit route, when there is one. */
export function editFailure(e: unknown): EditFailure | null {
  if (!(e instanceof ApiError) || !e.detail || typeof e.detail !== "object") return null;
  const d = e.detail as Partial<EditFailure>;
  return typeof d.error_code === "string" ? { message: d.message ?? e.message, error_code: d.error_code, failed_index: d.failed_index ?? null, op: d.op ?? "", eid: d.eid ?? "" } : null;
}

/** A short name for an element, for the toolbar title and the pending list. */
export function elementLabel(el?: ElementInfo | null): string {
  if (!el) return "element";
  const cls = el.classes.find(c => c !== "appear");
  const text = el.text.trim();
  if (text) return text.length > 28 ? `${text.slice(0, 28)}…` : text;
  return cls ? `.${cls}` : `<${el.tag}>`;
}

/** Why the server would refuse to remove this element, in the user's words. */
export function lockReason(el?: ElementInfo | null): string {
  if (!el || el.deletable) return "";
  if (el.locks.includes("only-top-level")) return "This is the slide's only block — the slide can't be left empty.";
  const hook = el.locks.find(l => l.startsWith("script:"))?.slice(7);
  return hook ? `The slide's script looks for ${hook}, and this is the last element carrying it.` : "This element is locked.";
}

/** Plain names for the CSS the toolbar and the resize handles write. The pending-changes list is
 *  something the user reads back before saving, so "grid-template-columns" is the wrong word for it. */
const STYLE_NAME: Record<string, string> = {
  "color": "Text colour", "background": "Fill", "background-color": "Fill", "border-color": "Border colour",
  "opacity": "Opacity", "font-weight": "Weight", "font-style": "Italics", "text-transform": "Capitals",
  "text-decoration": "Underline", "text-align": "Alignment", "border-radius": "Corners", "box-shadow": "Shadow",
  "font-size": "Text size", "line-height": "Line height", "letter-spacing": "Letter spacing",
  "width": "Width", "height": "Height", "min-width": "Minimum width", "min-height": "Minimum height",
  "max-width": "Maximum width", "max-height": "Maximum height", "border-width": "Border width",
  "margin": "Outer space", "padding": "Space inside", "gap": "Space between",
  "row-gap": "Row spacing", "column-gap": "Column spacing",
  "align-items": "Align", "justify-content": "Distribute", "flex-direction": "Direction",
  "flex-wrap": "Wrapping", "align-self": "Own alignment", "order": "Order",
  "grid-template-columns": "Columns", "grid-template-rows": "Rows", "grid-column": "Column span",
  "grid-row": "Row span", "flex": "Flex", "flex-grow": "Growth", "flex-shrink": "Shrink", "flex-basis": "Width",
  "object-fit": "Fit", "object-position": "Crop position",
};

const styleName = (prop: string) => STYLE_NAME[prop] ?? prop;

export function editOpLabel(op: EditOp, el?: ElementInfo | null): string {
  const what = elementLabel(el);
  if (op.op === "set_text") return `Text of ${what}`;
  if (op.op === "delete") return `Delete ${what}`;
  if (op.op === "reorder") return `Move ${what} to position ${op.index + 1}`;
  if (op.op === "set_src") return `Replace ${what}`;
  // A resize writes width and flex-basis together; they are one change to the reader.
  const props = Object.keys(op.style).filter((p, _, all) =>
    !(["flex-basis", "max-width", "max-height"].includes(p) && all.includes("width")) && !(p === "height" && op.style[p] === "auto"));
  const names = [...new Set(props.map(styleName))];
  const cleared = props.every(p => op.style[p] === "");
  return `${cleared ? "Reset " : ""}${names.join(", ")} on ${what}`;
}

/** Speaker notes allow <b>, <i>, <em>, <strong> only; everything else is escaped. */
export function safeNotesHtml(s: string): string {
  const esc = s.replace(/&(?!(amp|lt|gt|quot|#\d+);)/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return esc.replace(/&lt;(\/?)(b|i|em|strong)&gt;/g, "<$1$2>");
}

/* --------------------------------------------------------- the fact ledger
 * What the slide is required to say, and what the render actually said. The
 * required list comes from the slide; what became of each fact is derived from
 * the version's findings, because QA reports per fact only in its messages. */

/** Fidelity failures the repair loop is not allowed to give up on. */
export function qaFatal(v?: Version | null): string[] {
  const f = v?.qa?.fatal;
  return Array.isArray(f) ? f.filter((x): x is string => typeof x === "string") : [];
}

/** Every fidelity finding on a version, most severe first. */
export function fidelityFindings(v?: Version | null): Finding[] {
  const rank = (f: Finding) => (f.fatal ? 0 : f.severity === "error" ? 1 : 2);
  return qaFindings(v).filter(f => f.code.startsWith("fidelity")).sort((a, b) => rank(a) - rank(b));
}

/** True when this version says something the source does not — the one QA result that blocks a ship. */
export const hasFatalFidelity = (v?: Version | null) => qaFatal(v).length > 0 || qaFindings(v).some(f => f.fatal);

export const keyFacts = (facts: Fact[] | undefined) => (facts ?? []).filter(f => f.tier === "key");

