/**
 * The slide library: types mirroring `backend/app/library/schema.py`, its API calls and its live channel.
 * Change the shapes here and there together.
 */
import { useEffect } from "react";
import { useInfiniteQuery, useQuery, useQueryClient, keepPreviousData, type InfiniteData, type QueryClient } from "@tanstack/react-query";
import { ApiError, type Fact, type Slide, type SlideContent } from "./api";

export type DeckStatus = "ingesting" | "ready" | "error";
export type DeckOrigin = "upload" | "converted" | "generated";
export type AiStatus = "none" | "pending" | "done" | "error";

export interface LibDeck {
  id: string; project: string; title: string; filename: string;
  deck_date: string | null; origin: DeckOrigin; origin_project_id: string;
  /** The older deck this one replaces / the newer deck that replaced this one ("" when none). */
  supersedes_id: string; superseded_by: string;
  status: DeckStatus; stage_note: string; error: string; renderer: string;
  slide_count: number;
  /** Only filled by the list route. */
  favourites: number | null;
  cover: string; created_at: string | null; updated_at: string | null;
}

/** The deck a slide belongs to, as embedded in `slide_out`. */
export interface LibDeckRef {
  id: string; project: string; title: string; origin: DeckOrigin; deck_date: string | null;
  /** The Deck Builder project a converted or generated deck came from ("" or absent for an upload). */
  origin_project_id?: string;
}

export interface LibEntity { name: string; type?: string }

export interface LibSlide {
  id: string; deck_id: string; index: number; title: string; notes: string;
  favourite: boolean; favourited_at: string | null;
  ai_status: AiStatus; ai_error: string;
  summary: string; slide_type: string;
  /** LibTag slugs. */
  tags: string[];
  /** Read through `entityName` — the model's output is normalised server-side, but stay defensive. */
  entities: (LibEntity | string)[];
  /** Tag slugs the model proposed; never applied until the user approves them. */
  suggested: string[];
  /** The user edited these, so a re-tag leaves them alone. */
  tags_user: boolean; summary_user: boolean; slide_type_user: boolean;
  thumb: string; image: string;
  /** The same slide (by render fingerprint) in this many other decks. */
  also_in: number;
  superseded: boolean;
  deck: LibDeckRef | null;
  /** Converted/generated decks: the project slide this one was saved from (absent or "" otherwise). */
  origin_slide_id?: string;
  /** Search only: HTML with <mark> around matched words, everything else escaped server-side. */
  snippet: string;
  /** Search only: found by what it says, not by the words typed (needs an embedding model). */
  by_meaning?: boolean;
  created_at: string | null; updated_at: string | null;
}

/** `GET /slides/{id}`: the slide plus what was parsed out of it. `text` is every word on it, flattened. */
export interface LibSlideDetail extends LibSlide { text: string; content: SlideContent; facts: Fact[] | null }

export interface LibTag { slug: string; label: string; facet: string; aliases: string[]; approved: boolean; count: number }

export interface FacetValue { value: string; label: string; count: number }
export const FACET_KEYS = ["project", "tag", "type", "entity", "deck", "origin"] as const;
export type FacetKey = (typeof FACET_KEYS)[number];

export interface SearchResult {
  total: number; items: LibSlide[]; facets: Partial<Record<FacetKey, FacetValue[]>>;
  /** No slide matched every word, so these match any of them. */
  relaxed?: boolean;
  /** Asked for with `groups`: how many of the result's slides each deck holds — projects A–Z, newest deck first. */
  groups?: SlideGroup[];
}
export interface SlideGroup { project: string; deck: string; count: number }
export interface LibProject { project: string; decks: number; slides: number; favourites: number }
export interface Taxonomy { slide_types: unknown[]; facets: unknown[]; entity_types: unknown[] }
export interface DeckDetail { deck: LibDeck; slides: LibSlide[] }

export type SortKey = "relevance" | "added" | "deck_date" | "project";
export const SORTS: { value: SortKey; label: string }[] = [
  { value: "relevance", label: "Best match" },
  { value: "added", label: "Recently added" },
  { value: "deck_date", label: "Deck date" },
  { value: "project", label: "Project" },
];

