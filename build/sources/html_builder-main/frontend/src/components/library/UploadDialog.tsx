import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Copy, FileUp, Presentation, X } from "lucide-react";
import { useId, useRef, useState } from "react";
import { toast } from "sonner";
import { MAX_UPLOAD_BYTES } from "../../lib/api";
import { duplicateOf, libApi, libKeys, useLibProjects, type LibDeck } from "../../lib/library";
import { cn, formatBytes } from "../../lib/util";
import { Button, Dialog, Field, Spinner, inputClass } from "../ui";

type ItemStatus = "queued" | "uploading" | "done" | "duplicate" | "error";
interface Item { key: string; file: File; status: ItemStatus; pct: number; message: string; dupDeckId?: string }

const isPptx = (f: File) => f.name.toLowerCase().endsWith(".pptx");

/**
 * Add PowerPoints to the library. Files go up one at a time (the server renders each in PowerPoint, so
 * parallel uploads would only queue there). A file already in the library comes back as a 409 the user
 * can resolve per file: open the existing deck, or upload it anyway.
 */
export function UploadDialog({ open, onOpenChange, supersedes, defaultProject, onOpenDeck }: {
  open: boolean; onOpenChange: (o: boolean) => void;
  /** Upload a new version of this deck: it becomes superseded once the new one is in. */
  supersedes?: LibDeck | null;
  defaultProject?: string;
  onOpenDeck: (deckId: string) => void;
}) {
  const qc = useQueryClient();
  const listId = useId();
  const projects = useLibProjects();
  const input = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [project, setProject] = useState(supersedes?.project ?? defaultProject ?? "");
  const [title, setTitle] = useState("");
  const [over, setOver] = useState(false);
  const [running, setRunning] = useState(false);
  const single = !!supersedes;

  const update = (key: string, patch: Partial<Item>) => setItems(list => list.map(i => (i.key === key ? { ...i, ...patch } : i)));

  const add = (files: File[]) => {
    const bad = files.filter(f => !isPptx(f));
    const big = files.filter(f => isPptx(f) && f.size > MAX_UPLOAD_BYTES);
    if (bad.length) toast.error(`${bad.length === 1 ? `${bad[0]?.name} isn't` : `${bad.length} files aren't`} .pptx`, { description: "Save them as .pptx in PowerPoint, then add them again." });
    if (big.length) toast.error("Too large to upload", { description: `${big.map(f => `${f.name} (${formatBytes(f.size)})`).join(", ")} — the limit is 300 MB.` });
    const ok = files.filter(f => isPptx(f) && f.size <= MAX_UPLOAD_BYTES);
    setItems(list => {
      const fresh = ok.filter(f => !list.some(i => i.file.name === f.name && i.file.size === f.size))
        .map(f => ({ key: `${f.name}-${f.size}-${f.lastModified}`, file: f, status: "queued" as const, pct: 0, message: "" }));
      return single ? fresh.slice(0, 1) : [...list, ...fresh];
    });
  };

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: libKeys.decks });
    void qc.invalidateQueries({ queryKey: libKeys.projects });
    void qc.invalidateQueries({ queryKey: libKeys.searchAll });
  };

  /** Returns true when the file went in. */
  const send = async (it: Item, force = false): Promise<boolean> => {
    update(it.key, { status: "uploading", pct: 0, message: "" });
    try {
      await libApi.uploadDeck(it.file, {
        project: project.trim(),
        title: (items.length === 1 || single) ? title.trim() || undefined : undefined,
        supersedes: supersedes?.id, force,
      }, pct => update(it.key, { pct }));
      update(it.key, { status: "done", pct: 100 });
      return true;
    } catch (e) {
      const dup = duplicateOf(e);
      if (dup) update(it.key, { status: "duplicate", message: dup.message, dupDeckId: dup.deck_id });
      else update(it.key, { status: "error", message: (e as Error).message });
      return false;
    }
  };

  const start = async () => {
    if (!project.trim()) { toast.error("Which project are these for?", { description: "The project is what the library groups and searches by first." }); return; }
    setRunning(true);
    let ok = 0;
    const queue = items.filter(i => i.status === "queued" || i.status === "error");
    for (const it of queue) if (await send(it)) ok++;
    setRunning(false);
    refresh();
    if (ok) toast.success(`${ok} ${ok === 1 ? "deck" : "decks"} added`, { description: "Rendering and indexing in the background — they appear in the library as they finish." });
    if (ok === queue.length && queue.length) close(false);
  };

  const anyway = async (it: Item) => {
    setRunning(true);
    if (await send(it, true)) { refresh(); toast.success(`${it.file.name} added`); }
    setRunning(false);
  };

  const close = (o: boolean) => {
    if (!o && running) return;   // an upload in flight would be orphaned in this dialog's state
    if (!o) { setItems([]); setTitle(""); }
    onOpenChange(o);
  };

  const pending = items.filter(i => i.status === "queued" || i.status === "error").length;
  return (
    <Dialog open={open} onOpenChange={close}
      title={supersedes ? "Upload a new version" : "Add PowerPoints to the library"}
      description={supersedes
        ? `Replaces “${supersedes.title || supersedes.filename}”. Its slides stay searchable, marked as an old version.`
        : "Each slide is rendered, read and indexed, so you can find it again by what it says."}
      footer={<>
        <Button onClick={() => close(false)} disabled={running}>{items.some(i => i.status === "done") && !pending ? "Done" : "Cancel"}</Button>
        <Button variant="primary" loading={running} disabled={!pending || !project.trim()} onClick={() => void start()}>
          {pending > 1 ? `Upload ${pending} decks` : "Upload"}
        </Button>
      </>}>
      <div className="space-y-4">
        <Field label="Project" hint="Required. Pick an existing one to keep its decks together.">
          <input value={project} onChange={e => setProject(e.target.value)} list={listId} className={inputClass}
            placeholder="e.g. ZGX launch" autoFocus={!supersedes} disabled={running} required aria-required />
          <datalist id={listId}>{projects.data?.map(p => <option key={p.project} value={p.project}>{`${p.decks} decks`}</option>)}</datalist>
        </Field>
        {(single || items.length <= 1) && (
          <Field label="Title" hint="Optional — otherwise taken from the file.">
            <input value={title} onChange={e => setTitle(e.target.value)} className={inputClass} disabled={running}
              placeholder={supersedes?.title || "From the deck's properties or first slide"} />
          </Field>
        )}
        <div role="button" tabIndex={0} aria-label="Choose .pptx files, or drop them here"
          onClick={() => !running && input.current?.click()}
          onKeyDown={e => { if ((e.key === "Enter" || e.key === " ") && !running) { e.preventDefault(); input.current?.click(); } }}
          onDragOver={e => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={e => { e.preventDefault(); setOver(false); if (!running) add([...e.dataTransfer.files]); }}
          className={cn("flex cursor-pointer flex-col items-center rounded-xl border-2 border-dashed px-4 py-6 text-center transition-colors",
            over ? "border-accent bg-accent-soft" : "border-line hover:border-faint")}>
          <FileUp className="size-6 text-muted" />
          <div className="mt-2 text-sm font-semibold">{single ? "Choose the new .pptx" : "Choose .pptx files"}</div>
          <div className="text-[12px] text-muted">or drop {single ? "it" : "them"} here</div>
        </div>
        <input ref={input} type="file" multiple={!single} className="hidden"
          accept=".pptx,application/vnd.openxmlformats-officedocument.presentationml.presentation"
          onChange={e => { add([...(e.target.files ?? [])]); e.target.value = ""; }} />
        {items.length > 0 && (
          <ul className="max-h-64 space-y-1.5 overflow-auto scroll-thin" aria-live="polite">
            {items.map(it => (
              <li key={it.key} className="rounded-lg border border-line-2 bg-surface-2 px-3 py-2 text-[13px]">
                <div className="flex items-center gap-2">
                  {it.status === "done" ? <CheckCircle2 className="size-4 shrink-0 text-good" />
                    : it.status === "uploading" ? <Spinner className="shrink-0 text-accent" />
                      : it.status === "duplicate" ? <Copy className="size-4 shrink-0 text-warn" />
                        : it.status === "error" ? <AlertTriangle className="size-4 shrink-0 text-bad" />
                          : <Presentation className="size-4 shrink-0 text-muted" />}
                  <span className="min-w-0 flex-1 truncate font-semibold">{it.file.name}</span>
                  <span className="shrink-0 text-[12px] text-muted">{it.status === "uploading" ? `${it.pct}%` : formatBytes(it.file.size)}</span>
                  {(it.status === "queued" || it.status === "error" || it.status === "duplicate") && !running && (
                    <button aria-label={`Remove ${it.file.name}`} onClick={() => setItems(l => l.filter(x => x.key !== it.key))}
                      className="text-muted hover:text-ink"><X className="size-3.5" /></button>
                  )}
                </div>
                {it.status === "uploading" && (
                  <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-line"><div className="h-full bg-accent transition-all" style={{ width: `${it.pct}%` }} /></div>
                )}
                {it.status === "error" && <p className="mt-1 text-[12px] text-bad">{it.message}</p>}
                {it.status === "duplicate" && (
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[12px]">
                    <span className="text-warn">{it.message || "Already in the library."}</span>
                    {it.dupDeckId && <Button size="sm" variant="ghost" className="h-7" onClick={() => { const id = it.dupDeckId; close(false); if (id) onOpenDeck(id); }}>Open it</Button>}
                    <Button size="sm" variant="ghost" className="h-7" disabled={running || !project.trim()} onClick={() => void anyway(it)}>Upload anyway</Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Dialog>
  );
}
