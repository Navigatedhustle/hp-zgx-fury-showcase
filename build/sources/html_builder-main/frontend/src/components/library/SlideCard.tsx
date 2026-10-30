import { AlertTriangle, Check, Copy, History, ImageOff, Lock, Sparkles, Star } from "lucide-react";
import { useState, type MouseEvent } from "react";
import type { LibSlide, LibTag } from "../../lib/library";
import { cn } from "../../lib/util";
import { Spinner, Tip } from "../ui";
import type { ViewSize } from "./ViewControls";

/** How a click on a card was meant: open it, toggle it into the selection, or select a range up to it. */
export type PickMode = "open" | "toggle" | "range";

export interface CardHandlers {
  onPick: (s: LibSlide, mode: PickMode) => void;
  onFav: (s: LibSlide) => void;
  onRetry: (s: LibSlide) => void;
}

export const slideTitle = (s: Pick<LibSlide, "title" | "index">) => s.title.trim() || `Slide ${s.index}`;

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** A lazily loaded 16:9 picture with a placeholder when the server has no render (or it fails). */
export function Thumb({ src, className, alt = "" }: { src: string; className?: string; alt?: string }) {
  const [failed, setFailed] = useState<string | null>(null);
  return (
    <div className={cn("relative aspect-video overflow-hidden bg-surface-2", className)}>
      {failed !== src
        ? <img src={src} alt={alt} loading="lazy" decoding="async" draggable={false} onError={() => setFailed(src)} className="size-full object-contain" />
        : <div className="flex size-full flex-col items-center justify-center gap-1 text-faint"><ImageOff className="size-5" /><span className="text-[11px] font-semibold">No preview</span></div>}
    </div>
  );
}

/** Which way a click went, from its modifier keys. A keyboard press (detail 0) always opens. */
export function pickMode(e: MouseEvent, selecting: boolean): PickMode {
  if (e.detail === 0) return "open";
  if (e.shiftKey) return "range";
  if (e.ctrlKey || e.metaKey || selecting) return "toggle";
  return "open";
}

export function FavButton({ s, onFav, className }: { s: LibSlide; onFav: (s: LibSlide) => void; className?: string }) {
  const label = s.favourite ? "Remove from favourites" : "Add to favourites";
  return (
    <Tip label={`${label} (F)`}>
      <button aria-label={label} aria-pressed={s.favourite} onClick={e => { e.stopPropagation(); onFav(s); }}
        className={cn("flex size-7 items-center justify-center rounded-full transition-colors",
          s.favourite ? "text-warn" : "text-muted hover:text-ink", className)}>
        <Star className={cn("size-4", s.favourite && "fill-current")} />
      </button>
    </Tip>
  );
}

export function AiState({ s, onRetry, compact }: { s: LibSlide; onRetry: (s: LibSlide) => void; compact?: boolean }) {
  if (s.ai_status === "pending") {
    return (
      <Tip label="Being tagged by the review model">
        <span role="status" className="inline-flex h-6 items-center gap-1 rounded-full bg-accent-soft px-2 text-[11px] font-semibold text-accent">
          <Spinner className="size-3" />{!compact && "Tagging"}
        </span>
      </Tip>
    );
  }
  if (s.ai_status === "error") {
    return (
      <Tip label={`Tagging failed${s.ai_error ? `: ${s.ai_error}` : ""} — click to retry`}>
        <button onClick={e => { e.stopPropagation(); onRetry(s); }} aria-label="Tagging failed — retry"
          className="inline-flex h-6 items-center gap-1 rounded-full bg-bad-soft px-2 text-[11px] font-semibold text-bad hover:brightness-95">
          <AlertTriangle className="size-3" />{!compact && "Retry"}
        </button>
      </Tip>
    );
  }
  return null;
}

