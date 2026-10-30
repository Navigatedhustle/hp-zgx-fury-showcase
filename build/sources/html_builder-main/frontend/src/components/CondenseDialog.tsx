import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowDownToLine, ArrowUpToLine, Combine, Loader2, Scissors, Undo2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { api, isRemoved, type CondenseGroup, type CondenseProposal, type Project, type Slide } from "../lib/api";
import { cn } from "../lib/util";
import { Badge, Button, Dialog, Field, Textarea, inputClass } from "./ui";

/* ------------------------------------------------------------------ condense to N slides
 * "Cut this to 7 for a 10-minute slot." The model proposes which slides stay, which combine and which become
 * backup; the user reviews and adjusts; Apply makes it so — reversibly (backend/app/pipeline/deckops.py). */

export function CondenseDialog({ p, open, onOpenChange, keep }: {
  p: Project; open: boolean; onOpenChange: (v: boolean) => void; keep: string[];
}) {
  const qc = useQueryClient();
  const main = (p.slides ?? []).filter(s => !isRemoved(s) && !s.plan.appendix);
  const [target, setTarget] = useState(Math.max(1, Math.ceil(main.length / 2)));
  const [guidance, setGuidance] = useState("");
  const [waitingFor, setWaitingFor] = useState<string | null>(null);  // the proposal we are replacing
  const proposal = p.brief.condense_proposal;
  const key = proposal ? JSON.stringify(proposal) : "";
  const waiting = waitingFor !== null && waitingFor === key;
  const done = () => qc.invalidateQueries({ queryKey: ["project", p.id] });

  const propose = useMutation({
    mutationFn: () => api.proposeCondense(p.id, { target, keep: keep.filter(id => main.some(s => s.id === id)), guidance }),
    onMutate: () => setWaitingFor(key),
    onSuccess: done,
    onError: e => { setWaitingFor(null); toast.error("Couldn't propose a shorter deck", { description: (e as Error).message }); },
  });
  const dismiss = useMutation({ mutationFn: () => api.dismissCondense(p.id), onSuccess: done });

  return (
    <Dialog open={open} onOpenChange={onOpenChange} wide title="Condense the deck"
      description={`${main.length} slides now. Choose how many you have time for; what doesn't fit becomes appendix slides after the main deck — nothing is deleted, and it can be undone.`}>
      {proposal && !waiting ? (
        <Review p={p} proposal={proposal} onApplied={() => onOpenChange(false)}
          onRedo={() => dismiss.mutate(undefined, { onSuccess: () => { setTarget(proposal.target); setGuidance(proposal.guidance ?? ""); } })} />
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-[160px_1fr]">
            <Field label="Main slides">
              <input type="number" min={1} max={main.length} value={target} className={inputClass}
                onChange={e => setTarget(Math.max(1, Math.min(main.length, Number(e.target.value) || 1)))} />
            </Field>
            <Field label="What matters" hint="Audience, time slot, and what must survive. The planner reads this word for word.">
              <Textarea rows={3} value={guidance} onChange={e => setGuidance(e.target.value)}
                placeholder="e.g. 10-minute slot with the CFO — keep the cost comparison and the ask; the technical detail can go to backup." />
            </Field>
          </div>
          <p className="text-xs text-muted">
            {keep.length
              ? <>Slides you ticked stay in the main deck: <b>{main.filter(s => keep.includes(s.id)).map(s => s.label).join(", ")}</b>.</>
              : "Tip: tick slides in the plan first to make sure they stay."}
          </p>
          <div className="flex justify-end gap-2">
            <Button onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button variant="primary" icon={waiting ? <Loader2 className="size-4 animate-spin" /> : <Scissors className="size-4" />}
              disabled={waiting || target >= main.length} onClick={() => propose.mutate()}>
              {waiting ? "Proposing…" : `Propose ${target} slides`}
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}

function Review({ p, proposal, onApplied, onRedo }: {
  p: Project; proposal: CondenseProposal; onApplied: () => void; onRedo: () => void;
}) {
  const qc = useQueryClient();
  const byId = new Map((p.slides ?? []).map(s => [s.id, s]));
  const [main, setMain] = useState<CondenseGroup[]>(proposal.main);
  const [appendix, setAppendix] = useState<string[]>(proposal.appendix);
  const pos = (id: string) => byId.get(id)?.position ?? 0;
  const name = (id: string) => byId.get(id)?.label ?? "?";
  const title = (id: string) => byId.get(id)?.plan.headline || byId.get(id)?.source_title || "Untitled";

  const toAppendix = (i: number) => {
    const g = main[i];
    if (!g) return;
    setMain(main.filter((_, k) => k !== i));
    setAppendix([...appendix, ...g.ids].sort((a, b) => pos(a) - pos(b)));
  };
  const toMain = (id: string) => {
    setAppendix(appendix.filter(x => x !== id));
    const at = main.findIndex(g => Math.min(...g.ids.map(pos)) > pos(id));
    const next = [...main];
    next.splice(at < 0 ? next.length : at, 0, { ids: [id], headline: byId.get(id)?.plan.headline, why: "Added back by you." });
    setMain(next);
  };
  const apply = useMutation({
    mutationFn: () => api.applyCondense(p.id, { main, appendix }),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ["project", p.id] });
      toast.success(`Condensed to ${main.length} slides`, {
        description: `${appendix.length} moved to the appendix${r.created.length ? `; planning ${r.created.length} combined slide${r.created.length > 1 ? "s" : ""}` : ""}. Undo from the plan.`,
      });
      onApplied();
    },
    onError: e => toast.error("Couldn't apply it", { description: (e as Error).message }),
  });
  const over = main.length > proposal.target;

  return (
    <div className="space-y-4">
      {proposal.why && <p className="rounded-lg bg-surface-2 p-3 text-[13px] text-muted">{proposal.why}</p>}
      {proposal.source === "fallback" && (
        <p className="text-xs text-warn">The model's proposal didn't hold together, so this is a simple one: the slides you marked plus those with the most key figures, nothing combined. Adjust it, or propose again.</p>
      )}
      <div>
        <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-faint">Main deck · {main.length} of {proposal.target}</h3>
        <ol className="space-y-1.5">
          {main.map((g, i) => (
            <li key={g.ids.join("+")} className="flex items-start gap-3 rounded-lg border border-line px-3 py-2 text-[13px]">
              <span className="w-5 shrink-0 pt-0.5 font-bold tabular-nums text-muted">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <b className="truncate">{g.headline || title(g.ids[0] ?? "")}</b>
                  {g.ids.length > 1 && <Badge tone="accent"><Combine className="size-3" />{g.ids.map(name).join(" + ")}</Badge>}
                  {g.ids.length === 1 && <span className="text-xs text-muted">slide {name(g.ids[0] ?? "")}</span>}
                </div>
                {g.why && <p className="text-xs text-muted">{g.why}</p>}
              </div>
              <Button size="sm" variant="ghost" icon={<ArrowDownToLine className="size-3.5" />} disabled={main.length <= 1}
                onClick={() => toAppendix(i)}>To appendix</Button>
            </li>
          ))}
        </ol>
      </div>
      {appendix.length > 0 && (
        <div>
          <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-faint">Appendix · {appendix.length}</h3>
          <ul className="space-y-1">
            {appendix.map(id => (
              <li key={id} className="flex items-center gap-3 rounded-lg bg-surface-2 px-3 py-1.5 text-[13px]">
                <span className="w-8 shrink-0 font-bold tabular-nums text-muted">{name(id)}</span>
                <span className="min-w-0 flex-1 truncate">{title(id)}</span>
                <Button size="sm" variant="ghost" icon={<ArrowUpToLine className="size-3.5" />} onClick={() => toMain(id)}>To main</Button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-end gap-2">
        {over && <span className={cn("mr-auto text-xs text-warn")}>{main.length} main slides — more than the {proposal.target} you asked for.</span>}
        <Button onClick={onRedo}>Change and propose again</Button>
        <Button variant="primary" icon={<Scissors className="size-4" />} loading={apply.isPending} onClick={() => apply.mutate()}>
          Apply
        </Button>
      </div>
    </div>
  );
}

/** Shown in the plan once a condense was applied. */
export function CondensedBanner({ p }: { p: Project }) {
  const qc = useQueryClient();
  const undo = useMutation({
    mutationFn: () => api.undoCondense(p.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["project", p.id] }); toast.success("The full deck is back"); },
    onError: e => toast.error("Couldn't undo", { description: (e as Error).message }),
  });
  if (!p.brief.condense_undo) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-line-2 bg-surface-2 px-4 py-2 text-[13px]">
      <Scissors className="size-4 text-muted" />
      Condensed: <b>{p.counts.slides - (p.counts.appendix ?? 0)}</b> main slides{p.counts.appendix ? <> + <b>{p.counts.appendix}</b> in the appendix</> : null}.
      <Button size="sm" variant="ghost" className="ml-auto" icon={<Undo2 className="size-3.5" />} loading={undo.isPending}
        onClick={() => undo.mutate()}>Undo condense</Button>
    </div>
  );
}

export const isAppendix = (s: Slide) => !!s.plan.appendix;
