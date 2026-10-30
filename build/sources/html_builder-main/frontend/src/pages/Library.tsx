import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileUp, Filter, Library as LibraryIcon, SearchX, X } from "lucide-react";
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { TopBar } from "../components/AppShell";
import { FACET_LABEL, Facets, facetLabel } from "../components/library/Facets";
import { GroupedSlides } from "../components/library/GroupedSlides";
import { useGrouped, type DeckGroup } from "../components/library/grouped";
import { Lightbox } from "../components/library/Lightbox";
import { LibraryMenu } from "../components/library/LibraryMenu";
import { SearchBar } from "../components/library/SearchBar";
import { SelectionBar } from "../components/library/SelectionBar";
import type { PickMode } from "../components/library/SlideCard";
import { SlideGrid, SlideGridFrame } from "../components/library/SlideGrid";
import { TagManager } from "../components/library/TagManager";
import { UploadDialog } from "../components/library/UploadDialog";
import { ViewControls, useViewSize, type GroupBy } from "../components/library/ViewControls";
import type { GraphViewProps } from "../components/library/graph/GraphView";
import { Button, Empty, Spinner } from "../components/ui";
import { useKey } from "../lib/hooks";
import {
  DEFAULT_MIN_SHARED, FACET_KEYS, libApi, libKeys, mergeEdited, patchSlides, tagIndex, useLibDecks, useLibTags, useLibrarySearch, useLibraryEvents,
  type FacetKey, type GraphParams, type LibDeck, type LibSlide, type SearchParams, type SortKey,
} from "../lib/library";
import { cn } from "../lib/util";

// sigma + graphology are big: only the Graph tab loads them.
const GraphView = lazy(() => import("../components/library/graph/GraphView"));

type Tab = "slides" | "graph";
const TABS: Tab[] = ["slides", "graph"];

/** The Graph tab's own keys (`scope`, `gproject`, `min_shared`), apart from the Slides filters. */
function readGraphParams(sp: URLSearchParams): GraphParams {
  const min = Number(sp.get("min_shared"));
  return {
    scope: sp.get("scope") === "all" ? "all" : "favourites",
    project: sp.get("gproject") || undefined,
    min_shared: Number.isInteger(min) && min >= 1 ? min : DEFAULT_MIN_SHARED,
  };
}

/** Filters live in the URL, so a filtered view can be bookmarked, linked from Home, and survives a reload. */
function readParams(sp: URLSearchParams): SearchParams {
  const p: SearchParams = {};
  const q = sp.get("q");
  if (q) p.q = q;
  for (const k of FACET_KEYS) { const v = sp.get(k); if (v) p[k] = v; }
  if (sp.get("fav") === "true") p.fav = true;
  if (sp.get("superseded") === "true") p.superseded = true;
  const from = sp.get("from"); if (from) p.from = from;
  const to = sp.get("to"); if (to) p.to = to;
  const sort = sp.get("sort") as SortKey | null;
  if (sort) p.sort = sort;
  return p;
}

const hasFilters = (p: SearchParams) => FACET_KEYS.some(k => !!p[k]) || !!p.fav || !!p.superseded || !!p.from || !!p.to;

