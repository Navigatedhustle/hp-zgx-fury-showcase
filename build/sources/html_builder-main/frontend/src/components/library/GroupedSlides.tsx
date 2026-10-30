import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, ChevronRight, FilePlus2, Filter, History, Minus, MoreHorizontal, Pencil, RotateCcw, Tags, Trash2 } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { humanize, libApi, libKeys, useLibProjects, type LibDeck, type LibTag } from "../../lib/library";
import { cn, timeAgo } from "../../lib/util";
import { Badge, Button, Dialog, Field, Spinner, inputClass } from "../ui";
import type { DeckGroup, Grouped } from "./grouped";
import { Thumb, fmtDate, type CardHandlers } from "./SlideCard";
import { SlideCards } from "./SlideGrid";
import type { ViewSize } from "./ViewControls";

const itemClass = "flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-sm outline-none data-[highlighted]:bg-surface-2";
const plural = (n: number, one: string) => `${n.toLocaleString()} ${n === 1 ? one : `${one}s`}`;

export interface DeckActions {
  /** Narrow the view to this one deck. */
  onShowDeck: (deckId: string) => void;
  onNewVersion: (deck: LibDeck) => void;
  /** Select every slide of the deck that the search holds, or clear them when they all are. */
  onPickDeck: (group: DeckGroup) => void;
}

function EditDeckDialog({ deck, onClose }: { deck: LibDeck; onClose: () => void }) {
  const qc = useQueryClient();
  const listId = useId();
  const projects = useLibProjects();
  const [project, setProject] = useState(deck.project);
  const [title, setTitle] = useState(deck.title);
  const [date, setDate] = useState(deck.deck_date ? deck.deck_date.slice(0, 10) : "");
  const save = useMutation({
    // The date goes as YYYY-MM-DD (null clears it).
    mutationFn: () => libApi.patchDeck(deck.id, { project: project.trim(), title: title.trim(), deck_date: date }),  // "" clears it on the server; null would mean "unchanged"
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: libKeys.all });
      toast.success("Deck updated");
      onClose();
    },
    onError: e => toast.error("Couldn't save the deck", { description: (e as Error).message }),
  });
  return (
    <Dialog open onOpenChange={o => !o && onClose()} title="Deck details" description={deck.filename}
      footer={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" loading={save.isPending} disabled={!project.trim()} onClick={() => save.mutate()}>Save</Button>
      </>}>
      <div className="space-y-4">
        <Field label="Project">
          <input value={project} onChange={e => setProject(e.target.value)} list={listId} className={inputClass} required />
          <datalist id={listId}>{projects.data?.map(p => <option key={p.project} value={p.project} />)}</datalist>
        </Field>
        <Field label="Title"><input value={title} onChange={e => setTitle(e.target.value)} className={inputClass} /></Field>
        <Field label="Deck date" hint="When it was written — search can filter and sort by it.">
          <input type="date" value={date} onChange={e => setDate(e.target.value)} className={inputClass} />
        </Field>
      </div>
    </Dialog>
  );
}

/** Nothing, some or all of a deck's slides selected. */
type Checked = boolean | "mixed";

