import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CircleAlert, ListChecks, Loader2, MessagesSquare, RefreshCw, Wand2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api, type ConsistencyIssue, type Project, type Slide } from "../lib/api";
import { cn, patterns } from "../lib/util";
import { Badge, Button, Dialog, Field, Textarea, inputClass } from "./ui";

/* ------------------------------------------------------------------ redesign with a reason */
const REASONS: { key: string; label: string }[] = [
  { key: "too-dense", label: "Too dense" }, { key: "wrong-layout", label: "Wrong layout" },
  { key: "off-story", label: "Off-story" }, { key: "too-plain", label: "Too plain" },
  { key: "too-busy", label: "Too busy" }, { key: "facts-buried", label: "Key facts buried" },
  { key: "chart-wrong", label: "Chart is wrong" },
];

/** "Redesign both", with why. The reasons and what the rejected designs were built from go into the prompt, so
 *  the redesign doesn't repeat them (backend `runner.redesign_note`), and the reasons are kept as feedback. */
export function RedesignDialog({ slide, open, onOpenChange }: { slide: Slide; open: boolean; onOpenChange: (v: boolean) => void }) {
  const qc = useQueryClient();
  const [reasons, setReasons] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [pattern, setPattern] = useState("");
  const toggle = (k: string) => setReasons(r => r.includes(k) ? r.filter(x => x !== k) : [...r, k]);
  const go = useMutation({
    mutationFn: () => api.regenerate(slide.id, { reasons, note, pattern: reasons.includes("wrong-layout") && pattern ? pattern : null }),
    onSuccess: () => {
      toast.success(`Redesigning slide ${slide.label}`, { description: reasons.length || note ? "With your reasons — the new designs won't repeat the old ones." : undefined });
      qc.invalidateQueries({ queryKey: ["project"] });
      setReasons([]); setNote(""); setPattern("");
      onOpenChange(false);
    },
    onError: e => toast.error("Couldn't redesign the slide", { description: (e as Error).message }),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={`Redesign slide ${slide.label}`}
      description="Both designs are made again from the plan. Say what's wrong and the new ones won't repeat it."
      footer={<><Button onClick={() => onOpenChange(false)}>Cancel</Button>
        <Button variant="primary" icon={<RefreshCw className="size-4" />} loading={go.isPending} onClick={() => go.mutate()}>
          {reasons.length || note.trim() ? "Redesign with these reasons" : "Redesign anyway"}
        </Button></>}>
      <div className="space-y-4">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="What's wrong">
          {REASONS.map(r => (
            <button key={r.key} onClick={() => toggle(r.key)} aria-pressed={reasons.includes(r.key)}
              className={cn("rounded-full px-3 py-1 text-[13px] font-semibold ring-1 transition-colors",
                reasons.includes(r.key) ? "bg-accent text-accent-ink ring-accent" : "bg-surface text-muted ring-line hover:text-ink")}>
              {r.label}
            </button>
          ))}
        </div>
        {reasons.includes("wrong-layout") && (
          <Field label="Try this layout (optional)">
            <select value={pattern} onChange={e => setPattern(e.target.value)} className={inputClass}>
              <option value="">Let the designer choose a different one</option>
              {patterns.filter(x => x !== slide.plan.pattern).map(x => <option key={x} value={x}>{x.replace("-", " ")}</option>)}
            </select>
          </Field>
        )}
        <Field label="In your words (optional)">
          <Textarea rows={2} value={note} onChange={e => setNote(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) go.mutate(); }}
            placeholder="e.g. The saving is the point — make $4.2M the first thing people see." />
        </Field>
      </div>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ one instruction, every slide */
export function InstructDialog({ p, open, onOpenChange, selected }: {
  p: Project; open: boolean; onOpenChange: (v: boolean) => void; selected: string[];
}) {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [onlyPicked, setOnlyPicked] = useState(false);
  const designed = (p.slides ?? []).filter(s => s.included && !s.plan.removed && s.versions.some(v => v.status === "ready"));
  const picked = designed.filter(s => selected.includes(s.id));
  const scope = onlyPicked && picked.length ? picked : designed;
  const go = useMutation({
    mutationFn: () => api.instructDeck(p.id, text.trim(), onlyPicked && picked.length ? picked.map(s => s.id) : null),
    onSuccess: r => {
      toast.success(`Applying it to ${r.slides} slide${r.slides === 1 ? "" : "s"}`, {
        description: "One slide at a time. Approved slides stay approved when the revision passes its checks.",
      });
      qc.invalidateQueries({ queryKey: ["project", p.id] });
      setText("");
      onOpenChange(false);
    },
    onError: e => toast.error("Couldn't start", { description: (e as Error).message }),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Instruct the whole deck"
      description="One instruction, revised into every designed slide — each one still passes its own checks."
      footer={<><Button onClick={() => onOpenChange(false)}>Cancel</Button>
        <Button variant="primary" icon={<Wand2 className="size-4" />} disabled={!text.trim() || !scope.length}
          loading={go.isPending} onClick={() => go.mutate()}>Apply to {scope.length} slide{scope.length === 1 ? "" : "s"}</Button></>}>
      <div className="space-y-3">
        <Textarea rows={3} value={text} onChange={e => setText(e.target.value)} autoFocus
          placeholder={"e.g. Less text on every slide — move detail to the speaker notes.\nor: Call it “Z8 Fury G5” everywhere."} />
        {picked.length > 0 && (
          <label className="flex items-center gap-2 text-[13px]">
            <input type="checkbox" checked={onlyPicked} onChange={e => setOnlyPicked(e.target.checked)} />
            Only the {picked.length} slide{picked.length === 1 ? "" : "s"} I ticked ({picked.map(s => s.label).join(", ")})
          </label>
        )}
        {!designed.length && <p className="text-xs text-warn">Nothing is designed yet — design the slides first.</p>}
      </div>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ deck check: readiness + consistency */
export function DeckCheck({ p }: { p: Project }) {
  const qc = useQueryClient();
  const ready = useQuery({ queryKey: ["readiness", p.id, p.updated_at], queryFn: () => api.readiness(p.id) });
  const cons = p.brief.consistency;
  const review = useMutation({
    mutationFn: () => api.reviewConsistency(p.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project", p.id] }),
    onError: e => toast.error("Couldn't review the deck", { description: (e as Error).message }),
  });
  const fix = useMutation({
    mutationFn: (i: ConsistencyIssue) => api.instructDeck(p.id, i.fix || i.issue, i.slide_ids.slice(0, 1)),
    onSuccess: () => { toast.success("Revising that slide"); qc.invalidateQueries({ queryKey: ["project", p.id] }); },
    onError: e => toast.error("Couldn't start the fix", { description: (e as Error).message }),
  });
  const reviewing = review.isPending || /Reviewing the deck/.test(p.stage_note);
  const label = (id: string) => (p.slides ?? []).find(s => s.id === id)?.label ?? "?";
  const items = ready.data?.items ?? [];

  return (
    <section className="rounded-2xl border border-line bg-surface p-5">
      <div className="flex items-center gap-2">
        <ListChecks className="size-5 text-accent" />
        <h2 className="text-base font-bold">Before you send it</h2>
        {ready.data && (ready.data.ready
          ? <Badge tone="good"><CheckCircle2 className="size-3" />Ready</Badge>
          : <Badge tone="bad">{ready.data.blocks} to fix</Badge>)}
        {ready.data && ready.data.warnings > 0 && <Badge tone="warn">{ready.data.warnings} to check</Badge>}
      </div>
      {ready.isLoading && <p className="mt-3 flex items-center gap-2 text-xs text-muted"><Loader2 className="size-3.5 animate-spin" />Checking the deck</p>}
      {items.length > 0 && (
        <ul className="mt-3 max-h-72 space-y-1 overflow-y-auto">
          {items.map((it, i) => (
            <li key={i} className="flex items-start gap-2 text-[13px]">
              {it.severity === "block" ? <CircleAlert className="mt-0.5 size-4 shrink-0 text-bad" /> : <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warn" />}
              {it.slide_id
                ? <Link to={`/p/${p.id}/review?s=${it.slide_id}`} className="shrink-0 font-bold text-accent hover:underline">Slide {it.label}</Link>
                : <span className="shrink-0 font-bold">Deck</span>}
              <span className="min-w-0 text-muted">{it.message}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-5 flex items-center gap-2">
        <MessagesSquare className="size-4 text-muted" />
        <h3 className="text-[13px] font-bold">Consistency across slides</h3>
        <Button size="sm" variant="ghost" className="ml-auto" icon={reviewing ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
          disabled={reviewing || p.busy} onClick={() => review.mutate()}>{cons ? "Review again" : "Review the deck"}</Button>
      </div>
      {cons?.note && <p className="mt-1 text-xs text-warn">{cons.note}</p>}
      {cons && !cons.issues.length && <p className="mt-2 text-[13px] text-muted">No problems found across slides.</p>}
      {cons && cons.issues.length > 0 && (
        <ul className="mt-2 space-y-2">
          {cons.issues.map((i, k) => (
            <li key={k} className="rounded-lg bg-surface-2 p-2.5 text-[13px]">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge>{i.kind}</Badge>
                {i.slide_ids.map(id => <Link key={id} to={`/p/${p.id}/review?s=${id}`} className="font-bold text-accent hover:underline">Slide {label(id)}</Link>)}
              </div>
              <p className="mt-1">{i.issue}</p>
              {i.fix && (
                <div className="mt-1.5 flex items-start gap-2">
                  <p className="min-w-0 flex-1 text-xs text-muted">Fix: {i.fix}</p>
                  <Button size="sm" variant="ghost" icon={<Wand2 className="size-3.5" />} disabled={p.busy} loading={fix.isPending}
                    onClick={() => fix.mutate(i)}>Fix slide {label(i.slide_ids[0] ?? "")}</Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
