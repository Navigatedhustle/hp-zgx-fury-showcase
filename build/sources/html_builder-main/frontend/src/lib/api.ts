export type ProjectStatus = "uploaded" | "composing" | "ingesting" | "planning" | "ready" | "generating" | "reviewing" | "complete" | "error";
export type SlideStatus = "pending" | "generating" | "review" | "revising" | "approved" | "error";
export type VersionStatus = "queued" | "generating" | "qa" | "repairing" | "ready" | "failed" | "cancelled";
export type Lineage = "A" | "B";

export interface Finding {
  severity: "error" | "warn"; code: string; message: string;
  /** The slide asserts something the source does not. Never shippable, however good the layout. */
  fatal?: boolean;
}

/** One checkable assertion from the source slide. Mirrors `backend/app/facts.py::Fact`. */
export interface Fact {
  id: string;
  kind: "number" | "name";
  /** As the source wrote it: "$4.2M", "40%", "Z8 Fury G5". */
  raw: string;
  label: string;
  origin: "title" | "text" | "table" | "chart" | "notes" | "llm" | "doc";
  /** `key` facts must be visible on the slide; `supporting` ones may live in the speaker notes. */
  tier: "key" | "supporting";
  value?: number | null;
  unit?: string;
  unit_raw?: string;
}
export interface CriticIssue { severity: "high" | "medium" | "low"; area: string; problem: string; fix: string }
export interface Critic { scores?: Record<string, number> | null; issues?: CriticIssue[] | null; verdict?: string }

/**
 * The model's pairwise A-vs-B judgement, written onto both versions of a slide.
 * Advice, never a gate: `recommended` says the judge preferred *this* version.
 * Only `status: "ok"` carries a real verdict.
 */
export interface AbVerdict {
  status?: "ok" | "skipped" | "failed" | string;
  winner?: Lineage | "tie" | "";
  recommended?: boolean;
  confidence?: number | null;
  reason?: string;
  order?: "AB" | "BA" | string;
  versions?: Partial<Record<Lineage, string>>;
  note?: string;
  error?: string;
}

/** Best-of-n sampling for variant A: n drafts DOM-checked, the cleanest kept. Off by default. */
export interface BestOfDraft { draft: number; errors: number; warns: number; note?: string }
export interface BestOf {
  n?: number; requested?: number; returned?: number; picked?: number; clean?: number; drafts?: BestOfDraft[] | null;
}

/**
 * The QA payload grows on the backend independently of this client, so every
 * member is optional and unknown keys are allowed. Read it through the
 * `qa*` helpers in `lib/util`, never by reaching into nested fields directly.
 *
 * The slim project payload sends only the summary members (see `SlimProject`);
 * the rest arrive with the full one and are preserved across a slim refetch.
 */
export interface QaReport {
  passed?: boolean | null;
  findings?: Finding[] | null;
  critic?: Critic | null;
  iterations?: { attempt: number; score: number; errors: number }[] | null;
  vision?: boolean;
  /** "failed" means the critique never ran — the score is a conservative floor, not a verdict. */
  critic_status?: CriticStatus | null;
  critic_error?: string;
  critic_warning?: string;
  critic_skipped_reason?: string;
  ab?: AbVerdict | null;
  best_of?: BestOf | null;
  /** Fidelity failures no repair may shrug off: a value the slide changed from the source. */
  fatal?: string[] | null;
  [key: string]: unknown;
}

export type CriticStatus = "ok" | "skipped" | "failed";

/** How a version came to exist: `edit` is a batch of direct-manipulation ops, no model involved. */
export type VersionOrigin = "llm" | "edit";

export interface Version {
  id: string; slide_id: string; lineage: Lineage; number: number; parent_id: string | null; comment: string;
  origin: VersionOrigin;
  status: VersionStatus; stage_note: string; score: number | null; repairs: number; error: string;
  title: string; steps: number | null; notes: string[];
  qa?: QaReport | null;
  llm?: { calls?: number; prompt_tokens?: number; completion_tokens?: number; seconds?: number } | null;
  created_at: string; updated_at: string;
}