/** A deck's own bar: what it is, its import state, and everything that can be done to it. It stays in view while its slides scroll. */
function DeckBar({ group, open, onToggle, checked, bodyId, newer, older, actions, onEdit, onDelete }: {
  group: DeckGroup; open: boolean; onToggle: () => void; checked: Checked; bodyId: string;
  newer?: LibDeck; older?: LibDeck; actions: DeckActions; onEdit: () => void; onDelete: () => void;
}) {
  const { deck, count } = group;
  const qc = useQueryClient();
  const tagAll = useMutation({
    mutationFn: () => libApi.tagAll(deck.id),
    onSuccess: () => {
      toast.success("Tagging every slide", { description: "The review model works through them in the background." });
      void qc.invalidateQueries({ queryKey: libKeys.searchAll });
    },
    onError: e => toast.error("Couldn't start tagging", { description: (e as Error).message }),
  });
  const retry = useMutation({
    mutationFn: () => libApi.retryDeck(deck.id),
    onSuccess: d => {
      qc.setQueryData<LibDeck[]>(libKeys.decks, list => list?.map(x => (x.id === d.id ? { ...x, ...d } : x)));
      void qc.invalidateQueries({ queryKey: libKeys.decks });
      toast.success("Importing again");
    },
    onError: e => toast.error("Couldn't retry the import", { description: (e as Error).message }),
  });
  const busy = deck.status === "ingesting";
  const name = deck.title || deck.filename || "Untitled deck";
  return (
    <div className={cn("sticky top-[57px] z-20 flex items-center gap-2 rounded-xl border bg-surface p-2 shadow-sm", deck.superseded_by ? "border-line-2" : "border-line")}>
      <button aria-expanded={open} aria-controls={bodyId} aria-label={open ? `Hide the slides of ${name}` : `Show the slides of ${name}`} onClick={onToggle}
        className="flex size-7 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-ink">
        <ChevronRight className={cn("size-4 transition-transform", open && "rotate-90")} />
      </button>
      <button role="checkbox" aria-checked={checked} aria-label={`Select every slide of ${name}`} disabled={!count} onClick={() => actions.onPickDeck(group)}
        className={cn("flex size-5 shrink-0 items-center justify-center rounded-md border-2 transition-colors disabled:opacity-30",
          checked ? "border-accent bg-accent text-accent-ink" : "border-line bg-surface text-transparent hover:border-faint")}>
        {checked === "mixed" ? <Minus className="size-3.5" strokeWidth={3} /> : <Check className="size-3.5" strokeWidth={3} />}
      </button>
      {/* The chevron is the keyboard's way in; this is the same toggle as a bigger target for the mouse. */}
      <button onClick={onToggle} tabIndex={-1} aria-hidden className="group flex min-w-0 flex-1 items-center gap-3 rounded-lg text-left">
        <Thumb src={deck.cover} className={cn("hidden w-16 shrink-0 rounded ring-1 ring-line-2 sm:block", deck.superseded_by && "opacity-60")} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[14.5px] font-bold group-hover:text-accent">{name}</div>
          <div className="truncate text-[12.5px] text-muted">
            {count > 0 && count !== deck.slide_count ? `${count.toLocaleString()} of ${plural(deck.slide_count, "slide")}` : plural(deck.slide_count, "slide")}
            {deck.favourites ? ` · ${deck.favourites} ★` : ""}
            {deck.deck_date ? ` · ${fmtDate(deck.deck_date)}` : ""}
            {deck.origin !== "upload" ? ` · ${humanize(deck.origin)}` : ""}
            {deck.created_at ? ` · added ${timeAgo(deck.created_at)}` : ""}
            {deck.title && deck.filename ? ` · ${deck.filename}` : ""}
          </div>
          {busy && (
            <div className="mt-1.5 flex max-w-sm items-center gap-2">
              <div className="h-1 flex-1 overflow-hidden rounded-full bg-line"><div className="shimmer-light h-full w-full bg-accent/40" /></div>
              <span className="shrink-0 truncate text-[12px] font-semibold text-accent">{deck.stage_note || "Importing…"}</span>
            </div>
          )}
          {deck.status === "error" && <div className="mt-1 flex items-center gap-1.5 text-[12.5px] text-bad"><AlertTriangle className="size-3.5 shrink-0" /><span className="truncate" title={deck.error}>{deck.error || "Import failed"}</span></div>}
          {older && <div className="mt-0.5 truncate text-[12px] text-muted">Replaces “{older.title || older.filename}”</div>}
        </div>
      </button>
      <div className="hidden shrink-0 items-center gap-1.5 sm:flex">
        {deck.superseded_by && <Badge tone="warn"><History className="size-3" />{newer ? "Replaced" : "Old version"}</Badge>}
        {busy && <Badge tone="busy" pulse>Importing</Badge>}
        {deck.status === "error" && <Badge tone="bad">Failed</Badge>}
      </div>
      {deck.status === "error" && deck.origin !== "generated" && (
        <Button size="sm" icon={<RotateCcw className="size-3.5" />} loading={retry.isPending} onClick={() => retry.mutate()}>Retry import</Button>
      )}
      <Dropdown.Root>
        <Dropdown.Trigger aria-label={`Actions for ${name}`} className="flex size-8 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink">
          <MoreHorizontal className="size-4" />
        </Dropdown.Trigger>
        <Dropdown.Portal>
          <Dropdown.Content align="end" sideOffset={4} className="z-50 min-w-48 rounded-xl border border-line bg-surface p-1 shadow-card">
            <Dropdown.Item onSelect={() => actions.onShowDeck(deck.id)} className={itemClass}><Filter className="size-4" />Show only this deck</Dropdown.Item>
            <Dropdown.Item onSelect={onEdit} className={itemClass}><Pencil className="size-4" />Edit details</Dropdown.Item>
            <Dropdown.Item onSelect={() => tagAll.mutate()} disabled={busy} className={cn(itemClass, "data-[disabled]:opacity-40")}><Tags className="size-4" />Tag all slides</Dropdown.Item>
            <Dropdown.Item onSelect={() => actions.onNewVersion(deck)} className={itemClass}><FilePlus2 className="size-4" />Upload new version</Dropdown.Item>
            <Dropdown.Separator className="my-1 h-px bg-line-2" />
            <Dropdown.Item onSelect={onDelete} className={cn(itemClass, "text-bad data-[highlighted]:bg-bad-soft")}><Trash2 className="size-4" />Delete from library</Dropdown.Item>
          </Dropdown.Content>
        </Dropdown.Portal>
      </Dropdown.Root>
    </div>
  );
}

