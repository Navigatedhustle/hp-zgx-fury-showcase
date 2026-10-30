import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Check, ChevronDown, ChevronLeft, ChevronRight, CircleCheck, Expand, History, Image as ImageIcon, Layers, ListChecks,
  MessageSquareText, Pencil, RefreshCw, Sparkles, Undo2, Wand2, X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { RedesignDialog } from "../components/DeckTools";
import { FactReport } from "../components/FactLedger";
import { AddImageButton } from "../components/ImagePicker";
import { LibraryStar, SaveToLibraryButton } from "../components/library/LibraryStar";
import { EditBar, ElementToolbar, useEditSession, type EditSession } from "../components/SlideEditor";
import { SlideFrame } from "../components/SlideFrame";
import { Badge, Button, Dialog, Empty, Kbd, Spinner, Textarea, Tip } from "../components/ui";
import { api, urls, type DeckAsset, type Lineage, type Project, type Slide, type Version } from "../lib/api";
import { useKey } from "../lib/hooks";
import { useLibraryEvents } from "../lib/library";
import {
  abAdvice, bestOfSummary, cn, criticIssues, criticScores, criticState, hasFatalFidelity, isBusyVersion, lineageBlurb,
  lineageName, qaBestOf, qaCritic, qaFatal, qaFindings, safeNotesHtml, slideStatusText, slideTone, timeAgo,
} from "../lib/util";

/** An <img> that removes itself when the file isn't there, without touching the DOM behind React. */
function Thumb({ src, alt, className, fallback }: { src: string; alt: string; className?: string; fallback?: ReactNode }) {
  const [ok, setOk] = useState(true);
  if (!ok) return <>{fallback ?? null}</>;
  return <img src={src} alt={alt} loading="lazy" className={className} onError={() => setOk(false)} />;
}

/* ------------------------------------------------------------------ left rail */
function Rail({ slides, current, onPick }: { slides: Slide[]; current?: string; onPick: (id: string) => void }) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  useEffect(() => { if (current) refs.current[current]?.scrollIntoView({ block: "nearest" }); }, [current]);
  const dot = { good: "bg-good", warn: "bg-warn", bad: "bg-bad", busy: "bg-accent animate-pulse", idle: "bg-line" };
  return (
    <nav aria-label="Slides" className="scroll-thin h-full overflow-y-auto border-r border-line bg-surface p-2">
      {slides.map(s => {
        const tone = slideTone(s.status);
        const approved = s.versions.find(v => v.id === s.approved_version_id);
        const src = approved?.status === "ready" ? urls.shot(approved.id, "shot_final.png", approved.updated_at) : urls.source(s.id, true);
        return (
          <button key={s.id} ref={el => { refs.current[s.id] = el; }} onClick={() => onPick(s.id)} aria-current={s.id === current}
            className={cn("mb-1 flex w-full items-center gap-3 rounded-lg p-2 text-left transition-colors",
              s.id === current ? "bg-accent-soft" : "hover:bg-surface-2")}>
            <span className="w-6 shrink-0 text-right text-xs font-bold tabular-nums text-muted">{s.label ?? s.index}</span>
            <span className="relative aspect-video w-20 shrink-0 overflow-hidden rounded bg-surface-2 ring-1 ring-line-2">
              <Thumb key={src} src={src} alt="" className="size-full object-cover" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-semibold leading-tight">{s.plan.headline || s.source_title || "Untitled"}</span>
              <span className="mt-1 flex items-center gap-1.5 text-[11px] font-semibold text-muted">
                <span className={cn("size-1.5 rounded-full", dot[tone])} />
                {slideStatusText[s.status]}{approved && ` · ${lineageName[approved.lineage]}`}
              </span>
            </span>
          </button>
        );
      })}
    </nav>
  );
}

/** Slide navigation for narrow windows, where the rail is hidden. */
function MobileRail({ slides, current, onPick }: { slides: Slide[]; current: Slide; onPick: (id: string) => void }) {
  const idx = slides.indexOf(current);
  const step = (d: number) => { const n = slides[idx + d]; if (n) onPick(n.id); };
  return (
    <div className="flex items-center gap-2 border-b border-room-line px-4 py-2 md:hidden">
      <Button variant="room" size="sm" aria-label="Previous slide" disabled={idx <= 0} onClick={() => step(-1)}><ChevronLeft className="size-4" /></Button>
      <label className="min-w-0 flex-1">
        <span className="sr-only">Go to slide</span>
        <select value={current.id} onChange={e => onPick(e.target.value)}
          className="h-9 w-full rounded-lg border border-room-line bg-room-2 px-2 text-[13px] font-semibold text-room-ink focus:border-accent focus:outline-none">
          {slides.map(s => (
            <option key={s.id} value={s.id}>{s.label ?? s.index}. {s.plan.headline || s.source_title || "Untitled"} — {slideStatusText[s.status]}</option>
          ))}
        </select>
      </label>
      <Button variant="room" size="sm" aria-label="Next slide" disabled={idx < 0 || idx >= slides.length - 1} onClick={() => step(1)}><ChevronRight className="size-4" /></Button>
    </div>
  );
}

