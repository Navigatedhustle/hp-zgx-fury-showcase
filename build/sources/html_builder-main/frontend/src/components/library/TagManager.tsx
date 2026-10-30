import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Merge, Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { humanize, libApi, libKeys, options, useLibTags, useTaxonomy, type LibTag } from "../../lib/library";
import { cn } from "../../lib/util";
import { Button, Dialog, IconButton, Spinner, inputClass } from "../ui";

const DEFAULT_FACETS = ["topic", "product", "customer", "project"];
const selectClass = "h-8 rounded-lg border border-line bg-surface px-2 text-[13px] text-ink focus:border-accent focus:outline-none";

function useTagOp<T>(fn: (v: T) => Promise<unknown>, done: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      // Tag edits rewrite slides too (merge, delete, rename of labels shown on cards).
      void qc.invalidateQueries({ queryKey: libKeys.tags });
      void qc.invalidateQueries({ queryKey: libKeys.searchAll });
      void qc.invalidateQueries({ queryKey: ["library", "slide"] });
      if (done) toast.success(done);
    },
    onError: e => toast.error("That didn't work", { description: (e as Error).message }),
  });
}

function TagRow({ t, facets, checked, onCheck }: { t: LibTag; facets: { value: string; label: string }[]; checked: boolean; onCheck: (v: boolean) => void }) {
  const [renaming, setRenaming] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const patch = useTagOp((body: { label?: string; facet?: string }) => libApi.patchTag(t.slug, body), "");
  const approve = useTagOp(() => libApi.approveTag(t.slug), `“${t.label}” is now in the vocabulary`);
  const del = useTagOp(() => libApi.deleteTag(t.slug), `“${t.label}” deleted`);
  const saveName = () => {
    const v = renaming?.trim();
    if (v && v !== t.label) patch.mutate({ label: v }, { onSuccess: () => setRenaming(null) });
    else setRenaming(null);
  };
  const facetOpts = facets.some(f => f.value === t.facet) ? facets : [{ value: t.facet, label: humanize(t.facet) }, ...facets];
  return (
    <tr className={cn("border-t border-line-2", !t.approved && "bg-warn-soft/40")}>
      <td className="w-8 py-1.5 pl-1">
        <input type="checkbox" checked={checked} onChange={e => onCheck(e.target.checked)} aria-label={`Select ${t.label}`} className="size-4 accent-[var(--accent)]" />
      </td>
      <td className="py-1.5 pr-2">
        {renaming !== null ? (
          <div className="flex items-center gap-1">
            <input autoFocus value={renaming} onChange={e => setRenaming(e.target.value)} aria-label="Tag name"
              onKeyDown={e => { if (e.key === "Enter") saveName(); if (e.key === "Escape") { e.stopPropagation(); setRenaming(null); } }}
              className={cn(inputClass, "h-8 text-[13px]")} />
            <IconButton label="Save name" onClick={saveName}><Check className="size-4" /></IconButton>
          </div>
        ) : (
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="truncate text-[13px] font-semibold">{t.label}</span>
              {!t.approved && <span className="rounded-full bg-warn-soft px-1.5 text-[10px] font-bold uppercase text-warn">Suggested</span>}
            </div>
            <div className="truncate text-[11px] text-faint">{t.slug}{t.aliases.length ? ` · also ${t.aliases.join(", ")}` : ""}</div>
          </div>
        )}
      </td>
      <td className="py-1.5 pr-2">
        <select value={t.facet} aria-label={`Kind of ${t.label}`} className={selectClass} disabled={patch.isPending}
          onChange={e => patch.mutate({ facet: e.target.value })}>
          {facetOpts.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
        </select>
      </td>
      <td className="py-1.5 pr-2 text-right text-[13px] tabular-nums text-muted">{t.count}</td>
      <td className="py-1.5 pr-1">
        <div className="flex items-center justify-end gap-0.5">
          {!t.approved && <Button size="sm" variant="ghost" className="text-good" icon={<Check className="size-3.5" />} loading={approve.isPending} onClick={() => approve.mutate(undefined)}>Approve</Button>}
          {renaming === null && <IconButton label="Rename" onClick={() => setRenaming(t.label)}><Pencil className="size-3.5" /></IconButton>}
          {confirm ? (
            <>
              <Button size="sm" variant="danger" loading={del.isPending} onClick={() => del.mutate(undefined)}>Delete{t.count ? ` from ${t.count}` : ""}</Button>
              <IconButton label="Keep it" onClick={() => setConfirm(false)}><X className="size-3.5" /></IconButton>
            </>
          ) : <IconButton label="Delete tag" onClick={() => setConfirm(true)}><Trash2 className="size-3.5" /></IconButton>}
        </div>
      </td>
    </tr>
  );
}

export function TagManager({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const tags = useLibTags();
  const facets = options(useTaxonomy().data?.facets);
  const facetList = facets.length ? facets : DEFAULT_FACETS.map(f => ({ value: f, label: humanize(f) }));
  const [q, setQ] = useState("");
  const [show, setShow] = useState<string>("all");   // "all" | "suggested" | a facet
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [into, setInto] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [newFacet, setNewFacet] = useState("topic");

  const all = useMemo(() => tags.data ?? [], [tags.data]);
  const suggested = all.filter(t => !t.approved).length;
  const list = useMemo(() => {
    const n = q.trim().toLowerCase();
    return all
      .filter(t => show === "all" || (show === "suggested" ? !t.approved : t.facet === show))
      .filter(t => !n || t.label.toLowerCase().includes(n) || t.slug.includes(n) || t.aliases.some(a => a.toLowerCase().includes(n)))
      .sort((a, b) => Number(a.approved) - Number(b.approved) || b.count - a.count || a.label.localeCompare(b.label));
  }, [all, q, show]);

  const picked = all.filter(t => checked.has(t.slug));
  const target = picked.some(t => t.slug === into) ? into : picked[0]?.slug ?? "";
  const merge = useTagOp(() => libApi.mergeTags(picked.map(t => t.slug).filter(s => s !== target), target), "Tags merged");
  const create = useTagOp(() => libApi.createTag(newLabel.trim(), newFacet), `“${newLabel.trim()}” added`);

  const toggle = (slug: string, v: boolean) => setChecked(s => { const n = new Set(s); if (v) n.add(slug); else n.delete(slug); return n; });

  return (
    <Dialog open={open} onOpenChange={onOpenChange} wide title="Tags"
      description="The vocabulary the review model tags from. Rename, regroup, merge duplicates, and approve what it suggests.">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-48 flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="Find a tag" aria-label="Find a tag" className={cn(inputClass, "pl-8")} />
          </div>
          <div className="flex flex-wrap gap-1" role="group" aria-label="Show">
            {[{ value: "all", label: "All" }, ...facetList, ...(suggested ? [{ value: "suggested", label: `Suggested (${suggested})` }] : [])].map(f => (
              <button key={f.value} aria-pressed={show === f.value} onClick={() => setShow(f.value)}
                className={cn("h-8 rounded-lg px-2.5 text-[13px] font-semibold", show === f.value ? "bg-accent-soft text-accent" : "text-muted hover:bg-surface-2 hover:text-ink")}>
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {picked.length >= 2 && (
          <div className="flex flex-wrap items-center gap-2 rounded-xl bg-accent-soft px-3 py-2 text-[13px]">
            <Merge className="size-4 text-accent" />
            <span>Merge {picked.length} tags into</span>
            <select value={target} onChange={e => setInto(e.target.value)} className={selectClass} aria-label="Merge into">
              {picked.map(t => <option key={t.slug} value={t.slug}>{t.label}</option>)}
            </select>
            <span className="text-muted">— every slide is rewritten, the others become aliases.</span>
            <Button size="sm" variant="primary" className="ml-auto" loading={merge.isPending}
              onClick={() => merge.mutate(undefined, { onSuccess: () => setChecked(new Set()) })}>Merge</Button>
          </div>
        )}

        <div className="max-h-[55vh] overflow-auto rounded-xl border border-line scroll-thin">
          {tags.isLoading ? <div className="flex h-32 items-center justify-center text-muted"><Spinner /></div>
            : tags.isError ? <p className="p-4 text-sm text-bad">Couldn't load the tags: {tags.error.message}</p>
              : !list.length ? <p className="p-6 text-center text-sm text-muted">{all.length ? "No tags match." : "No tags yet — they appear as slides are tagged."}</p>
                : (
                  <table className="w-full table-fixed">
                    <colgroup><col className="w-8" /><col /><col className="w-32" /><col className="w-16" /><col className="w-56" /></colgroup>
                    <thead className="sticky top-0 bg-surface-2 text-left text-[11px] font-bold uppercase tracking-wider text-muted">
                      <tr><th className="py-2 pl-1"><span className="sr-only">Select</span></th><th className="py-2">Tag</th><th className="py-2">Kind</th><th className="py-2 pr-2 text-right">Slides</th><th className="py-2"><span className="sr-only">Actions</span></th></tr>
                    </thead>
                    <tbody className="px-2">
                      {list.map(t => <TagRow key={t.slug} t={t} facets={facetList} checked={checked.has(t.slug)} onCheck={v => toggle(t.slug, v)} />)}
                    </tbody>
                  </table>
                )}
        </div>

        <form className="flex flex-wrap items-center gap-2" onSubmit={e => {
          e.preventDefault();
          if (newLabel.trim()) create.mutate(undefined, { onSuccess: () => setNewLabel("") });
        }}>
          <input value={newLabel} onChange={e => setNewLabel(e.target.value)} placeholder="New tag" aria-label="New tag" className={cn(inputClass, "w-56 flex-1")} />
          <select value={newFacet} onChange={e => setNewFacet(e.target.value)} aria-label="Kind" className={cn(selectClass, "h-9")}>
            {facetList.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select>
          <Button type="submit" icon={<Plus className="size-4" />} loading={create.isPending} disabled={!newLabel.trim()}>Add tag</Button>
        </form>
      </div>
    </Dialog>
  );
}
