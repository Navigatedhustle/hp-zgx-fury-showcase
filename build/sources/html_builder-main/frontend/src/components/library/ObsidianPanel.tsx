import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, ExternalLink, FolderSync } from "lucide-react";
import { toast } from "sonner";
import {
  DEFAULT_MIN_SHARED, libApi, libKeys, libUrls, useObsidianStatus, type GraphParams, type ObsidianSyncResult,
} from "../../lib/library";
import { Button, Dialog, Kbd } from "../ui";
import { fmtDate } from "./SlideCard";

const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`;

/** `obsidian://…` hands over to the desktop app; nothing happens when it is not installed. */
export const openInObsidian = (uri: string) => { window.location.href = uri; };

/** What a vault holds, in words: "favourite slides of Apollo, tags on 2+ slides". */
export function describeScope(p: GraphParams): string {
  const what = p.scope === "favourites" ? "Favourite slides" : "All slides";
  const where = p.project ? ` in ${p.project}` : "";
  const min = p.min_shared ?? DEFAULT_MIN_SHARED;
  return `${what}${where}${min > 1 ? `, with tags and mentions shared by ${min}+ slides` : ""}`;
}

/** Sync the library into the configured vault, then offer to open it. */
export function useObsidianSync() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: GraphParams) => libApi.obsidianSync(p),
    onMutate: () => ({ toastId: toast.loading("Syncing to your Obsidian vault…") }),
    onSuccess: (r: ObsidianSyncResult, _p, ctx) => {
      toast.success(r.written || r.removed ? "Obsidian vault updated" : "Obsidian vault already up to date", {
        id: ctx?.toastId,
        description: `${plural(r.written, "note")} written · ${r.unchanged.toLocaleString()} unchanged · ${r.removed.toLocaleString()} removed`,
        duration: 12_000,
        action: r.open_uri ? { label: "Open in Obsidian", onClick: () => openInObsidian(r.open_uri) } : undefined,
      });
      void qc.invalidateQueries({ queryKey: libKeys.obsidian });
    },
    onError: (e, _p, ctx) => toast.error("Couldn't sync to Obsidian", { id: ctx?.toastId, description: (e as Error).message }),
  });
}

/** The vault as a zip download: always available, no setup. */
export function VaultDownload({ params, className }: { params: GraphParams; className?: string }) {
  return (
    <a href={libUrls.obsidianZip(params)} download className={className}>
      <Download className="size-4" />Download vault (.zip)
    </a>
  );
}

const btn = "inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-line bg-surface px-3.5 text-sm font-semibold text-ink hover:border-faint";

/** Obsidian: download the library as a vault, or sync it into the one set in OBSIDIAN_VAULT_DIR. */
export function ObsidianDialog({ open, onOpenChange, params }: { open: boolean; onOpenChange: (o: boolean) => void; params: GraphParams }) {
  const status = useObsidianStatus();
  const sync = useObsidianSync();
  const st = status.data;
  const ready = !!st?.configured && st.exists;
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title="Obsidian vault"
      description="The same knowledge as the graph, as linked Markdown notes — one per slide, plus a note per project, tag and mention, so it opens in Obsidian's graph view.">
      <div className="space-y-4 text-sm">
        <div className="rounded-lg bg-surface-2 px-3 py-2 text-[13px] text-muted ring-1 ring-line-2">
          <span className="font-semibold text-ink">Contents:</span> {describeScope(params)}
        </div>

        <section>
          <h3 className="mb-1 text-[13px] font-bold">Download</h3>
          <p className="mb-2 text-[13px] text-muted">Unzip it, then in Obsidian choose <b>Open folder as vault</b>.</p>
          <VaultDownload params={params} className={btn} />
        </section>

        <section className="border-t border-line-2 pt-4">
          <h3 className="mb-1 text-[13px] font-bold">Sync into your vault</h3>
          {status.isLoading ? <p className="text-[13px] text-muted">Checking…</p>
            : ready && st ? (
              <>
                <p className="mb-2 text-[13px] text-muted">
                  Writes to <code className="break-all rounded bg-surface-2 px-1 text-[12px] text-ink">{st.vault_dir}</code> in the
                  <b> HP Slide Library</b> folder only. Your own notes are never touched.
                  {st.last_sync && <> Last synced {fmtDate(st.last_sync)}.</>}
                  {!st.is_vault && " This folder isn't an Obsidian vault yet — open it in Obsidian once to make it one."}
                </p>
                <Button variant="primary" icon={<FolderSync className="size-4" />} loading={sync.isPending} onClick={() => sync.mutate(params)}>
                  Sync to Obsidian vault
                </Button>
              </>
            ) : st?.configured ? (
              <p className="text-[13px] text-bad">
                The folder set in <Kbd>OBSIDIAN_VAULT_DIR</Kbd> doesn't exist{st.vault_dir ? <>: <code className="break-all">{st.vault_dir}</code></> : ""}.
                Create it or fix the path in <b>.env</b>, then restart the app.
              </p>
            ) : (
              <ol className="list-decimal space-y-1 pl-5 text-[13px] text-muted">
                <li>Install Obsidian from <b>obsidian.md</b> and create (or pick) a vault.</li>
                <li>Set <Kbd>OBSIDIAN_VAULT_DIR</Kbd> in the app's <b>.env</b> to that vault's folder.</li>
                <li>Restart the app — a <b>Sync</b> button appears here and in the library menu.</li>
              </ol>
            )}
        </section>
        <p className="flex items-center gap-1.5 text-[12px] text-faint">
          <ExternalLink className="size-3.5" />Every note links back to its slide in this app.
        </p>
      </div>
    </Dialog>
  );
}
