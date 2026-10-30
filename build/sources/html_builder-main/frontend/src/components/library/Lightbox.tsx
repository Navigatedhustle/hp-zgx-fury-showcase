import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronLeft, ChevronRight, ExternalLink, Filter, Lock, RefreshCw, X } from "lucide-react";
import { useEffect, useState, type KeyboardEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { entityName, humanize, libApi, libKeys, mergeEdited, options, patchSlides, useLibTags, useTaxonomy, type LibSlide, type LibSlideDetail, type LibTag } from "../../lib/library";
import { cn } from "../../lib/util";
import { Button, IconButton, Kbd, Textarea } from "../ui";
import { AiState, FavButton, fmtDate, slideTitle } from "./SlideCard";
import { TagInput, ensureTag } from "./TagInput";

const typing = (t: EventTarget | null) => {
  const el = t as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
};

/** Edits to one slide: the server's answer is written back into every cached copy. */
function useSlideEdit(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { tags?: string[]; summary?: string; slide_type?: string }) => libApi.patchSlide(id, body),
    onSuccess: (s, body) => {
      patchSlides(qc, [id], cur => mergeEdited(cur, s));
      if (body.tags) void qc.invalidateQueries({ queryKey: libKeys.tags });
      if (body.summary === "") toast.success("The summary will be rewritten on the next retag");
    },
    onError: e => toast.error("Couldn't save that change", { description: (e as Error).message }),
  });
}

function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="border-t border-line-2 px-5 py-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-[11px] font-bold uppercase tracking-wider text-muted">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** Where a converted or generated slide came from in the Deck Builder: its plan, or its review page. */
function originalHref(s: LibSlide): string | null {
  const pid = s.deck?.origin_project_id;
  if (!pid || (s.deck?.origin !== "converted" && s.deck?.origin !== "generated")) return null;
  const sid = s.origin_slide_id;
  if (s.deck.origin === "generated") return sid ? `/p/${pid}/review?s=${encodeURIComponent(sid)}` : `/p/${pid}/review`;
  return `/p/${pid}/plan`;
}

const Locked = ({ what }: { what: string }) => (
  <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-faint" title={`You edited the ${what}, so re-tagging leaves it alone`}>
    <Lock className="size-3" />Yours
  </span>
);