/** Everything the search route filters on. One value per facet; more go in the query (`tag:x tag:y`). */
export interface SearchParams {
  q?: string; project?: string; tag?: string; type?: string; entity?: string; deck?: string; origin?: string;
  fav?: boolean; superseded?: boolean; from?: string; to?: string; sort?: SortKey;
}

/* --- knowledge graph (`backend/app/library/graph.py`) and its Obsidian vault (`obsidian.py`) */

export type GraphScope = "favourites" | "all";
export type GraphNodeType = "slide" | "project" | "tag" | "entity";
export const GRAPH_NODE_TYPES: GraphNodeType[] = ["slide", "project", "tag", "entity"];
export type GraphEdgeType = "in" | "tagged" | "mentions";

/** What a slide node carries. Read defensively: everything but the node id is optional. */
export interface GraphSlideData {
  slide_id?: string; deck_id?: string;
  /** The deck's title, or its ref. */
  deck?: string | Partial<LibDeckRef> | null;
  deck_title?: string; deck_date?: string | null; project?: string;
  thumb?: string; image?: string; summary?: string; slide_type?: string; favourite?: boolean;
  /** Position in its deck, and the number it had in the source PowerPoint. */
  index?: number; number?: number;
}
/**
 * Project: `{project, decks}` (`p:` with project "" is "No project"). Tag: `{slug, facet, slides}`.
 * Entity: `{key, name, type, slides}` — `name` is what the search's entity filter takes.
 */
export interface GraphHubData { slug?: string; facet?: string; key?: string; name?: string; type?: string; project?: string; decks?: number; slides?: number }

export interface GraphNode {
  /** `s:<slide id>`, `p:<project>`, `t:<tag slug>`, `e:<entity key>`. */
  id: string; type: GraphNodeType; label: string; degree: number;
  data?: GraphSlideData & GraphHubData;
}
export interface GraphEdge { source: string; target: string; type: GraphEdgeType }
export interface LibGraph {
  nodes: GraphNode[]; edges: GraphEdge[];
  stats: { slides: number; projects: number; tags: number; entities: number };
}
export interface GraphParams {
  scope: GraphScope; project?: string;
  /** Tag and entity nodes linked to fewer slides than this are dropped. */
  min_shared?: number;
}
export const DEFAULT_MIN_SHARED = 2;

/** The part of a node id after its `x:` prefix (a slide id, project name, tag slug or entity key). */
export const graphKey = (id: string) => id.replace(/^[spte]:/, "");

export interface ObsidianStatus {
  configured: boolean; vault_dir: string | null; exists: boolean;
  /** The folder already holds an Obsidian vault (has `.obsidian/`). */
  is_vault: boolean; last_sync: string | null;
}
export interface ObsidianSyncResult { written: number; unchanged: number; removed: number; folder: string; open_uri: string }

const graphQuery = (p: GraphParams) => searchQuery({ scope: p.scope, project: p.project, min_shared: p.min_shared });

export type ExportMode = "original" | "picture";
/** Mirrors the export route's cap (a 400 above it). */
export const MAX_EXPORT = 300;

/** The 409 body for a file already in the library. */
export interface DuplicateDetail { code: "duplicate"; deck_id: string; message: string }

export function duplicateOf(e: unknown): DuplicateDetail | null {
  if (!(e instanceof ApiError) || e.status !== 409 || !e.detail || typeof e.detail !== "object") return null;
  const d = e.detail as Partial<DuplicateDetail>;
  return d.code === "duplicate" && typeof d.deck_id === "string" ? { code: "duplicate", deck_id: d.deck_id, message: d.message ?? "" } : null;
}

/** Which of a project's two library decks: its PowerPoint ("source") or its approved designs ("generated"). */
export type LinkKind = "source" | "generated";

/** `GET /project-links/{pid}`: a project's library decks, and which of its slides are favourited there. */
export interface LinkedDeck {
  deck_id: string; status: DeckStatus;
  /** Project slide id → library slide id, favourited ones only — per kind: one slide can be starred as its
   * PowerPoint original (Plan) and as its design (Review), and the two are different library slides. */
  favourites: Record<string, string>;
  /** Project slide ids whose favourite waits for the deck to finish saving. */
  pending: string[];
}
export interface ProjectLinks {
  source: LinkedDeck | null;
  generated: (LinkedDeck & {
    /** Approved since the library copy was saved: the copy shows an older design. */
    stale_slide_ids: string[];
    /** Approved slides the library copy does not have at all. */
    missing_slide_ids: string[];
  }) | null;
  /** Both kinds merged — don't use it to draw a star; read `links[kind].favourites`. */
  favourites: Record<string, string>;
}

