import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckSquare, Download, Image, Presentation, Star, StarOff, Tag, TagsIcon, X } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { MAX_EXPORT, libApi, libKeys, patchSlides, saveBlob, useLibTags, type ExportMode, type LibSlide, type LibTag } from "../../lib/library";
import { Button, Dialog, IconButton, Kbd } from "../ui";
import { TagInput, ensureTag } from "./TagInput";

const plural = (n: number) => `${n} ${n === 1 ? "slide" : "slides"}`;
const itemClass = "flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-sm outline-none data-[highlighted]:bg-surface-2";

/**
 * What to do with the selected slides. `ids` is already in result order — exports keep that order,
 * which is the order the user is looking at.
 */
export function SelectionBar({ ids, items, tags, visible, onSelectAll, onClear }: {
  ids: string[]; items: LibSlide[]; tags: Map<string, LibTag>; visible: number;
  onSelectAll: () => void; onClear: () => void;
}) {
  const qc = useQueryClient();
  const allTags = useLibTags().data ?? [];
  const [adding, setAdding] = useState(false);
  const [exporting, setExporting] = useState<ExportMode | null>(null);
  const chosen = useMemo(() => { const set = new Set(ids); return items.filter(s => set.has(s.id)); }, [ids, items]);
  const present = useMemo(() => [...new Set(chosen.flatMap(s => s.tags))].sort(), [chosen]);

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: libKeys.searchAll });
    void qc.invalidateQueries({ queryKey: libKeys.favs });
    void qc.invalidateQueries({ queryKey: libKeys.tags });
    void qc.invalidateQueries({ queryKey: libKeys.decks });
    void qc.invalidateQueries({ queryKey: libKeys.projects });
  };

  const bulk = useMutation({
    mutationFn: (body: { favourite?: boolean; add_tags?: string[]; remove_tags?: string[] }) => libApi.bulk({ slide_ids: ids, ...body }),
    onMutate: body => {
      // Favouriting is instant on screen; tag changes wait for the server, which normalises them.
      if (body.favourite !== undefined) {
        const fav = body.favourite;
        patchSlides(qc, ids, s => ({ ...s, favourite: fav }));
      }
    },
    onSuccess: (r, body) => {
      const n = r.updated;
      if (body.favourite !== undefined) toast.success(`${n} ${n === 1 ? "slide" : "slides"} ${body.favourite ? "added to" : "removed from"} favourites`);
      else if (body.add_tags) toast.success(`Tagged ${n} ${n === 1 ? "slide" : "slides"}`);
      else toast.success(`Tag removed from ${n} ${n === 1 ? "slide" : "slides"}`);
    },
    onError: e => toast.error("Couldn't update those slides", { description: (e as Error).message }),
    onSettled: refresh,
  });

  const addTag = async (text: string, tag?: LibTag) => {
    try {
      const slug = tag?.slug ?? await ensureTag(text, allTags);
      setAdding(false);
      bulk.mutate({ add_tags: [slug] });
    } catch (e) { toast.error("Couldn't add that tag", { description: (e as Error).message }); }
  };

  const doExport = async (mode: ExportMode) => {
    if (ids.length > MAX_EXPORT) {
      toast.error(`Select at most ${MAX_EXPORT} slides to export`, { description: `${ids.length} are selected.` });
      return;
    }
    setExporting(mode);
    try {
      const r = await libApi.exportPptx(ids, mode);
      saveBlob(r.blob, r.filename);
      const placed = ids.length - r.skipped.length;
      const notes = [
        r.fallback.length ? `${plural(r.fallback.length)} exported as pictures (no original available).` : "",
        r.mode === "picture" && mode === "original" && !r.fallback.length ? "Exported as pictures — PowerPoint wasn't available." : "",
        r.skipped.length ? `${plural(r.skipped.length)} left out (no source and no picture).` : "",
        r.resized.length ? `${plural(r.resized.length)} came from a deck of another slide size and ${r.resized.length === 1 ? "was" : "were"} fitted to the page — worth a look.` : "",
      ].filter(Boolean).join(" ");
      const head = `${plural(placed)} exported`;
      if (notes) toast.warning(head, { description: notes, duration: 10_000 });
      else toast.success(head);
    } catch (e) {
      toast.error("Couldn't build the PowerPoint", { description: (e as Error).message });
    } finally { setExporting(null); }
  };

  const n = ids.length;
  return (
    <div role="toolbar" aria-label="Selected slides"
      className="fixed inset-x-0 bottom-4 z-30 mx-auto flex w-[calc(100vw-32px)] max-w-fit flex-wrap items-center gap-1.5 rounded-2xl border border-line bg-surface p-1.5 pl-4 shadow-card">
      <span className="mr-1 text-sm font-bold" aria-live="polite">{n} selected</span>
      {visible > n && <Button size="sm" variant="ghost" icon={<CheckSquare className="size-4" />} onClick={onSelectAll}>All {visible}</Button>}
      <span className="mx-1 h-5 w-px bg-line" />
      <Button size="sm" variant="ghost" icon={<Star className="size-4" />} disabled={bulk.isPending} onClick={() => bulk.mutate({ favourite: true })}>Favourite</Button>
      <Button size="sm" variant="ghost" icon={<StarOff className="size-4" />} disabled={bulk.isPending} onClick={() => bulk.mutate({ favourite: false })}>Unfavourite</Button>
      <Button size="sm" variant="ghost" icon={<Tag className="size-4" />} disabled={bulk.isPending} onClick={() => setAdding(true)}>Add tag</Button>
      <Dropdown.Root>
        <Dropdown.Trigger asChild>
          <Button size="sm" variant="ghost" icon={<TagsIcon className="size-4" />} disabled={bulk.isPending || !present.length}>Remove tag</Button>
        </Dropdown.Trigger>
        <Dropdown.Portal>
          <Dropdown.Content side="top" align="center" sideOffset={8} className="z-50 max-h-72 min-w-44 overflow-auto rounded-xl border border-line bg-surface p-1 shadow-card">
            {present.map(slug => (
              <Dropdown.Item key={slug} onSelect={() => bulk.mutate({ remove_tags: [slug] })} className={itemClass}>
                <X className="size-3.5 text-muted" />{tags.get(slug)?.label ?? slug}
              </Dropdown.Item>
            ))}
          </Dropdown.Content>
        </Dropdown.Portal>
      </Dropdown.Root>
      <Dropdown.Root>
        <Dropdown.Trigger asChild>
          <Button size="sm" variant="primary" icon={<Download className="size-4" />} loading={!!exporting}>Export</Button>
        </Dropdown.Trigger>
        <Dropdown.Portal>
          <Dropdown.Content side="top" align="end" sideOffset={8} className="z-50 w-72 rounded-xl border border-line bg-surface p-1 shadow-card">
            <Dropdown.Item onSelect={() => void doExport("original")} className={itemClass}>
              <Presentation className="size-4 shrink-0" />
              <span><span className="block font-semibold">As PowerPoint</span><span className="block text-[12px] text-muted">The original slides, editable, in this order</span></span>
            </Dropdown.Item>
            <Dropdown.Item onSelect={() => void doExport("picture")} className={itemClass}>
              <Image className="size-4 shrink-0" />
              <span><span className="block font-semibold">As pictures</span><span className="block text-[12px] text-muted">One image per slide, with speaker notes</span></span>
            </Dropdown.Item>
          </Dropdown.Content>
        </Dropdown.Portal>
      </Dropdown.Root>
      <IconButton label="Clear selection (Esc)" onClick={onClear}><X className="size-4" /></IconButton>
      <Dialog open={adding} onOpenChange={setAdding} title={`Tag ${n} ${n === 1 ? "slide" : "slides"}`}
        description="Pick a tag from the vocabulary, or type a new one.">
        <TagInput tags={allTags} onPick={(text, tag) => void addTag(text, tag)} autoFocus />
        <p className="mt-3 text-[12px] text-muted"><Kbd>Enter</Kbd> adds the tag. Tags you add are kept when slides are re-tagged.</p>
      </Dialog>
    </div>
  );
}