export interface SlidePlan {
  index?: number; role?: string; pattern?: string; eyebrow?: string; headline?: string; key_message?: string;
  idea_a?: string; idea_b?: string; theme?: string; include?: boolean;
  /** The planner's suggestion: source indexes this thin slide could share a slide with. Never applied automatically. */
  merge_with?: number[];
  /* Written by the user's slide management (backend/app/pipeline/deckops.py), and kept across a re-plan. */
  added?: boolean;                     // added by the user to a converted deck
  removed?: "deleted" | "merged";      // out of the deck; restorable
  merged_from?: string[]; merged_into?: string; merged_labels?: string[];
  no_split?: boolean;                  // the user undid a split, or merged: planned as one slide
  appendix?: boolean;                  // a backup slide after the main deck (condense)
  doc_sources?: string[];              // reference documents this slide's figures come from
  /** Inserted from the slide library (backend `library/reuse.py`): where its content and figures came from. */
  library_source?: { lib_slide_id: string; deck_id: string; project?: string; deck_title?: string; index?: number; label?: string };
}

/** One block of body copy, exactly as the model receives it: `lines` carries `  ` per indent level and `**bold**`. */
export interface ContentBlock { kind: string; position?: string; lines: string[] }

/** The slide's extracted content. Grows on the backend, so read it defensively. */
export interface SlideContent {
  title?: string;
  text?: ContentBlock[];
  tables?: string[][][];
  charts?: { type?: string; title?: string; categories?: string[]; series?: { name: string; values: (number | null)[] }[] }[];
  images?: { key: string; alt?: string; position?: string; px?: string; source?: "upload" }[];
  speaker_notes?: string;
  [key: string]: unknown;
}

/** A content edit: `blocks` replaces the body blocks of `Slide.content.text`, index for index. */
export interface ContentEdit { title?: string; blocks?: string[] }

/** One correction to the fact ledger. Mirrors `FactPatch` in backend/app/main.py. */
export interface FactPatch { id: string; tier?: "key" | "supporting"; drop?: boolean }

/** Typing into a composed slide. Unset fields are left alone. */
export interface SlideWrite { title?: string; body?: string; notes?: string }

export interface SlidePatchBody {
  included?: boolean; plan?: SlidePlan; content?: ContentEdit; reset_content?: boolean;
  facts?: FactPatch[]; reset_facts?: boolean;
}

export interface Slide {
  id: string; index: number; position: number; included: boolean; status: SlideStatus; error: string;
  approved_version_id: string | null; plan: SlidePlan; source_title: string; word_count: number;
  /** Which part of its source slide this is, and how many parts that slide was split into. */
  part: number; parts: number;
  /** What to call it on screen: "4", or "4a"/"4b" when the source slide was split. */
  label: string;
  /** The facts this slide is required to carry, with their tiers. */
  facts: Fact[];
  facts_edited: boolean;
  has_chart: boolean; has_table: boolean; image_count: number; notes: string; warnings: string[];
  /** Carries too little to earn its own slide (backend `is_thin`): a candidate to merge. */
  thin?: boolean;
  /** The copy generation will use: the parse with the user's edits laid over it. */
  content: SlideContent;
  /** What came out of the PowerPoint. Equal to `content` until the slide is edited. */
  content_original: SlideContent;
  content_edited: boolean;
  versions: Version[];
}

/* --------------------------------------------------------- direct editing
 * Mirrors backend/app/edit.py. Every op the UI offers must be one that module accepts:
 * an op that always 400s is worse than a control that isn't there. */

/** One addressable element, as the server sees it. `locks` explain why something can't be removed. */
export interface ElementInfo {
  eid: string; tag: string; classes: string[]; parent: string | null; index: number; depth: number;
  text: string; has_children: boolean; editable_text: boolean; deletable: boolean; locks: string[];
  /** For an <img>: the deck asset it shows (what "Replace image" swaps). Empty otherwise. */
  asset?: string;
}

export type EditOp =
  | { op: "set_text"; eid: string; text: string; replace_children?: boolean }
  | { op: "delete"; eid: string }
  | { op: "reorder"; eid: string; index: number }
  | { op: "set_style"; eid: string; style: Record<string, string> }
  | { op: "set_src"; eid: string; key: string };