/* ------------------------------------------------------------------ QA summary */
function QaBadge({ v, onOpen }: { v: Version; onOpen: () => void }) {
  const findings = qaFindings(v);
  const errors = findings.filter(f => f.severity === "error").length;
  const warns = findings.filter(f => f.severity === "warn").length;
  const critic = criticState(v);
  // A score with no critique behind it is a floor, not a verdict — never show it as "Quality 6.0".
  const unreviewed = critic?.status === "failed";
  const label = errors ? `${errors} issue${errors > 1 ? "s" : ""}`
    : unreviewed ? critic.label
    : v.score != null ? `Quality ${v.score.toFixed(1)}` : "Checked";
  return (
    <button onClick={onOpen} title={unreviewed ? critic.detail : undefined}
      className={cn("flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-semibold transition-colors",
      errors ? "bg-bad/15 text-[#ff8da0] hover:bg-bad/25"
        : unreviewed ? "bg-warn/15 text-[#f0b75b] hover:bg-warn/25"
        : "bg-room-2 text-room-muted hover:text-room-ink")}>
      {errors || unreviewed ? <AlertTriangle className="size-3.5" /> : <ListChecks className="size-3.5" />}{label}
      {!errors && !unreviewed && warns > 0 && <span className="opacity-70">· {warns} note{warns > 1 ? "s" : ""}</span>}
    </button>
  );
}

function QaDialog({ v, slide, open, onOpenChange, onUseFix }: {
  v: Version; slide?: Slide; open: boolean; onOpenChange: (o: boolean) => void; onUseFix: (text: string) => void;
}) {
  const critic = qaCritic(v);
  const scores = criticScores(critic);
  const issues = criticIssues(critic);
  const findings = qaFindings(v);
  // Fidelity has its own section above, so the generic list must not repeat it.
  const other = findings.filter(f => !f.code.startsWith("fidelity"));
  const vision = v.qa?.vision === true;
  const cstate = criticState(v);
  const reviewed = vision && cstate?.status !== "failed" && cstate?.status !== "skipped";
  const llm = v.llm ?? {};
  const best = qaBestOf(v);
  const ab = abAdvice(v);
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={`${lineageName[v.lineage]} v${v.number}: quality report`}
      description={`Rendered in Chromium and checked automatically${reviewed ? ", then reviewed by the vision model" : ""}. ${v.repairs ? `Repaired ${v.repairs} time${v.repairs > 1 ? "s" : ""}.` : ""}`}>
      {cstate && cstate.status !== "ok" && (
        <div className={cn("mb-4 rounded-lg border p-3 text-[13px]",
          cstate.status === "failed" ? "border-warn/40 bg-warn/10" : "border-line bg-surface-2")}>
          <div className="font-bold">{cstate.label}</div>
          <p className="mt-0.5 text-muted">
            {cstate.detail}
            {cstate.status === "failed" && " The score below is a conservative floor, not a design verdict."}
          </p>
        </div>
      )}
      {scores.length > 0 && (
        <div className="mb-5 grid grid-cols-3 gap-2">
          {scores.map(([k, n]) => (
            <div key={k} className="rounded-lg bg-surface-2 p-2.5">
              <div className="text-[11px] font-semibold capitalize text-muted">{k}</div>
              <div className={cn("text-lg font-extrabold tabular-nums", n >= 8 ? "text-good" : n >= 6 ? "text-warn" : "text-bad")}>{n}<span className="text-xs font-semibold text-faint">/10</span></div>
            </div>
          ))}
        </div>
      )}
      {slide && (<>
        <h4 className="mb-2 text-sm font-bold">Facts from the original slide</h4>
        <div className="mb-5"><FactReport slide={slide} version={v} /></div>
      </>)}
      <h4 className="mb-2 text-sm font-bold">Automated checks</h4>
      {other.length === 0 ? <p className="text-sm text-good">No layout or script problems found.</p> : (
        <ul className="space-y-1.5">{other.map((f, i) => (
          <li key={i} className="flex gap-2 text-[13px]">
            <Badge tone={f.severity === "error" ? "bad" : "warn"} className="h-5 shrink-0">{f.code}</Badge><span className="text-muted">{f.message}</span>
          </li>))}
        </ul>
      )}
      {issues.length > 0 && (<>
        <h4 className="mb-2 mt-5 text-sm font-bold">Design review</h4>
        <ul className="space-y-2">{issues.map((i, k) => (
          <li key={k} className="rounded-lg border border-line-2 p-2.5 text-[13px]">
            <div className="flex items-center gap-2">
              <Badge tone={i.severity === "high" ? "bad" : i.severity === "medium" ? "warn" : "idle"} className="h-5">{i.area}</Badge>
              <span className="font-semibold">{i.problem}</span>
            </div>
            {i.fix && (
              <div className="mt-1 flex items-start gap-2">
                <span className="text-muted">Suggested fix: {i.fix}</span>
                <Button size="sm" variant="secondary" className="ml-auto shrink-0" icon={<MessageSquareText className="size-3.5" />}
                  onClick={() => { onUseFix(i.fix); onOpenChange(false); }}>Use as comment</Button>
              </div>
            )}
          </li>))}
        </ul>
      </>)}
      {best && (<>
        <h4 className="mb-2 mt-5 text-sm font-bold">How this design was chosen</h4>
        <div className="flex items-start gap-2 rounded-lg bg-surface-2 p-2.5 text-[13px]">
          <Layers className="mt-0.5 size-4 shrink-0 text-muted" />
          <div>
            <div className="font-semibold">{bestOfSummary(best)}</div>
            <p className="text-muted">
              Best-of-{best.n} sampling: several designs were generated and the one with the fewest layout problems was kept.
              {best.returned != null && best.requested != null && best.returned < best.requested
                && ` ${best.requested - best.returned} draft${best.requested - best.returned > 1 ? "s" : ""} didn't come back.`}
            </p>
          </div>
        </div>
      </>)}
      {ab && (
        <p className="mt-4 flex items-start gap-2 text-[13px] text-muted">
          <Sparkles className="mt-0.5 size-4 shrink-0 text-accent" />
          <span>
            <b className="text-ink">{ab.tie ? "The model rated the two designs evenly." : ab.preferred ? "The model preferred this design." : "The model preferred the other design."}</b>
            {ab.reason && ` ${ab.reason}`}
          </span>
        </p>
      )}
      {llm.calls ? <p className="mt-5 text-xs text-faint">{llm.calls} model calls · {((llm.prompt_tokens || 0) / 1000).toFixed(0)}k in / {((llm.completion_tokens || 0) / 1000).toFixed(1)}k out · {Math.round(llm.seconds || 0)} s</p> : null}
    </Dialog>
  );
}

