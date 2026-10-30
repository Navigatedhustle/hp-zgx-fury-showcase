import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, FileText, FileUp, MoreHorizontal, PenLine, Plus, Presentation, Trash2, X } from "lucide-react";
import { useCallback, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { TopBar } from "../components/AppShell";
import { CountsBar } from "../components/CountsBar";
import { LibraryStrip } from "../components/library/HomeStrip";
import { Badge, Button, Dialog, Spinner, inputClass, type Tone } from "../components/ui";
import { MAX_UPLOAD_BYTES, api, urls, type Project } from "../lib/api";
import { cn, formatBytes, projectStatusText, timeAgo } from "../lib/util";

const statusTone = (p: Project): Tone =>
  p.status === "error" ? "bad" : p.status === "complete" ? "good" : p.status === "reviewing" ? "warn" : p.status === "ready" ? "idle" : "busy";

/**
 * The two ways in. They share everything downstream — planning, the two variants, QA, review, export —
 * and differ only in where the slide content comes from, so they are one choice made once rather than
 * two products. The converter is second because it is the one that already existed, not because it
 * matters less.
 */
function StartCards() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => api.createBlank(name.trim() || "Untitled deck", 1),
    onSuccess: p => { qc.invalidateQueries({ queryKey: ["projects"] }); nav(`/p/${p.id}/write`); },
    onError: e => toast.error("Couldn't start the deck", { description: (e as Error).message }),
  });
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2"><a href="/booth" className="rounded-2xl border border-accent bg-accent-soft p-6 md:col-span-2"><span className="text-xs font-bold uppercase tracking-widest text-accent">Start here · live booth experience</span><h2 className="mt-3 text-2xl font-bold">A brief. Three polished slides.</h2><p className="mt-2 text-muted">One local author call, a presentation preview, and editable PowerPoint export.</p><span className="mt-4 inline-flex items-center gap-2 font-bold text-accent">Create a short presentation <ArrowRight className="size-4" /></span></a>
        <button onClick={() => { setName(""); setNaming(true); }}
          className="group rounded-2xl border border-line bg-surface p-6 text-left transition-colors hover:border-accent">
          <span className="flex size-10 items-center justify-center rounded-xl bg-accent-soft text-accent"><PenLine className="size-5" /></span>
          <h2 className="mt-4 text-[19px] font-extrabold tracking-tight">Create a new deck</h2>
          <p className="mt-1.5 text-[14px] leading-relaxed text-muted">
            Write the slides here — a title, the lines that go on them, what you will say. Or describe the
            deck and have a first draft written for you to correct.
          </p>
          <span className="mt-4 inline-flex items-center gap-1.5 text-[13px] font-bold text-accent">
            Start writing<ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
          </span>
        </button>
        <Dropzone />
      </div>
      <Dialog open={naming} onOpenChange={setNaming} title="What is the deck about?"
        description="A working name — you can change it, and the title slide, at any point."
        footer={<>
          <Button onClick={() => setNaming(false)}>Cancel</Button>
          <Button variant="primary" loading={create.isPending} onClick={() => create.mutate()}>Create deck</Button>
        </>}>
        <input autoFocus value={name} onChange={e => setName(e.target.value)} className={inputClass}
          placeholder="Q3 business review" aria-label="Deck name"
          onKeyDown={e => { if (e.key === "Enter" && !create.isPending) create.mutate(); }} />
      </Dialog>
    </>
  );
}

const DOC_EXT = /\.(pdf|docx|txt|md)$/i;