/** `POST /project-favourite`. `pending`: the library deck is still being saved; the favourite lands when it is in. */
export interface ProjectFavouriteResult { lib_slide_id: string | null; deck_id: string; pending: boolean }

/** Where a library deck is shown on the Library page. */
export const deckHref = (deckId: string) => `/library?deck=${encodeURIComponent(deckId)}`;

export const entityName = (e: LibEntity | string) => (typeof e === "string" ? e : e.name);

/** Taxonomy lists may be plain strings or `{value|slug, label}` objects; both become options. */
export function options(list: unknown[] | undefined): { value: string; label: string }[] {
  return (list ?? []).flatMap(x => {
    if (typeof x === "string") return [{ value: x, label: humanize(x) }];
    if (x && typeof x === "object") {
      const o = x as Record<string, unknown>;
      const value = typeof o.value === "string" ? o.value : typeof o.slug === "string" ? o.slug : typeof o.name === "string" ? o.name : null;
      if (value) return [{ value, label: typeof o.label === "string" ? o.label : humanize(value) }];
    }
    return [];
  });
}

export const humanize = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1).replace(/[-_]+/g, " ") : s);

/* ------------------------------------------------------------------ http */

const rawDetail = (body: unknown): unknown =>
  body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : undefined;

function messageOf(body: unknown, fallback: string): string {
  const d = rawDetail(body);
  if (typeof d === "string") return d;
  if (d && typeof d === "object" && typeof (d as { message?: unknown }).message === "string") return (d as { message: string }).message;
  if (d != null) return JSON.stringify(d);
  return fallback;
}

async function fail(r: Response): Promise<never> {
  let body: unknown;
  try { body = await r.json(); } catch { /* not json */ }
  throw new ApiError(r.status, messageOf(body, r.statusText), rawDetail(body));
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) return fail(r);
  return r.json() as Promise<T>;
}

const json = (method: string, body?: unknown): RequestInit =>
  ({ method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });

const BASE = "/api/library";
export const PAGE_SIZE = 60;

/** Query string from a flat object: empty strings, false and undefined are left out. */
export function searchQuery(p: object): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(p) as [string, unknown][]) {
    if (v === undefined || v === "" || v === false) continue;  // superseded=false and fav=false are the defaults
    u.set(k, String(v));
  }
  return u.toString();
}

/** POST a multipart form with upload progress (fetch has none). Rejects with ApiError, keeping a structured detail. */
function sendForm<T>(path: string, fd: FormData, onProgress?: (pct: number) => void): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", path);
    x.upload.onprogress = e => { if (e.lengthComputable) onProgress?.(Math.round((e.loaded / e.total) * 100)); };
    x.onload = () => {
      let body: unknown = null;
      try { body = JSON.parse(x.responseText); } catch { /* not json */ }
      if (x.status >= 200 && x.status < 300) resolve(body as T);
      else reject(new ApiError(x.status, messageOf(body, "Upload failed"), rawDetail(body)));
    };
    x.onerror = () => reject(new ApiError(0, "Can't reach the Deck Builder server. Is it running?"));
    x.send(fd);
  });
}

/** `filename*=UTF-8''…` (RFC 5987) first, then a plain `filename="…"`. */
function filenameOf(r: Response, fallback: string): string {
  const cd = r.headers.get("Content-Disposition") ?? "";
  const star = /filename\*=(?:UTF-8|utf-8)''([^;]+)/.exec(cd);
  if (star?.[1]) { try { return decodeURIComponent(star[1].trim()); } catch { /* malformed */ } }
  const plain = /filename="?([^";]+)"?/.exec(cd);
  return plain?.[1]?.trim() || fallback;
}

/** `X-Export-Fallback` / `X-Export-Skipped`: comma-separated slide ids (a JSON array is accepted too). */
function listHeader(v: string | null): string[] {
  if (!v) return [];
  try {
    const j: unknown = JSON.parse(v);
    if (Array.isArray(j)) return j.map(String);
  } catch { /* not json */ }
  return v.split(",").map(s => s.trim()).filter(Boolean);
}

