import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { DeckCheck } from "../components/DeckTools";
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BookmarkPlus, CircleCheck, Copy, Download, FileText, GripVertical, History, Info, Library, Loader2, MonitorPlay, PencilLine, Presentation, RotateCcw } from "lucide-react";
import { useId, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { SlideFrame } from "../components/SlideFrame";
import { useSaveToLibrary } from "../components/library/LibraryStar";
import { Badge, Button, Kbd, Switch } from "../components/ui";
import { api, urls, type Project, type Slide } from "../lib/api";
import { deckHref, useLibraryEvents, useProjectLinks, type DuplicateDetail } from "../lib/library";
import { cn, formatBytes, lineageName } from "../lib/util";

function SortRow({ s, n, pid }: { s: Slide; n: number; pid: string }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: s.id });
  const v = s.versions.find(x => x.id === s.approved_version_id);
  return (
    <li ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn("flex items-center gap-2.5 rounded-lg border border-line bg-surface p-1.5 pr-3", isDragging && "relative z-10 shadow-card")}>
      <button {...attributes} {...listeners} aria-label={`Reorder slide ${s.index}`} className="flex h-8 w-6 cursor-grab items-center justify-center text-faint hover:text-ink active:cursor-grabbing">
        <GripVertical className="size-4" />
      </button>
      <span className="w-5 text-right text-xs font-bold tabular-nums text-muted">{n}</span>
      <span className="aspect-video w-16 shrink-0 overflow-hidden rounded bg-surface-2 ring-1 ring-line-2">
        {v ? <img src={urls.shot(v.id, "shot_final.png", v.updated_at)} alt="" className="size-full object-cover" /> : <img src={urls.source(s.id, true)} alt="" className="size-full object-cover opacity-50" />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-semibold">{s.plan.headline || s.source_title}</span>
        <span className="text-[11px] text-muted">{v ? lineageName[v.lineage] : <Link to={`/p/${pid}/review?s=${s.id}`} className="font-semibold text-warn hover:underline">Not approved</Link>}</span>
      </span>
    </li>
  );
}