function Dropzone() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [name, setName] = useState("");
  // Reference documents to read before the first plan (backend: create_project `context`).
  const [context, setContext] = useState<File[]>([]);
  const docInput = useRef<HTMLInputElement>(null);
  const addContext = (files: File[]) => {
    const ok = files.filter(f => DOC_EXT.test(f.name));
    if (ok.length < files.length) toast.error("Some files were skipped", { description: "Context documents can be PDF, Word (.docx), .txt or .md." });
    setContext(list => [...list, ...ok.filter(f => !list.some(x => x.name === f.name && x.size === f.size))]);
  };

  const upload = useCallback(async (file?: File | null, extra: File[] = []) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pptx")) {
      toast.error("That isn't a .pptx file", { description: "Open it in PowerPoint and save as .pptx, then upload again." });
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      toast.error("That file is too large", {
        description: `${formatBytes(file.size)} — the limit is 300 MB. Remove embedded video or compress the images in PowerPoint, then try again.`,
      });
      return;
    }
    setName(file.name);
    setProgress(0);
    try {
      const p = await api.upload(file, setProgress, [...context, ...extra]);
      qc.invalidateQueries({ queryKey: ["projects"] });
      nav(`/p/${p.id}/plan`);
    } catch (e) {
      toast.error("Upload failed", { description: (e as Error).message });
      setProgress(null);
      setName("");
    }
  }, [nav, qc, context]);

  // One drop may hold the deck and its documents together; documents alone are kept for the deck to come.
  const onFiles = (files: File[]) => {
    const deck = files.find(f => f.name.toLowerCase().endsWith(".pptx"));
    const rest = files.filter(f => f !== deck);
    if (deck) upload(deck, rest.filter(f => DOC_EXT.test(f.name)));
    else addContext(rest);
  };

  return (
    <div
      onDragOver={e => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={e => { e.preventDefault(); setOver(false); onFiles([...e.dataTransfer.files]); }}
      className={cn("rounded-2xl border-2 border-dashed p-6 transition-colors",
        over ? "border-accent bg-accent-soft" : "border-line bg-surface")}>
      <span className="flex size-10 items-center justify-center rounded-xl bg-surface-2 text-muted"><FileUp className="size-5" /></span>
      <h2 className="mt-4 text-[19px] font-extrabold tracking-tight">Convert a PowerPoint</h2>
      <p className="mt-1.5 text-[14px] leading-relaxed text-muted">
        Every slide is read for its text, tables, charts and images, then redesigned. Nothing is copied
        across — the figures are kept exactly, the layout is rebuilt.
      </p>
      <div className="mt-4">
        {progress === null ? (
          <>
            <Button variant="primary" size="sm" icon={<FileUp className="size-4" />} onClick={() => input.current?.click()}>
              Choose a .pptx
            </Button>
            <span className="ml-3 text-[13px] text-muted">or drop it here</span>
            <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[13px]">
              {context.map(f => (
                <span key={f.name + f.size} className="flex items-center gap-1 rounded-md bg-surface-2 py-0.5 pl-2 pr-1 text-[12px] font-semibold ring-1 ring-line">
                  <FileText className="size-3.5 text-muted" />{f.name}
                  <button aria-label={`Remove ${f.name}`} onClick={() => setContext(context.filter(x => x !== f))} className="text-muted hover:text-ink"><X className="size-3" /></button>
                </span>
              ))}
              <button onClick={() => docInput.current?.click()} className="inline-flex items-center gap-1 font-semibold text-accent hover:underline">
                <Plus className="size-3.5" />{context.length ? "Another document" : "Add context documents"}
              </button>
              {!context.length && <span className="text-muted">— optional: a brief, proposal or whitepaper the plan should use</span>}
            </div>
          </>
        ) : (
          <div className="flex items-center gap-3">
            <Spinner className="text-accent" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">{progress < 100 ? `Uploading ${name}` : `Opening ${name}`}</div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line"><div className="h-full bg-accent transition-all" style={{ width: `${progress}%` }} /></div>
            </div>
          </div>
        )}
      </div>
      <input ref={input} type="file" accept=".pptx,application/vnd.openxmlformats-officedocument.presentationml.presentation" className="hidden"
        onChange={e => { const f = e.target.files?.item(0) ?? null; e.target.value = ""; upload(f); }} />
      <input ref={docInput} type="file" multiple accept=".pdf,.docx,.txt,.md" className="hidden"
        onChange={e => { addContext([...(e.target.files ?? [])]); e.target.value = ""; }} />
    </div>
  );
}

