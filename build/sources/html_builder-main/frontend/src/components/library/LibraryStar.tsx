import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BookmarkPlus, Library, RefreshCw, Star } from "lucide-react";
import { useEffect, useSyncExternalStore } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  deckHref, duplicateOf, libApi, libKeys, useProjectLinks,
  type DuplicateDetail, type LinkKind, type ProjectLinks,
} from "../../lib/library";
import { cn } from "../../lib/util";
import { Button, Spinner, Tip } from "../ui";

/* ------------------------------------------------------------------ favourites waiting for a deck
 * Starring a slide whose library deck is still being saved comes back `pending`: the server applies the
 * favourite when the deck is in. Until then the links route can't show it, so the wish is kept here (per
 * project slide, across every star that shows it) and dropped once that deck has finished. */

interface Queued { want: boolean; deckId: string }
const queued = new Map<string, Queued>();
const subs = new Set<() => void>();
function setQueued(key: string, v: Queued | null) {
  if (v) queued.set(key, v); else if (!queued.delete(key)) return;
  for (const f of subs) f();
}
const subscribe = (f: () => void) => { subs.add(f); return () => { subs.delete(f); }; };
const useQueued = (key: string) => useSyncExternalStore(subscribe, () => queued.get(key));

function invalidateLibrary(qc: ReturnType<typeof useQueryClient>, projectId: string) {
  void qc.invalidateQueries({ queryKey: libKeys.links(projectId) });
  void qc.invalidateQueries({ queryKey: libKeys.decks });
  void qc.invalidateQueries({ queryKey: libKeys.projects });
  void qc.invalidateQueries({ queryKey: libKeys.favs });
  void qc.invalidateQueries({ queryKey: libKeys.searchAll });
}

/**
 * The star on a project slide: favourite it in the slide library without leaving the deck. The first star
 * saves the deck there (`kind` says which: the PowerPoint, or the approved designs). Optimistic, rolled
 * back on error; hidden when the library can't be reached.
 */
export function LibraryStar({ projectId, slideId, kind, room, className }: {
  projectId: string; slideId: string; kind: LinkKind;
  /** On the dark review/preview surface. */
  room?: boolean; className?: string;
}) {
  const qc = useQueryClient();
  const links = useProjectLinks(projectId);
  const key = `${projectId}:${slideId}`;
  const q = useQueued(key);
  const deck = links.data?.[kind] ?? null;

  // The deck the queued favourite waits for has finished: the links route speaks for it from now on.
  useEffect(() => {
    if (q && deck && deck.deck_id === q.deckId && deck.status !== "ingesting") setQueued(key, null);
  }, [q, deck, key]);

  const m = useMutation({
    mutationFn: (want: boolean) => libApi.projectFavourite({ slide_id: slideId, kind, favourite: want }),
    onMutate: async want => {
      const lk = libKeys.links(projectId);
      await qc.cancelQueries({ queryKey: lk });
      const prev = qc.getQueryData<ProjectLinks>(lk);
      const prevQueued = queued.get(key) ?? null;
      setQueued(key, null);
      qc.setQueryData<ProjectLinks>(lk, d => d && withKindFav(d, kind, slideId, want ? d[kind]?.favourites[slideId] ?? "" : null));
      return { prev, prevQueued };
    },
    onSuccess: (r, want) => {
      if (r.pending) {
        setQueued(key, { want, deckId: r.deck_id });
        if (want) toast("Saving this deck to the slide library", { description: "The slide is favourited as soon as it's in — usually under a minute." });
      } else {
        qc.setQueryData<ProjectLinks>(libKeys.links(projectId), d => d &&
          withKindFav(d, kind, slideId, want ? r.lib_slide_id ?? d[kind]?.favourites[slideId] ?? "" : null));
      }
    },
    onError: (e, _want, ctx) => {
      if (ctx?.prev) qc.setQueryData(libKeys.links(projectId), ctx.prev);
      setQueued(key, ctx?.prevQueued ?? null);
      toast.error("Couldn't update the library favourite", { description: (e as Error).message });
    },
    onSettled: () => invalidateLibrary(qc, projectId),
  });

  if (links.isError) return null;
  const fav = q ? q.want : deck?.favourites[slideId] !== undefined || !!deck?.pending.includes(slideId);
  const waiting = !!q && !m.isPending;
  const stale = kind === "generated" && fav && !!links.data?.generated?.stale_slide_ids.includes(slideId);
  const label = fav ? "Remove from library favourites" : "Favourite in the slide library";
  const tip = waiting ? "Saving the deck to the slide library — favourited once it's in"
    : stale ? "Favourited in the slide library, as an earlier design. Unstar and star again to keep this one."
      : fav ? "Favourited in the slide library — click to remove" : "Favourite in the slide library";
  return (
    <Tip label={tip}>
      <button type="button" aria-label={label} aria-pressed={fav} aria-busy={m.isPending || waiting || undefined}
        disabled={m.isPending || links.isLoading} onClick={() => m.mutate(!fav)}
        className={cn("relative inline-flex size-8 shrink-0 items-center justify-center rounded-lg transition-colors disabled:cursor-not-allowed",
          fav ? "text-warn" : room ? "text-room-muted hover:bg-room-2 hover:text-room-ink" : "text-muted hover:bg-surface-2 hover:text-ink",
          fav && (room ? "hover:bg-room-2" : "hover:bg-surface-2"), className)}>
        {m.isPending ? <Spinner className="size-4" /> : <Star className={cn("size-4", fav && "fill-current")} />}
        {(waiting || stale) && (
          <span aria-hidden className={cn("absolute right-1 top-1 size-1.5 rounded-full", waiting ? "animate-pulse bg-accent" : "bg-warn")} />
        )}
      </button>
    </Tip>
  );
}

