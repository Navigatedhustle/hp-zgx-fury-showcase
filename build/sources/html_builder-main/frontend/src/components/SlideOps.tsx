import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, Combine, Feather, Library, Plus, Split, Trash2, Undo2, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { api, isRemoved, type Project, type Slide } from "../lib/api";
import { Badge, Button, Dialog, IconButton, Tip } from "./ui";

/* ------------------------------------------------------------------ slide management
 * Add, delete, merge, undo a split — for converted and composed decks alike (backend/app/pipeline/deckops.py).
 * On a converted deck nothing is destroyed: a deleted or merged-away slide leaves the deck and is listed under
 * "Out of the deck", from where it comes back in one click. */

export function useSlideOps(projectId: string) {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ["project", projectId] });
  const fail = (what: string) => (e: unknown) => toast.error(`Couldn't ${what}`, { description: (e as Error).message });
  return {
    add: useMutation({
      mutationFn: (after?: number) => api.addSlide(projectId, after),
      onSuccess: () => { done(); toast.success("Slide added", { description: "Give it a headline and some copy, then design it." }); },
      onError: fail("add a slide"),
    }),
    remove: useMutation({
      mutationFn: (s: Slide) => api.deleteSlide(s.id),
      onSuccess: (_, s) => {
        done();
        const madeHere = s.plan.added || s.plan.merged_from;
        toast.success(`Slide ${s.label} deleted`, madeHere ? undefined : {
          description: "It's listed under “Out of the deck” if you want it back.",
          action: { label: "Undo", onClick: () => api.restoreSlide(s.id, s.position - 1).then(done) },
        });
      },
      onError: fail("delete the slide"),
    }),
    restore: useMutation({
      mutationFn: (s: Slide) => api.restoreSlide(s.id),
      onSuccess: (_, s) => { done(); toast.success(`Slide ${s.label} is back in the deck`); },
      onError: fail("restore the slide"),
    }),
    merge: useMutation({
      mutationFn: (ids: string[]) => api.mergeSlides(projectId, ids),
      onSuccess: m => {
        done();
        toast.success(m.plan.merged_from ? `Merged into slide ${m.label}` : `Slide ${m.label} is one slide again`, {
          description: m.plan.merged_from
            ? "Planning the combined slide now. The originals are under “Out of the deck” — Unmerge brings them back."
            : "The split is undone, and a re-plan won't split it again.",
        });
      },
      onError: fail("merge those slides"),
    }),
    unmerge: useMutation({
      mutationFn: (s: Slide) => api.unmergeSlide(s.id),
      onSuccess: () => { done(); toast.success("Unmerged — the original slides are back"); },
      onError: fail("unmerge"),
    }),
  };
}
export type SlideOps = ReturnType<typeof useSlideOps>;

/** Badges and one-click actions about the slide's shape: merged, split, thin, or suggested for a merge. */
export function SlideShape({ s, all, ops, locked }: { s: Slide; all: Slide[]; ops: SlideOps; locked: boolean }) {
  const live = all.filter(x => !isRemoved(x));
  const parts = live.filter(x => x.index === s.index && x.parts > 1);
  // The planner names other slides by source index; point at the live slide that carries it now.
  const suggested = (s.plan.merge_with ?? [])
    .map(i => live.find(x => x.index === i && x.part === 0 && x.id !== s.id))
    .filter((x): x is Slide => !!x);
  return (
    <>
      {s.plan.library_source ? (
        <Tip label={`Inserted from ${s.plan.library_source.label || "the slide library"}. Its figures are checked against that slide, and the design cites it.`}>
          <span><Badge tone="accent"><Library className="size-3" />From the library</Badge></span>
        </Tip>
      ) : s.plan.added && <Badge tone="accent">Added here</Badge>}
      {s.plan.appendix && <Badge>Appendix</Badge>}
      {s.plan.merged_from && (
        <span className="flex items-center gap-1">
          <Badge tone="accent"><Combine className="size-3" />Merged from {s.plan.merged_labels?.join(" + ")}</Badge>
          {!locked && <Button size="sm" variant="ghost" icon={<Undo2 className="size-3.5" />} loading={ops.unmerge.isPending}
            onClick={() => ops.unmerge.mutate(s)}>Unmerge</Button>}
        </span>
      )}
      {s.parts > 1 && s.part === 0 && parts.length > 1 && !locked && (
        <Tip label={`The planner split slide ${s.index} into ${s.parts}. Put it back on one slide — a re-plan won't split it again.`}>
          <span><Button size="sm" variant="ghost" icon={<Split className="size-3.5" />} loading={ops.merge.isPending}
            onClick={() => ops.merge.mutate(parts.map(x => x.id))}>Undo split</Button></span>
        </Tip>
      )}
      {s.thin && (
        <Tip label="Very little on this slide — a heading and a line or two. Consider merging it with a related slide, or deleting it.">
          <span><Badge tone="warn"><Feather className="size-3" />Thin</Badge></span>
        </Tip>
      )}
      {!locked && suggested.map(o => (
        <Tip key={o.id} label={`The planner thinks slides ${s.label} and ${o.label} cover the same ground and would be stronger as one.`}>
          <span><Button size="sm" variant="ghost" icon={<Combine className="size-3.5" />} loading={ops.merge.isPending}
            onClick={() => ops.merge.mutate([s.id, o.id])}>Merge with {o.label}</Button></span>
        </Tip>
      ))}
    </>
  );
}

