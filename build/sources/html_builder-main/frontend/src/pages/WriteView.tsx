import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, ChevronDown, ChevronUp, GripVertical, Library, Plus, Sparkles, Trash2, Wand2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { FactContract } from "../components/FactLedger";
import { SlideImages } from "../components/ImagePicker";
import { ReferenceDocs } from "../components/ReferenceDocs";
import { InsertFromLibrary, insertSpots } from "../components/library/InsertFromLibrary";
import { Badge, Button, Dialog, Field, IconButton, Spinner, Textarea, Tip, inputClass } from "../components/ui";
import { api, isRemoved, type Project, type Slide } from "../lib/api";
import { cn } from "../lib/util";

/**
 * Where a deck that was written here gets its content.
 *
 * It is deliberately the same three things the converter extracts from a PowerPoint slide — a title,
 * the lines that go on it, and what the presenter says — because everything downstream reads exactly
 * that. What the user types IS the source here, so there is no "revert to the original": the fact
 * ledger under each slide is extracted from the typing on every save, and is what the finished design
 * will be held to.
 *
 * Drafting is offered, never imposed. An empty deck is a legitimate place to start and the blank slide
 * is right there; the draft button is for when a blank page is the problem rather than the point.
 */

const SAVE_DEBOUNCE_MS = 700;

/** A textarea that grows with its content instead of scrolling a fixed box. */
function AutoTextarea({ value, onChange, onBlur, label, placeholder, rows = 2, className }: {
  value: string; onChange: (v: string) => void; onBlur: () => void; label: string;
  placeholder?: string; rows?: number; className?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);
  return (
    <Textarea ref={ref} rows={rows} value={value} aria-label={label} placeholder={placeholder} spellCheck
      onChange={e => onChange(e.target.value)} onBlur={onBlur}
      className={cn("max-h-72 overflow-auto", className)} />
  );
}

