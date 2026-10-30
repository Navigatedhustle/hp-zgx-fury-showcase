import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FileText, Loader2, RefreshCw, Star, Trash2, Upload } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";
import { toast } from "sonner";
import { api, type ProjectDoc } from "../lib/api";
import { cn } from "../lib/util";
import { Button, IconButton, Tip } from "./ui";

const ACCEPT = ".pdf,.docx,.txt,.md";

/**
 * Reference documents: the brief behind the deck (a proposal, a whitepaper, an RFP). The planner reads a digest of
 * each, the designer gets the passages relevant to each slide, and a figure from a document reaches a slide only
 * through the fact ledger, cited. See backend/app/docs.py.
 */
export function ReferenceDocs({ projectId, onReplan, replanning, locked }: {
  projectId: string; onReplan?: () => void; replanning?: boolean; locked?: boolean;
}) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [fresh, setFresh] = useState(false);  // a document arrived since the last plan
  const list = useQuery({
    queryKey: ["docs", projectId],
    queryFn: () => api.docs(projectId),
    // the digest is one model call; poll only while one is running
    refetchInterval: q => (q.state.data?.some(d => d.status === "digesting") ? 1500 : false),
  });
  const upload = useMutation({
    mutationFn: (f: File) => api.uploadDoc(projectId, f),
    onSuccess: d => {
      qc.invalidateQueries({ queryKey: ["docs", projectId] });
      setFresh(true);
      toast.success(`Added ${d.name}`, { description: `${d.pages} page${d.pages === 1 ? "" : "s"} read. Summarising it for the planner…` });
    },
    onError: e => toast.error("Couldn't add that document", { description: (e as Error).message }),
  });
  const remove = useMutation({
    mutationFn: (d: ProjectDoc) => api.deleteDoc(d.id),
    onSuccess: (r, d) => {
      qc.invalidateQueries({ queryKey: ["docs", projectId] });
      qc.invalidateQueries({ queryKey: ["project", projectId] });
      setFresh(true);
      const n = r.slides_affected.length;
      if (n) toast.warning(`${d.name} removed`, { description: `${n} slide${n === 1 ? "" : "s"} had figures from it. Their designs may still show them — redesign those slides.`, duration: 10_000 });
    },
    onError: e => toast.error("Couldn't remove the document", { description: (e as Error).message }),
  });
  const mark = useMutation({
    mutationFn: (d: ProjectDoc) => api.patchDoc(d.id, { primary: !d.primary }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["docs", projectId] }); setFresh(true); },
    onError: e => toast.error("Couldn't update the document", { description: (e as Error).message }),
  });
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    [...e.dataTransfer.files].forEach(f => upload.mutate(f));
  };
  const docs = list.data ?? [];
  const busy = docs.some(d => d.status === "digesting");
  // Two or more documents can disagree; the list changes when a digest lands or a document is marked.
  const stamp = docs.map(d => `${d.id}${d.status}${d.primary ? 1 : 0}`).join();
  const clash = useQuery({
    queryKey: ["docs", projectId, "conflicts", stamp], queryFn: () => api.docConflicts(projectId),
    enabled: docs.length > 1 && !busy,
  });
  const conflicts = docs.length > 1 ? clash.data ?? [] : [];

  return (
    <section className="rounded-2xl border border-line bg-surface p-5"
      onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-base font-bold">Reference documents</h2>
        <Button size="sm" variant="ghost" icon={upload.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />}
          disabled={locked || upload.isPending} onClick={() => input.current?.click()}>Add</Button>
      </div>
      <p className="text-xs text-muted">A proposal, whitepaper or brief behind this deck (PDF, Word, text). The planner uses it for
        emphasis and story; figures from it reach a slide only when quoted exactly, and are cited.</p>
      <input ref={input} type="file" accept={ACCEPT} multiple className="hidden"
        onChange={e => { [...(e.target.files ?? [])].forEach(f => upload.mutate(f)); e.target.value = ""; }} />
      {docs.length === 0 ? (
        <button onClick={() => input.current?.click()} disabled={locked}
          className={cn("mt-3 flex w-full flex-col items-center gap-1 rounded-xl border-2 border-dashed p-4 text-xs text-muted",
            over ? "border-accent bg-accent/5" : "border-line hover:border-accent")}>
          <FileText className="size-5" />Drop a document here, or browse
        </button>
      ) : (
        <ul className={cn("mt-3 space-y-1.5 rounded-xl", over && "ring-2 ring-accent")}>
          {docs.map(d => (
            <li key={d.id} className="flex items-center gap-2 rounded-lg bg-surface-2 px-2.5 py-2 text-[13px]">
              <FileText className="size-4 shrink-0 text-muted" />
              <Tip label={d.digest ? d.digest.slice(0, 600) : d.error || "Summarising…"}>
                <span className="min-w-0 flex-1 truncate font-semibold">{d.name}</span>
              </Tip>
              {docs.length > 1 && (
                <Tip label={d.primary ? "Primary — its figures win where documents disagree. Click to unmark." : "Mark as primary: believe this one where documents disagree"}>
                  <button aria-label={`Mark ${d.name} as primary`} aria-pressed={!!d.primary} disabled={locked} onClick={() => mark.mutate(d)}
                    className={cn("flex size-6 shrink-0 items-center justify-center rounded-md", d.primary ? "text-warn" : "text-faint hover:text-ink")}>
                    <Star className={cn("size-3.5", d.primary && "fill-current")} />
                  </button>
                </Tip>
              )}
              <span className="shrink-0 text-[11px] text-muted">
                {d.status === "digesting" ? <Loader2 className="size-3.5 animate-spin" />
                  : d.status === "error" ? <AlertTriangle className="size-3.5 text-bad" />
                  : `${d.pages} p.${d.truncated ? " (cut)" : ""}${d.sections && d.sections > 1 ? ` · ${d.sections} sections` : ""}${d.pictures ? ` · ${d.pictures} image${d.pictures === 1 ? "" : "s"}` : ""}`}
              </span>
              <IconButton label={`Remove ${d.name}`} disabled={locked} onClick={() => remove.mutate(d)}><Trash2 className="size-3.5" /></IconButton>
            </li>
          ))}
        </ul>
      )}
      {conflicts.length > 0 && (
        <div className="mt-3 rounded-xl bg-warn-soft px-3 py-2.5 text-[12px] text-warn">
          <div className="flex items-center gap-1.5 font-bold"><AlertTriangle className="size-3.5" />These documents disagree</div>
          <ul className="mt-1 space-y-0.5">
            {conflicts.map((c, i) => (
              <li key={i}>
                <span className="font-semibold">{c.label}:</span> {c.values.map(v => `${v.value} (${v.doc})`).join(" vs ")}
                {c.use && <span className="font-semibold"> — using {c.use}</span>}
              </li>
            ))}
          </ul>
          {conflicts.some(c => !c.use) && <p className="mt-1.5">Star the document to believe; until then neither figure is put on a slide.</p>}
        </div>
      )}
      {fresh && onReplan && docs.length > 0 && (
        <Button size="sm" variant="primary" className="mt-3 w-full" icon={<RefreshCw className="size-3.5" />}
          disabled={busy || locked} loading={replanning}
          onClick={() => { setFresh(false); onReplan(); }}>
          {busy ? "Summarising…" : "Re-plan with these documents"}
        </Button>
      )}
    </section>
  );
}
