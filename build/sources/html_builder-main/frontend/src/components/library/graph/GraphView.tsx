import { useQuery } from "@tanstack/react-query";
import { BookOpen, Filter, Focus, Maximize2, Minus, Network, Plus, Search, Star, X } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useState, type KeyboardEvent } from "react";
import {
  DEFAULT_MIN_SHARED, GRAPH_NODE_TYPES, graphKey, libApi, libImage, libKeys, useLibGraph, useLibProjects,
  type GraphNode, type GraphNodeType, type GraphParams, type LibGraph, type LibSlide, type LibTag,
} from "../../../lib/library";
import { useKey } from "../../../lib/hooks";
import { cn } from "../../../lib/util";
import { ErrorBoundary } from "../../ErrorBoundary";
import { Button, Empty, IconButton, Kbd, Spinner } from "../../ui";
import { Lightbox } from "../Lightbox";
import { ObsidianDialog } from "../ObsidianPanel";
import { Thumb } from "../SlideCard";
import { GraphCanvas, type CanvasApi, type Hover } from "./GraphCanvas";
import { buildGraph } from "./model";
import { TYPE_LABEL, TYPE_SINGULAR, useGraphColors, type GraphColors } from "./theme";

/** What "Show these slides" filters the Slides tab by. */
export interface SlideFilter { project?: string; tag?: string; entity?: string }

export interface GraphViewProps {
  params: GraphParams; onParams: (patch: Partial<GraphParams>) => void;
  tags: Map<string, LibTag>;
  onFav: (s: LibSlide) => void; onRetry: (s: LibSlide) => void; onShowDeck: (deckId: string) => void;
  onShowSlides: (f: SlideFilter) => void; onSlidesTab: () => void;
}

const HIDDEN_KEY = "library.graph.hidden";
const MIN_SHARED = [1, 2, 3, 5, 10];

function readHidden(): Set<GraphNodeType> {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(HIDDEN_KEY) ?? "[]");
    return new Set(Array.isArray(v) ? v.filter((x): x is GraphNodeType => GRAPH_NODE_TYPES.includes(x as GraphNodeType)) : []);
  } catch { return new Set(); }
}

const deckTitleOf = (n: GraphNode) => {
  const d = n.data ?? {};
  return d.deck_title || (typeof d.deck === "string" ? d.deck : d.deck?.title) || "";
};
const projectOf = (n: GraphNode) => {
  const d = n.data ?? {};
  return d.project || (typeof d.deck === "object" && d.deck?.project) || "";
};
const slideIdOf = (n: GraphNode) => n.data?.slide_id || graphKey(n.id);

/** A library slide from what the graph knows, for the Lightbox until the slide's full record has loaded. */
function slideStub(n: GraphNode): LibSlide {
  const d = n.data ?? {};
  const id = slideIdOf(n);
  const ref = typeof d.deck === "object" && d.deck ? d.deck : null;
  const deckId = d.deck_id || ref?.id || "";
  return {
    id, deck_id: deckId, index: d.index ?? 0, title: n.label, notes: "",
    favourite: !!d.favourite, favourited_at: null, ai_status: "done", ai_error: "",
    summary: d.summary ?? "", slide_type: d.slide_type ?? "", tags: [], entities: [], suggested: [],
    tags_user: false, summary_user: false, slide_type_user: false,
    thumb: d.thumb || libImage(id, true), image: d.image || libImage(id), also_in: 0, superseded: false,
    deck: deckId ? { id: deckId, project: projectOf(n), title: deckTitleOf(n), origin: ref?.origin ?? "upload", deck_date: d.deck_date ?? ref?.deck_date ?? null } : null,
    snippet: "", created_at: null, updated_at: null,
  };
}

const bySlideOrder = (a: GraphNode, b: GraphNode) =>
  projectOf(a).localeCompare(projectOf(b)) || deckTitleOf(a).localeCompare(deckTitleOf(b))
  || (a.data?.index ?? 0) - (b.data?.index ?? 0) || a.label.localeCompare(b.label);