export interface UploadOptions { project: string; title?: string; supersedes?: string; force?: boolean }

export const libApi = {
  search: (p: SearchParams & { limit?: number; offset?: number; dupes?: boolean; groups?: boolean }, signal?: AbortSignal) =>
    req<SearchResult>(`${BASE}/search?${searchQuery(p)}`, { signal }),
  decks: () => req<LibDeck[]>(`${BASE}/decks`),
  deck: (id: string) => req<DeckDetail>(`${BASE}/decks/${id}`),
  patchDeck: (id: string, body: { project?: string; title?: string; deck_date?: string }) =>
    req<LibDeck>(`${BASE}/decks/${id}`, json("PATCH", body)),
  deleteDeck: (id: string) => req<unknown>(`${BASE}/decks/${id}`, { method: "DELETE" }),
  /** Re-import a deck in status "error" from its stored source (400 for a generated deck). */
  retryDeck: (id: string) => req<LibDeck>(`${BASE}/decks/${id}/retry`, json("POST")),
  /** Put a Deck Builder project into the library: its source slides, or its approved designs. Same 409 as an upload. */
  fromProject: (projectId: string, body: { kind: "source" | "generated"; project?: string; title?: string; supersedes?: string; force?: boolean }) =>
    req<LibDeck>(`${BASE}/from-project/${projectId}`, json("POST", body)),
  projects: () => req<LibProject[]>(`${BASE}/projects`),
  projectLinks: (projectId: string) => req<ProjectLinks>(`${BASE}/project-links/${projectId}`),
  /** Star a project slide: saves its deck to the library first if needed (backend `library/reuse.py`). */
  projectFavourite: (body: { slide_id: string; kind: LinkKind; favourite: boolean }) =>
    req<ProjectFavouriteResult>(`${BASE}/project-favourite`, json("POST", body)),
  /** Library slides become slides of this deck, in this order, after `after` (a position; null = the end). */
  insertFromLibrary: (projectId: string, libSlideIds: string[], after: number | null) =>
    req<{ slides: Slide[] }>(`${BASE}/insert/${projectId}`, json("POST", { lib_slide_ids: libSlideIds, after })),
  uploadDeck: (file: File, o: UploadOptions, onProgress?: (pct: number) => void) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("project", o.project);
    if (o.title) fd.append("title", o.title);
    if (o.supersedes) fd.append("supersedes", o.supersedes);
    if (o.force) fd.append("force", "true");
    return sendForm<LibDeck>(`${BASE}/decks`, fd, onProgress);
  },
  slide: (id: string) => req<LibSlideDetail>(`${BASE}/slides/${id}`),
  /** Setting tags/summary/slide_type locks it against re-tags; `summary: ""` unlocks the summary again. */
  patchSlide: (id: string, body: { favourite?: boolean; tags?: string[]; summary?: string; slide_type?: string }) =>
    req<LibSlide>(`${BASE}/slides/${id}`, json("PATCH", body)),
  bulk: (body: { slide_ids: string[]; favourite?: boolean; add_tags?: string[]; remove_tags?: string[] }) =>
    req<{ updated: number }>(`${BASE}/slides/bulk`, json("POST", body)),
  retag: (id: string) => req<unknown>(`${BASE}/slides/${id}/retag`, json("POST")),
  tagAll: (deckId: string) => req<unknown>(`${BASE}/decks/${deckId}/tag-all`, json("POST")),
  tags: () => req<LibTag[]>(`${BASE}/tags`),
  createTag: (label: string, facet = "topic") => req<LibTag>(`${BASE}/tags`, json("POST", { label, facet })),
  patchTag: (slug: string, body: { label?: string; facet?: string; aliases?: string[] }) =>
    req<LibTag>(`${BASE}/tags/${encodeURIComponent(slug)}`, json("PATCH", body)),
  mergeTags: (from: string[], into: string) => req<unknown>(`${BASE}/tags/merge`, json("POST", { from, into })),
  approveTag: (slug: string) => req<unknown>(`${BASE}/tags/${encodeURIComponent(slug)}/approve`, json("POST")),
  deleteTag: (slug: string) => req<unknown>(`${BASE}/tags/${encodeURIComponent(slug)}`, { method: "DELETE" }),
  taxonomy: () => req<Taxonomy>(`${BASE}/taxonomy`),
  /** The server builds the file; this fetches it as a blob so an error reads as a message, not a page of JSON. */
  exportPptx: async (slideIds: string[], mode: ExportMode) => {
    const r = await fetch(`${BASE}/export.pptx`, json("POST", { slide_ids: slideIds, mode }));
    if (!r.ok) return fail(r);
    return {
      blob: await r.blob(),
      filename: filenameOf(r, mode === "original" ? "library-slides.pptx" : "library-pictures.pptx"),
      /** The mode the server actually built. */
      mode: (r.headers.get("X-Export-Mode") as ExportMode | null) ?? mode,
      /** Originals were asked for, but these came out as pictures. */
      fallback: listHeader(r.headers.get("X-Export-Fallback")),
      /** No source and no render: left out of the file. */
      skipped: listHeader(r.headers.get("X-Export-Skipped")),
      /** Originals from a deck of another slide size, fitted (scaled and centred) onto this file's page. */
      resized: listHeader(r.headers.get("X-Export-Resized")),
    };
  },
  restore: (file: File, onProgress?: (pct: number) => void) => {
    const fd = new FormData();
    fd.append("file", file);
    return sendForm<unknown>(`${BASE}/restore`, fd, onProgress);
  },
  graph: (p: GraphParams, signal?: AbortSignal) => req<LibGraph>(`${BASE}/graph?${graphQuery(p)}`, { signal }),
  obsidianStatus: () => req<ObsidianStatus>(`${BASE}/obsidian/status`),
  /** Writes into `<OBSIDIAN_VAULT_DIR>/HP Slide Library/` only; 400 when that is not configured or missing. */
  obsidianSync: (p: GraphParams) =>
    req<ObsidianSyncResult>(`${BASE}/obsidian/sync`, json("POST", { scope: p.scope, project: p.project || null, min_shared: p.min_shared ?? DEFAULT_MIN_SHARED })),
};