export default function LibraryPage() {
  useLibraryEvents();
  const qc = useQueryClient();
  const [sp, setSp] = useSearchParams();
  const tab: Tab = TABS.find(t => t === sp.get("view")) ?? "slides";
  const graphParams = useMemo(() => readGraphParams(sp), [sp]);
  const urlParams = useMemo(() => readParams(sp), [sp]);
  // "Best match" needs a query; without one the browse order is newest first.
  const params = useMemo<SearchParams>(() => ({
    ...urlParams,
    sort: urlParams.sort && (urlParams.q || urlParams.sort !== "relevance") ? urlParams.sort : urlParams.q ? "relevance" : "added",
  }), [urlParams]);

  const decks = useLibDecks();
  const tagsQ = useLibTags();
  const tags = useMemo(() => tagIndex(tagsQ.data), [tagsQ.data]);
  // Browsing shows the slides under their project and deck; a search is a ranked list unless grouping is asked for.
  const groupDefault: GroupBy = urlParams.q ? "none" : "project";
  const groupBy: GroupBy = sp.get("group") === "none" ? "none" : sp.get("group") === "project" ? "project" : groupDefault;
  const grouped = tab === "slides" && groupBy === "project";
  const search = useLibrarySearch(params, tab === "slides" && !grouped);
  const g = useGrouped(urlParams, grouped, decks.data);
  const listed = useMemo(() => {
    // Pages can overlap when results move between fetches; keep the first copy of each slide.
    const seen = new Set<string>();
    return (search.data?.pages ?? []).flatMap(pg => pg.items).filter(s => (seen.has(s.id) ? false : (seen.add(s.id), true)));
  }, [search.data]);
  const items = grouped ? g.items : listed;
  const first = grouped ? g.outline.data : search.data?.pages[0];
  const total = first?.total ?? 0;
  const loading = grouped ? g.outline.isLoading || decks.isLoading : search.isLoading;
  const failed = grouped ? g.outline.error ?? decks.error : search.error;
  const hasMore = !grouped && !!search.hasNextPage;

  const [view, setView] = useViewSize();
  const [qInput, setQInput] = useState(urlParams.q ?? "");
  // `?open=<slide id>` (links from Obsidian notes, Home) opens that slide in any view, listed or not; a click sets the state.
  const [pickedId, setOpenId] = useState<string | null>(null);
  const openId = pickedId ?? sp.get("open");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const anchor = useRef<string | null>(null);
  const [uploading, setUploading] = useState<{ supersedes?: LibDeck } | null>(() => (sp.get("upload") ? {} : null));
  const [tagMgr, setTagMgr] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const searchBox = useRef<HTMLInputElement>(null);

  /** Rewrite URL keys (undefined/false/"" removes one) without adding history entries for every keystroke. */
  const setUrl = useCallback((patch: Record<string, string | boolean | undefined | null>) => {
    setSp(prev => {
      const next = new URLSearchParams(prev);
      for (const [k, v] of Object.entries(patch)) {
        if (v === undefined || v === null || v === false || v === "") next.delete(k);
        else next.set(k, String(v));
      }
      return next;
    }, { replace: true });
  }, [setSp]);

  // Debounce typing into the URL (and so into the query key).
  useEffect(() => {
    const want = qInput.trim() ? qInput : "";
    if ((urlParams.q ?? "") === want) return;
    const t = window.setTimeout(() => setUrl({ q: want || undefined }), 250);
    return () => window.clearTimeout(t);
  }, [qInput, urlParams.q, setUrl]);

  const onFilter = (patch: Partial<SearchParams>) => setUrl({ ...patch });
  const clearFilters = () => {
    const patch: Record<string, undefined> = { fav: undefined, superseded: undefined, from: undefined, to: undefined };
    for (const k of FACET_KEYS) patch[k] = undefined;
    setUrl(patch);
  };
  const clearSearch = () => { setQInput(""); setUrl({ q: undefined }); };

  const deckById = useMemo(() => new Map((decks.data ?? []).map(d => [d.id, d])), [decks.data]);
  const showDeck = (deckId: string) => {
    const d = deckById.get(deckId);
    const patch: Record<string, string | boolean | undefined> = { view: undefined, group: undefined, deck: deckId, superseded: !!d?.superseded_by || undefined, q: undefined, open: undefined };
    for (const k of FACET_KEYS) if (k !== "deck") patch[k] = undefined;
    setQInput("");
    setOpenId(null);
    setUrl(patch);
  };
  /** A graph hub's "Show these slides": the Slides tab, filtered to it (and to favourites when the graph was). */
  const showSlides: GraphViewProps["onShowSlides"] = f => {
    const patch: Record<string, string | boolean | undefined> = { view: undefined, group: undefined, q: undefined, open: undefined, fav: graphParams.scope === "favourites" || undefined };
    for (const k of FACET_KEYS) patch[k] = undefined;
    Object.assign(patch, f);
    setQInput("");
    setUrl(patch);
  };
  const setGraph = (p: Partial<GraphParams>) => setUrl({
    ...("scope" in p ? { scope: p.scope === "all" ? "all" : undefined } : {}),
    ...("project" in p ? { gproject: p.project } : {}),
    ...("min_shared" in p ? { min_shared: p.min_shared === DEFAULT_MIN_SHARED ? undefined : String(p.min_shared) } : {}),
  });

  /* --- favourite (optimistic) and retry */
  const fav = useMutation({
    mutationFn: (s: LibSlide) => libApi.patchSlide(s.id, { favourite: !s.favourite }),
    onMutate: s => patchSlides(qc, [s.id], x => ({ ...x, favourite: !s.favourite })),
    onSuccess: r => patchSlides(qc, [r.id], x => mergeEdited(x, r)),
    onError: (e, s) => {
      patchSlides(qc, [s.id], x => ({ ...x, favourite: s.favourite }));
      toast.error("Couldn't update the favourite", { description: (e as Error).message });
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: libKeys.favs });
      void qc.invalidateQueries({ queryKey: libKeys.decks });
      void qc.invalidateQueries({ queryKey: libKeys.projects });
      void qc.invalidateQueries({ queryKey: libKeys.graphAll });
      if (params.fav) void qc.invalidateQueries({ queryKey: libKeys.searchAll });
    },
  });
  const retry = useMutation({
    mutationFn: (s: LibSlide) => libApi.retag(s.id),
    onMutate: s => patchSlides(qc, [s.id], x => ({ ...x, ai_status: "pending", ai_error: "" })),
    onError: (e, s) => {
      patchSlides(qc, [s.id], x => ({ ...x, ai_status: s.ai_status, ai_error: s.ai_error }));
      toast.error("Couldn't start tagging", { description: (e as Error).message });
    },
  });
  const onFav = useCallback((s: LibSlide) => fav.mutate(s), [fav]);
  const onRetry = useCallback((s: LibSlide) => retry.mutate(s), [retry]);

  /* --- selection: click opens, Ctrl/Cmd toggles, Shift selects a range; once selecting, a click toggles */
  const onPick = (s: LibSlide, mode: PickMode) => {
    if (mode === "open") { setOpenId(s.id); return; }
    setSelected(cur => {
      const next = new Set(cur);
      const from = anchor.current ? items.findIndex(x => x.id === anchor.current) : -1;
      const to = items.findIndex(x => x.id === s.id);
      if (mode === "range" && from >= 0 && to >= 0) {
        const [a, b] = from < to ? [from, to] : [to, from];
        for (const x of items.slice(a, b + 1)) next.add(x.id);
      } else if (next.has(s.id)) next.delete(s.id);
      else next.add(s.id);
      return next;
    });
    anchor.current = s.id;
  };
  const selectAll = useCallback(() => setSelected(new Set(items.map(s => s.id))), [items]);
  /** A deck's checkbox: all of its slides in, or — when they all are — all of them out. */
  const pickDeck = async (group: DeckGroup) => {
    try {
      const ids = await g.allIds(group);
      setSelected(cur => {
        const next = new Set(cur);
        const all = ids.every(id => cur.has(id));
        for (const id of ids) { if (all) next.delete(id); else next.add(id); }
        return next;
      });
    } catch (e) { toast.error("Couldn't select that deck", { description: (e as Error).message }); }
  };
  const clearSel = () => { setSelected(new Set()); anchor.current = null; };
  // Export order is the order on screen; selected slides no longer listed go last.
  const orderedSel = useMemo(() => {
    const listed = items.filter(s => selected.has(s.id)).map(s => s.id);
    const on = new Set(listed);
    return [...listed, ...[...selected].filter(id => !on.has(id))];
  }, [items, selected]);

  const dialogOpen = !!openId || !!uploading || tagMgr;
  useKey(e => {
    if (e.key === "/" && tab === "slides") { e.preventDefault(); searchBox.current?.focus(); }
    else if (e.key === "Escape" && !dialogOpen && selected.size) clearSel();
  });
  // Ctrl/Cmd+A selects every loaded slide (useKey ignores modified keys, so this one is separate).
  const latest = useRef({ selectAll, active: false });
  useEffect(() => { latest.current = { selectAll, active: tab === "slides" && !dialogOpen && items.length > 0 }; });
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a" && latest.current.active) { e.preventDefault(); latest.current.selectAll(); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  const setOpen = (id: string | null) => { setOpenId(id); if (!id && sp.get("open")) setUrl({ open: undefined }); };
  const closeUpload = () => { setUploading(null); if (sp.get("upload")) setUrl({ upload: undefined }); };
  const loadMore = useCallback(() => { if (hasMore && !search.isFetchingNextPage) void search.fetchNextPage(); }, [hasMore, search]);

  const empty = decks.data !== undefined && decks.data.length === 0;
  const filtered = hasFilters(params) || !!params.q;
  const facetNames: Partial<Record<FacetKey, (v: string) => string>> = { deck: id => deckById.get(id)?.title || deckById.get(id)?.filename || "This deck" };

  const uploadCta = (
    <Empty icon={<LibraryIcon className="size-6" />} title="Your slide library is empty"
      body="Add the PowerPoints you have made. Every slide is rendered and indexed so you can find it again by what it says — and reuse it."
      action={<Button variant="primary" icon={<FileUp className="size-4" />} onClick={() => setUploading({})}>Add PowerPoints</Button>} />
  );

  const chips: { key: string; label: string; clear: () => void }[] = [
    ...FACET_KEYS.filter(k => params[k]).map(k => {
      const v = params[k] ?? "";
      return { key: k, label: `${FACET_LABEL[k]}: ${facetNames[k]?.(v) && !first?.facets[k]?.some(f => f.value === v) ? facetNames[k]?.(v) : facetLabel(first?.facets, k, v)}`, clear: () => setUrl({ [k]: undefined }) };
    }),
    ...(params.fav ? [{ key: "fav", label: "Favourites", clear: () => setUrl({ fav: undefined }) }] : []),
    ...(params.superseded ? [{ key: "sup", label: "Including old versions", clear: () => setUrl({ superseded: undefined }) }] : []),
    ...(params.from || params.to ? [{ key: "date", label: `Dated ${params.from ?? "…"} – ${params.to ?? "…"}`, clear: () => setUrl({ from: undefined, to: undefined }) }] : []),
  ];

  return (
    <div className="min-h-full">
      <TopBar />
      <main className="mx-auto max-w-[1680px] px-4 pb-28 pt-6 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-[28px] font-extrabold leading-tight tracking-[-0.02em]">Slide library</h1>
            <p className="mt-1 text-[14px] text-muted">
              {decks.data ? `${decks.data.length} ${decks.data.length === 1 ? "deck" : "decks"} · ${decks.data.reduce((n, d) => n + d.slide_count, 0)} slides` : " "}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="primary" icon={<FileUp className="size-4" />} onClick={() => setUploading({})}>Add PowerPoints</Button>
            <LibraryMenu onTags={() => setTagMgr(true)} obsidian={tab === "graph" ? graphParams : undefined} />
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3 border-b border-line pb-3">
          <div role="tablist" aria-label="Library view" className="flex rounded-lg bg-surface-2 p-0.5 ring-1 ring-line-2">
            {TABS.map(t => (
              <button key={t} role="tab" aria-selected={tab === t} onClick={() => setUrl({ view: t === "slides" ? undefined : t })}
                className={cn("h-8 rounded-md px-3.5 text-[13px] font-semibold capitalize", tab === t ? "bg-surface text-ink shadow-sm" : "text-muted hover:text-ink")}>
                {t}
              </button>
            ))}
          </div>
          {tab === "slides" && <>
            <SearchBar ref={searchBox} value={qInput} onChange={setQInput} className="min-w-[220px]"
              busy={grouped ? g.outline.isFetching : search.isFetching && !search.isFetchingNextPage} />
            <Button size="sm" className="lg:hidden" icon={<Filter className="size-4" />} aria-expanded={showFilters} onClick={() => setShowFilters(f => !f)}>Filters</Button>
            <ViewControls view={view} onView={setView} sort={params.sort ?? "added"} relevance={!!params.q}
              onSort={s => setUrl({ sort: s })} group={groupBy} onGroup={v => setUrl({ group: v === groupDefault ? undefined : v })} />
          </>}
        </div>

        {tab === "graph" ? (
          empty ? <div className="mt-6">{uploadCta}</div> : (
            <Suspense fallback={<div className="flex h-[60vh] items-center justify-center text-muted"><Spinner className="size-5" /></div>}>
              <GraphView params={graphParams} onParams={setGraph} tags={tags} onFav={onFav} onRetry={onRetry} onShowDeck={showDeck}
                onShowSlides={showSlides} onSlidesTab={() => setUrl({ view: undefined })} />
            </Suspense>
          )
        ) : empty && !filtered ? uploadCta : (
          <div className="mt-5 grid gap-6 lg:grid-cols-[232px_1fr]">
            <aside className={cn("lg:block", showFilters ? "block" : "hidden")}>
              <div className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:overflow-auto lg:pr-1 scroll-thin">
                <Facets facets={first?.facets} params={params} onChange={onFilter} names={facetNames} />
              </div>
            </aside>
            <section aria-label="Results" className="min-w-0">
              <div className="mb-3 flex min-h-8 flex-wrap items-center gap-2">
                <span className="text-[13px] font-semibold text-muted" aria-live="polite">
                  {loading ? "Searching…" : `${total.toLocaleString()} ${total === 1 ? "slide" : "slides"}`}
                  {!loading && grouped && g.projects.length > 1 && ` · ${g.projects.length} projects`}
                  {!loading && first?.relaxed && " · no exact matches, showing partial ones"}
                </span>
                {chips.map(c => (
                  <span key={c.key} className="inline-flex h-7 items-center gap-1 rounded-full bg-accent-soft pl-2.5 pr-1 text-[12px] font-semibold text-accent">
                    {c.label}
                    <button aria-label={`Remove filter ${c.label}`} onClick={c.clear} className="flex size-5 items-center justify-center rounded-full hover:bg-accent hover:text-accent-ink"><X className="size-3" /></button>
                  </span>
                ))}
                {chips.length > 1 && <button onClick={clearFilters} className="text-[12px] font-semibold text-muted hover:text-ink hover:underline">Clear all</button>}
              </div>
              {failed ? <ServerError message={failed.message} />
                : loading ? <div className="flex h-60 items-center justify-center text-muted"><Spinner className="size-5" /></div>
                  : (grouped ? g.projects.length === 0 : items.length === 0) ? (
                    <Empty icon={<SearchX className="size-6" />} title="No slides match"
                      body={params.q
                        ? "Try fewer or shorter words — “gen” finds “generative” — or drop a filter. Numbers match as written, like 4.2M."
                        : "Nothing here with these filters."}
                      action={<div className="flex flex-wrap justify-center gap-2">
                        {params.q && <Button size="sm" onClick={clearSearch}>Clear search</Button>}
                        {hasFilters(params) && <Button size="sm" onClick={clearFilters}>Clear filters</Button>}
                        {!params.superseded && <Button size="sm" variant="ghost" onClick={() => setUrl({ superseded: true })}>Include old versions</Button>}
                      </div>} />
                  ) : grouped ? (
                    <SlideGridFrame view={view} onView={setView}>
                      <GroupedSlides g={g} decks={decks.data ?? []} view={view} selected={selected} tags={tags}
                        actions={{ onShowDeck: showDeck, onNewVersion: d => setUploading({ supersedes: d }), onPickDeck: d => void pickDeck(d) }}
                        onPick={onPick} onFav={onFav} onRetry={onRetry} />
                    </SlideGridFrame>
                  ) : (
                    <SlideGrid items={items} view={view} onView={setView} selected={selected} tags={tags}
                      hasMore={hasMore} loadingMore={search.isFetchingNextPage} onMore={loadMore}
                      onPick={onPick} onFav={onFav} onRetry={onRetry} />
                  )}
            </section>
          </div>
        )}
      </main>

      {selected.size > 0 && tab === "slides" && (
        <SelectionBar ids={orderedSel} items={grouped ? g.loaded : items} tags={tags} visible={items.length} onSelectAll={selectAll} onClear={clearSel} />
      )}
      <Lightbox items={items} openId={openId} onOpenId={setOpen} tags={tags} onFav={onFav} onRetry={onRetry}
        onShowDeck={showDeck} hasMore={hasMore} onMore={loadMore} />
      {uploading && (
        <UploadDialog key={uploading.supersedes?.id ?? "new"} open onOpenChange={o => !o && closeUpload()}
          supersedes={uploading.supersedes} defaultProject={params.project}
          onOpenDeck={id => { closeUpload(); showDeck(id); }} />
      )}
      <TagManager open={tagMgr} onOpenChange={setTagMgr} />
    </div>
  );
}

function ServerError({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-bad/30 bg-bad-soft p-4 text-sm text-bad">
      Couldn't load the library: {message}. If the server was just updated, restart it with <b>run.ps1</b>.
    </div>
  );
}
