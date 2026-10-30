import { Check, ChevronDown, Star } from "lucide-react";
import { useState } from "react";
import { humanize, type FacetKey, type FacetValue, type SearchParams } from "../../lib/library";
import { cn } from "../../lib/util";
import { Switch } from "../ui";

export const FACET_LABEL: Record<FacetKey, string> = {
  project: "Project", tag: "Tag", type: "Slide type", entity: "Mentions", deck: "Deck", origin: "Source",
};
const ORDER: FacetKey[] = ["project", "tag", "type", "entity", "deck", "origin"];
const SHOWN = 6;

/** Label for a facet value: what the facet list calls it, else a tidy version of the raw value. */
export function facetLabel(facets: Partial<Record<FacetKey, FacetValue[]>> | undefined, key: FacetKey, value: string): string {
  return facets?.[key]?.find(v => v.value === value)?.label || (key === "type" || key === "origin" ? humanize(value) : value);
}

function FacetGroup({ k, values, active, onPick, nameOf }: {
  k: FacetKey; values: FacetValue[]; active?: string; onPick: (v: string | undefined) => void; nameOf?: (v: string) => string;
}) {
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState(true);
  // The active value always shows, even when the current results no longer list it.
  const list = active && !values.some(v => v.value === active) ? [{ value: active, label: nameOf?.(active) ?? active, count: 0 }, ...values] : values;
  if (!list.length) return null;
  const shown = all ? list : list.slice(0, SHOWN);
  const id = `facet-${k}`;
  return (
    <section className="border-t border-line-2 py-3 first:border-t-0">
      <button aria-expanded={open} aria-controls={id} onClick={() => setOpen(o => !o)}
        className="flex w-full items-center justify-between rounded-md text-[11px] font-bold uppercase tracking-wider text-muted hover:text-ink">
        {FACET_LABEL[k]}<ChevronDown className={cn("size-3.5 transition-transform", !open && "-rotate-90")} />
      </button>
      {open && (
        <ul id={id} className="mt-1.5 space-y-0.5">
          {shown.map(v => {
            const on = v.value === active;
            return (
              <li key={v.value}>
                <button aria-pressed={on} onClick={() => onPick(on ? undefined : v.value)}
                  className={cn("flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-[13px]",
                    on ? "bg-accent-soft font-semibold text-accent" : "text-ink hover:bg-surface-2")}>
                  <span className="min-w-0 flex-1 truncate">{k === "type" || k === "origin" ? (v.label === v.value ? humanize(v.label) : v.label) : v.label || v.value}</span>
                  {on ? <Check className="size-3.5 shrink-0" /> : <span className="shrink-0 text-[11px] tabular-nums text-muted">{v.count}</span>}
                </button>
              </li>
            );
          })}
          {list.length > SHOWN && (
            <li><button onClick={() => setAll(a => !a)} className="px-2 py-1 text-[12px] font-semibold text-accent hover:underline">
              {all ? "Show fewer" : `Show all ${list.length}`}
            </button></li>
          )}
        </ul>
      )}
    </section>
  );
}

export function Facets({ facets, params, onChange, names }: {
  facets?: Partial<Record<FacetKey, FacetValue[]>>; params: SearchParams; onChange: (patch: Partial<SearchParams>) => void;
  /** Names for active values the current results don't list (a deck id picked from its deck bar or an upload). */
  names?: Partial<Record<FacetKey, (v: string) => string>>;
}) {
  return (
    <nav aria-label="Filters" className="space-y-1">
      <div className="space-y-2.5 pb-3">
        <label className="flex cursor-pointer items-center justify-between gap-2 text-[13px] font-semibold">
          <span className="flex items-center gap-1.5"><Star className="size-3.5 text-warn" />Favourites only</span>
          <Switch checked={!!params.fav} onCheckedChange={v => onChange({ fav: v || undefined })} label="Favourites only" />
        </label>
        <label className="flex cursor-pointer items-center justify-between gap-2 text-[13px] font-semibold">
          <span>Show old versions</span>
          <Switch checked={!!params.superseded} onCheckedChange={v => onChange({ superseded: v || undefined })} label="Show slides from superseded decks" />
        </label>
      </div>
      {ORDER.map(k => (
        <FacetGroup key={k} k={k} values={facets?.[k] ?? []} active={params[k]} nameOf={names?.[k]} onPick={v => onChange({ [k]: v })} />
      ))}
      <section className="border-t border-line-2 py-3">
        <h3 className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-muted">Deck date</h3>
        <div className="grid grid-cols-2 gap-1.5">
          <label className="text-[11px] text-muted">From
            <input type="date" value={params.from ?? ""} onChange={e => onChange({ from: e.target.value || undefined })}
              className="mt-0.5 h-8 w-full rounded-md border border-line bg-surface px-1.5 text-[12px] text-ink focus:border-accent focus:outline-none" />
          </label>
          <label className="text-[11px] text-muted">To
            <input type="date" value={params.to ?? ""} onChange={e => onChange({ to: e.target.value || undefined })}
              className="mt-0.5 h-8 w-full rounded-md border border-line bg-surface px-1.5 text-[12px] text-ink focus:border-accent focus:outline-none" />
          </label>
        </div>
      </section>
    </nav>
  );
}