function DetailPanel({ s, tags, onFav, onRetry, onShowDeck }: {
  s: LibSlide | LibSlideDetail; tags: Map<string, LibTag>;
  onFav: (s: LibSlide) => void; onRetry: (s: LibSlide) => void; onShowDeck: (deckId: string) => void;
}) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const original = originalHref(s);
  const edit = useSlideEdit(s.id);
  const allTags = useLibTags().data ?? [];
  const types = options(useTaxonomy().data?.slide_types);
  // null = not being edited, so a summary arriving from the tagger shows up instead of a stale copy.
  const [draft, setDraft] = useState<string | null>(null);
  const summary = draft ?? s.summary;
  const dirty = draft !== null && draft.trim() !== s.summary.trim();
  const saveSummary = () => edit.mutate({ summary: summary.trim() }, { onSuccess: () => setDraft(null) });
  // Adding a pending suggestion to a slide's tags is what approves it (the server does both at once).
  const approve = (slug: string) => edit.mutate({ tags: [...s.tags, slug] });
  const retag = useMutation({
    mutationFn: () => libApi.retag(s.id),
    onSuccess: () => patchSlides(qc, [s.id], cur => ({ ...cur, ai_status: "pending", ai_error: "" })),
    onError: e => toast.error("Couldn't start tagging", { description: (e as Error).message }),
  });
  const addTag = async (text: string, tag?: LibTag) => {
    try {
      const slug = tag?.slug ?? await ensureTag(text, allTags);
      if (!s.tags.includes(slug)) edit.mutate({ tags: [...s.tags, slug] });
    } catch (e) { toast.error("Couldn't add that tag", { description: (e as Error).message }); }
  };
  const detail = "content" in s ? s : null;
  const facts = detail?.facts ?? [];
  const typeOpts = s.slide_type && !types.some(t => t.value === s.slide_type) ? [{ value: s.slide_type, label: humanize(s.slide_type) }, ...types] : types;

  return (
    <>
      <div className="flex items-start gap-2 px-5 pb-4 pt-5">
        <div className="min-w-0 flex-1">
          <DialogPrimitive.Title className="text-[17px] font-bold leading-snug tracking-tight">{slideTitle(s)}</DialogPrimitive.Title>
          <div className="mt-1 text-[12.5px] text-muted">
            Slide {s.index}{s.deck && <> · {s.deck.title || "Untitled deck"}</>}
          </div>
        </div>
        <FavButton s={s} onFav={onFav} className="size-8 bg-surface-2" />
        <DialogPrimitive.Close asChild><IconButton label="Close (Esc)"><X className="size-4" /></IconButton></DialogPrimitive.Close>
      </div>

      {s.deck && (
        <Section title="Deck">
          <dl className="grid grid-cols-[5rem_1fr] gap-y-1 text-[13px]">
            <dt className="text-muted">Project</dt><dd className="truncate font-semibold">{s.deck.project || "—"}</dd>
            <dt className="text-muted">Deck</dt><dd className="truncate">{s.deck.title || "Untitled deck"}</dd>
            <dt className="text-muted">Date</dt><dd>{fmtDate(s.deck.deck_date) || "—"}</dd>
            <dt className="text-muted">Source</dt><dd>{humanize(s.deck.origin)}</dd>
          </dl>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {s.superseded && <span className="inline-flex h-6 items-center rounded-full bg-warn-soft px-2 text-[11px] font-semibold text-warn">A newer version of this deck exists</span>}
            {s.also_in > 0 && <span className="inline-flex h-6 items-center rounded-full bg-surface-2 px-2 text-[11px] font-semibold text-muted">Also in {s.also_in} other {s.also_in === 1 ? "deck" : "decks"}</span>}
          </div>
          <div className="-ml-2 mt-1 flex flex-wrap gap-1">
            <Button size="sm" variant="ghost" icon={<Filter className="size-3.5" />} onClick={() => s.deck && onShowDeck(s.deck.id)}>
              Show this deck's slides
            </Button>
            {original && (
              <Button size="sm" variant="ghost" icon={<ExternalLink className="size-3.5" />} onClick={() => nav(original)}>
                Open original
              </Button>
            )}
          </div>
        </Section>
      )}

      <Section title="Summary" aside={<div className="flex items-center gap-2">{s.summary_user && <Locked what="summary" />}<AiState s={s} onRetry={onRetry} /></div>}>
        <Textarea rows={3} value={summary} onChange={e => setDraft(e.target.value)} aria-label="Summary"
          placeholder={s.ai_status === "pending" ? "The review model is writing one…" : "What this slide says, in a sentence"}
          onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && dirty) saveSummary(); }} />
        {!dirty && s.summary_user && (
          <div className="mt-1.5 flex justify-end">
            <Button size="sm" variant="ghost" icon={<RefreshCw className="size-3.5" />} loading={edit.isPending}
              onClick={() => edit.mutate({ summary: "" })}>Let AI rewrite</Button>
          </div>
        )}
        {dirty && (
          <div className="mt-2 flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>Discard</Button>
            <Button size="sm" variant="primary" loading={edit.isPending} onClick={saveSummary}>Save summary</Button>
          </div>
        )}
      </Section>

      <Section title="Tags" aside={s.tags_user ? <Locked what="tags" /> : undefined}>
        <div className="mb-2 flex flex-wrap gap-1.5">
          {s.tags.map(slug => (
            <span key={slug} className="inline-flex h-6 items-center gap-1 rounded-full bg-accent-soft pl-2.5 pr-1 text-[12px] font-semibold text-accent">
              {tags.get(slug)?.label ?? slug}
              <button aria-label={`Remove tag ${tags.get(slug)?.label ?? slug}`} disabled={edit.isPending}
                onClick={() => edit.mutate({ tags: s.tags.filter(t => t !== slug) })}
                className="flex size-4 items-center justify-center rounded-full hover:bg-accent hover:text-accent-ink"><X className="size-3" /></button>
            </span>
          ))}
          {!s.tags.length && <span className="text-[12.5px] text-faint">No tags yet</span>}
        </div>
        <TagInput tags={allTags} exclude={s.tags} onPick={(text, tag) => void addTag(text, tag)} />
        {s.suggested.length > 0 && (
          <div className="mt-3">
            <div className="mb-1.5 text-[12px] text-muted">Suggested new tags</div>
            <div className="flex flex-wrap gap-1.5">
              {s.suggested.filter(slug => !s.tags.includes(slug)).map(slug => (
                <span key={slug} className="inline-flex h-6 items-center gap-1 rounded-full border border-dashed border-line pl-2.5 pr-1 text-[12px] font-semibold text-muted">
                  {tags.get(slug)?.label ?? humanize(slug)}
                  <button aria-label={`Approve tag ${tags.get(slug)?.label ?? slug}`} disabled={edit.isPending}
                    onClick={() => approve(slug)}
                    className="flex size-4 items-center justify-center rounded-full text-good hover:bg-good hover:text-white"><Check className="size-3" /></button>
                </span>
              ))}
            </div>
          </div>
        )}
      </Section>

      <Section title="Slide type" aside={s.slide_type_user ? <Locked what="slide type" /> : undefined}>
        <select value={s.slide_type} onChange={e => edit.mutate({ slide_type: e.target.value })} aria-label="Slide type"
          className="h-8 w-full rounded-lg border border-line bg-surface px-2 text-[13px] text-ink focus:border-accent focus:outline-none">
          <option value="">Not set</option>
          {typeOpts.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
      </Section>

      {s.entities.length > 0 && (
        <Section title="Mentions">
          <div className="flex flex-wrap gap-1.5">
            {s.entities.map((e, i) => (
              <span key={`${entityName(e)}-${i}`} className="inline-flex h-6 items-center gap-1.5 rounded-full bg-surface-2 px-2.5 text-[12px] font-semibold ring-1 ring-line-2">
                {entityName(e)}{typeof e !== "string" && e.type && <span className="font-normal text-muted">{humanize(e.type)}</span>}
              </span>
            ))}
          </div>
        </Section>
      )}

      {facts.length > 0 && (
        <Section title="Figures">
          <div className="flex flex-wrap gap-1.5">
            {facts.slice(0, 24).map(f => <span key={f.id} title={f.label} className="inline-flex h-6 items-center rounded-md bg-surface-2 px-2 text-[12px] font-semibold tabular-nums ring-1 ring-line-2">{f.raw}</span>)}
          </div>
        </Section>
      )}

      {detail?.text?.trim() && (
        <Section title="Text on the slide">
          <p className="max-h-40 overflow-auto whitespace-pre-wrap text-[13px] leading-relaxed text-muted scroll-thin">{detail.text}</p>
        </Section>
      )}

      {s.notes.trim() && (
        <Section title="Speaker notes">
          <p className="max-h-48 overflow-auto whitespace-pre-wrap text-[13px] leading-relaxed text-muted scroll-thin">{s.notes}</p>
        </Section>
      )}

      <Section title="Tagging">
        <p className="mb-2 text-[12.5px] text-muted">
          {s.ai_status === "done" ? "Tagged by the review model." : s.ai_status === "pending" ? "Being tagged now." : s.ai_status === "error" ? `Tagging failed${s.ai_error ? `: ${s.ai_error}` : "."}` : "Not tagged yet — favourites are tagged automatically."}
          {(s.tags_user || s.summary_user || s.slide_type_user) && " Your own edits are kept."}
        </p>
        <Button size="sm" icon={<RefreshCw className="size-3.5" />} loading={retag.isPending} disabled={s.ai_status === "pending"} onClick={() => retag.mutate()}>Retag</Button>
      </Section>
      <div className="px-5 pb-5 pt-2 text-[11px] text-faint">
        <Kbd>←</Kbd> <Kbd>→</Kbd> browse · <Kbd>F</Kbd> favourite · <Kbd>Esc</Kbd> close
      </div>
    </>
  );
}