function Flags({ s }: { s: LibSlide }) {
  return (
    <>
      {s.superseded && (
        <Tip label="This deck has a newer version in the library">
          <span className="inline-flex h-5 items-center gap-1 rounded-full bg-warn-soft px-1.5 text-[11px] font-semibold text-warn"><History className="size-3" />Old version</span>
        </Tip>
      )}
      {s.by_meaning && (
        <Tip label="None of your words are on this slide — it is here because it is about the same thing">
          <span className="inline-flex h-5 items-center gap-1 rounded-full bg-accent-soft px-1.5 text-[11px] font-semibold text-accent"><Sparkles className="size-3" />Related</span>
        </Tip>
      )}
      {s.also_in > 0 && (
        <Tip label={`The same slide appears in ${s.also_in} other ${s.also_in === 1 ? "deck" : "decks"}`}>
          <span className="inline-flex h-5 items-center gap-1 rounded-full bg-surface-2 px-1.5 text-[11px] font-semibold text-muted ring-1 ring-line"><Copy className="size-3" />+{s.also_in}</span>
        </Tip>
      )}
    </>
  );
}

function Checkbox({ s, selected, onPick }: { s: LibSlide; selected: boolean; onPick: CardHandlers["onPick"] }) {
  return (
    <button role="checkbox" aria-checked={selected} aria-label={`Select ${slideTitle(s)}`}
      onClick={e => { e.stopPropagation(); onPick(s, e.shiftKey ? "range" : "toggle"); }}
      className={cn("flex size-5 items-center justify-center rounded-md border-2 transition-colors",
        selected ? "border-accent bg-accent text-accent-ink" : "border-white/90 bg-black/25 text-transparent hover:bg-black/40")}>
      <Check className="size-3.5" strokeWidth={3} />
    </button>
  );
}

/**
 * Search snippet. The backend escapes everything and adds only <mark> around matched words
 * (`schema.slide_out`), so this HTML is safe to inject as is.
 */
export function Snippet({ html, className }: { html: string; className?: string }) {
  if (!html) return null;
  return <p className={cn("text-[12px] leading-snug text-muted [&_mark]:rounded-sm [&_mark]:bg-warn-soft [&_mark]:px-0.5 [&_mark]:text-ink", className)}
    dangerouslySetInnerHTML={{ __html: html }} />;
}

export function TagChip({ slug, tags, className }: { slug: string; tags: Map<string, LibTag>; className?: string }) {
  const t = tags.get(slug);
  return <span className={cn("inline-flex h-5 items-center rounded-full bg-surface-2 px-2 text-[11px] font-semibold text-muted ring-1 ring-line-2", className)}>{t?.label ?? slug}</span>;
}

interface Props extends CardHandlers {
  s: LibSlide; view: ViewSize; selected: boolean; selecting: boolean; tags: Map<string, LibTag>;
}

