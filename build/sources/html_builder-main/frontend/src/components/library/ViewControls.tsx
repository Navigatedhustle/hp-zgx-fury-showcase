import { Layers, LayoutGrid, List } from "lucide-react";
import { useCallback, useState } from "react";
import { SORTS, type SortKey } from "../../lib/library";
import { cn } from "../../lib/util";
import { Tip } from "../ui";

export type GridSize = "s" | "m" | "l" | "xl";
export type ViewSize = GridSize | "details";
export const GRID_SIZES: GridSize[] = ["s", "m", "l", "xl"];
/** Minimum card width per size; the grid fills the row with as many as fit. */
export const CARD_MIN: Record<GridSize, number> = { s: 150, m: 220, l: 320, xl: 460 };
const SIZE_LABEL: Record<GridSize, string> = { s: "Small", m: "Medium", l: "Large", xl: "Extra large" };

/** Slides under their project and deck, or one flat list. */
export type GroupBy = "project" | "none";

const KEY = "library.view";
const isView = (v: unknown): v is ViewSize => v === "details" || GRID_SIZES.includes(v as GridSize);

/** The chosen thumbnail size, remembered per browser. Storage can be unavailable — then it simply isn't remembered. */
export function useViewSize(): [ViewSize, (v: ViewSize) => void] {
  const [view, setView] = useState<ViewSize>(() => {
    try { const v = localStorage.getItem(KEY); return isView(v) ? v : "m"; } catch { return "m"; }
  });
  const set = useCallback((v: ViewSize) => {
    setView(v);
    try { localStorage.setItem(KEY, v); } catch { /* storage unavailable */ }
  }, []);
  return [view, set];
}

/** One step bigger (+1) or smaller (-1); Details sits below Small. */
export function stepView(v: ViewSize, dir: 1 | -1): ViewSize {
  const order: ViewSize[] = ["details", ...GRID_SIZES];
  const i = order.indexOf(v) + dir;
  return order[Math.max(0, Math.min(order.length - 1, i))] ?? v;
}

export function ViewControls({ view, onView, sort, onSort, relevance, group, onGroup }: {
  view: ViewSize; onView: (v: ViewSize) => void; sort: SortKey; onSort: (s: SortKey) => void;
  /** "Best match" only means something with a query. */
  relevance: boolean;
  group: GroupBy; onGroup: (g: GroupBy) => void;
}) {
  const gridIdx = view === "details" ? 1 : GRID_SIZES.indexOf(view);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Tip label={group === "project" ? "Grouped by project and deck — click for one flat list" : "Group by project and deck"}>
        <button aria-label="Group by project and deck" aria-pressed={group === "project"} onClick={() => onGroup(group === "project" ? "none" : "project")}
          className={cn("flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-[13px] font-semibold",
            group === "project" ? "border-accent bg-accent-soft text-accent" : "border-line bg-surface text-muted hover:text-ink")}>
          <Layers className="size-4" /><span className="hidden sm:inline">Group</span>
        </button>
      </Tip>
      {/* A grouped list has one order: projects A–Z, the newest deck first. */}
      {group === "none" && (
        <label className="flex items-center gap-2 text-[13px] text-muted">
          <span className="sr-only sm:not-sr-only">Sort</span>
          <select value={sort} onChange={e => onSort(e.target.value as SortKey)}
            className="h-8 rounded-lg border border-line bg-surface px-2 text-[13px] font-semibold text-ink focus:border-accent focus:outline-none">
            {SORTS.filter(s => relevance || s.value !== "relevance").map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </label>
      )}
      <div className="flex items-center gap-1 rounded-lg border border-line bg-surface p-0.5" role="group" aria-label="View">
        <Tip label="Details list">
          <button aria-label="Details list" aria-pressed={view === "details"} onClick={() => onView("details")}
            className={cn("flex size-7 items-center justify-center rounded-md", view === "details" ? "bg-accent-soft text-accent" : "text-muted hover:text-ink")}>
            <List className="size-4" />
          </button>
        </Tip>
        <Tip label={view === "details" ? "Thumbnail grid" : `${SIZE_LABEL[view]} thumbnails — Ctrl + scroll to resize`}>
          <button aria-label="Thumbnail grid" aria-pressed={view !== "details"} onClick={() => view === "details" && onView("m")}
            className={cn("flex size-7 items-center justify-center rounded-md", view !== "details" ? "bg-accent-soft text-accent" : "text-muted hover:text-ink")}>
            <LayoutGrid className="size-4" />
          </button>
        </Tip>
        <input type="range" min={0} max={GRID_SIZES.length - 1} step={1} value={gridIdx}
          aria-label="Thumbnail size" aria-valuetext={view === "details" ? "Details list" : SIZE_LABEL[view]}
          onChange={e => onView(GRID_SIZES[Number(e.target.value)] ?? "m")}
          className={cn("mx-1.5 w-20 accent-[var(--accent)]", view === "details" && "opacity-40")} />
        <span className="w-6 pr-1 text-center text-[11px] font-bold uppercase text-muted" aria-hidden>{view === "details" ? "—" : view}</span>
      </div>
    </div>
  );
}
