import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlignCenter, AlignHorizontalSpaceAround, AlignLeft, AlignRight, AlignVerticalSpaceAround, AlertTriangle, Bold,
  CaseUpper, ChevronDown, ChevronUp, Columns3, ImageUp, Loader2, Lock, Maximize2, Palette, PaintBucket, Pencil, Rows3,
  Scaling, Space, Squircle, SquareDashed, Trash2, Type, Undo2, X,
} from "lucide-react";
import { useCallback, useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { api, type EditFailure, type EditNote, type EditOp, type ElementInfo } from "../lib/api";
import { cn, editFailure, editOpLabel, elementLabel, lockReason } from "../lib/util";
import type { EditSelection, ElementLock, FrameEditEvent } from "./SlideFrame";
import { ImagePicker } from "./ImagePicker";
import { Button, Tip } from "./ui";

/* ------------------------------------------------------------------ what the server will accept
 * Every value below is one backend/app/edit.py's allowlist passes: an allowed property and a token
 * shape it can parse. Offering a control that always 400s is worse than not having the control, so
 * nothing here is invented — the colours and sizes are brand tokens from runtime/tokens.css, and an
 * empty value is the engine's way of removing a declaration. `hex` is only for the swatch, because
 * the builder's own stylesheet doesn't define the deck's variables. */
interface Choice { label: string; value: string; hex?: string }

const COLORS: Choice[] = [
  { label: "Ink", value: "var(--ink)", hex: "#0A0A0F" },
  { label: "Blue", value: "var(--blue)", hex: "#024AD8" },
  { label: "Muted", value: "var(--mute)", hex: "#565C6E" },
  { label: "Paper", value: "var(--paper)", hex: "#FFFFFF" },
  { label: "Sky", value: "var(--sky)", hex: "#8FD3FF" },
  { label: "Positive", value: "var(--good)", hex: "#0B8F5E" },
  { label: "Caution", value: "var(--warn)", hex: "#B86E00" },
  { label: "Alert", value: "var(--alert)", hex: "#C81E3C" },
  { label: "Back to the design", value: "", hex: undefined },
];

const FILLS: Choice[] = [
  { label: "Tint", value: "var(--tint)", hex: "#E8EEFC" },
  { label: "Track", value: "var(--track)", hex: "#F2F4FA" },
  { label: "Paper", value: "var(--paper)", hex: "#FFFFFF" },
  { label: "Blue", value: "var(--blue)", hex: "#024AD8" },
  { label: "Ink", value: "var(--ink)", hex: "#0A0A0F" },
  { label: "No fill", value: "", hex: undefined },
];

// font-size is a layout property: the server flags these for a QA re-check, which is correct.
const SIZES: Choice[] = [
  { label: "Hero", value: "var(--t-hero)" }, { label: "Title", value: "var(--t-title)" },
  { label: "Heading", value: "var(--t-h2)" }, { label: "Subhead", value: "var(--t-h3)" },
  { label: "Lede", value: "var(--t-lede)" }, { label: "Body", value: "var(--t-body)" },
  { label: "Small", value: "var(--t-small)" }, { label: "Caption", value: "var(--t-micro)" },
  { label: "Back to the design", value: "" },
];

const WEIGHTS: Choice[] = [
  { label: "Regular", value: "400" }, { label: "Semibold", value: "600" }, { label: "Bold", value: "800" },
  { label: "Back to the design", value: "" },
];

/* ------------------------------------------------------------------ layout
 * Resizing is a drag on the slide itself; these are the reshaping decisions a drag cannot express —
 * how many columns a grid has, which way a row stacks, how much air is inside and between things.
 * Every value is one edit.py's allowlist passes, and none of them takes an element out of the
 * 1600x900 flow the slide's CSS was written against: that is why `position` and `transform` stay
 * refused and a drag writes `width`, never a coordinate. */

const COLUMNS: Choice[] = [
  { label: "One across", value: "1fr" }, { label: "Two across", value: "repeat(2, 1fr)" },
  { label: "Three across", value: "repeat(3, 1fr)" }, { label: "Four across", value: "repeat(4, 1fr)" },
  { label: "Wide then narrow", value: "2fr 1fr" }, { label: "Narrow then wide", value: "1fr 2fr" },
  { label: "Back to the design", value: "" },
];

const DIRECTION: Choice[] = [
  { label: "Side by side", value: "row" }, { label: "Stacked", value: "column" },
  { label: "Side by side, reversed", value: "row-reverse" }, { label: "Stacked, reversed", value: "column-reverse" },
  { label: "Back to the design", value: "" },
];

// The spacing scale from runtime/tokens.css, so a hand edit lands on the same rhythm as the design.
const SPACE: Choice[] = [
  { label: "None", value: "0" }, { label: "Tight", value: "var(--s-1)" }, { label: "Snug", value: "var(--s-2)" },
  { label: "Normal", value: "var(--s-3)" }, { label: "Roomy", value: "var(--s-4)" },
  { label: "Generous", value: "var(--s-5)" }, { label: "Back to the design", value: "" },
];

const ALIGN: Choice[] = [
  { label: "Top", value: "flex-start" }, { label: "Middle", value: "center" },
  { label: "Bottom", value: "flex-end" }, { label: "Stretch", value: "stretch" },
  { label: "Back to the design", value: "" },
];

const JUSTIFY: Choice[] = [
  { label: "Start", value: "flex-start" }, { label: "Centre", value: "center" },
  { label: "End", value: "flex-end" }, { label: "Spread out", value: "space-between" },
  { label: "Back to the design", value: "" },
];

// Dragging a handle writes width/height/flex-basis; this is the only way back to the design's own size.
const SIZE_RESET: Choice[] = [{ label: "Back to the design's size", value: "" }];

// An <img> sits inside `.figure img{max-width:80%;max-height:80%}` and is capped at its natural size, so a
// size that only set `width` would do nothing past the cap. Each preset lifts the caps with it; the width is
// a share of the image's frame, so it means the same thing whatever the layout. Height follows the ratio.
const IMG_UNCAP = { height: "auto", "max-width": "none", "max-height": "none" };
const IMAGE_SIZES: { label: string; style: Record<string, string> }[] = [
  { label: "Small", style: { width: "35%", ...IMG_UNCAP } },
  { label: "Medium", style: { width: "55%", ...IMG_UNCAP } },
  { label: "Large", style: { width: "80%", ...IMG_UNCAP } },
  { label: "Fill the frame", style: { width: "100%", height: "100%", "max-width": "none", "max-height": "none", "object-fit": "contain" } },
  { label: "Back to the design", style: { width: "", height: "", "max-width": "", "max-height": "", "object-fit": "" } },
];

const RADIUS: Choice[] = [
  { label: "Square", value: "0" }, { label: "Slight", value: "var(--r-s)" },
  { label: "Rounded", value: "var(--r-m)" }, { label: "Very rounded", value: "var(--r-l)" },
  { label: "Pill", value: "999px" }, { label: "Back to the design", value: "" },
];

/* ------------------------------------------------------------------ the session */

/** Fold a new op into the pending list: one op per element per kind, last value wins. */
function mergeOp(list: EditOp[], op: EditOp): EditOp[] {
  if (list.some(o => o.op === "delete" && o.eid === op.eid)) return list;  // already going away
  if (op.op === "delete") return [...list.filter(o => o.eid !== op.eid), op];
  const i = list.findIndex(o => o.op === op.op && o.eid === op.eid);
  if (i < 0) return [...list, op];
  const out = [...list];
  out[i] = op.op === "set_style"
    ? { ...op, style: { ...(out[i] as Extract<EditOp, { op: "set_style" }>).style, ...op.style } }
    : op;
  return out;
}

export interface EditSession {
  projectId: string;
  /** The version being edited, or null when edit mode is off. */
  vid: string | null;
  elements: Record<string, ElementInfo>;
  locks: Record<string, ElementLock>;
  loading: boolean;
  error: Error | null;
  selected: string | null;
  setSelected: (eid: string | null) => void;
  pending: EditOp[];
  push: (op: EditOp) => void;
  drop: (i: number) => void;
  handle: (e: FrameEditEvent) => void;
  save: () => void;
  saving: boolean;
  warnings: EditNote[];
  failure: EditFailure | null;
  start: (vid: string) => void;
  stop: () => void;
}

/**
 * One editing session = one new version.
 *
 * The boundary is an explicit **Save**, not a debounce: an op queue the user can read and undo makes
 * the batch a decision rather than a side effect of pausing, and the result is one reviewable entry
 * in the slide's history instead of a version per keystroke. Ops are queued locally, so the SSE
 * stream invalidating `["project"]` in the background never touches work in progress.
 */
export function useEditSession(projectId: string): EditSession {
  const qc = useQueryClient();
  const [vid, setVid] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [pending, setPending] = useState<EditOp[]>([]);
  const [warnings, setWarnings] = useState<EditNote[]>([]);
  const [failure, setFailure] = useState<EditFailure | null>(null);

  const outline = useQuery({
    queryKey: ["outline", vid],
    queryFn: () => api.outline(vid as string),
    enabled: !!vid,
    // The ids are stamped and persisted server-side, so they can't drift under an open session;
    // refetching mid-edit would only throw the locks map away and back again.
    staleTime: Infinity,
    retry: false,
  });

  const els = outline.data?.elements;
  const elements = useMemo(() => Object.fromEntries((els ?? []).map(e => [e.eid, e])), [els]);
  const locks = useMemo(
    () => Object.fromEntries((els ?? []).map(e => [e.eid, { editable_text: e.editable_text, deletable: e.deletable, locks: e.locks }])),
    [els],
  );

  const push = useCallback((op: EditOp) => {
    setFailure(null);
    setPending(list => mergeOp(list, op));
  }, []);
  const drop = useCallback((i: number) => {
    setFailure(null);
    setPending(list => list.filter((_, k) => k !== i));
  }, []);

  const handle = useCallback((e: FrameEditEvent) => {
    if (e.kind === "select") setSelected(e.sel?.eid ?? null);
    else if (e.kind === "op") push(e.op);
    else if (e.kind === "dirty") push({ op: "set_text", eid: e.eid, text: e.text });
  }, [push]);

  const reset = (id: string | null) => {
    setVid(id);
    setSelected(null);
    setPending([]);
    setWarnings([]);
    setFailure(null);
  };

  const saver = useMutation({
    mutationFn: ({ id, ops }: { id: string; ops: EditOp[] }) => api.editVersion(id, ops),
    onSuccess: res => {
      setPending([]);
      setSelected(null);
      setFailure(null);
      setWarnings(res.warnings);
      qc.invalidateQueries({ queryKey: ["project", projectId] });
      if (!res.changed) {
        toast("Nothing changed", { description: "Your edits left the slide exactly as it was." });
        return;
      }
      setVid(res.version.id);  // keep editing, now on top of the version that was just written
      toast.success(`Saved as v${res.version.number}`, {
        description: res.qa_recommended
          ? "Re-checking the layout, because the change can move things around."
          : "Hand-edited — no model involved. The previous version is still in the history.",
      });
    },
    onError: e => {
      const f = editFailure(e);
      setFailure(f);
      toast.error("That change was refused", { description: f?.message ?? (e as Error).message });
    },
  });

  const save = useCallback(() => {
    if (vid && pending.length) saver.mutate({ id: vid, ops: pending });
  }, [vid, pending, saver]);

  return {
    projectId, vid, elements, locks, loading: outline.isLoading, error: (outline.error as Error) ?? null,
    selected, setSelected, pending, push, drop, handle, save, saving: saver.isPending, warnings, failure,
    start: (id: string) => reset(id),
    stop: () => reset(null),
  };
}

/* ------------------------------------------------------------------ floating toolbar */
function Swatch({ hex }: { hex?: string }) {
  return hex
    ? <span className="size-3.5 shrink-0 rounded-full ring-1 ring-line" style={{ background: hex }} />
    : <Undo2 className="size-3.5 shrink-0 text-muted" />;
}

function Menu({ label, icon, choices, onPick, swatches }: {
  label: string; icon: ReactNode; choices: Choice[]; onPick: (value: string) => void; swatches?: boolean;
}) {
  return (
    <Dropdown.Root>
      <Tip label={label}>
        <Dropdown.Trigger aria-label={label}
          className="inline-flex size-8 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-ink">
          {icon}
        </Dropdown.Trigger>
      </Tip>
      <Dropdown.Portal>
        <Dropdown.Content align="start" sideOffset={6} className="z-50 w-48 rounded-xl border border-line bg-surface p-1 shadow-card">
          <Dropdown.Label className="px-2.5 py-1.5 text-[11px] font-bold uppercase tracking-wide text-faint">{label}</Dropdown.Label>
          {choices.map(c => (
            <Dropdown.Item key={c.label} onSelect={() => onPick(c.value)}
              className="flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13px] font-semibold outline-none data-[highlighted]:bg-surface-2">
              {swatches ? <Swatch hex={c.hex} /> : c.value === "" ? <Undo2 className="size-3.5 text-muted" /> : null}
              {c.label}
            </Dropdown.Item>
          ))}
        </Dropdown.Content>
      </Dropdown.Portal>
    </Dropdown.Root>
  );
}

function Pill({ label, icon, disabled, onClick, tone }: {
  label: string; icon: ReactNode; disabled?: boolean; onClick: () => void; tone?: "bad";
}) {
  return (
    <Tip label={label}>
      <button aria-label={label} disabled={disabled} onClick={onClick}
        className={cn("inline-flex size-8 items-center justify-center rounded-lg transition-colors disabled:cursor-not-allowed disabled:opacity-35",
          tone === "bad" ? "text-bad hover:bg-bad-soft" : "text-muted hover:bg-surface-2 hover:text-ink")}>
        {icon}
      </button>
    </Tip>
  );
}

/**
 * The controls for the selected element, floated over the stage.
 * `box` arrives already converted from stage coordinates to CSS pixels by SlideFrame.
 */
export function ElementToolbar({ sel, box, session }: {
  sel: EditSelection; box: { left: number; top: number; width: number; height: number }; session: EditSession;
}) {
  const [text, setText] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const el: ElementInfo | undefined = session.elements[sel.eid];
  const isImage = sel.tag === "img";
  // The outline is the server's own answer; the frame's flags are the fallback before it lands.
  const canText = el ? el.editable_text && !el.has_children : sel.canText && !sel.text.includes("\n");
  const canDelete = el ? el.deletable : sel.canDelete;
  const siblings = el ? Object.values(session.elements).filter(e => e.parent === el.parent).length : 0;
  const style = (prop: string, value: string) => session.push({ op: "set_style", eid: sel.eid, style: { [prop]: value } });

  const below = box.top < 56;
  const pos = { left: Math.max(4, box.left), top: below ? box.top + box.height + 8 : box.top - 46 };

  return (
    <div className="on-light pointer-events-auto absolute z-20 flex items-center gap-0.5 rounded-xl border border-line bg-surface p-1 shadow-card"
      style={pos} role="toolbar" aria-label={`Edit ${elementLabel(el)}`} onPointerDown={e => e.stopPropagation()}>
      {text === null ? (
        <>
          <span className="max-w-28 shrink-0 truncate px-2 text-[11px] font-bold text-muted" title={`<${sel.tag}> ${sel.classes.join(" ")}`}>
            {elementLabel(el) || `<${sel.tag}>`}
          </span>
          <span className="mx-0.5 h-5 w-px bg-line-2" />
          {canText
            ? <Pill label="Edit the text" icon={<Pencil className="size-4" />} onClick={() => setText(el?.text ?? sel.text)} />
            : <Tip label={el?.has_children ? "This block holds other elements — edit those instead." : "The runtime writes this element's content."}>
                <span className="inline-flex size-8 items-center justify-center rounded-lg text-faint"><Pencil className="size-4" /></span>
              </Tip>}
          {isImage && (
            <>
              <Menu label="Image size" icon={<Scaling className="size-4" />}
                choices={IMAGE_SIZES.map(c => ({ label: c.label, value: c.label }))}
                onPick={v => { const c = IMAGE_SIZES.find(x => x.label === v); if (c) session.push({ op: "set_style", eid: sel.eid, style: c.style }); }} />
              <Pill label="Replace image" icon={<ImageUp className="size-4" />} onClick={() => setPicking(true)} />
              <ImagePicker projectId={session.projectId} open={picking} onOpenChange={setPicking} title="Replace this image"
                onPick={a => session.push({ op: "set_src", eid: sel.eid, key: a.key })} />
              <span className="mx-0.5 h-5 w-px bg-line-2" />
            </>
          )}
          <Menu label="Text colour" icon={<Palette className="size-4" />} choices={COLORS} swatches onPick={v => style("color", v)} />
          <Menu label="Fill" icon={<PaintBucket className="size-4" />} choices={FILLS} swatches onPick={v => style("background-color", v)} />
          <Menu label="Text size" icon={<Type className="size-4" />} choices={SIZES} onPick={v => style("font-size", v)} />
          <Menu label="Weight" icon={<Bold className="size-4" />} choices={WEIGHTS} onPick={v => style("font-weight", v)} />
          <span className="mx-0.5 h-5 w-px bg-line-2" />
          <Menu label="Columns" icon={<Columns3 className="size-4" />} choices={COLUMNS}
            onPick={v => style("grid-template-columns", v)} />
          <Menu label="Direction" icon={<Rows3 className="size-4" />} choices={DIRECTION}
            onPick={v => style("flex-direction", v)} />
          <Menu label="Space between" icon={<Space className="size-4" />} choices={SPACE} onPick={v => style("gap", v)} />
          <Menu label="Space inside" icon={<SquareDashed className="size-4" />} choices={SPACE} onPick={v => style("padding", v)} />
          <Menu label="Align" icon={<AlignVerticalSpaceAround className="size-4" />} choices={ALIGN}
            onPick={v => style("align-items", v)} />
          <Menu label="Distribute" icon={<AlignHorizontalSpaceAround className="size-4" />} choices={JUSTIFY}
            onPick={v => style("justify-content", v)} />
          <Menu label="Corners" icon={<Squircle className="size-4" />} choices={RADIUS}
            onPick={v => style("border-radius", v)} />
          <Menu label="Size" icon={<Maximize2 className="size-4" />} choices={SIZE_RESET}
            onPick={v => session.push({ op: "set_style", eid: sel.eid, style: { width: v, height: v, "flex-basis": v } })} />
          <span className="mx-0.5 h-5 w-px bg-line-2" />
          <Pill label="Align left" icon={<AlignLeft className="size-4" />} onClick={() => style("text-align", "left")} />
          <Pill label="Align centre" icon={<AlignCenter className="size-4" />} onClick={() => style("text-align", "center")} />
          <Pill label="Align right" icon={<AlignRight className="size-4" />} onClick={() => style("text-align", "right")} />
          <Pill label="Capitals" icon={<CaseUpper className="size-4" />} onClick={() => style("text-transform", "uppercase")} />
          <span className="mx-0.5 h-5 w-px bg-line-2" />
          <Pill label="Move earlier" icon={<ChevronUp className="size-4" />} disabled={!el || el.index <= 0}
            onClick={() => el && session.push({ op: "reorder", eid: sel.eid, index: el.index - 1 })} />
          <Pill label="Move later" icon={<ChevronDown className="size-4" />} disabled={!el || el.index >= siblings - 1}
            onClick={() => el && session.push({ op: "reorder", eid: sel.eid, index: el.index + 1 })} />
          {canDelete
            ? <Pill label="Delete this element" tone="bad" icon={<Trash2 className="size-4" />} onClick={() => session.push({ op: "delete", eid: sel.eid })} />
            : <Tip label={lockReason(el) || "This element can't be removed."}>
                <span className="inline-flex size-8 items-center justify-center rounded-lg text-faint"><Lock className="size-4" /></span>
              </Tip>}
        </>
      ) : (
        <form className="flex items-center gap-1" onSubmit={e => { e.preventDefault(); session.push({ op: "set_text", eid: sel.eid, text }); setText(null); }}>
          <input autoFocus value={text} onChange={e => setText(e.target.value)} aria-label="Element text"
            onKeyDown={e => { if (e.key === "Escape") { e.preventDefault(); setText(null); } }}
            className="h-8 w-80 rounded-lg border border-line bg-surface px-2.5 text-[13px] text-ink focus:border-accent focus:outline-none" />
          <Button size="sm" variant="primary" type="submit">Apply</Button>
          <Pill label="Cancel" icon={<X className="size-4" />} onClick={() => setText(null)} />
        </form>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ session bar */
export function EditBar({ session, onExit }: { session: EditSession; onExit: () => void }) {
  const { pending, warnings, failure } = session;
  const dirty = pending.length > 0;
  return (
    <div className="mt-3 rounded-xl bg-room-2/60 p-2 ring-1 ring-room-line">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5 rounded-md bg-accent px-2 py-1 text-[11px] font-extrabold uppercase tracking-wide text-accent-ink">
          <Pencil className="size-3" />Editing
        </span>
        {session.loading && <span className="flex items-center gap-1.5 text-xs text-room-muted"><Loader2 className="size-3.5 animate-spin" />Reading the slide</span>}
        {session.error && <span className="text-xs font-semibold text-[#ff8da0]">Couldn't read the slide's elements: {session.error.message}</span>}
        {!session.loading && !session.error && (
          <span className="text-xs text-room-muted">
            {dirty ? `${pending.length} unsaved change${pending.length > 1 ? "s" : ""}` : "Click anything on the slide to change it"}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="room" onClick={onExit} disabled={session.saving}>{dirty ? "Discard" : "Done"}</Button>
          <Button size="sm" variant="primary" disabled={!dirty} loading={session.saving} onClick={session.save}>
            Save as a new version
          </Button>
        </div>
      </div>

      {dirty && (
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {pending.map((op, i) => (
            <li key={`${op.op}:${op.eid}:${i}`}
              className={cn("flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold",
                failure?.failed_index === i ? "bg-bad/20 text-[#ff8da0]" : "bg-room text-room-ink ring-1 ring-room-line")}>
              {editOpLabel(op, session.elements[op.eid])}
              <button onClick={() => session.drop(i)} aria-label={`Undo: ${editOpLabel(op, session.elements[op.eid])}`}
                className="ml-0.5 text-room-muted hover:text-room-ink"><X className="size-3" /></button>
            </li>
          ))}
        </ul>
      )}

      {failure && (
        <p className="mt-2 flex items-start gap-1.5 text-xs text-[#ff8da0]">
          <AlertTriangle className="mt-px size-3.5 shrink-0" />
          <span>
            {failure.failed_index != null && <b>Change {failure.failed_index + 1} was refused. </b>}
            {failure.message} Nothing was saved — remove that change and save again.
          </span>
        </p>
      )}

      {!dirty && warnings.length > 0 && (
        <ul className="mt-2 space-y-1">
          {warnings.map((w, i) => (
            <li key={i} className="flex items-start gap-1.5 text-xs text-room-muted">
              <AlertTriangle className="mt-px size-3.5 shrink-0 text-warn" /><span>{w.message}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