export const libUrls = {
  backup: `${BASE}/backup`,
  /** A zip that is a vault: unzip it and use Obsidian's "Open folder as vault". */
  obsidianZip: (p: GraphParams) => `${BASE}/obsidian.zip?${graphQuery(p)}`,
};

/** Save a blob under a name. Firefox only downloads from an anchor that is in the document. */
export function saveBlob(blob: Blob, name: string) {
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  a.rel = "noopener";
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(href), 60_000);
}

/* ------------------------------------------------------------------ queries */

export const libKeys = {
  all: ["library"] as const,
  search: (p: SearchParams) => ["library", "search", p] as const,
  searchAll: ["library", "search"] as const,
  /** The grouped view's outline and its per-deck pages: under `searchAll`, so whatever refreshes a search refreshes them. */
  groups: (p: SearchParams) => ["library", "search", "groups", p] as const,
  deckPage: (p: SearchParams, deck: string, offset: number) => ["library", "search", "deck", p, deck, offset] as const,
  favs: ["library", "favs"] as const,
  decks: ["library", "decks"] as const,
  deck: (id: string) => ["library", "deck", id] as const,
  projects: ["library", "projects"] as const,
  tags: ["library", "tags"] as const,
  taxonomy: ["library", "taxonomy"] as const,
  slide: (id: string) => ["library", "slide", id] as const,
  links: (projectId: string) => ["library", "links", projectId] as const,
  linksAll: ["library", "links"] as const,
  graph: (p: GraphParams) => ["library", "graph", p] as const,
  graphAll: ["library", "graph"] as const,
  obsidian: ["library", "obsidian"] as const,
};

export type SearchPages = InfiniteData<SearchResult, number>;

export function useLibrarySearch(p: SearchParams, enabled = true) {
  return useInfiniteQuery({
    enabled,
    queryKey: libKeys.search(p),
    queryFn: ({ pageParam, signal }) => libApi.search({ ...p, limit: PAGE_SIZE, offset: pageParam }, signal),
    initialPageParam: 0,
    getNextPageParam: (last, all) => {
      const seen = all.reduce((n, pg) => n + pg.items.length, 0);
      return last.items.length > 0 && seen < last.total ? seen : undefined;
    },
    placeholderData: keepPreviousData,
  });
}