function withFav(map: Record<string, string>, slideId: string, value: string | null): Record<string, string> {
  const next = { ...map };
  if (value === null) delete next[slideId]; else next[slideId] = value;
  return next;
}

/** Set one star in the cached links — in its own kind's map, so a Plan star never lights the Review one. */
function withKindFav(d: ProjectLinks, kind: LinkKind, slideId: string, value: string | null): ProjectLinks {
  const deck = d[kind];
  return { ...d, favourites: withFav(d.favourites, slideId, value), [kind]: deck && { ...deck, favourites: withFav(deck.favourites, slideId, value) } };
}

/* ------------------------------------------------------------------ saving a whole deck */

export interface SaveVars { kind: LinkKind; force?: boolean; supersedes?: string }

/**
 * Put this project into the library (the round-1 from-project route). A 409 means the very same deck is
 * already there: by default that is a toast with the way to it; `onDuplicate` lets a caller offer more.
 */
export function useSaveToLibrary(projectId: string, onDuplicate?: (d: DuplicateDetail, v: SaveVars) => void) {
  const qc = useQueryClient();
  const nav = useNavigate();
  return useMutation({
    mutationFn: (v: SaveVars) => libApi.fromProject(projectId, v),
    onSuccess: (d, v) => {
      toast.success(v.kind === "source" ? "Saving the deck to the slide library" : "Saving the approved slides to the slide library", {
        description: "Rendered and indexed in the background — searchable in a minute or so.",
        action: { label: "Open", onClick: () => nav(deckHref(d.id)) },
      });
    },
    onError: (e, v) => {
      const dup = duplicateOf(e);
      if (dup && onDuplicate) { onDuplicate(dup, v); return; }
      if (dup) {
        toast("Already in the slide library", {
          description: dup.message || "This deck is saved there already.",
          action: { label: "Open in library", onClick: () => nav(deckHref(dup.deck_id)) },
        });
        return;
      }
      toast.error("Couldn't save to the slide library", { description: (e as Error).message });
    },
    onSettled: () => invalidateLibrary(qc, projectId),
  });
}

/**
 * "Save deck to library" as a toolbar button. Once saved it becomes the way to the deck in the library;
 * for approved designs that have changed since, it saves a new version that replaces the old one.
 */
export function SaveToLibraryButton({ projectId, kind, room, disabled, label }: {
  projectId: string; kind: LinkKind; room?: boolean; disabled?: boolean; label: string;
}) {
  const nav = useNavigate();
  const links = useProjectLinks(projectId);
  const save = useSaveToLibrary(projectId);
  const deck = links.data?.[kind] ?? null;
  const variant = room ? "room" : "ghost";
  const g = links.data?.generated;
  const stale = kind === "generated" && g ? g.stale_slide_ids.length + (g.missing_slide_ids?.length ?? 0) : 0;

  if (deck?.status === "ingesting") {
    return <Button size="sm" variant={variant} loading disabled>Saving to library…</Button>;
  }
  if (deck && deck.status === "ready" && stale > 0) {
    return (
      <Tip label={`${stale} approved ${stale === 1 ? "slide is" : "slides are"} newer than the library copy, or missing from it. Saves a new version that replaces it; favourites and your tags carry over.`}>
        <span><Button size="sm" variant={variant} icon={<RefreshCw className="size-3.5" />} loading={save.isPending} disabled={disabled}
          onClick={() => save.mutate({ kind, force: true, supersedes: deck.deck_id })}>Update in library</Button></span>
      </Tip>
    );
  }
  if (deck && deck.status === "ready") {
    return (
      <Tip label="Open this deck in the slide library">
        <span><Button size="sm" variant={variant} icon={<Library className="size-3.5" />} onClick={() => nav(deckHref(deck.deck_id))}>In the library</Button></span>
      </Tip>
    );
  }
  return (
    <Tip label={kind === "source" ? "Keep the original PowerPoint's slides in the slide library, searchable and reusable in other decks." : "Keep the approved designs in the slide library, searchable and reusable in other decks."}>
      <span><Button size="sm" variant={variant} icon={<BookmarkPlus className="size-3.5" />} loading={save.isPending} disabled={disabled}
        onClick={() => save.mutate({ kind })}>{label}</Button></span>
    </Tip>
  );
}
