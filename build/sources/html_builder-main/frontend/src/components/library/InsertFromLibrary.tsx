import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Library as LibraryIcon, SearchX, Star, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { libApi, libKeys, mergeEdited, patchSlides, tagIndex, useLibTags, useLibrarySearch, type LibSlide, type SearchParams } from "../../lib/library";
import { cn } from "../../lib/util";
import { Button, Empty, IconButton, Spinner, Switch } from "../ui";
import { SearchBar } from "./SearchBar";
import { Thumb, slideTitle, type PickMode } from "./SlideCard";
import { SlideGrid } from "./SlideGrid";
import type { ViewSize } from "./ViewControls";

/** One choice of where the picked slides go: `after` is a deck position (0 = the start), null the end. */
export interface InsertSpot { after: number | null; label: string }

const spotValue = (after: number | null) => (after === null ? "end" : String(after));

/**
 * Pick slides from the library and make them slides of this deck (backend `POST /library/insert`). Their
 * figures come with them into the fact ledger, so they are held to the library slide like a converted one.
 *
 * Works like the Library page: the same search box, cards and keyboard. A click (or Enter) picks a slide;
 * picks are kept in the order they were made, which is the order they go into the deck.
 */
export function InsertFromLibrary({ projectId, open, onOpenChange, spots, defaultAfter }: {
  projectId: string; open: boolean; onOpenChange: (o: boolean) => void;
  /** Where the slides can go, in deck order. */
  spots: InsertSpot[];
  /** The spot chosen when the dialog opens. */
  defaultAfter: number | null;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-ink/40 backdrop-blur-[2px]" />
        <DialogPrimitive.Content
          // Esc in a filled search box clears it (SearchBar) rather than closing the dialog and losing the picks.
          onEscapeKeyDown={e => { const t = e.target as HTMLInputElement | null; if (t?.type === "search" && t.value) e.preventDefault(); }}
          className="fixed left-1/2 top-1/2 z-50 flex h-[min(90vh,960px)] w-[calc(100vw-32px)] max-w-6xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-card outline-none">
          {open && <Picker projectId={projectId} spots={spots} defaultAfter={defaultAfter} onDone={() => onOpenChange(false)} />}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function Picker({ projectId, spots, defaultAfter, onDone }: {
  projectId: string; spots: InsertSpot[]; defaultAfter: number | null; onDone: () => void;
}) {
  const qc = useQueryClient();
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [favOnly, setFavOnly] = useState(true);
  const [view, setView] = useState<ViewSize>("m");
  const [picked, setPicked] = useState<LibSlide[]>([]);
  const [anchor, setAnchor] = useState<string | null>(null);
  const [after, setAfter] = useState<string>(spotValue(defaultAfter));

  useEffect(() => {
    const t = window.setTimeout(() => setQ(qInput.trim()), 250);
    return () => window.clearTimeout(t);
  }, [qInput]);

  const params = useMemo<SearchParams>(() => ({ q: q || undefined, fav: favOnly || undefined, sort: q ? "relevance" : "added" }), [q, favOnly]);
  const search = useLibrarySearch(params);
  const tags = tagIndex(useLibTags().data);
  const items = useMemo(() => {
    const seen = new Set<string>();
    return (search.data?.pages ?? []).flatMap(pg => pg.items).filter(s => (seen.has(s.id) ? false : (seen.add(s.id), true)));
  }, [search.data]);
  const total = search.data?.pages[0]?.total ?? 0;
  const relaxed = !!search.data?.pages[0]?.relaxed;
  const selected = useMemo(() => new Set(picked.map(s => s.id)), [picked]);
  const loadMore = useCallback(() => { if (search.hasNextPage && !search.isFetchingNextPage) void search.fetchNextPage(); }, [search]);

  /* --- picking: a click toggles; Shift adds the range from the last pick, in list order */
  const onPick = (s: LibSlide, mode: PickMode) => {
    if (mode === "range" && anchor) {
      const a = items.findIndex(x => x.id === anchor);
      const b = items.findIndex(x => x.id === s.id);
      if (a >= 0 && b >= 0) {
        const range = (a < b ? items.slice(a, b + 1) : items.slice(b, a + 1).reverse()).filter(x => !selected.has(x.id));
        setPicked(cur => [...cur, ...range]);
        setAnchor(s.id);
        return;
      }
    }
    setPicked(cur => (cur.some(x => x.id === s.id) ? cur.filter(x => x.id !== s.id) : [...cur, s]));
    setAnchor(s.id);
  };
  const unpick = (id: string) => setPicked(cur => cur.filter(x => x.id !== id));

  /* --- favourite and retry, as on the Library page */
  const fav = useMutation({
    mutationFn: (s: LibSlide) => libApi.patchSlide(s.id, { favourite: !s.favourite }),
    onMutate: s => patchSlides(qc, [s.id], x => ({ ...x, favourite: !s.favourite })),
    onSuccess: r => patchSlides(qc, [r.id], x => mergeEdited(x, r)),
    onError: (e, s) => {
      patchSlides(qc, [s.id], x => ({ ...x, favourite: s.favourite }));
      toast.error("Couldn't update the favourite", { description: (e as Error).message });
    },
    onSettled: () => { void qc.invalidateQueries({ queryKey: libKeys.favs }); },
  });
  const retry = useMutation({
    mutationFn: (s: LibSlide) => libApi.retag(s.id),
    onMutate: s => patchSlides(qc, [s.id], x => ({ ...x, ai_status: "pending", ai_error: "" })),
    onError: (e, s) => {
      patchSlides(qc, [s.id], x => ({ ...x, ai_status: s.ai_status, ai_error: s.ai_error }));
      toast.error("Couldn't start tagging", { description: (e as Error).message });
    },
  });

  const insert = useMutation({
    mutationFn: () => libApi.insertFromLibrary(projectId, picked.map(s => s.id), after === "end" ? null : Number(after)),
    onSuccess: r => {
      void qc.invalidateQueries({ queryKey: ["project", projectId] });
      const n = r.slides?.length ?? picked.length;
      toast.success(`${n} ${n === 1 ? "slide" : "slides"} inserted from the library`, {
        description: "Their figures are in the fact ledger and cite the library deck. Plan and design them with the rest.",
      });
      onDone();
    },
    onError: e => toast.error("Couldn't insert those slides", { description: (e as Error).message }),
  });

  const n = picked.length;
  return (
    <>
      <div className="flex items-start justify-between gap-4 px-6 pb-3 pt-5">
        <div className="min-w-0">
          <DialogPrimitive.Title className="text-lg font-bold tracking-tight">Insert from the slide library</DialogPrimitive.Title>
          <DialogPrimitive.Description className="mt-1 text-sm text-muted">
            Pick slides to bring into this deck. Their figures are checked like any source slide, and the slide cites the deck it came from.
          </DialogPrimitive.Description>
        </div>
        <DialogPrimitive.Close asChild><IconButton label="Close (Esc)"><X className="size-4" /></IconButton></DialogPrimitive.Close>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-b border-line px-6 pb-3">
        <SearchBar value={qInput} onChange={setQInput} busy={search.isFetching && !search.isFetchingNextPage} className="min-w-[220px]" />
        <label className="flex h-10 items-center gap-2 rounded-xl border border-line px-3 text-[13px] font-semibold">
          <Star className={cn("size-4", favOnly ? "fill-current text-warn" : "text-muted")} />
          Favourites only
          <Switch checked={favOnly} onCheckedChange={setFavOnly} label="Favourites only" />
        </label>
      </div>

      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-6 pt-3">
        <div className="mb-3 text-[13px] font-semibold text-muted" aria-live="polite">
          {search.isLoading ? "Searching…" : `${total.toLocaleString()} ${total === 1 ? "slide" : "slides"}${favOnly ? " in your favourites" : ""}`}
          {!search.isLoading && relaxed && " · no exact matches, showing partial ones"}
        </div>
        {search.isError ? (
          <div className="rounded-xl border border-bad/30 bg-bad-soft p-4 text-sm text-bad">Couldn't search the library: {search.error.message}</div>
        ) : search.isLoading ? (
          <div className="flex h-60 items-center justify-center text-muted"><Spinner className="size-5" /></div>
        ) : items.length === 0 ? (
          <Empty icon={favOnly ? <Star className="size-6" /> : q ? <SearchX className="size-6" /> : <LibraryIcon className="size-6" />}
            title={favOnly ? (q ? "No favourites match" : "No favourites yet") : q ? "No slides match" : "The library is empty"}
            body={favOnly
              ? "Favourites are the slides you star in the library or in a deck. Search everything instead?"
              : q ? "Try fewer or shorter words — “gen” finds “generative”." : "Add PowerPoints on the Library page, or save a deck there, then insert its slides here."}
            action={favOnly ? <Button size="sm" onClick={() => setFavOnly(false)}>Show all slides</Button>
              : q ? <Button size="sm" onClick={() => setQInput("")}>Clear search</Button> : undefined} />
        ) : (
          <SlideGrid items={items} view={view} onView={setView} selected={selected} tags={tags}
            hasMore={!!search.hasNextPage} loadingMore={search.isFetchingNextPage} onMore={loadMore}
            onPick={onPick} onFav={s => fav.mutate(s)} onRetry={s => retry.mutate(s)} />
        )}
      </div>

      <div className="border-t border-line bg-surface-2/60 px-6 py-3">
        {n > 0 && (
          <ol className="scroll-thin mb-3 flex gap-2 overflow-x-auto pb-1" aria-label="Picked slides, in the order they will be inserted">
            {picked.map((s, i) => (
              <li key={s.id} className="relative w-28 shrink-0">
                <Thumb src={s.thumb} alt="" className="rounded-md ring-1 ring-line" />
                <span className="absolute left-1 top-1 flex size-5 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-accent-ink">{i + 1}</span>
                <button type="button" aria-label={`Remove ${slideTitle(s)} from the picks`} onClick={() => unpick(s.id)}
                  className="absolute right-1 top-1 flex size-5 items-center justify-center rounded-full bg-black/55 text-white hover:bg-black/75">
                  <X className="size-3" />
                </button>
                <div className="mt-1 truncate text-[11px] font-semibold text-muted" title={slideTitle(s)}>{slideTitle(s)}</div>
              </li>
            ))}
          </ol>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[13px] font-semibold" aria-live="polite">
            {n ? `${n} ${n === 1 ? "slide" : "slides"} picked` : <span className="font-normal text-muted">Click slides to pick them — they go in in the order you pick.</span>}
          </span>
          {n > 0 && <button type="button" onClick={() => setPicked([])} className="text-[12px] font-semibold text-muted hover:text-ink hover:underline">Clear</button>}
          <label className="ml-auto flex items-center gap-2 text-[13px] text-muted">
            Insert
            <select value={after} onChange={e => setAfter(e.target.value)} aria-label="Where to insert"
              className="h-9 max-w-[260px] rounded-lg border border-line bg-surface px-2 text-[13px] text-ink focus:border-accent focus:outline-none">
              {spots.map(sp => <option key={spotValue(sp.after)} value={spotValue(sp.after)}>{sp.label}</option>)}
            </select>
          </label>
          <DialogPrimitive.Close asChild><Button>Cancel</Button></DialogPrimitive.Close>
          <Button variant="primary" disabled={!n} loading={insert.isPending} onClick={() => insert.mutate()}>
            {n > 1 ? `Insert ${n} slides` : "Insert slide"}
          </Button>
        </div>
      </div>
    </>
  );
}

/** The usual choices: the end, the start, or after any slide (labelled by its number and headline). */
export function insertSpots(slides: { position: number; label?: string; title: string }[]): InsertSpot[] {
  return [
    { after: null, label: "at the end" },
    { after: 0, label: "at the start" },
    ...slides.map(s => ({ after: s.position, label: `after ${s.label ?? s.position}${s.title ? ` — ${s.title.slice(0, 40)}` : ""}` })),
  ];
}
