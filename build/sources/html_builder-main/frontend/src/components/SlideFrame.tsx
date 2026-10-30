import { ChevronLeft, ChevronRight, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import type { EditOp } from "../lib/api";
import { cn } from "../lib/util";

interface DeckState { index: number; step: number; steps: number; count: number; errors: number }

/** The stage is always 1600x900; a rect from the runtime is in those coordinates, never CSS pixels. */
export const STAGE_W = 1600;

export interface EditSelection {
  eid: string; tag: string; classes: string[]; text: string;
  rect: { x: number; y: number; w: number; h: number };
  canText: boolean; canDelete: boolean; locks: string[];
}

export interface ElementLock { editable_text: boolean; deletable: boolean; locks: string[] }

export type FrameEditEvent =
  | { kind: "ready" }
  | { kind: "select"; sel: EditSelection | null }
  | { kind: "op"; op: EditOp }
  | { kind: "dirty"; eid: string; text: string };

/** The parent half of the editing channel. See runtime/shell.js for the other half. */
export interface EditChannel {
  on: boolean;
  /** What the server would refuse, keyed by eid — forwarded so the UI greys controls out instead of 400ing. */
  locks?: Record<string, ElementLock>;
  /** Selection driven from outside the frame (an outline list, say). */
  selected?: string | null;
  onEvent: (e: FrameEditEvent) => void;
  /** Rendered over the stage. `box` is the selection rect already converted to CSS pixels. */
  overlay?: (a: { sel: EditSelection; box: { left: number; top: number; width: number; height: number } }) => ReactNode;
}

const str = (v: unknown, fallback = "") => (typeof v === "string" ? v : fallback);
const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const strList = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

/** The runtime is sandboxed but still runs model-written markup: nothing from it is trusted unchecked. */
export function readSelection(d: Record<string, unknown>): EditSelection | null {
  const eid = str(d.eid);
  if (!eid) return null;
  const r = (d.rect ?? {}) as Record<string, unknown>;
  return {
    eid, tag: str(d.tag, "div"), classes: strList(d.classes), text: str(d.text),
    rect: { x: num(r.x), y: num(r.y), w: num(r.w), h: num(r.h) },
    canText: d.canText !== false, canDelete: d.canDelete !== false, locks: strList(d.locks),
  };
}

/** Accept only ops app/edit.py can apply; anything else would be a guaranteed 400. */
export function readOp(raw: unknown): EditOp | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const eid = str(o.eid);
  if (!eid) return null;
  if (o.op === "set_text" && typeof o.text === "string") return { op: "set_text", eid, text: o.text, replace_children: o.replace_children === true };
  if (o.op === "delete") return { op: "delete", eid };
  if (o.op === "reorder" && typeof o.index === "number" && Number.isInteger(o.index) && o.index >= 0) return { op: "reorder", eid, index: o.index };
  if (o.op === "set_style" && o.style && typeof o.style === "object") {
    const style: Record<string, string> = {};
    for (const [k, v] of Object.entries(o.style as Record<string, unknown>)) if (typeof v === "string") style[k] = v;
    return Object.keys(style).length ? { op: "set_style", eid, style } : null;
  }
  if (o.op === "set_src" && typeof o.key === "string" && o.key) return { op: "set_src", eid, key: o.key };
  return null;
}

/**
 * Live, interactive preview of an assembled deck/slide in a 1600x900 iframe scaled to its container.
 * Talks to the deck runtime over postMessage (embed API).
 */