/* ------------------------------------------------------------------ the model's A/B suggestion */
/**
 * The pairwise judge's opinion, shown above the two designs where the decision is actually made.
 *
 * Deliberately framed as advice and deliberately attributed: it is one vision-model call comparing
 * two screenshots, it is wrong often enough to matter, and the person looking at both designs is a
 * better judge than it is. So it suggests, it explains itself in one sentence, and it never styles
 * itself like an approval — the only green on this page belongs to the slide the user picked.
 */
function AbAdvice({ shown }: { shown: { A?: Version; B?: Version } }) {
  const advice = abAdvice(shown.A) ?? abAdvice(shown.B);
  if (!advice) return null;
  const pick = advice.tie ? null : abAdvice(shown.A)?.preferred ? "A" : abAdvice(shown.B)?.preferred ? "B" : null;
  if (!pick && !advice.tie) return null;
  return (
    <div className="mb-3 flex flex-wrap items-start gap-x-3 gap-y-1 rounded-xl bg-room-2/60 px-3 py-2.5 text-[13px] ring-1 ring-room-line">
      <span className="flex items-center gap-1.5 font-bold text-room-ink">
        <Sparkles className="size-4 text-accent" />
        {advice.tie ? "The model rates these two evenly" : `The model would pick ${lineageName[pick as Lineage]}`}
      </span>
      {advice.reason && <span className="min-w-0 flex-1 text-room-muted">{advice.reason}</span>}
      <span className="text-[11px] text-room-muted">
        Automated suggestion{advice.confidence != null && ` · ${Math.round(advice.confidence * 100)}% confident`} — your call
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ one variant column */
function VariantPanel({ slide, lineage, version, versions, onPickVersion, onChoose, onExpand, onUseFix, choosing, shortcut, session, onEdit }: {
  slide: Slide; lineage: Lineage; version?: Version; versions: Version[]; onPickVersion: (v: Version) => void;
  onChoose: (v: Version) => void; onExpand: (v: Version) => void; onUseFix: (text: string) => void; choosing: boolean; shortcut: string;
  session: EditSession; onEdit: (v: Version) => void;
}) {
  const [qaOpen, setQaOpen] = useState(false);
  const approved = !!version && slide.approved_version_id === version.id;
  const busy = isBusyVersion(version);
  const started = useMemo(() => (version ? new Date(version.created_at).getTime() : 0), [version]);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [busy]);
  const elapsed = started ? Math.max(0, Math.round((now - started) / 1000)) : 0;
  const editing = !!version && session.vid === version.id;
  // Rebuilt every render, but SlideFrame only watches the primitive/memoised members, so this
  // doesn't re-send commands to the iframe.
  const channel = editing
    ? {
      on: true, locks: session.locks, selected: session.selected, onEvent: session.handle,
      overlay: ({ sel, box }: { sel: Parameters<typeof ElementToolbar>[0]["sel"]; box: Parameters<typeof ElementToolbar>[0]["box"] }) =>
        <ElementToolbar sel={sel} box={box} session={session} />,
    }
    : undefined;

  return (
    <div className={cn("flex min-w-0 flex-col rounded-xl p-3 transition-shadow", approved ? "bg-good/10 ring-2 ring-good" : "bg-room-2/40 ring-1 ring-room-line")}>
      <div className="mb-2.5 flex items-center gap-2">
        <span className={cn("flex size-6 items-center justify-center rounded-md text-xs font-extrabold", lineage === "A" ? "bg-accent text-white" : "bg-room-ink text-room")}>{lineage}</span>
        <div className="min-w-0">
          <div className="text-sm font-bold leading-tight text-room-ink">{lineageName[lineage]}</div>
          <div className="text-[11px] text-room-muted">{lineageBlurb[lineage]}</div>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          {versions.length > 1 && version && (
            <Dropdown.Root>
              <Dropdown.Trigger className="flex h-7 items-center gap-1 rounded-md bg-room-2 px-2 text-xs font-semibold text-room-muted hover:text-room-ink">
                <History className="size-3.5" />v{version.number}<ChevronDown className="size-3" />
              </Dropdown.Trigger>
              <Dropdown.Portal>
                <Dropdown.Content align="end" sideOffset={4} className="z-50 w-72 rounded-xl border border-line bg-surface p-1 shadow-card">
                  {[...versions].reverse().map(v => (
                    <Dropdown.Item key={v.id} onSelect={() => onPickVersion(v)}
                      className={cn("flex cursor-pointer flex-col rounded-lg px-2.5 py-2 text-sm outline-none data-[highlighted]:bg-surface-2", v.id === version.id && "bg-accent-soft")}>
                      <span className="flex items-center gap-2 font-semibold">v{v.number}
                        {slide.approved_version_id === v.id && <Badge tone="good" className="h-5">Approved</Badge>}
                        {isBusyVersion(v) && <Spinner className="size-3" />}
                        {v.status === "failed" && <Badge tone="bad" className="h-5">Failed</Badge>}
                        <span className="ml-auto text-xs font-normal text-muted">{timeAgo(v.created_at)}</span>
                      </span>
                      <span className="truncate text-xs text-muted">
                        {v.origin === "edit" ? v.comment || "Hand-edited" : v.comment ? `“${v.comment}”` : "Original design"}
                      </span>
                    </Dropdown.Item>
                  ))}
                </Dropdown.Content>
              </Dropdown.Portal>
            </Dropdown.Root>
          )}
          {version?.origin === "edit" && (
            <Tip label="Changed by hand, without the model. The version it came from is still in the history.">
              <span className="flex h-7 items-center gap-1 rounded-md bg-room-2 px-2 text-xs font-semibold text-room-muted"><Pencil className="size-3" />Hand-edited</span>
            </Tip>
          )}
          {version?.status === "ready" && abAdvice(version)?.preferred && (
            <Tip label="A vision model compared the two finished designs and preferred this one. It is a suggestion, not a decision.">
              <span className="flex h-7 items-center gap-1 rounded-md bg-accent-soft px-2 text-xs font-semibold text-accent">
                <Sparkles className="size-3" />Model's pick
              </span>
            </Tip>
          )}
          {version?.status === "ready" && version.stage_note && (
            <span className="flex items-center gap-1.5 text-[11px] font-semibold text-room-muted"><Spinner className="size-3" />{version.stage_note}</span>
          )}
          {version?.status === "ready" && hasFatalFidelity(version) && (
            <Tip label={qaFatal(version)[0] || "This design states a figure the original slide does not."}>
              <button onClick={() => setQaOpen(true)}
                className="flex h-7 items-center gap-1 rounded-md bg-bad px-2 text-xs font-bold text-white">
                <AlertTriangle className="size-3" />Changes a fact
              </button>
            </Tip>
          )}
          {version?.status === "ready" && <QaBadge v={version} onOpen={() => setQaOpen(true)} />}
        </div>
      </div>

      {!version && <div className="flex aspect-video items-center justify-center rounded-lg bg-room-2 text-sm text-room-muted ring-1 ring-room-line">Not designed yet</div>}
      {busy && version && (
        <div className="shimmer relative flex aspect-video flex-col items-center justify-center gap-2 rounded-lg ring-1 ring-room-line">
          <Spinner className="size-5 text-room-ink" />
          <div className="text-sm font-semibold text-room-ink">{version.stage_note || "Designing"}</div>
          <div className="text-xs tabular-nums text-room-muted">{elapsed} s{version.comment && " · applying your comment"}</div>
        </div>
      )}
      {version && (version.status === "failed" || version.status === "cancelled") && (
        <div className="flex aspect-video flex-col items-center justify-center gap-2 rounded-lg bg-room-2 p-6 text-center ring-1 ring-room-line">
          <AlertTriangle className="size-5 text-[#ff8da0]" />
          <div className="text-sm font-semibold text-room-ink">{version.status === "cancelled" ? "Stopped before it finished" : "This design didn't come through"}</div>
          <div className="line-clamp-3 max-w-md text-xs text-room-muted">{version.error || "Regenerate the slide to try again."}</div>
        </div>
      )}
      {version?.status === "ready" && (
        // While editing, `updated_at` is deliberately out of the key: a background QA re-check
        // must not reload the document the user is working in.
        <SlideFrame key={editing ? version.id : version.id + version.updated_at} src={urls.preview(version.id, version.updated_at)}
          title={`${lineageName[lineage]} design`} startAtEnd edit={channel} />
      )}
      {editing && <EditBar session={session} onExit={session.stop} />}

      <div className="mt-3 flex items-center gap-2">
        {approved ? (
          <Badge tone="good" className="h-9 px-3 text-sm"><CircleCheck className="size-4" />In the deck</Badge>
        ) : (
          <Button variant={version?.status === "ready" ? "primary" : "room"} disabled={version?.status !== "ready"} loading={choosing}
            icon={<Check className="size-4" />} onClick={() => version && onChoose(version)}>
            Use {lineageName[lineage]} <Kbd>{shortcut}</Kbd>
          </Button>
        )}
        {version?.status === "ready" && !editing && (
          <Button variant="room" size="sm" icon={<Pencil className="size-4" />} onClick={() => onEdit(version)}>Edit</Button>
        )}
        {version?.status === "ready" && (
          <Tip label="Present full screen"><button onClick={() => onExpand(version)} aria-label="Present full screen"
            className="flex size-9 items-center justify-center rounded-lg text-room-muted hover:bg-room-2 hover:text-room-ink"><Expand className="size-4" /></button></Tip>
        )}
        {version?.comment && version.origin !== "edit" && <span className="ml-auto truncate text-xs text-room-muted" title={version.comment}>From: “{version.comment}”</span>}
      </div>
      {version?.status === "ready" && <QaDialog v={version} slide={slide} open={qaOpen} onOpenChange={setQaOpen} onUseFix={onUseFix} />}
    </div>
  );
}

/* ------------------------------------------------------------------ comment composer */
function Composer({ projectId, slide, shown, draft, onDraft, focusTick, onSent }: {
  projectId: string; slide: Slide; shown: { A?: Version; B?: Version }; draft: string; onDraft: (t: string) => void; focusTick: number; onSent: () => void;
}) {
  const qc = useQueryClient();
  const [chosen, setChosen] = useState<Lineage | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [pics, setPics] = useState<DeckAsset[]>([]);  // images to bring into this revision
  const area = useRef<HTMLTextAreaElement>(null);
  const [picsFor, setPicsFor] = useState(slide.id);
  if (picsFor !== slide.id) { setPicsFor(slide.id); setPics([]); }  // images belong to the slide they were added on

  const readyOf = (l: Lineage) => (shown[l]?.status === "ready" ? shown[l] : undefined);
  // Default to whichever lineage is actually finished, not always A.
  const base: Lineage | undefined = chosen && readyOf(chosen) ? chosen : readyOf("A") ? "A" : readyOf("B") ? "B" : undefined;
  const baseVersion = base ? readyOf(base) : undefined;
  const wasApproved = !!slide.approved_version_id;

  useKey(e => { if (e.key === "c" || e.key === "C") { e.preventDefault(); area.current?.focus(); } });
  useEffect(() => { if (focusTick > 0) area.current?.focus(); }, [focusTick]);

  const send = useMutation({
    mutationFn: ({ versionId, comment }: { versionId: string; comment: string }) =>
      api.revise(slide.id, versionId, comment, pics.map(a => a.key)),
    onSuccess: () => {
      setPics([]);
      toast.success(`Revising ${base ? lineageName[base] : "the design"}`, { description: "The new version appears in its column when it's ready." });
      onDraft("");
      qc.invalidateQueries({ queryKey: ["project"] });
      onSent();
    },
    onError: e => toast.error("Couldn't send your comment", { description: (e as Error).message }),
  });

  const hasInput = !!draft.trim() || pics.length > 0;
  const canSend = hasInput && !!baseVersion && !send.isPending;
  const fire = () => { if (baseVersion && hasInput) send.mutate({ versionId: baseVersion.id, comment: draft.trim() }); };
  const submit = () => {
    if (!canSend) return;
    if (wasApproved) setConfirm(true);
    else fire();
  };

  return (
    <div className="on-light rounded-xl bg-surface p-3 shadow-card">
      <div className="flex flex-col gap-3 md:flex-row md:items-end">
        <div className="min-w-0 flex-1">
          <label htmlFor="comment" className="mb-1.5 flex items-center gap-2 text-[13px] font-bold">
            <MessageSquareText className="size-4 text-accent" />Neither is right? Describe what to change <Kbd>C</Kbd>
          </label>
          <Textarea id="comment" ref={area} rows={2} value={draft} onChange={e => onDraft(e.target.value)} disabled={!baseVersion}
            onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(); if (e.key === "Escape") area.current?.blur(); }}
            placeholder={baseVersion
              ? "e.g. Keep the chart from Cinematic but use Refined's calmer layout, shorten the title, and highlight the 3.4× growth."
              : "A revision starts from a finished design — wait for one to come through."} />
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {pics.map(a => (
              <span key={a.key} className="flex items-center gap-1 rounded-md bg-surface-2 py-0.5 pl-0.5 pr-1.5 text-[11px] font-semibold ring-1 ring-line">
                <img src={a.url} alt="" className="size-6 rounded object-cover" />
                <button aria-label="Remove image" onClick={() => setPics(pics.filter(x => x.key !== a.key))} className="text-muted hover:text-ink"><X className="size-3" /></button>
              </span>
            ))}
            <AddImageButton projectId={projectId} label={pics.length ? "Another image" : "Add an image"}
              onPick={a => setPics(list => list.some(x => x.key === a.key) ? list : [...list, a])} />
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <div className="flex rounded-lg border border-line p-0.5" role="radiogroup" aria-label="Start from">
            {(["A", "B"] as const).map(l => (
              <button key={l} role="radio" aria-checked={base === l} onClick={() => setChosen(l)} disabled={!readyOf(l)}
                className={cn("h-8 rounded-md px-3 text-[13px] font-semibold transition-colors disabled:opacity-40",
                  base === l ? "bg-ink text-canvas" : "text-muted hover:text-ink")}>
                Start from {lineageName[l]}
              </button>
            ))}
          </div>
          <Button variant="primary" icon={<Wand2 className="size-4" />} disabled={!canSend} loading={send.isPending} onClick={submit}>Revise</Button>
        </div>
      </div>
      {!baseVersion && (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-muted">
          <AlertTriangle className="size-3.5 text-warn" />
          Neither design is ready yet, so there's nothing to revise from. Wait for one to finish, or use <b>Redesign both</b>.
        </p>
      )}
      {baseVersion && wasApproved && (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-muted">
          <AlertTriangle className="size-3.5 text-warn" />
          This slide is approved. Sending a comment removes the approval until you pick a design again.
        </p>
      )}
      <Dialog open={confirm} onOpenChange={setConfirm} title="Revising removes this slide's approval"
        description={`Slide ${slide.label ?? slide.index} is currently in the deck. A revision drops it back to “Pick a design” until you approve one — the approved version stays in the history.`}
        footer={<>
          <Button onClick={() => setConfirm(false)}>Keep the approval</Button>
          <Button variant="primary" onClick={() => { setConfirm(false); fire(); }}>Revise anyway</Button>
        </>} />
    </div>
  );
}