/** One image the deck can use: the PowerPoint's own (`img3`) or the user's upload (`u_…`). */
export interface DeckAsset {
  key: string; upload: boolean; bytes?: number; url: string; width?: number; height?: number;
  /** The reference document this picture was taken from ("" or absent for the PowerPoint's own and uploads). */
  doc?: string;
}

/** A side effect the edit engine flagged (a re-timed reveal, a counter the runtime rewrites). */
export interface EditNote { code: string; message: string; eid: string }

export interface EditResponse {
  ok: boolean; changed: boolean; version: Version; warnings: EditNote[];
  qa_recommended: boolean; qa_reasons: string[];
}

/** The body of a 400 from the edit route: which op was refused and why. */
export interface EditFailure { message: string; error_code: string; failed_index: number | null; op: string; eid: string }

export interface Counts { slides: number; included: number; approved: number; review: number; generating: number; error: number; removed?: number; appendix?: number }

export interface ConsistencyIssue { slide_ids: string[]; kind: string; issue: string; fix: string; source: "code" | "model" }
export interface ReadinessItem { slide_id: string | null; label: string; severity: "block" | "warn"; kind: string; message: string }
export interface Readiness { ready: boolean; blocks: number; warnings: number; items: ReadinessItem[] }

/** One main slide of a condense proposal: kept as is (one id) or combined from several. */
export interface CondenseGroup { ids: string[]; headline?: string; why?: string }
export interface CondenseProposal {
  main: CondenseGroup[]; appendix: string[]; why?: string;
  target: number; guidance?: string; keep?: string[]; source?: "llm" | "fallback" | "offline";
}

/** One quantity two documents give different values for; `use` names the primary document when one is marked. */
export interface DocConflict { label: string; values: { doc: string; value: string }[]; use: string }
/** A document's sections, to choose from before drafting an outline. `ref` is what the outline route takes. */
export interface DocSections {
  doc_id: string; name: string; primary: boolean;
  sections: { ref: string; n: number; title: string; where: string; chars: number; summary: string }[];
}

/** A PDF, Word or text file the planner and generator read as background (backend `app/docs.py`). */
export interface ProjectDoc {
  id: string; name: string; pages: number; chars: number; truncated: boolean;
  status: "digesting" | "ready" | "error"; error: string; digest: string; created_at: string;
  /** Digested in this many sections (0 = read whole); `semantic` = also indexed by an embedding model. */
  sections?: number; semantic?: boolean;
  /** The user's mark: believe this one where documents disagree. `pictures`: figures it added to the deck's images. */
  primary?: boolean; pictures?: number;
}

export interface Project {
  id: string; name: string; filename: string; status: ProjectStatus; stage_note: string; error: string;
  /** "pptx" = converted from a PowerPoint; "composed" = written here. Decides which editor a slide gets. */
  source: "pptx" | "composed";
  deck_title: string; brief: {
    audience?: string; tone?: string; narrative?: string; deck_title?: string; allow_split?: boolean;
    /** A shorter version of the deck awaiting the user's review (backend `deckops.propose_condense`). */
    condense_proposal?: CondenseProposal;
    /** Present after a condense was applied: what "Undo condense" puts back. */
    condense_undo?: { order: string[]; appendix: string[]; created: string[] };
    /** The last consistency review across slides (backend `deckreview.review_consistency`). */
    consistency?: { at: string; issues: ConsistencyIssue[]; note?: string };
  };
  renderer: string; warnings: string[]; created_at: string; updated_at: string; busy: boolean; counts: Counts;
  cover_slide_index: number | null; slides?: Slide[];
  /** True on a payload from `?slim=true`: a subset, only ever laid over a full one. */
  slim?: boolean;
}

/* --------------------------------------------------------- the slim polling payload
 * `GET /api/projects/{id}?slim=true` keeps every field that moves during a generation
 * (statuses, stage notes, scores, counts, the QA summary) and drops the ones that
 * cannot change without the version also changing status: the spec's title and notes,
 * the token ledger, the QA detail, and the parsed PowerPoint copy on each slide.
 *
 * Its keys are a strict subset of the full payload's — enforced by a backend test — which
 * is what lets `mergeSlim` in `lib/hooks` apply it as a plain spread over what is cached. */

