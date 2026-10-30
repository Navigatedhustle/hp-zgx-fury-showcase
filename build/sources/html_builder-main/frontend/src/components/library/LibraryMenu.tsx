import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { useQueryClient } from "@tanstack/react-query";
import { ArchiveRestore, BookOpen, Download, FolderSync, MoreHorizontal, Tags } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { DEFAULT_MIN_SHARED, libApi, libKeys, libUrls, useLibProjects, useObsidianStatus, type GraphParams } from "../../lib/library";
import { ObsidianDialog, useObsidianSync } from "./ObsidianPanel";

const itemClass = "flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-sm outline-none data-[highlighted]:bg-surface-2";

/**
 * The library's less frequent actions: the tag vocabulary, backing the whole library up or restoring it, and the
 * Obsidian vault. `obsidian` is what the vault holds (the Graph tab passes its own view); by default the favourites,
 * or every slide while there are none.
 */
export function LibraryMenu({ onTags, obsidian }: { onTags: () => void; obsidian?: GraphParams }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [vaultOpen, setVaultOpen] = useState(false);
  const favs = (useLibProjects().data ?? []).reduce((n, p) => n + p.favourites, 0);
  const vault: GraphParams = obsidian ?? { scope: favs > 0 ? "favourites" : "all", min_shared: DEFAULT_MIN_SHARED };
  const status = useObsidianStatus().data;
  const sync = useObsidianSync();
  const canSync = !!status?.configured && status.exists;

  const restore = async (file: File | null | undefined) => {
    if (!file) return;
    const id = toast.loading(`Restoring ${file.name}…`);
    try {
      await libApi.restore(file, pct => toast.loading(pct < 100 ? `Uploading ${file.name} — ${pct}%` : "Merging into the library…", { id }));
      toast.success("Backup restored", { id, description: "Decks and slides already in the library were left as they are." });
      void qc.invalidateQueries({ queryKey: libKeys.all });
    } catch (e) {
      toast.error("Couldn't restore that backup", { id, description: (e as Error).message });
    }
  };

  return (
    <>
      <Dropdown.Root>
        <Dropdown.Trigger aria-label="More library actions" className="flex size-9 items-center justify-center rounded-lg border border-line bg-surface text-muted hover:border-faint hover:text-ink">
          <MoreHorizontal className="size-4" />
        </Dropdown.Trigger>
        <Dropdown.Portal>
          <Dropdown.Content align="end" sideOffset={6} className="z-50 min-w-56 rounded-xl border border-line bg-surface p-1 shadow-card">
            <Dropdown.Item onSelect={onTags} className={itemClass}><Tags className="size-4" />Manage tags</Dropdown.Item>
            <Dropdown.Separator className="my-1 h-px bg-line-2" />
            {/* A plain download: the browser streams the zip, which can be large. */}
            <Dropdown.Item asChild className={itemClass}>
              <a href={libUrls.backup} download><Download className="size-4" />Download backup</a>
            </Dropdown.Item>
            <Dropdown.Item onSelect={() => input.current?.click()} className={itemClass}><ArchiveRestore className="size-4" />Restore from backup…</Dropdown.Item>
            <Dropdown.Separator className="my-1 h-px bg-line-2" />
            <Dropdown.Label className="px-2.5 pb-0.5 pt-1.5 text-[11px] font-bold uppercase tracking-wider text-muted">
              Obsidian · {vault.scope === "favourites" ? "favourites" : "all slides"}{vault.project ? ` in ${vault.project}` : ""}
            </Dropdown.Label>
            <Dropdown.Item asChild className={itemClass}>
              <a href={libUrls.obsidianZip(vault)} download><Download className="size-4" />Download Obsidian vault (.zip)</a>
            </Dropdown.Item>
            {canSync && (
              <Dropdown.Item disabled={sync.isPending} onSelect={() => sync.mutate(vault)} className={`${itemClass} data-[disabled]:opacity-50`}>
                <FolderSync className="size-4" />Sync to Obsidian vault
              </Dropdown.Item>
            )}
            <Dropdown.Item onSelect={() => setVaultOpen(true)} className={itemClass}>
              <BookOpen className="size-4" />{canSync ? "Obsidian options…" : "Set up Obsidian sync…"}
            </Dropdown.Item>
          </Dropdown.Content>
        </Dropdown.Portal>
      </Dropdown.Root>
      <input ref={input} type="file" accept=".zip,application/zip" className="hidden"
        onChange={e => { const f = e.target.files?.item(0); e.target.value = ""; void restore(f); }} />
      <ObsidianDialog open={vaultOpen} onOpenChange={setVaultOpen} params={vault} />
    </>
  );
}
