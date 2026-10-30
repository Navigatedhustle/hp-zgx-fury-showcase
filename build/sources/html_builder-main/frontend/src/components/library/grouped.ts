import { useQueries, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { PAGE_SIZE, deckPageQuery, useLibraryGroups, type LibDeck, type LibSlide, type SearchParams, type SearchResult } from "../../lib/library";

/** A deck in the grouped view, with how many of its slides the current search holds. */
export interface DeckGroup { deck: LibDeck; count: number }
export interface ProjectGroup { project: string; decks: DeckGroup[]; slides: number }
/** What is loaded of one deck. `rest` slides are still to fetch ("Show all"). */
export interface DeckSlides { items: LibSlide[]; loading: boolean; error: string | null; rest: number }

const NOTHING: DeckSlides = { items: [], loading: false, error: null, rest: 0 };
const offsets = (count: number, all: boolean) => Array.from({ length: all ? Math.ceil(count / PAGE_SIZE) : 1 }, (_, i) => i * PAGE_SIZE);

/**
 * The Slides view grouped by project, then deck. The outline (which decks, how many slides each) is one request;
 * a deck's slides are fetched when it is first shown — its first page, then the rest on request — so a library
 * of thousands of slides opens as a short list of projects.
 */
export function useGrouped(params: SearchParams, enabled: boolean, decks: LibDeck[] | undefined) {
  const qc = useQueryClient();
  const outline = useLibraryGroups(params, enabled);
  // Open/closed as the user left it: `p:<project>` / `d:<deck id>`. Anything untouched follows the defaults below.
  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  // Decks wanted whole, not just their first page.
  const [full, setFull] = useState<Set<string>>(new Set());

  // Only slide-level filters hide a deck that has no matching slide; without one, a deck still importing
  // (or one that failed) is listed too, so its progress and its "Retry import" have somewhere to live.
  const deckLevel = !params.q && !params.tag && !params.type && !params.entity && !params.origin && !params.fav && !params.from && !params.to;
  const groups = outline.data?.groups;
  const projects = useMemo<ProjectGroup[]>(() => {
    if (!groups || !decks) return [];
    const byId = new Map(decks.map(d => [d.id, d]));
    const out = new Map<string, DeckGroup[]>();
    const seen = new Set<string>();
    const add = (deck: LibDeck, count: number) => { out.set(deck.project, [...(out.get(deck.project) ?? []), { deck, count }]); seen.add(deck.id); };
    for (const g of groups) { const d = byId.get(g.deck); if (d) add(d, g.count); }
    if (deckLevel) for (const d of decks) {
      if (seen.has(d.id) || (params.project && d.project !== params.project) || (params.deck && d.id !== params.deck)) continue;
      if (d.superseded_by && !params.superseded && d.id !== params.deck) continue;
      add(d, 0);
    }
    // Projects A–Z, the newest deck first within each.
    return [...out.entries()].sort(([a], [b]) => a.toLowerCase().localeCompare(b.toLowerCase())).map(([project, list]) => ({
      project,
      decks: list.sort((a, b) => (b.deck.created_at ?? "").localeCompare(a.deck.created_at ?? "")),
      slides: list.reduce((n, d) => n + d.count, 0),
    }));
  }, [groups, decks, deckLevel, params.project, params.deck, params.superseded]);

  // A result small enough to take in at once opens whole; otherwise projects start closed.
  const openAll = projects.length === 1 || (outline.data?.total ?? 0) <= PAGE_SIZE;
  const projectOpen = useCallback((project: string) => toggled[`p:${project}`] ?? openAll, [toggled, openAll]);
  const deckOpen = useCallback((id: string) => toggled[`d:${id}`] ?? true, [toggled]);
  const toggle = (key: string, now: boolean) => setToggled(t => ({ ...t, [key]: !now }));

  const wanted = useMemo(() => projects.flatMap(pg => pg.decks.flatMap(({ deck, count }) => {
    const visible = projectOpen(pg.project) && deckOpen(deck.id);
    if (!count || (!visible && !full.has(deck.id))) return [];
    return offsets(count, full.has(deck.id)).map(offset => ({ deck: deck.id, count, offset, visible }));
  })), [projects, projectOpen, deckOpen, full]);

  const combine = useCallback((results: UseQueryResult<SearchResult>[]) => {
    const byDeck = new Map<string, DeckSlides>();
    const items: LibSlide[] = [];
    const loaded: LibSlide[] = [];
    wanted.forEach((w, i) => {
      const r = results[i];
      const cur = byDeck.get(w.deck) ?? { items: [], loading: false, error: null, rest: w.count };
      const page = r?.data?.items ?? [];
      const next: DeckSlides = {
        items: [...cur.items, ...page], loading: cur.loading || !!r?.isLoading,
        error: cur.error ?? (r?.isError ? r.error.message : null), rest: Math.max(0, cur.rest - page.length),
      };
      byDeck.set(w.deck, next);
      loaded.push(...page);
      if (w.visible) items.push(...page);
    });
    return { byDeck, items, loaded };
  }, [wanted]);
  const { byDeck, items, loaded } = useQueries({
    queries: wanted.map(w => ({ ...deckPageQuery(params, w.deck, w.offset), enabled })),
    combine,
  });

  /** Every slide id of a deck within the search, fetching what is not loaded yet; the deck then stays loaded whole. */
  const allIds = async ({ deck, count }: DeckGroup): Promise<string[]> => {
    const pages = await Promise.all(offsets(count, true).map(o => qc.ensureQueryData(deckPageQuery(params, deck.id, o))));
    setFull(f => new Set(f).add(deck.id));
    return [...new Set(pages.flatMap(p => p.items.map(s => s.id)))];
  };

  return {
    outline, projects,
    /** Visible slides in the order shown, and everything loaded (a closed deck's slides can still be selected). */
    items, loaded,
    slidesOf: (deckId: string) => byDeck.get(deckId) ?? NOTHING,
    projectOpen, deckOpen,
    toggleProject: (project: string) => toggle(`p:${project}`, projectOpen(project)),
    toggleDeck: (id: string) => toggle(`d:${id}`, deckOpen(id)),
    showAll: (id: string) => setFull(f => new Set(f).add(id)),
    allIds,
  };
}

export type Grouped = ReturnType<typeof useGrouped>;