/**
 * The grouped view. Every deck is shown whole (`dupes`): a slide that is also in another deck still belongs to
 * this one. The outline is the same search with no slides in it.
 */
export const useLibraryGroups = (p: SearchParams, enabled = true) =>
  useQuery({
    enabled, queryKey: libKeys.groups(p), placeholderData: keepPreviousData,
    queryFn: ({ signal }) => libApi.search({ ...p, sort: "project", dupes: true, groups: true, limit: 0 }, signal),
  });

/** One page of one deck's slides within the search `p`. Its `count` is in the outline, so the pages are known up front. */
export const deckPageQuery = (p: SearchParams, deck: string, offset: number) => ({
  queryKey: libKeys.deckPage(p, deck, offset),
  queryFn: ({ signal }: { signal?: AbortSignal }) => libApi.search({ ...p, deck, sort: "project", dupes: true, limit: PAGE_SIZE, offset }, signal),
});

/** A project's library links. Quiet on failure: the stars and buttons that read it simply don't show. */
export const useProjectLinks = (projectId: string, enabled = true) =>
  useQuery({ queryKey: libKeys.links(projectId), queryFn: () => libApi.projectLinks(projectId), enabled, retry: false, staleTime: 5_000 });

/** The knowledge graph. The previous graph stays up while another scope loads, so the canvas never blanks. */
export const useLibGraph = (p: GraphParams, enabled = true) =>
  useQuery({ queryKey: libKeys.graph(p), queryFn: ({ signal }) => libApi.graph(p, signal), enabled, placeholderData: keepPreviousData, staleTime: 10_000 });

/** Whether an Obsidian vault is set up. Quiet on failure: the sync action then reads as not configured. */
export const useObsidianStatus = () =>
  useQuery({ queryKey: libKeys.obsidian, queryFn: libApi.obsidianStatus, retry: false, staleTime: 30_000 });

export const useLibDecks = () => useQuery({ queryKey: libKeys.decks, queryFn: libApi.decks });
export const useLibProjects = () => useQuery({ queryKey: libKeys.projects, queryFn: libApi.projects });
export const useLibTags = () => useQuery({ queryKey: libKeys.tags, queryFn: libApi.tags, staleTime: 10_000 });
export const useTaxonomy = () => useQuery({ queryKey: libKeys.taxonomy, queryFn: libApi.taxonomy, staleTime: Infinity, retry: false });

/** slug → tag, for showing labels where the API returns slugs. */
export function tagIndex(tags: LibTag[] | undefined): Map<string, LibTag> {
  return new Map((tags ?? []).map(t => [t.slug, t]));
}

/** Apply `fn` to the slides with these ids wherever they are cached: every search page (paged or single), and their detail. */
export function patchSlides(qc: QueryClient, ids: Iterable<string>, fn: (s: LibSlide) => LibSlide) {
  const want = new Set(ids);
  const patch = (pg: SearchResult): SearchResult => ({ ...pg, items: pg.items.map(s => (want.has(s.id) ? fn(s) : s)) });
  qc.setQueriesData<SearchPages | SearchResult>({ queryKey: libKeys.searchAll }, d => d && ("pages" in d ? { ...d, pages: d.pages.map(patch) } : patch(d)));
  qc.setQueryData<SearchResult>(libKeys.favs, d => d && patch(d));
  for (const id of want) qc.setQueryData<LibSlideDetail>(libKeys.slide(id), d => d && { ...d, ...fn(d) });
}

/**
 * Lay a slide returned by an edit route over the cached copy. Only the fields an edit can change are taken:
 * an edit route's `slide_out` has no search context, so its `deck`, `also_in` and `snippet` would be blanks.
 */
export function mergeEdited(cur: LibSlide, s: LibSlide): LibSlide {
  return {
    ...cur,
    favourite: s.favourite, favourited_at: s.favourited_at, ai_status: s.ai_status, ai_error: s.ai_error,
    summary: s.summary, slide_type: s.slide_type, tags: s.tags, entities: s.entities, suggested: s.suggested,
    tags_user: s.tags_user, summary_user: s.summary_user, slide_type_user: s.slide_type_user,
    thumb: s.thumb ?? cur.thumb, image: s.image ?? cur.image, updated_at: s.updated_at,
  };
}