// One export format: a full-width row with an icon, a title and a one-line explanation. The HTML deck is the
// primary (solid accent); the others are tinted so they read as buttons, not text, in both themes.
function ExportOption({ icon, title, sub, primary, busy, disabled, href, onClick, describedBy }: {
  icon: ReactNode; title: string; sub: string; primary?: boolean; busy?: boolean; disabled?: boolean;
  href?: string; onClick?: () => void; describedBy?: string;
}) {
  const off = disabled || busy;
  const cls = cn(
    "group flex w-full items-center gap-3 rounded-xl p-3 text-left transition-[background-color,border-color,filter] select-none",
    primary ? "bg-accent text-accent-ink shadow-sm" : "border border-accent/25 bg-accent-soft text-ink",
    !off && (primary ? "hover:brightness-110" : "hover:border-accent"),
    disabled && "cursor-not-allowed opacity-50", busy && "cursor-progress",
  );
  const body = (
    <>
      <span className={cn("flex size-9 shrink-0 items-center justify-center rounded-lg",
        primary ? "bg-white/15" : "bg-surface text-accent ring-1 ring-accent/20")}>
        {busy ? <Loader2 className="size-[18px] animate-spin" /> : icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[14px] leading-tight font-semibold">{busy ? `Creating ${title}…` : title}</span>
        <span className={cn("mt-0.5 block truncate text-xs", primary ? "text-accent-ink/80" : "text-muted")}>{sub}</span>
      </span>
      <Download aria-hidden className={cn("size-4 shrink-0", primary ? "opacity-90" : "text-accent", off && "opacity-40")} />
    </>
  );
  // A plain download link when the server streams the file; a button when we fetch it first to surface errors.
  if (href !== undefined) {
    return disabled
      ? <a role="link" aria-disabled="true" aria-describedby={describedBy} className={cls}>{body}</a>
      : <a href={href} download className={cls}>{body}</a>;
  }
  return (
    <button type="button" className={cls} disabled={off} aria-busy={busy || undefined} aria-describedby={describedBy} onClick={onClick}>
      {body}
    </button>
  );
}

/**
 * Keep the approved designs in the slide library (kind "generated"). Saved once, it says so; when approvals have
 * moved on since, or the user asks, a new version replaces the old one there (favourites and own tags carry over).
 */
function KeepInLibrary({ p }: { p: Project }) {
  const links = useProjectLinks(p.id);
  const [dup, setDup] = useState<DuplicateDetail | null>(null);
  const save = useSaveToLibrary(p.id, d => setDup(d));
  const deck = links.data?.generated ?? null;
  const stale = deck ? deck.stale_slide_ids.length + (deck.missing_slide_ids?.length ?? 0) : 0;
  const none = p.counts.approved === 0;
  const run = (supersedes?: string, force?: boolean) => { setDup(null); save.mutate({ kind: "generated", supersedes, force }); };
  return (
    <section aria-labelledby="export-library" className="mt-4 rounded-2xl border border-line bg-surface p-4">
      <h2 id="export-library" className="text-base font-bold">Keep in the slide library</h2>
      <p className="mt-1 text-[13px] text-muted">Save the approved slides there to find and reuse them in other decks.</p>
      {deck && (
        <div className="mt-3 flex items-center gap-2 text-[13px]">
          {deck.status === "ingesting" ? <Loader2 className="size-4 shrink-0 animate-spin text-accent" />
            : deck.status === "error" ? <AlertTriangle className="size-4 shrink-0 text-bad" />
              : stale ? <History className="size-4 shrink-0 text-warn" /> : <CircleCheck className="size-4 shrink-0 text-good" />}
          <span className="min-w-0 flex-1">
            {deck.status === "ingesting" ? "Saving to the library…"
              : deck.status === "error" ? "The last save didn't finish."
                : stale ? `In the library — ${stale} ${stale === 1 ? "slide has" : "slides have"} changed since`
                  : "In the library"}
          </span>
          {deck.status !== "ingesting" && <Link to={deckHref(deck.deck_id)} className="shrink-0 font-semibold text-accent hover:underline">Open</Link>}
        </div>
      )}
      {dup && (
        <div role="status" className="mt-3 rounded-lg bg-warn-soft p-3 text-[13px] text-ink">
          <div className="flex items-start gap-2"><Copy className="mt-0.5 size-4 shrink-0 text-warn" /><span>{dup.message || "These approved slides are in the library already."}</span></div>
          <div className="mt-2 flex flex-wrap gap-2">
            <Link to={deckHref(dup.deck_id)} className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-line bg-surface px-3 font-semibold hover:border-faint">
              <Library className="size-3.5" />Open in library
            </Link>
            <Button size="sm" variant="ghost" loading={save.isPending} onClick={() => run(dup.deck_id, true)}>Save as new version</Button>
          </div>
        </div>
      )}
      {!dup && (
        <div className="mt-3 flex flex-wrap gap-2">
          {!deck || deck.status === "error" ? (
            <Button size="sm" icon={<BookmarkPlus className="size-3.5" />} loading={save.isPending} disabled={none} onClick={() => run()}>
              Save approved slides
            </Button>
          ) : deck.status === "ready" && (
            <Button size="sm" variant={stale ? "secondary" : "ghost"} icon={<RotateCcw className="size-3.5" />} loading={save.isPending} disabled={none}
              onClick={() => run(deck.deck_id, true)}>
              Save as new version
            </Button>
          )}
        </div>
      )}
      {none && <p className="mt-2 text-xs text-muted">Approve at least one slide first.</p>}
    </section>
  );
}

export default function ExportView({ project: p }: { project: Project }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [fill, setFill] = useState(true);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pptxBusy, setPptxBusy] = useState(false);
  const [editBusy, setEditBusy] = useState(false);
  useLibraryEvents();
  const included = useMemo(() => (p.slides ?? []).filter(s => s.included), [p.slides]);
  // Stable string keys: `included` is a fresh array on every refetch, so its
  // identity must never drive state.
  const includedKey = included.map(s => s.id).join(",");
  const approvedKey = included.map(s => s.approved_version_id).join(",");
  const [order, setOrder] = useState<string[]>(() => (includedKey ? includedKey.split(",") : []));
  const [syncedOrderKey, setSyncedOrderKey] = useState(includedKey);
  // The preview iframe reloads when the deck's content changes, not on a timer.
  const deckKey = `${approvedKey}|${fill}`;
  const [nonce, setNonce] = useState(1);
  const [syncedDeckKey, setSyncedDeckKey] = useState(deckKey);

  const reorder = useMutation({
    mutationFn: (ids: string[]) => api.reorder(p.id, ids),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["project", p.id] }); setNonce(n => n + 1); },
    onError: e => toast.error("Couldn't save the new order", { description: (e as Error).message }),
  });

  // Follow the server's order, but never while our own reorder is in flight —
  // an SSE refetch mid-drag would otherwise snap the list back.
  if (!reorder.isPending && syncedOrderKey !== includedKey) {
    setSyncedOrderKey(includedKey);
    setOrder(includedKey ? includedKey.split(",") : []);
  }

  if (syncedDeckKey !== deckKey) { setSyncedDeckKey(deckKey); setNonce(n => n + 1); }

  const stats = useQuery({ queryKey: ["export-stats", p.id, fill, approvedKey], queryFn: () => api.exportStats(p.id, fill) });
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const onDragEnd = (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return;
    const next = arrayMove(order, order.indexOf(String(e.active.id)), order.indexOf(String(e.over.id)));
    setOrder(next);
    const excluded = (p.slides ?? []).filter(s => !s.included).map(s => s.id);
    reorder.mutate([...next, ...excluded]);
  };

  const unapproved = included.filter(s => s.status !== "approved").length;
  const inDeck = stats.data ? stats.data.approved + stats.data.filled : 0;
  // On failure `stats.data` is undefined, which must never be read as "nothing is ready".
  const blocked = stats.isError || inDeck === 0;
  const reasonId = useId();
  const blockedReason: ReactNode = !blocked ? null
    : stats.isError ? "Downloads are paused until the deck size can be read. Use Retry above."
    : stats.isLoading ? "Checking which slides are ready…"
    : unapproved > 0 && !fill
      ? <>No slides are approved yet. Turn on <b>Fill unapproved slides</b>, or <Link to={`/p/${p.id}/review`} className="font-semibold text-accent hover:underline">approve a design in Review</Link>.</>
      : <>No slides are ready to export. <Link to={`/p/${p.id}/review`} className="font-semibold text-accent hover:underline">Approve a design in Review</Link> first.</>;

  // Both of these render server-side and can fail with a message worth reading, so they go through
  // fetch rather than a plain <a download> — an error would otherwise replace the page with JSON.
  const download = async (url: string, ext: string, label: string, setBusy: (b: boolean) => void) => {
    setBusy(true);
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error((await r.json().catch(() => ({} as { detail?: string }))).detail || r.statusText);
      const blob = await r.blob();
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = `${(p.deck_title || p.name).replace(/[^\w\- ]+/g, "").trim().replace(/ /g, "_") || "deck"}.${ext}`;
      a.rel = "noopener";
      a.style.display = "none";
      // Firefox only fires the download for an anchor that is in the document,
      // and the object URL must outlive the click.
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(href), 60_000);
      toast.success(`${label} downloaded`);
    } catch (e) {
      toast.error(`Couldn't create the ${label}`, { description: (e as Error).message });
    } finally { setBusy(false); }
  };

  return (
    // Below lg the two panes stack and the page scrolls as one, with Download first so it is in view.
    <div className="scroll-thin grid h-full grid-cols-1 overflow-y-auto lg:grid-cols-[1fr_380px] lg:overflow-hidden">
      <div className="room scroll-thin bg-room p-4 sm:p-6 lg:min-h-0 lg:overflow-y-auto">
        <div className="mx-auto max-w-[1280px]">
          <div className="mb-3 flex items-center gap-3">
            <h2 className="text-lg font-extrabold tracking-tight text-room-ink">Deck preview</h2>
            <span className="text-xs text-room-muted">Click the slide, then use the arrow keys to present</span>
          </div>
          {stats.isError ? (
            <div className="flex aspect-video flex-col items-center justify-center gap-3 rounded-lg bg-room-2 p-8 text-center ring-1 ring-room-line">
              <AlertTriangle className="size-5 text-warn" />
              <div className="text-sm font-semibold text-room-ink">Couldn't work out what's in the deck</div>
              <p className="max-w-md text-xs text-room-muted">{(stats.error as Error).message} Your approved slides are unaffected.</p>
              <Button variant="room" size="sm" icon={<RotateCcw className="size-3.5" />} loading={stats.isFetching} onClick={() => stats.refetch()}>Try again</Button>
            </div>
          ) : stats.isLoading ? (
            <div className="shimmer aspect-video rounded-lg ring-1 ring-room-line" />
          ) : inDeck === 0 ? (
            <div className="flex aspect-video flex-col items-center justify-center gap-3 rounded-lg bg-room-2 p-8 text-center ring-1 ring-room-line">
              <div className="text-sm font-semibold text-room-ink">No slides are ready yet</div>
              <p className="max-w-md text-xs text-room-muted">Approve a design for at least one slide, or turn on “Fill unapproved slides” to export the highest-scoring design instead.</p>
              <div className="flex gap-2">
                <Button variant="primary" size="sm" onClick={() => nav(`/p/${p.id}/review`)}>Go to review</Button>
                {unapproved > 0 && !fill && <Button variant="room" size="sm" onClick={() => setFill(true)}>Fill unapproved slides</Button>}
              </div>
            </div>
          ) : <SlideFrame key={String(nonce)} src={urls.deck(p.id, fill, String(nonce))} title="Deck preview" />}
          <div className="mt-6 grid gap-3 text-[13px] text-room-muted sm:grid-cols-2">
            <div className="rounded-lg bg-room-2 p-3 ring-1 ring-room-line">
              <div className="mb-1.5 font-semibold text-room-ink">Presenting the exported file</div>
              <div className="space-y-1">
                <div><Kbd>→</Kbd> <Kbd>Space</Kbd> next click or slide</div>
                <div><Kbd>F</Kbd> full screen · <Kbd>S</Kbd> presenter window with notes and timer</div>
                <div><Kbd>O</Kbd> overview · <Kbd>C</Kbd> show sources · <Kbd>?</Kbd> all shortcuts</div>
              </div>
            </div>
            <div className="rounded-lg bg-room-2 p-3 ring-1 ring-room-line">
              <div className="mb-1.5 font-semibold text-room-ink">Works anywhere</div>
              One self-contained HTML file: fonts, images and interactions are embedded. It opens offline in any modern browser, with no install or internet needed.
            </div>
          </div>
        </div>
      </div>

      <aside className="scroll-thin order-first border-b border-line bg-canvas p-4 sm:p-5 lg:order-none lg:min-h-0 lg:overflow-y-auto lg:border-b-0 lg:border-l">
        <section aria-labelledby="export-download" className="rounded-2xl border border-line bg-surface p-4">
          <h2 id="export-download" className="text-base font-bold">Download</h2>
          <div className="mt-3 flex items-center gap-3">
            {unapproved === 0 ? <CircleCheck className="size-5 text-good" /> : <AlertTriangle className="size-5 text-warn" />}
            <div className="text-sm">
              <b>{p.counts.approved} of {p.counts.included}</b> slides approved
              {unapproved > 0 && <div className="text-[13px] text-muted">{unapproved} still need a decision</div>}
            </div>
          </div>
          {unapproved > 0 && (
            <label className="mt-4 flex items-start gap-3 rounded-lg bg-surface-2 p-3 text-[13px]">
              <Switch checked={fill} onCheckedChange={setFill} label="Fill unapproved slides" />
              <span><b>Fill unapproved slides</b><span className="block text-muted">Use the highest-scoring design for slides you haven't approved. Turn off to export approved slides only.</span></span>
            </label>
          )}
          <div className="mt-4 flex items-center justify-between text-[13px] text-muted">
            <span className={cn(stats.isError && "text-bad")}>
              {stats.isError ? "Couldn't read the export size" : stats.isLoading ? "Calculating…" : `${inDeck} slides in the file${stats.data?.skipped ? `, ${stats.data.skipped} left out` : ""}`}
            </span>
            {stats.isError
              ? <Button size="sm" variant="ghost" loading={stats.isFetching} onClick={() => stats.refetch()}>Retry</Button>
              : stats.data && <Badge>{formatBytes(stats.data.bytes)}</Badge>}
          </div>
          {blocked && (
            <div id={reasonId} role="status" className="mt-4 flex items-start gap-2 rounded-lg bg-warn-soft p-3 text-[13px] text-ink">
              {stats.isLoading ? <Loader2 className="mt-0.5 size-4 shrink-0 animate-spin text-muted" /> : <Info className="mt-0.5 size-4 shrink-0 text-warn" />}
              <span>{blockedReason}</span>
            </div>
          )}
          <div className="mt-4 grid gap-2" role="group" aria-label="Download formats">
            <ExportOption primary href={urls.exportHtml(p.id, fill)} disabled={blocked} describedBy={blocked ? reasonId : undefined}
              icon={<MonitorPlay className="size-[18px]" />} title="HTML deck" sub="Interactive deck — the original" />
            <ExportOption busy={pdfBusy} disabled={blocked} describedBy={blocked ? reasonId : undefined}
              icon={<FileText className="size-[18px]" />} title="PDF" sub="Print and share"
              onClick={() => download(urls.exportPdf(p.id, fill), "pdf", "PDF", setPdfBusy)} />
            <ExportOption busy={pptxBusy} disabled={blocked} describedBy={blocked ? reasonId : undefined}
              icon={<Presentation className="size-[18px]" />} title="PowerPoint" sub="One picture per slide — looks exact"
              onClick={() => download(urls.exportPptx(p.id, fill), "pptx", "PowerPoint file", setPptxBusy)} />
            <ExportOption busy={editBusy} disabled={blocked} describedBy={blocked ? reasonId : undefined}
              icon={<PencilLine className="size-[18px]" />} title="Editable PowerPoint" sub="Text boxes you can edit"
              onClick={() => download(urls.exportPptx(p.id, fill, true), "pptx", "editable PowerPoint", setEditBusy)} />
          </div>
          <p className="mt-2 text-xs text-muted">
            The PDF and the PowerPoint show every slide at its final step; interactions only work in the HTML deck, and your
            speaker notes come across. <b>PowerPoint</b> is one picture per slide. <b>Editable PowerPoint</b> turns the words into text boxes
            and the images into pictures you can move, over a picture of the rest of the design (charts and diagrams stay pictures).
            Install the Archivo and IBM Plex Mono fonts for the text to match — otherwise PowerPoint substitutes them.
          </p>
        </section>

        <KeepInLibrary p={p} />

        <div className="mt-4"><DeckCheck p={p} /></div>

        <section className="mt-4">
          <div className="mb-2 flex items-baseline justify-between px-1">
            <h2 className="text-base font-bold">Slide order</h2>
            <span className="text-xs text-muted">{reorder.isPending ? "Saving…" : "Drag to reorder"}</span>
          </div>
          {order.length === 0 ? (
            <div className="rounded-xl border border-line bg-surface p-5 text-center text-[13px] text-muted">
              <p>No slides are switched on for this deck.</p>
              <Button size="sm" className="mt-3" onClick={() => nav(`/p/${p.id}/plan`)}>Choose slides in the plan</Button>
            </div>
          ) : (
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
              <SortableContext items={order} strategy={verticalListSortingStrategy}>
                <ol className="space-y-1.5">
                  {order.map((id, i) => { const s = included.find(x => x.id === id); return s ? <SortRow key={id} s={s} n={i + 1} pid={p.id} /> : null; })}
                </ol>
              </SortableContext>
            </DndContext>
          )}
        </section>
      </aside>
    </div>
  );
}
