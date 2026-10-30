import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BarChart3, Check, Image as ImageIcon, Library, RefreshCw, Plus, Scissors, Sparkles, Table2, Wand2 } from "lucide-react";
import { Fragment, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { FactContract } from "../components/FactLedger";
import { CondenseDialog, CondensedBanner } from "../components/CondenseDialog";
import { InstructDialog } from "../components/DeckTools";
import { InsertFromLibrary, insertSpots } from "../components/library/InsertFromLibrary";
import { LibraryStar, SaveToLibraryButton } from "../components/library/LibraryStar";
import { SlideImages } from "../components/ImagePicker";
import { ReferenceDocs } from "../components/ReferenceDocs";
import { MergeBar, RemovedList, RowActions, SlideShape, useSlideOps, type SlideOps } from "../components/SlideOps";
import SlideContentEditor from "../components/SlideContentEditor";
import { Badge, Button, Dialog, Field, Spinner, Switch, Textarea, Tip, inputClass } from "../components/ui";
import { api, isRemoved, urls, type Project, type Slide } from "../lib/api";
import { libImage, useLibraryEvents } from "../lib/library";
import { cn, patterns } from "../lib/util";

function ImportProgress({ p }: { p: Project }) {
  const steps = [
    { key: "ingesting", label: "Read slides, text, charts and images" },
    { key: "render", label: "Render previews with PowerPoint" },
    { key: "planning", label: "Plan the story and a design for each slide" },
  ];
  const active = p.status === "planning" ? 2 : p.stage_note.toLowerCase().includes("render") ? 1 : 0;
  return (
    <div className="mx-auto max-w-xl px-6 py-16">
      <h2 className="text-2xl font-extrabold tracking-tight">Preparing {p.filename}</h2>
      <p className="mt-1 text-sm text-muted">This usually takes under a minute. You can leave this page; work continues on the server.</p>
      <ol className="mt-8 space-y-3">
        {steps.map((s, i) => (
          <li key={s.key} className={cn("flex items-center gap-3 rounded-xl border p-4 text-sm font-semibold",
            i === active ? "border-accent bg-surface" : "border-line bg-surface", i > active && "text-faint")}>
            <span className={cn("flex size-6 items-center justify-center rounded-full text-xs",
              i < active ? "bg-good text-white" : i === active ? "bg-accent-soft text-accent" : "bg-surface-2")}>
              {i < active ? <Check className="size-3.5" /> : i === active ? <Spinner className="size-3.5" /> : i + 1}
            </span>
            {s.label}
          </li>
        ))}
      </ol>
      {p.stage_note && <p className="mt-4 text-sm text-muted">{p.stage_note}…</p>}
    </div>
  );
}

function BriefCard({ p }: { p: Project }) {
  const qc = useQueryClient();
  const server = useMemo(
    () => ({ deck_title: p.deck_title, audience: p.brief.audience || "", tone: p.brief.tone || "", narrative: p.brief.narrative || "" }),
    [p.deck_title, p.brief]);
  const [form, setForm] = useState(server);
  // Adopt the server's values when they actually change — not on every refetch,
  // which would wipe what the user is typing.
  const serverKey = JSON.stringify(server);
  const [syncedKey, setSyncedKey] = useState(serverKey);
  if (syncedKey !== serverKey) { setSyncedKey(serverKey); setForm(server); }
  const save = useMutation({
    mutationFn: () => api.patchProject(p.id, { deck_title: form.deck_title, brief: { audience: form.audience, tone: form.tone, narrative: form.narrative } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project", p.id] }),
    onError: e => toast.error("Couldn't save the brief", { description: (e as Error).message }),
  });
  const split = useMutation({
    mutationFn: (allow_split: boolean) => api.patchProject(p.id, { brief: { allow_split } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project", p.id] }),
    onError: e => toast.error("Couldn't save that setting", { description: (e as Error).message }),
  });
  const dirty = form.deck_title !== p.deck_title || form.audience !== (p.brief.audience || "") || form.tone !== (p.brief.tone || "") || form.narrative !== (p.brief.narrative || "");
  const blur = () => dirty && save.mutate();
  return (
    <section className="rounded-2xl border border-line bg-surface p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-bold">Deck brief</h2>
        <span className="text-xs text-muted">{save.isPending ? "Saving…" : dirty ? "Unsaved" : "Saved"}</span>
      </div>
      <div className="space-y-4">
        <Field label="Deck title"><input className={inputClass} value={form.deck_title} onChange={e => setForm({ ...form, deck_title: e.target.value })} onBlur={blur} /></Field>
        <Field label="Audience" hint="Who is in the room? The model tunes language and emphasis to them.">
          <input className={inputClass} value={form.audience} onChange={e => setForm({ ...form, audience: e.target.value })} onBlur={blur} />
        </Field>
        <Field label="Tone"><input className={inputClass} value={form.tone} onChange={e => setForm({ ...form, tone: e.target.value })} onBlur={blur} /></Field>
        <Field label="Story" hint="The arc of the deck, in two or three sentences.">
          <Textarea rows={5} value={form.narrative} onChange={e => setForm({ ...form, narrative: e.target.value })} onBlur={blur} />
        </Field>
        <label className="flex items-start justify-between gap-3 text-[13px]">
          <span>
            <span className="font-semibold text-ink">Split dense slides</span>
            <span className="mt-0.5 block text-xs text-muted">When off, every PowerPoint slide stays one slide and detail moves to the notes. Applies on the next re-plan.</span>
          </span>
          <Switch checked={p.brief.allow_split !== false} label="Split dense slides"
            onCheckedChange={v => split.mutate(v)} />
        </label>
      </div>
    </section>
  );
}

/** A slide of the PowerPoint itself — not added, merged or inserted here — so it has a library twin (by render index). */
/** The picture of where a slide came from: its PowerPoint render, or the library slide it was inserted from. */
const originalSrc = (s: Slide, thumb = false) =>
  s.plan.library_source ? libImage(s.plan.library_source.lib_slide_id, thumb) : urls.source(s.id, thumb);

const isSourceSlide = (s: Slide) => !s.plan.added && !s.plan.merged_from && !s.plan.library_source && s.part === 0;

function SlideRow({ projectId, s, all, ops, selected, onSelect, lastLive, onZoom, locked, converted }: {
  projectId: string; s: Slide; all: Slide[]; ops: SlideOps; selected: boolean; onSelect: (on: boolean) => void;
  lastLive: boolean; onZoom: (s: Slide) => void; locked: boolean; converted: boolean;
}) {
  const qc = useQueryClient();
  const serverHeadline = s.plan.headline || "";
  const [headline, setHeadline] = useState(serverHeadline);
  const [syncedHeadline, setSyncedHeadline] = useState(serverHeadline);
  if (syncedHeadline !== serverHeadline) { setSyncedHeadline(serverHeadline); setHeadline(serverHeadline); }
  const patch = useMutation({
    mutationFn: (body: Parameters<typeof api.patchSlide>[1]) => api.patchSlide(s.id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project"] }),
    onError: e => toast.error("Couldn't update the slide", { description: (e as Error).message }),
  });
  const [thumbOk, setThumbOk] = useState(true);
  return (
    <li className={cn("grid grid-cols-[28px_132px_1fr] items-start gap-4 border-b border-line-2 px-4 py-4 last:border-0 sm:grid-cols-[28px_132px_1fr_auto]",
      !s.included && "opacity-55", selected && "bg-accent-soft/40")}>
      <label className="flex flex-col items-start gap-1.5 pt-1">
        <span className="text-sm font-bold tabular-nums text-muted">{s.label ?? s.index}</span>
        <input type="checkbox" checked={selected} disabled={locked} onChange={e => onSelect(e.target.checked)}
          aria-label={`Select slide ${s.label} to merge`} className="size-4 accent-[var(--color-accent)]" />
      </label>
      <button onClick={() => onZoom(s)} className="relative aspect-video w-[132px] overflow-hidden rounded-md bg-surface-2 ring-1 ring-line-2 hover:ring-accent" aria-label={`Enlarge original slide ${s.index}`}>
        {thumbOk ? <img src={originalSrc(s, true)} alt="" loading="lazy" className="size-full object-contain" onError={() => setThumbOk(false)} />
          : <span className="flex size-full items-center justify-center text-[11px] text-faint">No preview</span>}
      </button>
      <div className="min-w-0 space-y-2">
        <div className="flex items-center gap-2">
          <div className="min-w-0 flex-1 truncate text-xs text-muted" title={s.source_title}>
            Original: {s.source_title || "untitled"}
          </div>
          {s.parts > 1 && (
            <Tip label={`Slide ${s.index} carried more than one slide's worth of content, so it was split into ${s.parts}. Both parts share the original.`}>
              <span><Badge>Part {s.part + 1} of {s.parts}</Badge></span>
            </Tip>
          )}
          {converted && isSourceSlide(s) && <LibraryStar projectId={projectId} slideId={s.id} kind="source" />}
          <RowActions s={s} ops={ops} locked={locked} lastLive={lastLive} />
        </div>
        <input value={headline} disabled={locked} onChange={e => setHeadline(e.target.value)}
          onBlur={() => headline !== (s.plan.headline || "") && patch.mutate({ plan: { headline } })}
          className={cn(inputClass, "h-9 font-semibold")} aria-label={`Headline for slide ${s.label ?? s.index}`} />
        {s.plan.key_message && <p className="line-clamp-2 text-[13px] text-muted">{s.plan.key_message}</p>}
        <div className="flex flex-wrap items-center gap-1.5">
          {s.has_chart && <Badge><BarChart3 className="size-3" />Chart data</Badge>}
          {s.has_table && <Badge><Table2 className="size-3" />Table</Badge>}
          {s.image_count > 0 && <Badge><ImageIcon className="size-3" />{s.image_count} image{s.image_count > 1 ? "s" : ""}</Badge>}
          {s.warnings.length > 0 && <Tip label={s.warnings.join("; ")}><span><Badge tone="warn"><AlertTriangle className="size-3" />{s.warnings.length} skipped</Badge></span></Tip>}
          <SlideImages projectId={projectId} slide={s} locked={locked} />
          <SlideShape s={s} all={all} ops={ops} locked={locked} />
        </div>
        <SlideContentEditor slide={s} locked={locked} saving={patch.isPending} onPatch={patch.mutate} />
        <FactContract slide={s} locked={locked} onPatch={patch.mutate} />
      </div>
      <div className="col-span-3 flex items-center gap-3 sm:col-span-1 sm:flex-col sm:items-end">
        <select value={s.plan.pattern || ""} disabled={locked} onChange={e => patch.mutate({ plan: { pattern: e.target.value } })}
          className={cn(inputClass, "w-40")} aria-label={`Layout pattern for slide ${s.label ?? s.index}`}>
          {!patterns.includes(s.plan.pattern || "") && s.plan.pattern && <option>{s.plan.pattern}</option>}
          {patterns.map(x => <option key={x} value={x}>{x.replace("-", " ")}</option>)}
        </select>
        <label className="flex items-center gap-2 text-[13px] font-semibold text-muted">
          In deck <Switch checked={s.included} onCheckedChange={v => patch.mutate({ included: v })} label={`Include slide ${s.label ?? s.index}`} />
        </label>
      </div>
    </li>
  );
}

export default function PlanView({ project: p }: { project: Project }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [zoom, setZoom] = useState<Slide | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
  const [condense, setCondense] = useState(false);
  const [instruct, setInstruct] = useState(false);
  const [inserting, setInserting] = useState(false);
  const ops = useSlideOps(p.id);
  const converted = p.source !== "composed";
  useLibraryEvents();
  const every = p.slides ?? [];
  const slides = every.filter(s => !isRemoved(s));
  const designed = slides.filter(s => s.versions.length > 0).length;
  const pending = slides.filter(s => s.included && s.versions.length === 0);
  const busy = p.status === "generating" || p.counts.generating > 0;

  const generate = useMutation({
    mutationFn: (ids?: string[]) => api.generate(p.id, ids),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["project", p.id] }); nav(`/p/${p.id}/review`); },
    onError: e => toast.error("Couldn't start designing", { description: (e as Error).message }),
  });
  const replan = useMutation({
    mutationFn: () => api.replan(p.id),
    onSuccess: () => { toast.success("Re-planning the deck"); qc.invalidateQueries({ queryKey: ["project", p.id] }); },
    onError: e => toast.error("Couldn't re-plan", { description: (e as Error).message }),
  });

  if (["uploaded", "ingesting", "planning"].includes(p.status)) return <ImportProgress p={p} />;
  if (p.status === "error" && slides.length === 0) {
    return <div className="mx-auto max-w-xl px-6 py-16"><div className="rounded-xl border border-bad/30 bg-bad-soft p-5 text-sm text-bad"><b>Import failed.</b> {p.error}<div className="mt-2 text-ink">Check that the file opens in PowerPoint, then upload it again from the home page.</div></div></div>;
  }

  // One ticked slide says where: right after it. Otherwise at the end.
  const tickedLive = slides.filter(s => picked.includes(s.id));
  const insertAfter = tickedLive.length === 1 ? tickedLive[0]?.position ?? null : null;

  const primary = designed === 0
    ? { label: `Design ${p.counts.included} slides`, run: () => generate.mutate(undefined) }
    : pending.length
      ? { label: `Design ${pending.length} new slide${pending.length > 1 ? "s" : ""}`, run: () => generate.mutate(pending.map(s => s.id)) }
      : { label: "Go to review", run: () => nav(`/p/${p.id}/review`) };

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-auto scroll-thin">
        <div className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[340px_1fr]">
          <div className="space-y-4 lg:sticky lg:top-6 lg:self-start">
            <BriefCard p={p} />
            <ReferenceDocs projectId={p.id} locked={busy} replanning={replan.isPending} onReplan={() => replan.mutate()} />
            {p.warnings.length > 0 && (
              <div className="rounded-xl border border-warn/30 bg-warn-soft p-4 text-[13px] text-warn">
                <b>Some content was skipped:</b>
                <ul className="mt-1 list-disc pl-4">{p.warnings.slice(0, 5).map(w => <li key={w}>{w}</li>)}</ul>
              </div>
            )}
            {p.renderer === "none" && (
              <div className="rounded-xl border border-line bg-surface p-4 text-[13px] text-muted">
                Slide previews weren't rendered (PowerPoint and LibreOffice unavailable). Designs are still generated from the slide content.
              </div>
            )}
          </div>
          <section className="rounded-2xl border border-line bg-surface">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line-2 px-4 py-3">
              <div>
                <h2 className="text-base font-bold">Slide plan</h2>
                <p className="text-[13px] text-muted">Edit headlines, layouts and the slide copy before designing — edited copy is used word for word. Tick two or more slides to merge them; delete the ones you don't need.</p>
              </div>
              <div className="flex flex-wrap gap-1">
                {converted && <SaveToLibraryButton projectId={p.id} kind="source" label="Save deck to library" />}
                <Tip label="One instruction for every designed slide — e.g. “less text everywhere”.">
                  <span><Button size="sm" variant="ghost" icon={<Wand2 className="size-3.5" />} disabled={busy || designed === 0}
                    onClick={() => setInstruct(true)}>Instruct deck</Button></span>
                </Tip>
                <Tip label="Cut the deck to the slides you have time for. Leftovers become appendix slides; undoable.">
                  <span><Button size="sm" variant="ghost" icon={<Scissors className="size-3.5" />} disabled={busy || slides.length < 3}
                    onClick={() => setCondense(true)}>Condense</Button></span>
                </Tip>
                <Button size="sm" variant="ghost" icon={<RefreshCw className="size-3.5" />} loading={replan.isPending} disabled={busy} onClick={() => replan.mutate()}>Re-plan</Button>
              </div>
            </div>
            <CondensedBanner p={p} />
            <MergeBar selected={picked.filter(id => slides.some(s => s.id === id))} slides={slides} ops={ops} onClear={() => setPicked([])} />
            <ul>{slides.map((s, i) => (
              <Fragment key={s.id}>
              {s.plan.appendix && !slides[i - 1]?.plan.appendix && (
                <li className="border-b border-line-2 bg-surface-2 px-4 py-2 text-[11px] font-bold uppercase tracking-wide text-muted">
                  Appendix — backup slides after the main deck
                </li>
              )}
              <SlideRow projectId={p.id} s={s} all={every} ops={ops} onZoom={setZoom} locked={busy} converted={converted}
                lastLive={slides.length <= 1} selected={picked.includes(s.id)}
                onSelect={on => setPicked(list => on ? [...list, s.id] : list.filter(x => x !== s.id))} />
              </Fragment>
            ))}</ul>
            <div className="flex flex-wrap gap-1 border-t border-line-2 px-4 py-2">
              <Button size="sm" variant="ghost" icon={<Plus className="size-3.5" />} disabled={busy} loading={ops.add.isPending}
                onClick={() => ops.add.mutate(undefined)}>Add a slide</Button>
              <Tip label="Bring slides from the slide library into this deck — their figures come with them and are checked.">
                <span><Button size="sm" variant="ghost" icon={<Library className="size-3.5" />} disabled={busy}
                  onClick={() => setInserting(true)}>Insert from library</Button></span>
              </Tip>
            </div>
            <RemovedList p={p} ops={ops} locked={busy} />
          </section>
        </div>
      </div>
      <footer className="border-t border-line bg-surface">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-3 sm:px-6">
          <p className="text-sm text-muted">
            <b className="text-ink">{p.counts.included - (p.counts.appendix ?? 0)}</b> of {p.counts.slides} slides in the deck
            {!!p.counts.appendix && <> + <b className="text-ink">{p.counts.appendix}</b> appendix</>}
            {designed > 0 && <> · <b className="text-ink">{designed}</b> designed</>}
          </p>
          <div className="ml-auto flex gap-2">
            {designed > 0 && <Button onClick={() => setConfirm(true)} disabled={busy}>Redesign all</Button>}
            <Button variant="primary" icon={<Sparkles className="size-4" />} loading={generate.isPending} disabled={busy && designed === 0} onClick={primary.run}>{primary.label}</Button>
          </div>
        </div>
      </footer>
      <CondenseDialog p={p} open={condense} onOpenChange={setCondense} keep={picked} />
      <InstructDialog p={p} open={instruct} onOpenChange={setInstruct} selected={picked} />
      <InsertFromLibrary projectId={p.id} open={inserting} onOpenChange={setInserting}
        spots={insertSpots(slides.map(s => ({ position: s.position, label: s.label, title: s.plan.headline || s.source_title })))}
        defaultAfter={insertAfter} />
      <Dialog open={!!zoom} onOpenChange={o => !o && setZoom(null)} wide title={`Original slide ${zoom?.index}`} description={zoom?.source_title}>
        {zoom && <img src={originalSrc(zoom)} alt={`Original slide ${zoom.index}`} className="w-full rounded-lg ring-1 ring-line" />}
        {zoom?.notes && <p className="mt-4 whitespace-pre-wrap rounded-lg bg-surface-2 p-3 text-sm text-muted"><b className="text-ink">Speaker notes: </b>{zoom.notes}</p>}
      </Dialog>
      <Dialog open={confirm} onOpenChange={setConfirm} title="Redesign every slide?"
        description="New Cinematic and Refined designs are created for all slides in the deck. Existing designs stay in each slide's history, but approvals are cleared."
        footer={<><Button onClick={() => setConfirm(false)}>Cancel</Button>
          <Button variant="primary" onClick={() => { setConfirm(false); generate.mutate(undefined); }}>Redesign all</Button></>} />
    </div>
  );
}