/* ------------------------------------------------------------------ live events */

type LibraryEvent =
  | { type: "deck"; deck_id: string; status?: DeckStatus; stage_note?: string; error?: string }
  | { type: "slide"; slide_id: string; ai_status?: AiStatus; ai_error?: string }
  | { type: "tags" }
  | { type: "resync"; dropped?: number };

function parseEvent(data: string): LibraryEvent | null {
  try {
    const v: unknown = JSON.parse(data);
    if (v && typeof v === "object" && typeof (v as { type?: unknown }).type === "string") return v as LibraryEvent;
  } catch { /* malformed frame */ }
  return null;
}

/**
 * Subscribe to the library's channel. Deck progress and a slide's tagging status are written straight
 * into the cache so the UI never lags; anything that also changes other fields (a finished ingest, a
 * finished tag run) asks for a debounced refetch, since a tag-all run can send hundreds of events.
 */
export function useLibraryEvents() {
  const qc = useQueryClient();
  useEffect(() => {
    let es: EventSource | null = null;
    let retry: number | undefined;
    const timers = new Map<string, number>();
    const later = (key: string, ms: number, fn: () => void) => {
      window.clearTimeout(timers.get(key));
      timers.set(key, window.setTimeout(fn, ms));
    };
    const refetch = (what: "decks" | "search" | "tags" | "all") => {
      if (what === "decks") later("decks", 400, () => {
        void qc.invalidateQueries({ queryKey: libKeys.decks });
        void qc.invalidateQueries({ queryKey: libKeys.projects });
        void qc.invalidateQueries({ queryKey: libKeys.linksAll });
      });
      if (what === "search") later("search", 1200, () => {
        void qc.invalidateQueries({ queryKey: libKeys.searchAll });
        void qc.invalidateQueries({ queryKey: libKeys.linksAll });
        void qc.invalidateQueries({ queryKey: libKeys.favs });
        void qc.invalidateQueries({ queryKey: ["library", "slide"] });
        void qc.invalidateQueries({ queryKey: ["library", "deck"] });
      });
      if (what === "tags") later("tags", 800, () => void qc.invalidateQueries({ queryKey: libKeys.tags }));
      if (what === "all") later("all", 300, () => void qc.invalidateQueries({ queryKey: libKeys.all }));
    };
    const onUpdate = (e: MessageEvent<string>) => {
      const ev = parseEvent(e.data);
      if (!ev || ev.type === "resync") { refetch("all"); return; }
      if (ev.type === "deck") {
        qc.setQueryData<LibDeck[]>(libKeys.decks, list => list?.map(d => d.id === ev.deck_id ? {
          ...d, status: ev.status ?? d.status, stage_note: ev.stage_note ?? d.stage_note, error: ev.error ?? d.error,
        } : d));
        refetch("decks");
        if (ev.status === "ready" || ev.status === "error") refetch("search");
        return;
      }
      if (ev.type === "slide") {
        if (ev.ai_status) {
          const status = ev.ai_status;
          patchSlides(qc, [ev.slide_id], s => ({ ...s, ai_status: status, ai_error: ev.ai_error ?? s.ai_error }));
        }
        if (ev.ai_status !== "pending") { refetch("search"); refetch("tags"); }
        return;
      }
      refetch("tags");
      refetch("search");
    };
    let connectedBefore = false;
    const open = () => {
      es = new EventSource(`${BASE}/events`);
      // A reconnection may have missed anything, so catch up once (the first connection has nothing to catch up on).
      es.addEventListener("hello", () => { if (connectedBefore) refetch("all"); connectedBefore = true; });
      es.addEventListener("update", onUpdate);
      es.onerror = () => {
        es?.close();
        retry = window.setTimeout(open, 3000);
      };
    };
    open();
    return () => {
      es?.close();
      window.clearTimeout(retry);
      for (const t of timers.values()) window.clearTimeout(t);
    };
  }, [qc]);
}

/** A library slide's picture by id — for a deck slide inserted from the library, which has no render of its own. */
export const libImage = (libSlideId: string, thumb = false) => `${BASE}/slides/${libSlideId}/image${thumb ? "?thumb=true" : ""}`;