function ProjectRow({ p, onDelete }: { p: Project; onDelete: (p: Project) => void }) {
  const [img, setImg] = useState(true);
  const c = p.counts;
  const busy = ["ingesting", "planning", "generating"].includes(p.status);
  // A composed deck goes back to where its content is written until it has actually been planned.
  const target = ["reviewing", "generating", "complete"].includes(p.status) ? "review"
    : p.source === "composed" && !p.counts.included ? "write" : "plan";
  return (
    <div className="group relative flex items-center gap-4 rounded-xl border border-line bg-surface p-3 pr-2 transition-colors hover:border-faint">
      <Link to={`/p/${p.id}/${target}`} className="absolute inset-0 rounded-xl" aria-label={`Open ${p.deck_title || p.name}`} />
      <div className="relative hidden aspect-video w-32 shrink-0 overflow-hidden rounded-md bg-surface-2 ring-1 ring-line-2 sm:block">
        {/* Booth/composed decks have no uploaded raster cover; keep the honest icon fallback. */}
        {p.filename && p.cover_slide_index && img ? <img src={urls.cover(p)} alt="" className="size-full object-cover" onError={() => setImg(false)} />
          : <div className="flex size-full items-center justify-center text-faint"><Presentation className="size-5" /></div>}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h3 className="truncate text-[15px] font-bold">{p.deck_title || p.name}</h3>
        </div>
        <div className="mt-0.5 truncate text-[13px] text-muted">
          {p.source === "composed" ? "Written here" : p.filename} · {c.slides} slides · updated {timeAgo(p.updated_at)}
        </div>
        {c.included > 0 && ["generating", "reviewing", "complete"].includes(p.status) && (
          <div className="mt-2.5 flex max-w-md items-center gap-3">
            <CountsBar {...c} />
            <span className="shrink-0 text-xs font-semibold text-muted">{c.approved}/{c.included} approved</span>
          </div>
        )}
        {p.status === "error" && <div className="mt-1.5 flex items-center gap-1.5 text-[13px] text-bad"><AlertTriangle className="size-3.5" />{p.error}</div>}
      </div>
      <span className="hidden sm:block"><Badge tone={statusTone(p)} pulse={busy}>{projectStatusText[p.status]}</Badge></span>
      <Dropdown.Root>
        <Dropdown.Trigger aria-label="Project actions" className="relative z-10 flex size-8 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink">
          <MoreHorizontal className="size-4" />
        </Dropdown.Trigger>
        <Dropdown.Portal>
          <Dropdown.Content align="end" sideOffset={4} className="z-50 min-w-40 rounded-xl border border-line bg-surface p-1 shadow-card">
            <Dropdown.Item onSelect={() => onDelete(p)} className="flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-bad outline-none data-[highlighted]:bg-bad-soft">
              <Trash2 className="size-4" />Delete project
            </Dropdown.Item>
          </Dropdown.Content>
        </Dropdown.Portal>
      </Dropdown.Root>
    </div>
  );
}

export default function Home() {
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["projects"], queryFn: api.projects,
    refetchInterval: q => (q.state.data?.some(p => p.busy || ["ingesting", "planning", "generating"].includes(p.status)) ? 2500 : false),
  });
  const [showAll, setShowAll] = useState(false);
  const [toDelete, setToDelete] = useState<Project | null>(null);
  const del = useMutation({
    mutationFn: (id: string) => api.deleteProject(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["projects"] }); toast.success("Project deleted"); setToDelete(null); },
    onError: e => toast.error("Couldn't delete the project", { description: (e as Error).message }),
  });

  return (
    <div className="min-h-full">
      <TopBar />
      <main className="mx-auto max-w-5xl px-4 pb-20 pt-8 sm:px-6">
        <h1 className="text-[32px] font-extrabold leading-[1.1] tracking-[-0.025em] sm:text-[38px]">
          Your next presentation<br className="hidden sm:block" /> starts here.
        </h1>
        <p className="mt-2.5 max-w-2xl text-[15px] leading-relaxed text-muted">
          HP ZGX Fury demo experience. Start a short booth presentation or use the full authoring and conversion tools below. Fury host inference; Frankfurt access requires WAN.
        </p>
        <div className="mt-7"><StartCards /></div>
        <LibraryStrip />
        <section className="mt-12">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-lg font-bold tracking-tight">Your decks</h2>
            {data && data.length > 0 && <span className="text-sm text-muted">{data.length} {data.length === 1 ? "project" : "projects"}</span>}
          </div>
          {isLoading && <div className="space-y-2">{[0, 1, 2].map(i => <div key={i} className="shimmer-light h-[94px] rounded-xl" />)}</div>}
          {isError && <div className="rounded-xl border border-bad/30 bg-bad-soft p-4 text-sm text-bad">Presentation service unavailable. Ask the booth operator to check the local slide service, then reload.</div>}
          {data && data.length === 0 && (
            <div className="rounded-xl border border-line bg-surface p-8 text-center text-sm text-muted">No decks yet — write one or convert a PowerPoint above.</div>
          )}
          <div className="space-y-2">{(showAll ? data : data?.slice(0,6))?.map(p => <ProjectRow key={p.id} p={p} onDelete={setToDelete} />)}</div>
          {data && data.length > 6 && <Button className="mt-4" onClick={() => setShowAll(!showAll)}>{showAll ? "Show recent decks" : `Show all ${data.length} decks`}</Button>}
        </section>
      </main>
      <Dialog open={!!toDelete} onOpenChange={o => !o && setToDelete(null)} title="Delete this project?"
        description={`"${toDelete?.deck_title || toDelete?.name}" and all of its generated designs will be removed. This can't be undone.`}
        footer={<>
          <Button onClick={() => setToDelete(null)}>Keep it</Button>
          <Button variant="danger" loading={del.isPending} onClick={() => toDelete && del.mutate(toDelete.id)}>Delete project</Button>
        </>} />
    </div>
  );
}