export type SlimVersion = Pick<Version,
  "id" | "slide_id" | "lineage" | "number" | "parent_id" | "comment" | "origin" | "status" |
  "stage_note" | "score" | "repairs" | "error" | "created_at" | "updated_at"> & { qa?: QaReport | null };

export type SlimSlide = Pick<Slide,
  "id" | "index" | "position" | "included" | "status" | "error" | "approved_version_id" | "plan" | "source_title">
  & { versions: SlimVersion[] };

export type SlimProject = Omit<Project, "slides"> & { slim: true; slides: SlimSlide[] };

export interface Endpoint {
  ok: boolean; mock: boolean; models: string[]; model: string; base_url: string; role?: string;
  vision: boolean | null; error?: string; max_model_len?: number | null;
}

export interface Health {
  /** The authoring server (plan, generate, repair, revise). */
  llm: Endpoint;
  /** The review server (critic, pairwise A/B, grounding). Equal to `llm` unless `split`. */
  review: Endpoint;
  /** True when review runs on its own vLLM server, so the two are worth reporting separately. */
  split: boolean;
  renderer: string; qa_max_repairs: number;
}

/** One rollup row of the usage ledger (backend/app/usage.py). `costs` is keyed by frontier id, plus `same_size`. */
export interface UsageBucket {

  calls: number; prompt_tokens: number; completion_tokens: number; total_tokens: number;
  images: number; seconds: number; costs: Record<string, number>;
}
export interface CloudPrice { id?: string; name: string; vendor?: string; hf?: string; input: number; cached: number; output: number; source?: string }
export interface Usage {
  unknown_usage_calls?: number;
  as_of: string; days: number | null; mock: boolean;
  endpoints: Record<"author" | "review", { model: string; base_url: string }>;
  frontier: (CloudPrice & { id: string; vendor: string })[];
  same_size: CloudPrice[];
  /** Tokens from a model `pricing.json` has no same-size cloud price for — left out of that comparison. */
  same_size_unpriced_tokens: number;
  totals: UsageBucket & { decks: number; cached_tokens: number; cache_reported: boolean };
  models: (UsageBucket & { model: string; name: string; hf: string; roles: string[]; tok_s: number | null; p50_s: number | null })[];
  stages: (UsageBucket & { stage: string })[];
  decks: (UsageBucket & { project_id: string; title: string; deleted: boolean; last_at: string })[];
  daily: (UsageBucket & { day: string })[];
}

export class ApiError extends Error {
  /** The raw `detail` body, when the route sent a structured one (see `EditFailure`). */
  constructor(public status: number, message: string, public detail?: unknown) { super(message); }
}

/** Mirrors MAX_UPLOAD in backend/app/main.py — checked here so a huge file fails instantly. */
export const MAX_UPLOAD_BYTES = 300 * 1024 * 1024;

const rawDetail = (body: unknown): unknown =>
  body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : undefined;