/** The three fields of one slide, saved on a debounce and flushed on blur. */
function SlideCard({ projectId, slide, total, onMove, onDelete, onAddAfter }: {
  projectId: string; slide: Slide; total: number;
  onMove: (to: number) => void; onDelete: () => void; onAddAfter: () => void;
}) {
  const qc = useQueryClient();
  const server = {
    title: slide.content.title ?? "",
    body: (slide.content.text ?? []).flatMap(b => b.lines ?? []).join("\n"),
    notes: slide.content.speaker_notes ?? "",
  };
  const [draft, setDraft] = useState<typeof server | null>(null);
  const key = JSON.stringify(server);
  // The server caught up with the draft (or replaced it): follow the server again.
  if (draft !== null && JSON.stringify(draft) === key) setDraft(null);

  const sent = useRef<string | null>(key);
  const save = useMutation({
    mutationFn: (body: typeof server) => api.writeSlide(slide.id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project"] }),
    onError: e => toast.error("Couldn't save the slide", { description: (e as Error).message }),
  });
  const commit = (next: typeof server) => {
    const k = JSON.stringify(next);
    if (k === sent.current) return;
    sent.current = k;
    save.mutate(next);
  };
  useEffect(() => {
    if (draft === null) return;
    const t = window.setTimeout(() => commit(draft), SAVE_DEBOUNCE_MS);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  const v = draft ?? server;
  const set = (patch: Partial<typeof server>) => setDraft({ ...v, ...patch });
  const pos = slide.position - 1;

  return (
    <li className="rounded-xl border border-line bg-surface">
      <div className="flex items-center gap-2 border-b border-line-2 px-3 py-2">
        <GripVertical className="size-4 shrink-0 text-faint" aria-hidden />
        <span className="text-sm font-bold tabular-nums text-muted">{slide.position}</span>
        {save.isPending ? <span className="text-[11px] text-faint">Saving…</span>
          : draft !== null ? <span className="text-[11px] text-faint">Unsaved</span> : null}
        {slide.plan.library_source && (
          <Tip label={`Inserted from ${slide.plan.library_source.label || "the slide library"}. Its figures are checked against that slide, and the design cites it.`}>
            <span><Badge tone="accent"><Library className="size-3" />From the library</Badge></span>
          </Tip>
        )}
        <div className="ml-auto flex items-center">
          <IconButton label="Move up" disabled={pos === 0} onClick={() => onMove(pos - 1)}><ChevronUp className="size-4" /></IconButton>
          <IconButton label="Move down" disabled={pos >= total - 1} onClick={() => onMove(pos + 1)}><ChevronDown className="size-4" /></IconButton>
          <IconButton label="Add a slide below" onClick={onAddAfter}><Plus className="size-4" /></IconButton>
          <Tip label={total <= 1 ? "A deck needs at least one slide." : "Delete this slide"}>
            <span>
              <IconButton label="Delete this slide" disabled={total <= 1} onClick={onDelete}>
                <Trash2 className="size-4" />
              </IconButton>
            </span>
          </Tip>
        </div>
      </div>

      <div className="space-y-3 p-3">
        <input value={v.title} onChange={e => set({ title: e.target.value })} onBlur={() => commit(v)}
          aria-label={`Slide ${slide.position} title`} placeholder="An assertion, not a topic"
          className={cn(inputClass, "h-10 text-[15px] font-bold")} />
        <AutoTextarea value={v.body} onChange={body => set({ body })} onBlur={() => commit(v)} rows={3}
          label={`Slide ${slide.position} content`}
          placeholder={"What goes on the slide, one line each.\nTwo spaces to indent, **bold** for the line that matters."} />
        <AutoTextarea value={v.notes} onChange={notes => set({ notes })} onBlur={() => commit(v)}
          label={`Slide ${slide.position} speaker notes`} className="text-[13px]"
          placeholder="What you'll say. Detail that doesn't fit on the slide belongs here." />
        <div className="flex flex-wrap items-center gap-1.5"><SlideImages projectId={projectId} slide={slide} /></div>
        <CarriedData slide={slide} />
        <FactContract slide={slide} />
      </div>
    </li>
  );
}

const ANGLES = ["Executive pitch", "Technical deep-dive", "Financial case"];

/** Ask the model for a first draft. Replaces the deck, so it asks first once there is anything to lose. */
function DraftDialog({ project, open, onOpenChange }: {
  project: Project; open: boolean; onOpenChange: (o: boolean) => void;
}) {
  const qc = useQueryClient();
  const [about, setAbout] = useState("");
  const [source, setSource] = useState("");
  const [count, setCount] = useState(10);
  const [angle, setAngle] = useState("");
  // Sections the user took out. Nothing pasted + documents added = the draft comes from them, so which
  // parts of a long one it draws on is the user's call.
  const [off, setOff] = useState<Set<string>>(new Set());
  const sections = useQuery({ queryKey: ["docs", project.id, "sections"], queryFn: () => api.docSections(project.id), enabled: open });
  const fromDocs = !source.trim();
  const choices = (sections.data ?? []).filter(d => d.sections.length > 0);
  const all = choices.flatMap(d => d.sections.map(s => s.ref));
  const chosen = all.filter(r => !off.has(r));
  const pick = fromDocs && all.length > 1;
  const toggle = (refs: string[], on: boolean) => setOff(cur => {
    const next = new Set(cur);
    for (const r of refs) { if (on) next.delete(r); else next.add(r); }
    return next;
  });
  const draft = useMutation({
    mutationFn: () => api.draftOutline(project.id, {
      about, source_text: source, slides: count, angle,
      sections: pick && chosen.length < all.length ? chosen : undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["project", project.id] });
      onOpenChange(false);
      toast.success("Drafting the deck", { description: "Read it through and correct it — every figure in it becomes a fact the design is held to." });
    },
    onError: e => toast.error("Couldn't start the draft", { description: (e as Error).message }),
  });
  const written = (project.slides ?? []).some(s => s.content.title || (s.content.text ?? []).length);

  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Draft this deck"
      description="A starting point to correct, not a finished deck. Nothing is designed yet."
      footer={<>
        <Button onClick={() => onOpenChange(false)}>Cancel</Button>
        <Button variant="primary" loading={draft.isPending} icon={<Sparkles className="size-4" />}
          disabled={pick && chosen.length === 0} onClick={() => draft.mutate()}>Draft {count} slides</Button>
      </>}>
      <div className="space-y-4">
        <Field label="What is this deck for?" hint="Who is in the room, what you want them to do, what the argument is.">
          <Textarea rows={3} value={about} onChange={e => setAbout(e.target.value)}
            placeholder="Persuade the infrastructure board to standardise on Z8 workstations for the visualisation team." />
        </Field>
        <Field label="Material to work from" hint="Notes, an email, a report — anything with the real figures in it. Leave it empty to draft from the reference documents you added.">
          <Textarea rows={6} value={source} onChange={e => setSource(e.target.value)}
            placeholder="Paste the numbers, names and dates the deck should be built on." />
        </Field>
        {pick && (
          <Field label="Sections to draw on" hint={`${chosen.length} of ${all.length} sections. Untick what this deck is not about.`}>
            <div className="max-h-56 space-y-3 overflow-y-auto rounded-lg border border-line p-2.5">
              {choices.map(d => {
                const refs = d.sections.map(s => s.ref);
                const on = refs.filter(r => !off.has(r)).length;
                return (
                  <div key={d.doc_id}>
                    <label className="flex cursor-pointer items-center gap-2 text-[13px] font-bold">
                      <input type="checkbox" className="size-3.5 accent-[var(--accent)]" checked={on === refs.length}
                        ref={el => { if (el) el.indeterminate = on > 0 && on < refs.length; }}
                        onChange={e => toggle(refs, e.target.checked)} />
                      <span className="min-w-0 truncate">{d.name}</span>
                    </label>
                    {d.sections.length > 1 && (
                      <ul className="mt-1 space-y-1 pl-5">
                        {d.sections.map(s => (
                          <li key={s.ref}>
                            <label className="flex cursor-pointer items-start gap-2 text-[12.5px]">
                              <input type="checkbox" className="mt-0.5 size-3.5 shrink-0 accent-[var(--accent)]" checked={!off.has(s.ref)}
                                onChange={e => toggle([s.ref], e.target.checked)} />
                              <span className="min-w-0">
                                <span className="font-semibold">{s.title}</span>{s.where && <span className="text-muted"> · {s.where}</span>}
                                {s.summary && <span className="line-clamp-2 block text-muted">{s.summary}</span>}
                              </span>
                            </label>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>
          </Field>
        )}
        <Field label="What kind of deck?" hint="Decides what is selected from the material and how deep it goes. Optional.">
          <div className="flex flex-wrap gap-1.5">
            {ANGLES.map(a => (
              <button key={a} type="button" aria-pressed={angle === a} onClick={() => setAngle(angle === a ? "" : a)}
                className={cn("h-8 rounded-full border px-3 text-[13px] font-semibold",
                  angle === a ? "border-accent bg-accent-soft text-accent" : "border-line text-muted hover:text-ink")}>{a}</button>
            ))}
          </div>
        </Field>
        <Field label="About how many slides?">
          <input type="number" min={3} max={30} value={count} className={cn(inputClass, "h-9 w-24")}
            onChange={e => setCount(Math.max(3, Math.min(30, Number(e.target.value) || 10)))} />
        </Field>
        {written && (
          <p className="rounded-lg bg-warn-soft px-3 py-2 text-[13px] text-warn">
            This replaces the slides you have written.
          </p>
        )}
      </div>
    </Dialog>
  );
}

export default function WriteView({ project }: { project: Project }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [drafting, setDrafting] = useState(false);
  const [inserting, setInserting] = useState(false);
  const slides = (project.slides ?? []).filter(s => !isRemoved(s));
  const busy = project.status === "composing";
  const refresh = () => qc.invalidateQueries({ queryKey: ["project", project.id] });

  const add = useMutation({ mutationFn: (after?: number) => api.addSlide(project.id, after), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (id: string) => api.deleteSlide(id), onSuccess: refresh,
    onError: e => toast.error("Couldn't delete the slide", { description: (e as Error).message }) });
  const move = useMutation({ mutationFn: (v: { id: string; to: number }) => api.moveSlide(v.id, v.to), onSuccess: refresh });
  const plan = useMutation({
    mutationFn: () => api.replan(project.id),
    onSuccess: () => { refresh(); nav(`/p/${project.id}/plan`); },
    onError: e => toast.error("Couldn't plan the deck", { description: (e as Error).message }),
  });

  const empty = slides.every(s => !s.content.title && !(s.content.text ?? []).length);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 pb-24 pt-6 sm:px-6">
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-xl font-extrabold tracking-tight">Write the deck</h2>
            <p className="mt-1 text-sm text-muted">
              A title, what goes on the slide, and what you'll say. The design comes next — this is the content it
              will be built from, and held to.
            </p>
          </div>
          <Button icon={<Wand2 className="size-4" />} onClick={() => setDrafting(true)} disabled={busy}>
            {empty ? "Draft it for me" : "Redraft"}
          </Button>
        </div>

        {busy && (
          <div className="mt-6 flex items-center gap-3 rounded-xl border border-line bg-surface p-4">
            <Spinner className="size-4 text-accent" />
            <div className="text-sm font-semibold">{project.stage_note || "Drafting the deck"}</div>
          </div>
        )}

        <div className="mt-6"><ReferenceDocs projectId={project.id} locked={busy} /></div>

        {project.error && (
          <p className="mt-6 rounded-xl border border-bad/30 bg-bad-soft p-3 text-[13px] text-bad">{project.error}</p>
        )}

        <ul className="mt-6 space-y-3">
          {slides.map(s => (
            <SlideCard key={s.id} projectId={project.id} slide={s} total={slides.length}
              onMove={to => move.mutate({ id: s.id, to })}
              onDelete={() => remove.mutate(s.id)}
              onAddAfter={() => add.mutate(s.position)} />
          ))}
        </ul>

        <div className="mt-3 flex gap-2">
          <Button className="flex-1" icon={<Plus className="size-4" />} onClick={() => add.mutate(undefined)} disabled={busy}>
            Add a slide
          </Button>
          <Tip label="Bring slides from the slide library into this deck — their figures come with them and are checked.">
            <span className="flex"><Button icon={<Library className="size-4" />} onClick={() => setInserting(true)} disabled={busy}>
              Insert from library
            </Button></span>
          </Tip>
        </div>

        <div className="mt-8 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface p-4">
          <div className="min-w-0 flex-1">
            <div className="text-sm font-bold">Ready to design it?</div>
            <p className="mt-0.5 text-[13px] text-muted">
              {empty
                ? "Write at least one slide first, or have a draft written for you."
                : `${slides.length} ${slides.length === 1 ? "slide" : "slides"}. Planning decides the story and a design for each one; you can still change everything after.`}
            </p>
          </div>
          <Badge>{slides.length} slides</Badge>
          <Button variant="primary" icon={<ArrowRight className="size-4" />} disabled={empty || busy}
            loading={plan.isPending} onClick={() => plan.mutate()}>
            Plan the deck
          </Button>
        </div>
      </div>
      <DraftDialog project={project} open={drafting} onOpenChange={setDrafting} />
      <InsertFromLibrary projectId={project.id} open={inserting} onOpenChange={setInserting} defaultAfter={null}
        spots={insertSpots(slides.map(s => ({ position: s.position, label: String(s.position), title: s.content.title ?? "" })))} />
    </div>
  );
}

/** Tables and charts can't be typed here, but a slide inserted from the library keeps its own (and their
 * figures stay in the fact ledger). Without this line such a slide reads as empty. */
function CarriedData({ slide }: { slide: Slide }) {
  const tables = slide.content.tables?.length ?? 0;
  const charts = slide.content.charts?.length ?? 0;
  if (!tables && !charts) return null;
  const parts = [tables && `${tables} ${tables === 1 ? "table" : "tables"}`, charts && `${charts} ${charts === 1 ? "chart" : "charts"}`].filter(Boolean);
  return (
    <p className="text-[12px] text-muted">
      Also keeps {parts.join(" and ")}{slide.plan.library_source ? " from the library slide" : ""} — laid out in the design, figures unchanged.
    </p>
  );
}