export function Lightbox({ items, openId, onOpenId, tags, onFav, onRetry, onShowDeck, hasMore, onMore }: {
  items: LibSlide[]; openId: string | null; onOpenId: (id: string | null) => void; tags: Map<string, LibTag>;
  onFav: (s: LibSlide) => void; onRetry: (s: LibSlide) => void; onShowDeck: (deckId: string) => void;
  hasMore: boolean; onMore: () => void;
}) {
  const idx = openId ? items.findIndex(s => s.id === openId) : -1;
  const listed = idx >= 0 ? items[idx] : undefined;
  const detail = useQuery({ queryKey: libKeys.slide(openId ?? ""), queryFn: () => libApi.slide(openId ?? ""), enabled: !!openId });
  // The list copy carries the snippet and the live status; the detail adds content and facts.
  const s: LibSlide | LibSlideDetail | undefined = detail.data ? { ...detail.data, ...(listed ?? {}), ...pickLive(detail.data) } : listed;
  const prev = idx > 0 ? items[idx - 1] : undefined;
  const next = idx >= 0 ? items[idx + 1] : undefined;

  // Browsing towards the end of what is loaded pulls in the next page.
  useEffect(() => {
    if (idx >= 0 && idx >= items.length - 3 && hasMore) onMore();
  }, [idx, items.length, hasMore, onMore]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (typing(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "ArrowLeft" && prev) { e.preventDefault(); onOpenId(prev.id); }
    else if (e.key === "ArrowRight" && next) { e.preventDefault(); onOpenId(next.id); }
    else if ((e.key === "f" || e.key === "F") && s) { e.preventDefault(); onFav(s); }
  };

  return (
    <DialogPrimitive.Root open={!!openId} onOpenChange={o => !o && onOpenId(null)}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/80" />
        <DialogPrimitive.Content aria-describedby={undefined} onKeyDown={onKeyDown}
          className="fixed inset-0 z-50 flex flex-col overflow-auto outline-none lg:flex-row lg:overflow-hidden">
          <div className="relative flex min-h-[50vh] flex-1 items-center justify-center p-4 sm:p-10">
            {s && (
              <img key={s.id} src={s.image} alt={slideTitle(s)}
                style={{ backgroundImage: `url("${s.thumb}")` }}
                className="max-h-full w-auto max-w-full rounded-md bg-room-2 bg-contain bg-center bg-no-repeat object-contain shadow-2xl"
                onError={e => { e.currentTarget.style.visibility = "hidden"; }} />
            )}
            <button aria-label="Previous slide" disabled={!prev} onClick={() => prev && onOpenId(prev.id)}
              className="absolute left-3 top-1/2 flex size-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-white backdrop-blur hover:bg-white/20 disabled:opacity-0">
              <ChevronLeft className="size-6" />
            </button>
            <button aria-label="Next slide" disabled={!next} onClick={() => next && onOpenId(next.id)}
              className="absolute right-3 top-1/2 flex size-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-white backdrop-blur hover:bg-white/20 disabled:opacity-0">
              <ChevronRight className="size-6" />
            </button>
            {idx >= 0 && <div className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-black/50 px-3 py-1 text-[12px] font-semibold text-white/80">{idx + 1} of {items.length}{hasMore ? "+" : ""}</div>}
          </div>
          <aside className={cn("w-full shrink-0 bg-surface text-ink lg:h-full lg:w-[400px] lg:overflow-auto scroll-thin")}>
            {s ? <DetailPanel key={s.id} s={s} tags={tags} onFav={onFav} onRetry={onRetry} onShowDeck={onShowDeck} />
              : <div className="p-5"><DialogPrimitive.Title className="text-sm text-muted">Loading…</DialogPrimitive.Title></div>}
          </aside>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

/** Fields the live channel and optimistic edits keep current: the detail's copy wins for these. */
function pickLive(d: LibSlide) {
  return { favourite: d.favourite, ai_status: d.ai_status, ai_error: d.ai_error, tags: d.tags, summary: d.summary, slide_type: d.slide_type, suggested: d.suggested, tags_user: d.tags_user, summary_user: d.summary_user, slide_type_user: d.slide_type_user };
}