export function SlideCard({ s, view, selected, selecting, tags, onPick, onFav, onRetry }: Props) {
  if (view === "details") return <SlideRow {...{ s, selected, selecting, tags, onPick, onFav, onRetry }} />;
  const small = view === "s";
  const title = slideTitle(s);
  return (
    <div data-slide-id={s.id}
      className={cn("group relative overflow-hidden rounded-xl border bg-surface transition-[border-color,box-shadow]",
        selected ? "border-accent ring-2 ring-accent" : "border-line hover:border-faint")}>
      <button data-card-main onClick={e => onPick(s, pickMode(e, selecting))}
        aria-label={`${title}${s.deck ? ` — ${s.deck.title || s.deck.project}` : ""}`}
        className="absolute inset-0 z-[1] rounded-xl focus-visible:outline-offset-[-2px]" />
      <div className="relative">
        <Thumb src={view === "xl" ? s.image : s.thumb} />
        <div className={cn("absolute left-2 top-2 z-[2] transition-opacity",
          selected || selecting ? "opacity-100" : "opacity-0 group-focus-within:opacity-100 group-hover:opacity-100")}>
          <Checkbox s={s} selected={selected} onPick={onPick} />
        </div>
        <div className={cn("absolute right-1.5 top-1.5 z-[2] rounded-full bg-surface/90 shadow-sm transition-opacity",
          s.favourite ? "opacity-100" : "opacity-0 group-focus-within:opacity-100 group-hover:opacity-100")}>
          <FavButton s={s} onFav={onFav} />
        </div>
        <div className="pointer-events-none absolute bottom-1.5 left-1.5 right-1.5 flex items-end justify-between gap-1">
          <div className="pointer-events-auto relative z-[2] flex flex-wrap gap-1"><Flags s={s} /></div>
          <div className="pointer-events-auto relative z-[2]"><AiState s={s} onRetry={onRetry} compact={small} /></div>
        </div>
      </div>
      {!small && (
        <div className="space-y-1 px-3 pb-3 pt-2.5">
          <div className="truncate text-[13px] font-bold" title={title}>{title}</div>
          <div className="truncate text-[12px] text-muted">{s.deck ? `${s.deck.title || "Untitled deck"} · ${s.deck.project}` : ""}</div>
          {s.snippet ? <Snippet html={s.snippet} className="line-clamp-2" />
            : view !== "m" && s.summary && <p className="line-clamp-2 text-[12px] leading-snug text-muted">{s.summary}</p>}
        </div>
      )}
    </div>
  );
}

function SlideRow({ s, selected, selecting, tags, onPick, onFav, onRetry }: Omit<Props, "view">) {
  const title = slideTitle(s);
  return (
    <div data-slide-id={s.id}
      className={cn("group relative grid grid-cols-[auto_9rem_1fr] items-start gap-3 rounded-xl border bg-surface p-2.5 sm:grid-cols-[auto_11rem_1fr_13rem_auto]",
        selected ? "border-accent ring-2 ring-accent" : "border-line hover:border-faint")}>
      <button data-card-main onClick={e => onPick(s, pickMode(e, selecting))} aria-label={title}
        className="absolute inset-0 z-[1] rounded-xl focus-visible:outline-offset-[-2px]" />
      <div className={cn("relative z-[2] self-center transition-opacity [&_button]:border-line [&_button]:bg-surface",
        selected || selecting ? "opacity-100" : "opacity-0 group-focus-within:opacity-100 group-hover:opacity-100")}>
        <Checkbox s={s} selected={selected} onPick={onPick} />
      </div>
      <Thumb src={s.thumb} className="rounded-md ring-1 ring-line-2" />
      <div className="min-w-0 space-y-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-[14px] font-bold">{title}</span>
          {(s.tags_user || s.summary_user || s.slide_type_user) && <Lock className="size-3 shrink-0 text-faint" aria-label="Edited by you" />}
        </div>
        {s.snippet ? <Snippet html={s.snippet} className="line-clamp-2" />
          : s.summary ? <p className="line-clamp-2 text-[12.5px] leading-snug text-muted">{s.summary}</p>
            : <p className="text-[12.5px] italic text-faint">{s.ai_status === "pending" ? "Summary on its way…" : "Not tagged yet"}</p>}
        <div className="flex flex-wrap gap-1 pt-0.5">
          {s.tags.slice(0, 6).map(t => <TagChip key={t} slug={t} tags={tags} />)}
          <Flags s={s} />
        </div>
      </div>
      <div className="hidden min-w-0 text-[12px] text-muted sm:block">
        <div className="truncate font-semibold text-ink">{s.deck?.title || "Untitled deck"}</div>
        <div className="truncate">{s.deck?.project}</div>
        <div className="truncate">{fmtDate(s.deck?.deck_date) || fmtDate(s.created_at)} · slide {s.index}</div>
      </div>
      <div className="relative z-[2] hidden flex-col items-end gap-1.5 sm:flex">
        <FavButton s={s} onFav={onFav} />
        <AiState s={s} onRetry={onRetry} compact />
      </div>
    </div>
  );
}
