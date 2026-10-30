import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Loader2, Upload, X } from "lucide-react";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { toast } from "sonner";
import { api, type DeckAsset, type Slide } from "../lib/api";
import { cn } from "../lib/util";
import { Dialog } from "./ui";

const ACCEPT = "image/png,image/jpeg,image/webp,image/gif";

/** The deck's images plus an upload slot. Uploading picks the new image straight away. */
export function ImagePicker({ projectId, open, onOpenChange, onPick, title = "Choose an image", description }: {
  projectId: string; open: boolean; onOpenChange: (v: boolean) => void; onPick: (a: DeckAsset) => void;
  title?: string; description?: string;
}) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const assets = useQuery({ queryKey: ["assets", projectId], queryFn: () => api.assets(projectId), enabled: open });

  const upload = useMutation({
    mutationFn: (f: File) => api.uploadAsset(projectId, f),
    onSuccess: a => {
      qc.invalidateQueries({ queryKey: ["assets", projectId] });
      onPick(a);
      onOpenChange(false);
    },
    onError: e => toast.error("Couldn't add that image", { description: (e as Error).message }),
  });

  // A screenshot on the clipboard is the most common way a picture arrives; paste it straight in.
  useEffect(() => {
    if (!open) return;
    const onPaste = (e: ClipboardEvent) => {
      const f = [...(e.clipboardData?.files ?? [])].find(x => x.type.startsWith("image/"));
      if (f) { e.preventDefault(); upload.mutate(new File([f], f.name || "pasted.png", { type: f.type })); }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [open, upload]);

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    const f = [...e.dataTransfer.files].find(x => x.type.startsWith("image/"));
    if (f) upload.mutate(f);
  };

  const list = (assets.data ?? []).filter(a => a.key !== "hp");
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={title} wide
      description={description ?? "Upload, drop or paste an image, or reuse one already in this deck."}>
      <div onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}
        className={cn("flex flex-col items-center gap-2 rounded-xl border-2 border-dashed p-6 text-center transition-colors",
          over ? "border-accent bg-accent/5" : "border-line")}>
        {upload.isPending
          ? <Loader2 className="size-6 animate-spin text-muted" />
          : <Upload className="size-6 text-muted" />}
        <p className="text-sm font-semibold text-ink">Drop an image here, paste one, or
          <button className="ml-1 text-accent underline-offset-2 hover:underline" onClick={() => input.current?.click()}>browse</button>
        </p>
        <p className="text-xs text-muted">PNG, JPEG, WebP or GIF, up to 20 MB. White or transparent borders are trimmed.</p>
        <input ref={input} type="file" accept={ACCEPT} className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
      </div>

      {list.length > 0 && (
        <>
          <h3 className="mt-5 mb-2 text-[11px] font-bold uppercase tracking-wide text-faint">In this deck</h3>
          <ul className="grid max-h-80 grid-cols-3 gap-2 overflow-y-auto sm:grid-cols-4">
            {list.map(a => (
              <li key={a.key}>
                <button onClick={() => { onPick(a); onOpenChange(false); }} title={a.doc ? `From ${a.doc}` : a.key}
                  className="group relative flex aspect-[4/3] w-full items-center justify-center overflow-hidden rounded-lg bg-surface-2 ring-1 ring-line hover:ring-2 hover:ring-accent">
                  <img src={a.url} alt="" loading="lazy" className="max-h-full max-w-full object-contain" />
                  {a.doc ? <span className="absolute inset-x-1 bottom-1 truncate rounded bg-ink/70 px-1.5 py-0.5 text-[10px] font-semibold text-canvas">{a.doc}</span>
                    : a.upload && <span className="absolute left-1 top-1 rounded bg-accent px-1.5 py-0.5 text-[10px] font-bold text-accent-ink">Yours</span>}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {assets.isLoading && <p className="mt-4 flex items-center gap-2 text-xs text-muted"><Loader2 className="size-3.5 animate-spin" />Loading the deck's images</p>}
    </Dialog>
  );
}

/** A small "Add image" trigger that opens the picker. */
export function AddImageButton({ projectId, onPick, label = "Add image", className }: {
  projectId: string; onPick: (a: DeckAsset) => void; label?: string; className?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}
        className={cn("inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-semibold text-muted hover:bg-surface-2 hover:text-ink", className)}>
        <ImagePlus className="size-3.5" />{label}
      </button>
      <ImagePicker projectId={projectId} open={open} onOpenChange={setOpen} onPick={onPick} />
    </>
  );
}

/** The images the user put on a slide, and a way to add another. The next design lays them out. */
export function SlideImages({ projectId, slide, locked }: { projectId: string; slide: Slide; locked?: boolean }) {
  const qc = useQueryClient();
  const attach = useMutation({
    mutationFn: ({ key, detach }: { key: string; detach?: boolean }) => api.attachImage(slide.id, key, detach),
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: ["project"] });
      if (!v.detach) toast.success("Image added", { description: "The next design of this slide will lay it out." });
    },
    onError: e => toast.error("Couldn't change the slide's images", { description: (e as Error).message }),
  });
  const uploads = (slide.content.images ?? []).filter(i => i.source === "upload");
  return (
    <>
      {uploads.map(i => (
        <span key={i.key} className="flex items-center gap-1 rounded-md bg-surface-2 py-0.5 pl-0.5 pr-1.5 text-[11px] font-semibold ring-1 ring-line">
          <img src={`/api/projects/${projectId}/assets/${i.key}`} alt="" className="size-6 rounded object-cover" />
          {!locked && <button aria-label="Remove this image from the slide" onClick={() => attach.mutate({ key: i.key, detach: true })}
            className="text-muted hover:text-ink"><X className="size-3" /></button>}
        </span>
      ))}
      {!locked && <AddImageButton projectId={projectId} onPick={a => attach.mutate({ key: a.key })} />}
    </>
  );
}