export function SlideFrame({ src, className, controls = true, dark = true, onState, title = "Slide preview", autoFocus, startAtEnd, edit }: {
  src: string; className?: string; controls?: boolean; dark?: boolean; onState?: (s: DeckState) => void; title?: string; autoFocus?: boolean;
  /** Open on the final step so the whole design is visible; replay shows the build. */
  startAtEnd?: boolean;
  /** Two-way editing channel. Absent (or `on: false`) leaves the frame a read-only preview. */
  edit?: EditChannel;
}) {
  const box = useRef<HTMLDivElement>(null);
  const frame = useRef<HTMLIFrameElement>(null);
  const [scale, setScale] = useState(0);
  const [state, setState] = useState<DeckState | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [sel, setSel] = useState<EditSelection | null>(null);
  const [ready, setReady] = useState(0);
  // Handlers live in a ref so the message listener is subscribed once and still sees fresh props.
  const cb = useRef({ onState, onEvent: edit?.onEvent });
  useEffect(() => { cb.current = { onState, onEvent: edit?.onEvent }; });

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setScale(el.clientWidth / STAGE_W));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      // The preview is served by this backend, so a message that matters comes from this frame's
      // window and this origin. Anything else posting at us is ignored outright.
      if (e.source !== frame.current?.contentWindow || e.origin !== window.location.origin) return;
      const d = e.data as Record<string, unknown> | null;
      if (!d || d.type !== "hpdeck") return;
      if (d.event === "state") {
        setState(d as unknown as DeckState);
        cb.current.onState?.(d as unknown as DeckState);
        return;
      }
      if (d.event === "edit-ready") { setReady(t => t + 1); cb.current.onEvent?.({ kind: "ready" }); return; }
      if (d.event === "edit-select") {
        const next = readSelection(d);
        setSel(next);
        cb.current.onEvent?.({ kind: "select", sel: next });
        return;
      }
      if (d.event === "edit-op") {
        const op = readOp(d.op);
        if (op) cb.current.onEvent?.({ kind: "op", op });
        return;
      }
      if (d.event === "edit-dirty" && typeof d.text === "string" && str(d.eid)) {
        cb.current.onEvent?.({ kind: "dirty", eid: str(d.eid), text: d.text });
      }
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);

  // A new src means a new document: reset while rendering rather than in an
  // effect, so the stale preview is never shown for a frame.
  const [shownSrc, setShownSrc] = useState(src);
  if (shownSrc !== src) {
    setShownSrc(src);
    setLoaded(false);
    setState(null);
    setSel(null);
    setReady(0);
  }

  // Same-origin by construction (the preview comes from this backend), so the commands are
  // addressed to it rather than to "*".
  const send = useCallback((msg: object) => frame.current?.contentWindow?.postMessage({ type: "hpdeck", ...msg }, window.location.origin), []);

  const editOn = !!edit?.on;
  const locks = edit?.locks;
  const selected = edit?.selected;
  const selEid = sel?.eid ?? null;

  // Leaving edit mode drops the selection during render, like a new src does: an effect would
  // render the stale toolbar for a frame first.
  const [wasEditing, setWasEditing] = useState(editOn);
  if (wasEditing !== editOn) {
    setWasEditing(editOn);
    if (sel) setSel(null);
  }

  // `ready` re-sends after the runtime announces itself, in case it booted after the load handler.
  useEffect(() => {
    if (loaded) send({ cmd: "edit", on: editOn });
  }, [editOn, loaded, ready, send]);

  useEffect(() => {
    if (loaded && editOn && locks) send({ cmd: "locks", map: locks });
  }, [locks, loaded, editOn, ready, send]);

  useEffect(() => {
    // Only when the outside disagrees with the frame, so echoing a click back is not a loop.
    if (!loaded || !editOn || selected === undefined || (selected ?? null) === selEid) return;
    send({ cmd: "select", eid: selected ?? null });
  }, [selected, selEid, loaded, editOn, send]);

  return (
    <div className={cn("flex flex-col", className)}>
      <div ref={box} className={cn("relative aspect-video w-full overflow-hidden rounded-lg", dark ? "bg-room-2 ring-1 ring-room-line" : "bg-surface-2 ring-1 ring-line")}>
        {!loaded && <div className={cn("absolute inset-0", dark ? "shimmer" : "shimmer-light")} />}
        {scale > 0 && (
          <iframe ref={frame} src={src} title={title} onLoad={() => { setLoaded(true); send(startAtEnd ? { cmd: "goto", index: 0, step: "end" } : { cmd: "state" }); if (autoFocus) frame.current?.focus(); }}
            className={cn("absolute left-0 top-0 origin-top-left border-0 bg-white transition-opacity", loaded ? "opacity-100" : "opacity-0")}
            style={{ width: 1600, height: 900, transform: `scale(${scale})` }} sandbox="allow-scripts allow-popups allow-same-origin allow-modals" />
        )}
        {editOn && sel && scale > 0 && edit?.overlay && (
          <div className="pointer-events-none absolute inset-0">
            {edit.overlay({
              sel,
              box: { left: sel.rect.x * scale, top: sel.rect.y * scale, width: sel.rect.w * scale, height: sel.rect.h * scale },
            })}
          </div>
        )}
      </div>
      {controls && (
        <div className={cn("mt-2 flex items-center gap-1", dark ? "text-room-muted" : "text-muted")}>
          <FrameBtn dark={dark} label="Previous step" onClick={() => send({ cmd: "prev" })}><ChevronLeft className="size-4" /></FrameBtn>
          <FrameBtn dark={dark} label="Next step" onClick={() => send({ cmd: "next" })}><ChevronRight className="size-4" /></FrameBtn>
          <FrameBtn dark={dark} label="Replay from the start" onClick={() => send({ cmd: "goto", index: state?.index ?? 0, step: 0 })}><RotateCcw className="size-3.5" /></FrameBtn>
          <StepDots dark={dark} step={state?.step ?? 0} steps={state?.steps ?? 0}
            onPick={s => send({ cmd: "goto", index: state?.index ?? 0, step: s })} />
          {state && state.count > 1 && <span className="ml-auto text-xs font-semibold">Slide {state.index + 1} of {state.count}</span>}
          {state && state.errors > 0 && <span className="ml-auto text-xs font-semibold text-bad">Script error</span>}
        </div>
      )}
    </div>
  );
}

function FrameBtn({ dark, label, onClick, children }: { dark: boolean; label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button aria-label={label} title={label} onClick={onClick}
      className={cn("flex size-7 items-center justify-center rounded-md transition-colors", dark ? "hover:bg-room-2 hover:text-room-ink" : "hover:bg-surface-2 hover:text-ink")}>
      {children}
    </button>
  );
}

function StepDots({ step, steps, onPick, dark }: { step: number; steps: number; onPick: (s: number) => void; dark: boolean }) {
  if (!steps) return <span className="ml-1.5 text-xs">No click steps</span>;
  return (
    <div className="ml-1.5 flex items-center gap-1" aria-label={`Step ${step} of ${steps}`}>
      {Array.from({ length: steps + 1 }, (_, i) => (
        <button key={i} onClick={() => onPick(i)} aria-label={`Go to step ${i}`}
          className={cn("h-1.5 rounded-full transition-all", i === step ? "w-5 bg-accent" : cn("w-1.5", i < step ? "bg-accent/60" : dark ? "bg-room-line" : "bg-line"))} />
      ))}
      <span className="ml-1.5 text-xs tabular-nums">{step}/{steps}</span>
    </div>
  );
}