function detailOf(body: unknown): string | undefined {
  const d = rawDetail(body);
  if (typeof d === "string") return d;
  // A structured detail carries a human sentence under `message`; only fall back to the dump.
  if (d && typeof d === "object" && typeof (d as { message?: unknown }).message === "string") return (d as { message: string }).message;
  if (d != null) return JSON.stringify(d);
  return undefined;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) {
    let msg = r.statusText;
    let detail: unknown;
    try {
      const body: unknown = await r.json();
      msg = detailOf(body) ?? msg;
      detail = rawDetail(body);
    } catch { /* not json */ }
    throw new ApiError(r.status, msg, detail);
  }
  return r.json() as Promise<T>;
}
const json = (method: string, body?: unknown): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  health: () => req<Health>("/api/health"),
  usage: (days?: number) => req<Usage>(`/api/usage${days ? `?days=${days}` : ""}`),
  projects: () => req<Project[]>("/api/projects"),
  project: (id: string) => req<Project>(`/api/projects/${id}`),
  /** The polling variant. Only ever merged onto a full payload — see `SlimProject`. */
  projectSlim: (id: string) => req<SlimProject>(`/api/projects/${id}?slim=true`),
  /** Upload a PowerPoint, with any reference documents to read before the first plan. */
  upload: (file: File, onProgress?: (pct: number) => void, context: File[] = []) =>
    new Promise<Project>((resolve, reject) => {
      const x = new XMLHttpRequest();
      const fd = new FormData();
      fd.append("file", file);
      context.forEach(f => fd.append("context", f));
      x.open("POST", "/api/projects");
      x.upload.onprogress = e => e.lengthComputable && onProgress?.(Math.round((e.loaded / e.total) * 100));
      x.onload = () => {
        let body: unknown = null;
        try { body = JSON.parse(x.responseText); } catch { /* ignore */ }
        if (x.status >= 200 && x.status < 300) resolve(body as Project);
        else reject(new ApiError(x.status, detailOf(body) ?? "Upload failed"));
      };
      x.onerror = () => reject(new ApiError(0, "Can't reach the Deck Builder server. Is it running?"));
      x.send(fd);
    }),
  patchProject: (id: string, body: Partial<Pick<Project, "name" | "deck_title" | "brief">>) => req<Project>(`/api/projects/${id}`, json("PATCH", body)),

  /* --- decks written here rather than converted (backend/app/compose.py) --- */
  createBlank: (name: string, slides = 1) => req<Project>("/api/projects/blank", json("POST", { name, slides })),
  draftOutline: (id: string, body: { about?: string; source_text?: string; slides?: number; sections?: string[]; angle?: string }) =>
    req(`/api/projects/${id}/outline`, json("POST", body)),
  addSlide: (projectId: string, after?: number) => req<Slide>(`/api/projects/${projectId}/slides`, json("POST", { after: after ?? null })),
  /** A converted slide leaves the deck (restorable); a slide made here is really deleted. */
  deleteSlide: (slideId: string) => req(`/api/slides/${slideId}`, { method: "DELETE" }),
  restoreSlide: (slideId: string, after?: number) => req<Slide>(`/api/slides/${slideId}/restore`, json("POST", { after: after ?? null })),
  /** Merge slides into one — or, for the parts of one split slide, undo the split. */
  mergeSlides: (projectId: string, slideIds: string[]) => req<Slide>(`/api/projects/${projectId}/merge`, json("POST", { slide_ids: slideIds })),
  docs: (projectId: string) => req<ProjectDoc[]>(`/api/projects/${projectId}/docs`),
  uploadDoc: (projectId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<ProjectDoc>(`/api/projects/${projectId}/docs`, { method: "POST", body: fd });
  },
  deleteDoc: (docId: string) => req<{ ok: boolean; slides_affected: string[] }>(`/api/docs/${docId}`, { method: "DELETE" }),
  patchDoc: (docId: string, body: { primary: boolean }) => req<ProjectDoc>(`/api/docs/${docId}`, json("PATCH", body)),
  docConflicts: (projectId: string) => req<DocConflict[]>(`/api/projects/${projectId}/docs/conflicts`),
  docSections: (projectId: string) => req<DocSections[]>(`/api/projects/${projectId}/docs/sections`),
  proposeCondense: (projectId: string, body: { target: number; keep: string[]; guidance: string }) =>
    req(`/api/projects/${projectId}/condense/propose`, json("POST", body)),
  applyCondense: (projectId: string, body: { main: CondenseGroup[]; appendix: string[] }) =>
    req<{ ok: boolean; created: string[] }>(`/api/projects/${projectId}/condense/apply`, json("POST", body)),
  undoCondense: (projectId: string) => req(`/api/projects/${projectId}/condense/undo`, json("POST")),
  dismissCondense: (projectId: string) => req(`/api/projects/${projectId}/condense/proposal`, { method: "DELETE" }),
  unmergeSlide: (slideId: string) => req<{ ok: boolean; restored: string[] }>(`/api/slides/${slideId}/unmerge`, json("POST")),
  moveSlide: (slideId: string, to: number) => req(`/api/slides/${slideId}/move`, json("POST", { to })),
  writeSlide: (slideId: string, body: SlideWrite) => req<Slide>(`/api/slides/${slideId}/write`, json("POST", body)),

  deleteProject: (id: string) => req(`/api/projects/${id}`, { method: "DELETE" }),
  replan: (id: string) => req(`/api/projects/${id}/replan`, json("POST")),
  generate: (id: string, slide_ids?: string[]) => req(`/api/projects/${id}/generate`, json("POST", { slide_ids: slide_ids ?? null })),
  cancel: (id: string) => req<{ cancelled: number }>(`/api/projects/${id}/cancel`, json("POST")),
  reorder: (id: string, slide_ids: string[]) => req(`/api/projects/${id}/order`, json("PUT", { slide_ids })),
  patchSlide: (id: string, body: SlidePatchBody) => req(`/api/slides/${id}`, json("PATCH", body)),
  /** Redesign both variants; with reasons, the redesign is told what to fix and what not to repeat. */
  regenerate: (id: string, body?: { reasons: string[]; note: string; pattern: string | null }) =>
    req(`/api/slides/${id}/regenerate`, json("POST", body ?? {})),
  instructDeck: (projectId: string, instruction: string, slideIds: string[] | null) =>
    req<{ ok: boolean; slides: number }>(`/api/projects/${projectId}/instruct`, json("POST", { instruction, slide_ids: slideIds })),
  reviewConsistency: (projectId: string) => req(`/api/projects/${projectId}/consistency`, json("POST")),
  readiness: (projectId: string) => req<Readiness>(`/api/projects/${projectId}/readiness`),
  choose: (slideId: string, versionId: string) => req(`/api/slides/${slideId}/choose`, json("POST", { version_id: versionId })),
  unapprove: (slideId: string) => req(`/api/slides/${slideId}/unapprove`, json("POST")),
  revise: (slideId: string, baseVersionId: string, comment: string, assetKeys: string[] = []) =>
    req(`/api/slides/${slideId}/revise`, json("POST", { base_version_id: baseVersionId, comment, asset_keys: assetKeys })),
  assets: (projectId: string) => req<DeckAsset[]>(`/api/projects/${projectId}/assets`),
  uploadAsset: (projectId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<DeckAsset>(`/api/projects/${projectId}/assets`, { method: "POST", body: fd });
  },
  /** Put an image on a slide's content (or take it off), so the next design or revision lays it out. */
  attachImage: (slideId: string, key: string, detach = false) =>
    req(`/api/slides/${slideId}/images`, json("POST", { key, detach })),
  outline: (versionId: string) => req<{ version_id: string; elements: ElementInfo[] }>(`/api/versions/${versionId}/outline`),
  /** Commit one editing session. Creates a new hand-edited version; throws ApiError(400) with an `EditFailure` detail. */
  editVersion: (versionId: string, ops: EditOp[]) => req<EditResponse>(`/api/versions/${versionId}/edit`, json("POST", { ops })),
  exportStats: (id: string, fill: boolean) => req<{ approved: number; filled: number; skipped: number; bytes: number }>(`/api/projects/${id}/export/stats?fill=${fill}`),
};