const count = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`;
const fold = (s: string) => s.toLocaleLowerCase().normalize("NFKD").replace(/\p{M}/gu, "");

/** Node index and adjacency, straight from the API payload (independent of the canvas). */
function useIndex(data: LibGraph | undefined) {
  return useMemo(() => {
    const byId = new Map<string, GraphNode>();
    const adj = new Map<string, string[]>();
    for (const n of data?.nodes ?? []) { byId.set(n.id, n); adj.set(n.id, []); }
    for (const e of data?.edges ?? []) {
      if (!byId.has(e.source) || !byId.has(e.target)) continue;
      adj.get(e.source)?.push(e.target);
      adj.get(e.target)?.push(e.source);
    }
    const slides = (data?.nodes ?? []).filter(n => n.type === "slide").sort(bySlideOrder);
    const counts: Record<GraphNodeType, number> = { slide: 0, project: 0, tag: 0, entity: 0 };
    for (const n of data?.nodes ?? []) counts[n.type]++;
    return { byId, adj, slides, counts };
  }, [data]);
}

export default function GraphView({ params, onParams, tags, onFav, onRetry, onShowDeck, onShowSlides, onSlidesTab }: GraphViewProps) {
  const q = useLibGraph(params);
  const data = q.data;
  const projects = useLibProjects().data ?? [];
  const colors = useGraphColors();
  const { byId, adj, slides, counts } = useIndex(data);
  const built = useMemo(() => (data ? buildGraph(data) : null), [data]);

  const [hidden, setHidden] = useState<Set<GraphNodeType>>(readHidden);
  const [focus, setFocus] = useState<string | null>(null);
  const [hover, setHover] = useState<Hover | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [api, setApi] = useState<CanvasApi | null>(null);
  const [arranging, setArranging] = useState(false);
  const [vaultOpen, setVaultOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [box, setBox] = useState({ w: 0, h: 0 });
  const [frame, setFrame] = useState<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!frame) return;
    const ro = new ResizeObserver(([e]) => { if (e) setBox({ w: e.contentRect.width, h: e.contentRect.height }); });
    ro.observe(frame);
    return () => ro.disconnect();
  }, [frame]);

  // A focus or hover on a node the new data no longer has is dropped.
  const focused = focus && byId.has(focus) ? focus : null;
  const hovered = hover && byId.has(hover.id) ? hover : null;

  const toggleType = (t: GraphNodeType) => setHidden(cur => {
    const next = new Set(cur);
    if (next.has(t)) next.delete(t); else next.add(t);
    try { localStorage.setItem(HIDDEN_KEY, JSON.stringify([...next])); } catch { /* storage unavailable */ }
    return next;
  });

  const neighbourhood = useCallback((id: string) => [id, ...(adj.get(id) ?? [])], [adj]);
  const focusOn = useCallback((id: string) => {
    setFocus(id);
    api?.fit(neighbourhood(id));
  }, [api, neighbourhood]);

  /* --- the Lightbox walks the slides currently in view: a focused hub's, else every slide */
  const walk = useMemo(() => {
    const f = focused ? byId.get(focused) : undefined;
    if (f && f.type !== "slide") return (adj.get(f.id) ?? []).map(id => byId.get(id)).filter((n): n is GraphNode => n?.type === "slide").sort(bySlideOrder);
    return hidden.has("slide") ? [] : slides;
  }, [focused, byId, adj, slides, hidden]);
  const openNode = useCallback((n: GraphNode) => setOpenId(slideIdOf(n)), []);
  // The open slide's full record (shared with the Lightbox's own query) replaces its stub, so nothing it shows is blank.
  const openDetail = useQuery({ queryKey: libKeys.slide(openId ?? ""), queryFn: () => libApi.slide(openId ?? ""), enabled: !!openId });
  const items = useMemo(() => {
    const list = walk.some(n => slideIdOf(n) === openId) ? walk : slides;
    return list.map(n => (slideIdOf(n) === openId && openDetail.data ? openDetail.data : slideStub(n)));
  }, [walk, slides, openId, openDetail.data]);

  const onClickNode = useCallback((id: string) => {
    const n = byId.get(id);
    if (!n) return;
    if (n.type === "slide") openNode(n);
    else focusOn(id);
  }, [byId, openNode, focusOn]);
  const onClickStage = useCallback(() => setFocus(null), []);

  /* --- search */
  const matches = useMemo(() => {
    const t = fold(term.trim());
    if (!t || !data) return [];
    const rank = (n: GraphNode) => {
      const l = fold(n.label);
      const at = l.indexOf(t);
      return at < 0 ? -1 : (at === 0 ? 0 : 1) * 2 + (n.type === "slide" ? 1 : 0);
    };
    return data.nodes.filter(n => !hidden.has(n.type))
      .map(n => ({ n, r: rank(n) })).filter(x => x.r >= 0)
      .sort((a, b) => a.r - b.r || b.n.degree - a.n.degree || a.n.label.localeCompare(b.n.label))
      .map(x => x.n);
  }, [term, data, hidden]);
  const matchSet = useMemo(() => (term.trim() && !focused ? new Set(matches.map(n => n.id)) : null), [term, matches, focused]);

  useKey(e => {
    if (e.key !== "Escape" || openId || vaultOpen) return;
    if (focused) setFocus(null);
    else if (term) setTerm("");
  });

  const onCanvasKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.target !== e.currentTarget || !api) return;
    if (e.key === "+" || e.key === "=") { e.preventDefault(); api.zoomIn(); }
    else if (e.key === "-" || e.key === "_") { e.preventDefault(); api.zoomOut(); }
    else if (e.key === "0") { e.preventDefault(); api.reset(); }
  };

  const projectOptions = projects.filter(p => params.scope === "all" || p.favourites > 0 || p.project === params.project);
  const minShared = params.min_shared ?? DEFAULT_MIN_SHARED;
  const stats = data?.stats;
  const nothing = !!data && data.nodes.length === 0;
  const hoverNode = hovered ? byId.get(hovered.id) : undefined;
  const focusNode = focused ? byId.get(focused) : undefined;

  return (
    <div className="mt-5">
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <div role="radiogroup" aria-label="Which slides" className="flex rounded-lg border border-line bg-surface p-0.5">
          {(["favourites", "all"] as const).map(s => (
            <button key={s} role="radio" aria-checked={params.scope === s} onClick={() => onParams({ scope: s })}
              className={cn("flex h-7 items-center gap-1.5 rounded-md px-3 text-[13px] font-semibold",
                params.scope === s ? "bg-accent-soft text-accent" : "text-muted hover:text-ink")}>
              {s === "favourites" ? <><Star className="size-3.5" />Favourites</> : "All slides"}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-[13px] text-muted">
          <span className="sr-only sm:not-sr-only">Project</span>
          <select value={params.project ?? ""} onChange={e => onParams({ project: e.target.value || undefined })}
            className="h-8 max-w-56 rounded-lg border border-line bg-surface px-2 text-[13px] font-semibold text-ink focus:border-accent focus:outline-none">
            <option value="">All projects</option>
            {projectOptions.map(p => <option key={p.project} value={p.project}>{p.project}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 text-[13px] text-muted">
          Hide tags &amp; mentions on fewer than
          <select value={minShared} onChange={e => onParams({ min_shared: Number(e.target.value) })}
            className="h-8 rounded-lg border border-line bg-surface px-2 text-[13px] font-semibold text-ink focus:border-accent focus:outline-none">
            {MIN_SHARED.map(n => <option key={n} value={n}>{n}</option>)}
          </select>
          slides
        </label>
        <GraphSearch term={term} onTerm={setTerm} matches={matches} disabled={!data || nothing}
          onPick={n => { setTerm(""); focusOn(n.id); }} />
        <div className="ml-auto">
          <Button size="sm" icon={<BookOpen className="size-4" />} onClick={() => setVaultOpen(true)}>Obsidian</Button>
        </div>
      </div>

      <div ref={setFrame} className="relative h-[calc(100dvh-24.5rem)] min-h-[460px] overflow-hidden rounded-xl border border-line bg-surface shadow-card">
        {q.isError && !data ? (
          <div className="flex h-full items-center justify-center">
            <Empty icon={<Network className="size-6" />} title="Couldn't load the graph"
              body={`${q.error.message}. If the server was just updated, restart it with run.ps1.`}
              action={<Button size="sm" onClick={() => void q.refetch()}>Try again</Button>} />
          </div>
        ) : !data ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-[13px] text-muted"><Spinner className="size-5" />Building the graph…</div>
        ) : nothing ? (
          <div className="flex h-full items-center justify-center">
            {params.scope === "favourites" ? (
              <Empty icon={<Star className="size-6" />} title={params.project ? `No favourites in ${params.project} yet` : "No favourites yet"}
                body="The graph links your favourite slides through their projects, tags and what they mention. Star slides you'd reuse — or map the whole library now."
                action={<div className="flex flex-wrap justify-center gap-2">
                  <Button size="sm" variant="primary" onClick={() => onParams({ scope: "all" })}>Map all slides</Button>
                  <Button size="sm" onClick={onSlidesTab}>Go to slides</Button>
                </div>} />
            ) : (
              <Empty icon={<Network className="size-6" />} title={params.project ? `Nothing in ${params.project} to map` : "Nothing to map yet"}
                body="Slides join the graph once they have been tagged. Favourites are tagged automatically; others can be retagged from the slide."
                action={params.project ? <Button size="sm" onClick={() => onParams({ project: undefined })}>All projects</Button> : undefined} />
            )}
          </div>
        ) : built && (
          <>
            <ErrorBoundary resetKey={params.scope + (params.project ?? "")} title="The graph couldn't be drawn">
              <div tabIndex={0} role="application" aria-roledescription="graph" onKeyDown={onCanvasKey}
                aria-label={`Knowledge graph: ${stats ? statsText(stats) : ""}. Use the search box to focus a node; plus and minus zoom, 0 resets.`}
                className={cn("absolute inset-0 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent", hovered ? "cursor-pointer" : "cursor-grab active:cursor-grabbing")}>
                <GraphCanvas graph={built.graph} fresh={built.fresh} colors={colors} hidden={hidden} focus={focused} hovered={hovered?.id ?? null}
                  matches={matchSet} onHover={setHover} onClickNode={onClickNode} onClickStage={onClickStage} onApi={setApi} onLayout={setArranging} />
              </div>
            </ErrorBoundary>

            <Legend colors={colors} counts={counts} hidden={hidden} onToggle={toggleType} />

            <div className="absolute bottom-3 right-3 flex flex-col gap-1 rounded-lg border border-line bg-surface p-0.5 shadow-card" role="group" aria-label="Zoom">
              <IconButton label="Zoom in (+)" onClick={() => api?.zoomIn()}><Plus className="size-4" /></IconButton>
              <IconButton label="Zoom out (−)" onClick={() => api?.zoomOut()}><Minus className="size-4" /></IconButton>
              <IconButton label="Fit the whole graph (0)" onClick={() => { setFocus(null); api?.reset(); }}><Maximize2 className="size-4" /></IconButton>
            </div>

            <div className="pointer-events-none absolute bottom-3 left-3 flex flex-wrap items-center gap-2 text-[12px] text-muted">
              {stats && <span className="rounded-md bg-surface/85 px-2 py-1 font-semibold backdrop-blur" aria-live="polite">{statsText(stats)}</span>}
              {(arranging || q.isPlaceholderData || q.isFetching) && (
                <span className="inline-flex items-center gap-1.5 rounded-md bg-surface/85 px-2 py-1 backdrop-blur"><Spinner className="size-3.5" />{arranging ? "Arranging…" : "Updating…"}</span>
              )}
              <span className="hidden rounded-md bg-surface/85 px-2 py-1 backdrop-blur xl:inline">Scroll to zoom · drag to pan · click a project, tag or mention to focus it</span>
            </div>

            {hoverNode?.type === "slide" && hovered && (
              <HoverCard node={hoverNode} x={hovered.x} y={hovered.y} box={box} />
            )}
            {focusNode && (
              <FocusPanel node={focusNode} adj={adj} byId={byId}
                onClose={() => setFocus(null)} onFocus={focusOn} onOpen={openNode} onShowSlides={onShowSlides} />
            )}
          </>
        )}
      </div>

      <Lightbox items={items} openId={openId} onOpenId={setOpenId} tags={tags} onFav={onFav} onRetry={onRetry}
        onShowDeck={onShowDeck} hasMore={false} onMore={noop} />
      <ObsidianDialog open={vaultOpen} onOpenChange={setVaultOpen} params={params} />
    </div>
  );
}

const noop = () => {};

function statsText(s: LibGraph["stats"]): string {
  return [count(s.slides, "slide"), count(s.projects, "project"), count(s.tags, "tag"), count(s.entities, "mention")].join(" · ");
}

/** The legend is also the filter: each entry shows or hides its kind of node. */
function Legend({ colors, counts, hidden, onToggle }: {
  colors: GraphColors; counts: Record<GraphNodeType, number>; hidden: ReadonlySet<GraphNodeType>; onToggle: (t: GraphNodeType) => void;
}) {
  return (
    <div role="group" aria-label="Show or hide node types" className="absolute left-3 top-3 flex flex-col gap-0.5 rounded-lg border border-line bg-surface/95 p-1 shadow-card backdrop-blur">
      {(["project", "tag", "entity", "slide"] as const).map(t => {
        const on = !hidden.has(t);
        return (
          <button key={t} aria-pressed={on} onClick={() => onToggle(t)} title={on ? `Hide ${TYPE_LABEL[t].toLowerCase()}` : `Show ${TYPE_LABEL[t].toLowerCase()}`}
            className={cn("flex h-7 items-center gap-2 rounded-md px-2 text-[12.5px] font-semibold hover:bg-surface-2", on ? "text-ink" : "text-faint")}>
            <span aria-hidden className={cn("rounded-full", t === "slide" ? "size-2" : t === "project" ? "size-3.5" : "size-2.5")}
              style={on ? { background: colors.node[t] } : { boxShadow: `inset 0 0 0 1.5px ${colors.node[t]}` }} />
            <span className={cn("flex-1 text-left", !on && "line-through")}>{TYPE_LABEL[t]}</span>
            <span className="pl-2 text-[11px] tabular-nums text-muted">{counts[t].toLocaleString()}</span>
          </button>
        );
      })}
    </div>
  );
}

function HoverCard({ node, x, y, box }: { node: GraphNode; x: number; y: number; box: { w: number; h: number } }) {
  const W = 240, H = 200;
  const left = x + 16 + W > box.w ? Math.max(8, x - 16 - W) : x + 16;
  const top = Math.max(8, Math.min(y + 16, box.h - H - 8));
  const deck = deckTitleOf(node), project = projectOf(node);
  return (
    <div className="pointer-events-none absolute z-10 w-60 overflow-hidden rounded-lg border border-line bg-surface shadow-card" style={{ left, top }}>
      <Thumb src={node.data?.thumb || libImage(slideIdOf(node), true)} />
      <div className="px-3 py-2">
        <div className="line-clamp-2 text-[13px] font-semibold leading-snug">{node.label || "Untitled slide"}</div>
        <div className="mt-0.5 flex items-center gap-1 truncate text-[11.5px] text-muted">
          {node.data?.favourite && <Star className="size-3 shrink-0 fill-current text-warn" />}
          <span className="truncate">{[deck, project].filter(Boolean).join(" · ") || "Library slide"}</span>
        </div>
      </div>
    </div>
  );
}

/** A focused node, as a panel: what it is, what it links to — the keyboard's way into the graph. */
function FocusPanel({ node, adj, byId, onClose, onFocus, onOpen, onShowSlides }: {
  node: GraphNode; adj: Map<string, string[]>; byId: Map<string, GraphNode>;
  onClose: () => void; onFocus: (id: string) => void; onOpen: (n: GraphNode) => void; onShowSlides: (f: SlideFilter) => void;
}) {
  const near = (adj.get(node.id) ?? []).map(id => byId.get(id)).filter((n): n is GraphNode => !!n);
  const slides = near.filter(n => n.type === "slide").sort(bySlideOrder);
  const hubs = near.filter(n => n.type !== "slide").sort((a, b) => b.degree - a.degree || a.label.localeCompare(b.label));
  // "No project" (id `p:`) has nothing the Slides filters can name, so it gets no button.
  const filter: SlideFilter | null = node.type === "project" ? (graphKey(node.id) ? { project: node.data?.project || graphKey(node.id) } : null)
    : node.type === "tag" ? { tag: node.data?.slug || graphKey(node.id) }
      : node.type === "entity" ? { entity: node.data?.name || node.label } : null;
  const titleId = useId();
  return (
    <aside aria-labelledby={titleId} className="absolute right-3 top-3 flex max-h-[calc(100%-1.5rem)] w-72 flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-card">
      <div className="flex items-start gap-2 border-b border-line-2 px-3.5 py-3">
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-bold uppercase tracking-wider text-muted">
            {TYPE_SINGULAR[node.type]}{node.type === "entity" && node.data?.type ? ` · ${node.data.type}` : ""}{node.type === "tag" && node.data?.facet ? ` · ${node.data.facet}` : ""}
          </div>
          <h3 id={titleId} className="mt-0.5 line-clamp-2 text-[15px] font-bold leading-snug">{node.label || "Untitled"}</h3>
        </div>
        <IconButton label="Clear focus (Esc)" onClick={onClose}><X className="size-4" /></IconButton>
      </div>
      <div className="min-h-0 flex-1 overflow-auto px-3.5 py-3 scroll-thin">
        {node.type === "slide" ? (
          <>
            <button onClick={() => onOpen(node)} className="block w-full overflow-hidden rounded-md ring-1 ring-line-2 hover:ring-accent" aria-label={`Open ${node.label}`}>
              <Thumb src={node.data?.thumb || libImage(slideIdOf(node), true)} />
            </button>
            <p className="mt-2 text-[12.5px] text-muted">{[deckTitleOf(node), projectOf(node)].filter(Boolean).join(" · ")}</p>
            {node.data?.summary && <p className="mt-1.5 text-[13px] leading-relaxed">{node.data.summary}</p>}
            <Button size="sm" variant="primary" className="mt-3 w-full" onClick={() => onOpen(node)}>Open slide</Button>
          </>
        ) : (
          <>
            <div className="mb-1.5 text-[12px] font-semibold text-muted">{count(slides.length, "slide")}</div>
            <ul className="space-y-0.5">
              {slides.map(s => (
                <li key={s.id}>
                  <button onClick={() => onOpen(s)} className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-[13px] hover:bg-surface-2">
                    <Thumb src={s.data?.thumb || libImage(slideIdOf(s), true)} className="w-14 shrink-0 rounded-sm" />
                    <span className="min-w-0 flex-1">
                      <span className="line-clamp-2 leading-snug">{s.label || "Untitled slide"}</span>
                      {node.type !== "project" && projectOf(s) && <span className="block truncate text-[11px] text-muted">{projectOf(s)}</span>}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
        {hubs.length > 0 && (
          <div className="mt-3">
            <div className="mb-1.5 text-[12px] font-semibold text-muted">{node.type === "slide" ? "Linked to" : "Also linked"}</div>
            <div className="flex flex-wrap gap-1">
              {hubs.slice(0, 30).map(h => (
                <button key={h.id} onClick={() => onFocus(h.id)}
                  className="inline-flex h-6 items-center gap-1 rounded-full bg-surface-2 px-2 text-[12px] font-semibold ring-1 ring-line-2 hover:ring-accent">
                  <Focus className="size-3 text-muted" />{h.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
      {filter && slides.length > 0 && (
        <div className="border-t border-line-2 p-2.5">
          <Button size="sm" className="w-full" icon={<Filter className="size-3.5" />} onClick={() => onShowSlides(filter)}>Show these slides</Button>
        </div>
      )}
    </aside>
  );
}

/** Type to light up matching nodes; pick one (Enter, or click) to focus it. */
function GraphSearch({ term, onTerm, matches, onPick, disabled }: {
  term: string; onTerm: (t: string) => void; matches: GraphNode[]; onPick: (n: GraphNode) => void; disabled: boolean;
}) {
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const listId = useId();
  const shown = matches.slice(0, 8);
  const cur = Math.min(active, Math.max(0, shown.length - 1));
  const expanded = open && !!term.trim();
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive(Math.min(cur + 1, shown.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(Math.max(cur - 1, 0)); }
    else if (e.key === "Enter") { const n = shown[cur]; if (n) { e.preventDefault(); onPick(n); setOpen(false); } }
    else if (e.key === "Escape") { if (term) { e.preventDefault(); e.stopPropagation(); onTerm(""); } }
  };
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
      <input type="search" value={term} disabled={disabled} placeholder="Find a node…" aria-label="Find a node in the graph"
        role="combobox" aria-expanded={expanded} aria-controls={listId} aria-autocomplete="list"
        aria-activedescendant={expanded && shown[cur] ? `${listId}-${cur}` : undefined}
        onChange={e => { onTerm(e.target.value); setActive(0); setOpen(true); }} onKeyDown={onKey}
        onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
        className="h-8 w-56 rounded-lg border border-line bg-surface pl-8 pr-2 text-[13px] text-ink placeholder:text-faint focus:border-accent focus:outline-none disabled:opacity-50" />
      {expanded && (
        <ul id={listId} role="listbox" aria-label="Matching nodes"
          className="absolute left-0 top-full z-20 mt-1 w-80 overflow-hidden rounded-xl border border-line bg-surface p-1 shadow-card">
          {shown.length === 0 && <li className="px-2.5 py-2 text-[13px] text-muted">No node matches “{term.trim()}”</li>}
          {shown.map((n, i) => (
            <li key={n.id} id={`${listId}-${i}`} role="option" aria-selected={i === cur}
              onMouseDown={e => { e.preventDefault(); onPick(n); setOpen(false); }} onMouseEnter={() => setActive(i)}
              className={cn("flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13px]", i === cur && "bg-surface-2")}>
              <span className="min-w-0 flex-1 truncate">{n.label || graphKey(n.id)}</span>
              <span className="shrink-0 text-[11px] font-semibold text-muted">{TYPE_SINGULAR[n.type]}</span>
            </li>
          ))}
          {matches.length > shown.length && <li className="px-2.5 pb-1 pt-1.5 text-[11px] text-faint">{matches.length - shown.length} more — keep typing</li>}
          <li className="border-t border-line-2 px-2.5 pb-0.5 pt-1.5 text-[11px] text-faint"><Kbd>↑</Kbd> <Kbd>↓</Kbd> choose · <Kbd>Enter</Kbd> focus</li>
        </ul>
      )}
    </div>
  );
}
