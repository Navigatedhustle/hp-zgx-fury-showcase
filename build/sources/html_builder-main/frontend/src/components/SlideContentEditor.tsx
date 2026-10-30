import { ChevronDown, Plus, Undo2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge, Button, IconButton, Textarea } from "./ui";
import type { ContentBlock, SlidePatchBody, Slide } from "../lib/api";
import { cn } from "../lib/util";

const SAVE_DEBOUNCE_MS = 700;

const toText = (blocks: ContentBlock[] | undefined): string[] => (blocks ?? []).map(b => (b.lines ?? []).join("\n"));
const key = (blocks: string[]) => JSON.stringify(blocks);
const lineCount = (blocks: string[]) => blocks.reduce((n, b) => n + b.split("\n").filter(l => l.trim()).length, 0);

/** A textarea that grows with its content instead of scrolling a fixed box. */
function AutoTextarea({ value, onChange, onBlur, disabled, label }: {
  value: string; onChange: (v: string) => void; onBlur: () => void; disabled?: boolean; label: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);
  return (
    <Textarea ref={ref} rows={1} value={value} disabled={disabled} aria-label={label} spellCheck
      onChange={e => onChange(e.target.value)} onBlur={onBlur}
      className="max-h-56 overflow-auto px-2.5 py-1.5 text-[13px] disabled:opacity-60" />
  );
}

function ReadOnlyExtras({ content }: { content: Slide["content"] }) {
  const tables = content.tables ?? [];
  const charts = content.charts ?? [];
  if (!tables.length && !charts.length) return null;
  return (
    <div className="space-y-1.5">
      {tables.map((rows, i) => (
        <div key={`t${i}`} className="overflow-hidden rounded-md border border-line-2">
          <div className="border-b border-line-2 bg-surface-2 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-faint">
            Table {i + 1} · used as it came out of the PowerPoint
          </div>
          <div className="max-h-32 overflow-auto px-2 py-1 text-[12px] text-muted">
            {rows.map((r, j) => <div key={j} className="truncate">{r.join(" · ")}</div>)}
          </div>
        </div>
      ))}
      {charts.map((c, i) => (
        <div key={`c${i}`} className="rounded-md border border-line-2 px-2 py-1 text-[12px] text-muted">
          Chart {i + 1}: {c.title || c.type || "data"} · {(c.series ?? []).length} series, {(c.categories ?? []).length} categories
        </div>
      ))}
    </div>
  );
}

/**
 * The slide's body copy, editable in place. What is shown here is exactly what the model
 * receives, and once edited it is treated as exact copy rather than raw material.
 *
 * Saves are debounced while typing and flushed on blur. A local draft always beats the
 * server value, so the frequent SSE-driven refetches of ["project"] cannot wipe an edit
 * in progress; the draft is dropped again only once the server has caught up with it.
 */
export default function SlideContentEditor({ slide, locked, saving, onPatch }: {
  slide: Slide; locked: boolean; saving: boolean; onPatch: (body: SlidePatchBody) => void;
}) {
  const server = toText(slide.content.text);
  const serverKey = key(server);
  const [draft, setDraft] = useState<string[] | null>(null);
  const [open, setOpen] = useState(false);
  const [showOriginal, setShowOriginal] = useState(false);
  // The server caught up with the draft (or replaced it): follow the server again.
  if (draft !== null && key(draft) === serverKey) setDraft(null);

  const sent = useRef<string | null>(serverKey);
  const patchRef = useRef(onPatch);
  useEffect(() => { patchRef.current = onPatch; });
  useEffect(() => { if (draft === null) sent.current = serverKey; }, [draft, serverKey]);

  const commit = useCallback((next: string[]) => {
    const k = key(next);
    if (k === sent.current) return;
    sent.current = k;
    patchRef.current({ content: { blocks: next } });
  }, []);

  useEffect(() => {
    if (draft === null) return;
    const t = window.setTimeout(() => commit(draft), SAVE_DEBOUNCE_MS);
    return () => window.clearTimeout(t);
  }, [draft, commit]);

  const blocks = draft ?? server;
  const dirty = draft !== null;  // a draft only survives while it differs from the server
  const preview = blocks.flatMap(b => b.split("\n")).map(l => l.trim()).filter(Boolean);
  const revert = () => {
    setDraft(null);
    sent.current = null;
    onPatch({ reset_content: true });
  };

  return (
    <div className="rounded-lg border border-line-2">
      <div className="flex items-center gap-2 px-2 py-1">
        <button type="button" onClick={() => setOpen(o => !o)} aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-1.5 py-0.5 text-left text-[11px] font-bold uppercase tracking-wide text-muted hover:text-ink">
          <ChevronDown className={cn("size-3.5 shrink-0 transition-transform", !open && "-rotate-90")} />
          Content
          <span className="truncate font-medium normal-case tracking-normal text-faint">
            {preview.length ? `${lineCount(blocks)} line${lineCount(blocks) === 1 ? "" : "s"}` : "no text"}
          </span>
        </button>
        {saving ? <span className="text-[11px] text-faint">Saving…</span>
          : dirty ? <span className="text-[11px] text-faint">Unsaved</span>
            : slide.content_edited ? <Badge tone="accent">Edited</Badge> : null}
        {slide.content_edited && (
          <IconButton label="Revert to the original PowerPoint text" onClick={revert} disabled={locked}>
            <Undo2 className="size-3.5" />
          </IconButton>
        )}
      </div>

      {!open && preview.length > 0 && (
        <p className="line-clamp-2 px-2 pb-1.5 text-[12px] leading-snug text-muted">{preview.join(" · ")}</p>
      )}

      {open && (
        <div className="space-y-2 px-2 pb-2">
          {blocks.map((text, i) => (
            <AutoTextarea key={i} value={text} disabled={locked} label={`Slide ${slide.index}, content block ${i + 1}`}
              onChange={v => setDraft(blocks.map((b, j) => (j === i ? v : b)))} onBlur={() => commit(blocks)} />
          ))}
          {blocks.length === 0 && (
            <Button size="sm" variant="ghost" icon={<Plus className="size-3.5" />} disabled={locked}
              onClick={() => setDraft([""])}>Add text</Button>
          )}
          <ReadOnlyExtras content={slide.content} />
          <p className="text-[11px] leading-snug text-faint">
            This is the copy the design uses word for word — it is only ever shortened to fit, never reworded.
            Indent with two spaces per level, wrap a line in ** for bold.
          </p>
          {slide.content_edited && (
            <div>
              <button type="button" onClick={() => setShowOriginal(o => !o)}
                className="text-[11px] font-semibold text-muted underline-offset-2 hover:text-ink hover:underline">
                {showOriginal ? "Hide" : "Show"} the original PowerPoint text
              </button>
              {showOriginal && (
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded-md bg-surface-2 p-2 text-[12px] leading-snug text-muted">
                  {toText(slide.content_original.text).join("\n\n") || "(no text)"}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