interface Props extends CardHandlers {
  g: Grouped; decks: LibDeck[]; view: ViewSize; selected: Set<string>; tags: Map<string, LibTag>; actions: DeckActions;
}

/** The slides, under their deck, under their project. Projects and decks fold; a deck's bar carries its actions. */
export function GroupedSlides({ g, decks, view, selected, tags, actions, ...handlers }: Props) {
  const qc = useQueryClient();
  const uid = useId();
  const [editing, setEditing] = useState<LibDeck | null>(null);
  const [deleting, setDeleting] = useState<LibDeck | null>(null);
  const byId = new Map(decks.map(d => [d.id, d]));
  const del = useMutation({
    mutationFn: (id: string) => libApi.deleteDeck(id),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: libKeys.all }); toast.success("Deck removed from the library"); setDeleting(null); },
    onError: e => toast.error("Couldn't delete the deck", { description: (e as Error).message }),
  });

  return (
    <div className="space-y-3">
      {g.projects.map((pg, pi) => {
        const open = g.projectOpen(pg.project);
        const listId = `${uid}-p${pi}`;
        return (
          <section key={pg.project} aria-label={pg.project || "No project"}>
            <button aria-expanded={open} aria-controls={listId} onClick={() => g.toggleProject(pg.project)}
              className="group flex w-full items-baseline gap-2 rounded-lg py-1.5 text-left">
              <ChevronRight className={cn("size-4 shrink-0 self-center text-muted transition-transform group-hover:text-ink", open && "rotate-90")} />
              <h2 className="min-w-0 truncate text-[17px] font-bold tracking-tight group-hover:text-accent">{pg.project || "No project"}</h2>
              <span className="shrink-0 text-[12.5px] text-muted">{plural(pg.decks.length, "deck")} · {plural(pg.slides, "slide")}</span>
            </button>
            {open && (
              <ul id={listId} className="mb-5 mt-1 space-y-4">
                {pg.decks.map(group => {
                  const { deck, count } = group;
                  const shown = g.deckOpen(deck.id);
                  const slides = g.slidesOf(deck.id);
                  const picked = slides.items.reduce((n, s) => n + (selected.has(s.id) ? 1 : 0), 0);
                  const bodyId = `${uid}-d${deck.id}`;
                  return (
                    <li key={deck.id}>
                      <DeckBar group={group} open={shown} onToggle={() => g.toggleDeck(deck.id)} bodyId={bodyId} actions={actions}
                        checked={picked === 0 ? false : picked >= count ? true : "mixed"}
                        newer={deck.superseded_by ? byId.get(deck.superseded_by) : undefined}
                        older={deck.supersedes_id ? byId.get(deck.supersedes_id) : undefined}
                        onEdit={() => setEditing(deck)} onDelete={() => setDeleting(deck)} />
                      {shown && (
                        <div id={bodyId} className="pt-3">
                          {slides.error ? <p className="px-1 text-[13px] text-bad">Couldn't load the slides: {slides.error}</p>
                            : !count ? <p className="px-1 text-[13px] text-muted">{deck.status === "ingesting" ? "Slides appear here as the deck is read." : deck.status === "error" ? "Nothing was imported." : "This deck has no slides."}</p>
                              : <>
                                <SlideCards items={slides.items} view={view} selected={selected} tags={tags} {...handlers} />
                                {slides.loading ? <div className="flex h-16 items-center justify-center text-muted"><Spinner /></div>
                                  : slides.rest > 0 && (
                                    <div className="flex justify-center pt-3">
                                      <Button size="sm" variant="ghost" onClick={() => g.showAll(deck.id)}>Show the other {plural(slides.rest, "slide")}</Button>
                                    </div>
                                  )}
                              </>}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        );
      })}
      {editing && <EditDeckDialog key={editing.id} deck={editing} onClose={() => setEditing(null)} />}
      <Dialog open={!!deleting} onOpenChange={o => !o && setDeleting(null)} title="Delete this deck from the library?"
        description={`“${deleting?.title || deleting?.filename}” and its ${deleting?.slide_count ?? 0} slides — with your favourites, tags and summaries — will be removed. This can't be undone.`}
        footer={<>
          <Button onClick={() => setDeleting(null)}>Keep it</Button>
          <Button variant="danger" loading={del.isPending} onClick={() => deleting && del.mutate(deleting.id)}>Delete deck</Button>
        </>} />
    </div>
  );
}