/** Per-row: add a slide below, delete this one. */
export function RowActions({ s, ops, locked, lastLive }: { s: Slide; ops: SlideOps; locked: boolean; lastLive: boolean }) {
  const [confirm, setConfirm] = useState(false);
  const madeHere = !!(s.plan.added || s.plan.merged_from);
  return (
    <div className="flex items-center">
      <IconButton label="Add a slide below" disabled={locked} onClick={() => ops.add.mutate(s.position)}><Plus className="size-4" /></IconButton>
      <Tip label={lastLive ? "A deck needs at least one slide." : "Delete this slide"}>
        <span><IconButton label="Delete this slide" disabled={locked || lastLive} onClick={() => setConfirm(true)}><Trash2 className="size-4" /></IconButton></span>
      </Tip>
      <Dialog open={confirm} onOpenChange={setConfirm} title={`Delete slide ${s.label}?`}
        description={madeHere
          ? s.plan.merged_from
            ? "This slide was made by a merge. Deleting it removes it; its original slides move to “Out of the deck”, where you can restore them."
            : "This slide was added here, so deleting it removes it and its designs for good."
          : "It leaves the deck with its designs, and is listed under “Out of the deck” — restore it any time."}
        footer={<><Button onClick={() => setConfirm(false)}>Keep it</Button>
          <Button variant="danger" onClick={() => { setConfirm(false); ops.remove.mutate(s); }}>Delete</Button></>} />
    </div>
  );
}

/** Shown while two or more slides are ticked. */
export function MergeBar({ selected, slides, ops, onClear }: { selected: string[]; slides: Slide[]; ops: SlideOps; onClear: () => void }) {
  if (selected.length < 2) return null;
  const picked = slides.filter(s => selected.includes(s.id));
  return (
    <div className="sticky top-0 z-10 flex flex-wrap items-center gap-2 border-b border-line-2 bg-accent-soft px-4 py-2 text-sm">
      <b>{picked.length} slides selected</b>
      <span className="text-muted">({picked.map(s => s.label).join(", ")})</span>
      <div className="ml-auto flex gap-2">
        <Button size="sm" variant="ghost" icon={<X className="size-3.5" />} onClick={onClear}>Clear</Button>
        <Button size="sm" variant="primary" icon={<Combine className="size-3.5" />} loading={ops.merge.isPending}
          disabled={picked.length > 4}
          onClick={() => ops.merge.mutate(picked.map(s => s.id), { onSuccess: onClear })}>
          {picked.length > 4 ? "Merge at most 4" : `Merge into one slide`}
        </Button>
      </div>
    </div>
  );
}

/** Slides that left the deck, and the way back. */
export function RemovedList({ p, ops, locked }: { p: Project; ops: SlideOps; locked: boolean }) {
  const all = p.slides ?? [];
  const removed = all.filter(isRemoved);
  const [open, setOpen] = useState(false);
  if (!removed.length) return null;
  const labelOf = (id?: string) => all.find(x => x.id === id)?.label ?? "?";
  return (
    <div className="border-t border-line-2">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-4 py-3 text-left text-[13px] font-semibold text-muted hover:text-ink">
        <ArchiveRestore className="size-4" />Out of the deck ({removed.length}) <span className="ml-auto text-xs">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <ul className="px-4 pb-3">
          {removed.map(s => (
            <li key={s.id} className="flex items-center gap-3 border-t border-line-2 py-2 text-[13px]">
              <span className="w-10 shrink-0 font-bold tabular-nums text-muted">{s.label}</span>
              <span className="min-w-0 flex-1 truncate">{s.plan.headline || s.source_title || "Untitled"}</span>
              {s.plan.removed === "merged"
                ? <span className="text-xs text-muted">Merged into slide {labelOf(s.plan.merged_into)} — unmerge it to bring this back</span>
                : <Button size="sm" variant="ghost" icon={<ArchiveRestore className="size-3.5" />} disabled={locked}
                    loading={ops.restore.isPending} onClick={() => ops.restore.mutate(s)}>Restore</Button>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