/** Out of the deck — deleted or merged into another slide — but still restorable. */
export const isRemoved = (s: Pick<Slide, "plan">) => !!s.plan?.removed;

export const urls = {
  // cover_slide_index is effectively constant, so the cache key is the project's mtime.
  cover: (p: Project) => `/api/projects/${p.id}/cover.jpg?v=${encodeURIComponent(p.updated_at)}`,
  source: (slideId: string, thumb = false) => `/api/slides/${slideId}/source.png${thumb ? "?thumb=true" : ""}`,
  preview: (versionId: string, updatedAt?: string) => `/api/versions/${versionId}/preview?v=${encodeURIComponent(updatedAt || "")}`,
  shot: (versionId: string, name: "shot_0.png" | "shot_final.png", updatedAt?: string) => `/api/versions/${versionId}/shot/${name}?v=${encodeURIComponent(updatedAt || "")}`,
  deck: (projectId: string, fill: boolean, nonce: string) => `/api/projects/${projectId}/deck?fill=${fill}&n=${nonce}`,
  exportHtml: (projectId: string, fill: boolean) => `/api/projects/${projectId}/export.html?fill=${fill}`,
  exportPdf: (projectId: string, fill: boolean) => `/api/projects/${projectId}/export.pdf?fill=${fill}`,
  exportPptx: (projectId: string, fill: boolean, editable = false) => `/api/projects/${projectId}/export.pptx?fill=${fill}${editable ? "&editable=true" : ""}`,
};