/* ------------------------------------------------------------------ page */
export default function ReviewView({ project: p }: { project: Project }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const slides = useMemo(() => (p.slides ?? []).filter(s => s.included), [p.slides]);
  const firstOpen = slides.find(s => s.status === "review") ?? slides[0];
  const current = slides.find(s => s.id === params.get("s")) ?? firstOpen;
  const idx = current ? slides.indexOf(current) : -1;
  const [picked, setPicked] = useState<Record<string, string>>({}); // lineage-key -> version id
  // Comment drafts are kept per slide so J/K never throws away a typed sentence.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [focusTick, setFocusTick] = useState(0);
  const [expand, setExpand] = useState<Version | null>(null);
  const [showSource, setShowSource] = useState(false);
  // Direct editing. The queue lives here, above everything the SSE stream invalidates, so a
  // background refetch of ["project"] can never take unsaved changes with it.
  const session = useEditSession(p.id);
  useLibraryEvents();
  const editSlide = useRef<string | null>(null);
  const dirty = session.pending.length > 0;
  const go = (id: string) => {
    if (dirty) {
      toast("Save or discard your edits first", { description: "They belong to the slide you're on." });
      return;
    }
    setParams({ s: id }, { replace: true });
  };
  const setDraft = (id: string, text: string) => setDrafts(d => ({ ...d, [id]: text }));

  // Leaving the slide closes the session; `editSlide` rather than the version list, because a save
  // switches to a version the project payload hasn't been refetched with yet.
  useEffect(() => {
    if (session.vid && editSlide.current && editSlide.current !== current?.id) session.stop();
  }, [current, session]);

  const byLineage = (l: Lineage) => (current ? current.versions.filter(v => v.lineage === l) : []);
  const shownFor = (l: Lineage): Version | undefined => {
    const list = byLineage(l);
    const pin = picked[`${current?.id}:${l}`];
    return list.find(v => v.id === pin) ?? list[list.length - 1];
  };
  const shown = { A: shownFor("A"), B: shownFor("B") };

  const choose = useMutation({
    mutationFn: (v: Version) => api.choose(v.slide_id, v.id),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: ["project", p.id] });
      const next = slides.slice(idx + 1).find(s => s.status !== "approved");
      toast.success(`Slide ${current?.index}: ${lineageName[v.lineage]} approved`, next ? { description: `Moving to slide ${next.index}` } : undefined);
      if (next) go(next.id);
    },
    onError: e => toast.error("Couldn't approve", { description: (e as Error).message }),
  });
  const [redesign, setRedesign] = useState(false);
  const unapprove = useMutation({
    mutationFn: (slideId: string) => api.unapprove(slideId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project", p.id] }),
    onError: e => toast.error("Couldn't undo the approval", { description: (e as Error).message }),
  });
  const startEdit = (v: Version) => {
    editSlide.current = v.slide_id;
    session.start(v.id);
  };

  useKey(e => {
    if (expand) return;
    if (e.key === "Escape" && session.vid && !dirty) { session.stop(); return; }
    if (e.key === "e" || e.key === "E") {
      const v = shown.A?.status === "ready" ? shown.A : shown.B?.status === "ready" ? shown.B : undefined;
      if (v && !session.vid) { e.preventDefault(); startEdit(v); return; }
    }
    if (e.key === "j" || e.key === "ArrowDown") { const n = slides[idx + 1]; if (n) { e.preventDefault(); go(n.id); } }
    if (e.key === "k" || e.key === "ArrowUp") { const n = slides[idx - 1]; if (n) { e.preventDefault(); go(n.id); } }
    if (e.key === "1" && shown.A?.status === "ready") choose.mutate(shown.A);
    if (e.key === "2" && shown.B?.status === "ready") choose.mutate(shown.B);
    if (e.key === "o" || e.key === "O") setShowSource(x => !x);
  });

  if (!current) {
    return (
      <Empty icon={<ImageIcon className="size-5" />} title="No slides are in the deck yet"
        body="Every slide is switched off, so there's nothing to review. Turn the ones you want back on in the Plan step."
        action={<Button variant="primary" onClick={() => nav(`/p/${p.id}/plan`)}>Go to the plan</Button>} />
    );
  }
  const allApproved = slides.every(s => s.status === "approved");
  const draft = drafts[current.id] ?? "";
  const useFix = (fix: string) => {
    setDrafts(d => {
      const prev = (d[current.id] ?? "").trim();
      return { ...d, [current.id]: prev ? `${prev}\n${fix}` : fix };
    });
    setFocusTick(t => t + 1);
  };

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-[260px_1fr]">
      <div className="hidden min-h-0 md:block"><Rail slides={slides} current={current.id} onPick={go} /></div>
      <div className="room flex min-h-0 flex-col bg-room">
        <MobileRail slides={slides} current={current} onPick={go} />
        <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1500px] px-4 py-4 sm:px-6">
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <div className="min-w-0">
                <div className="text-xs font-semibold text-room-muted">Slide {current.index} of {p.counts.slides} · {current.plan.pattern?.replace("-", " ")}</div>
                <h2 className="truncate text-xl font-extrabold tracking-tight text-room-ink">{current.plan.headline || current.source_title}</h2>
              </div>
              <div className="ml-auto flex flex-wrap items-center gap-2">
                {current.status === "approved" && current.approved_version_id && (
                  <LibraryStar room projectId={p.id} slideId={current.id} kind="generated" />
                )}
                {p.counts.approved > 0 && <SaveToLibraryButton room projectId={p.id} kind="generated" label="Save approved to library" />}
                {allApproved && <Button variant="primary" size="sm" icon={<CircleCheck className="size-4" />} onClick={() => nav(`/p/${p.id}/export`)}>All approved: export</Button>}
                <Button variant="room" size="sm" icon={<ImageIcon className="size-4" />} onClick={() => setShowSource(x => !x)} aria-pressed={showSource}>
                  {showSource ? "Hide original" : "Show original"} <Kbd>O</Kbd>
                </Button>
                {current.status === "approved" && <Button variant="room" size="sm" icon={<Undo2 className="size-4" />} loading={unapprove.isPending} onClick={() => unapprove.mutate(current.id)}>Undo approval</Button>}
                <Button variant="room" size="sm" icon={<RefreshCw className="size-4" />}
                  disabled={current.status === "generating" || current.status === "revising"} onClick={() => setRedesign(true)}>Redesign both</Button>
              </div>
            </div>

            {showSource && (
              <div className="mb-4 flex gap-4 rounded-xl bg-room-2/60 p-3 ring-1 ring-room-line">
                <Thumb key={current.id} src={urls.source(current.id)} alt={`Original slide ${current.index}`} className="w-72 rounded-md bg-white"
                  fallback={<div className="flex aspect-video w-72 items-center justify-center rounded-md bg-room-2 text-xs text-room-muted ring-1 ring-room-line">No preview was rendered</div>} />
                <div className="min-w-0 text-[13px] text-room-muted">
                  <div className="font-semibold text-room-ink">Original: {current.source_title || "untitled"}</div>
                  {current.plan.key_message && <p className="mt-2"><span className="text-room-ink">Key message:</span> {current.plan.key_message}</p>}
                  {current.notes && <p className="mt-2 line-clamp-4 whitespace-pre-wrap"><span className="text-room-ink">Speaker notes:</span> {current.notes}</p>}
                </div>
              </div>
            )}

            <AbAdvice shown={shown} />
            <div className="grid gap-4 xl:grid-cols-2">
              {(["A", "B"] as const).map((l, i) => (
                <VariantPanel key={l} slide={current} lineage={l} version={shown[l]} versions={byLineage(l)} shortcut={String(i + 1)}
                  onPickVersion={v => setPicked(x => ({ ...x, [`${current.id}:${l}`]: v.id }))}
                  onChoose={v => choose.mutate(v)} onExpand={setExpand} onUseFix={useFix} session={session} onEdit={startEdit}
                  choosing={choose.isPending && choose.variables?.lineage === l} />
              ))}
            </div>
          </div>
        </div>
        <div className="border-t border-room-line px-4 py-3 sm:px-6">
          <div className="mx-auto max-w-[1500px]">
            <RedesignDialog slide={current} open={redesign} onOpenChange={setRedesign} />
            <Composer projectId={p.id} slide={current} shown={shown} draft={draft} focusTick={focusTick}
              onDraft={t => setDraft(current.id, t)}
              onSent={() => setPicked(x => { const y = { ...x }; delete y[`${current.id}:A`]; delete y[`${current.id}:B`]; return y; })} />
            <div className="mt-2 hidden flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-room-muted sm:flex">
              <span><Kbd>J</Kbd> <Kbd>K</Kbd> next / previous slide</span>
              <span><Kbd>1</Kbd> <Kbd>2</Kbd> use a design</span>
              <span><Kbd>E</Kbd> edit the slide directly</span>
              <span>Click a preview, then use arrow keys to step through it</span>
              <span><Kbd>?</Kbd> all shortcuts</span>
            </div>
          </div>
        </div>
      </div>

      <Dialog open={!!expand} onOpenChange={o => !o && setExpand(null)} wide title={expand ? `${lineageName[expand.lineage]} v${expand.number}` : ""}
        description="Use the arrow keys to step through clicks. Interactive controls work as they will in the final deck.">
        {expand && <SlideFrame src={urls.preview(expand.id, expand.updated_at)} dark={false} autoFocus />}
        {expand && expand.notes.length > 0 && (
          <div className="mt-4 rounded-lg bg-surface-2 p-3 text-sm">
            <div className="mb-1 font-bold">Speaker notes</div>
            <ul className="list-disc space-y-1 pl-5 text-muted">{expand.notes.map((n, i) => <li key={i} dangerouslySetInnerHTML={{ __html: safeNotesHtml(n) }} />)}</ul>
          </div>
        )}
      </Dialog>
    </div>
  );
}
