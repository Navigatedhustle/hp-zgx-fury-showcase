import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import type { LibSlide, LibTag } from "../../lib/library";
import { Button, Spinner } from "../ui";
import { SlideCard, type CardHandlers } from "./SlideCard";
import { CARD_MIN, stepView, type ViewSize } from "./ViewControls";

interface CardsProps extends CardHandlers {
  items: LibSlide[]; view: ViewSize; selected: Set<string>; tags: Map<string, LibTag>;
}
interface Props extends CardsProps {
  onView: (v: ViewSize) => void;
  hasMore: boolean; loadingMore: boolean; onMore: () => void;
}

/** Move focus between cards with the arrow keys: left/right in reading order, up/down to the nearest card in the next row. */
function moveFocus(root: HTMLElement, from: HTMLElement, key: string): boolean {
  const cards = [...root.querySelectorAll<HTMLElement>("[data-card-main]")];
  const i = cards.indexOf(from);
  if (i < 0) return false;
  let target: HTMLElement | undefined;
  if (key === "ArrowRight") target = cards[i + 1];
  else if (key === "ArrowLeft") target = cards[i - 1];
  else if (key === "Home") target = cards[0];
  else if (key === "End") target = cards[cards.length - 1];
  else {
    const r = from.getBoundingClientRect();
    const down = key === "ArrowDown";
    let best = Infinity;
    for (const c of cards) {
      const b = c.getBoundingClientRect();
      const dy = down ? b.top - r.top : r.top - b.top;
      if (dy < 4) continue;
      const score = dy * 4 + Math.abs(b.left - r.left);
      if (score < best) { best = score; target = c; }
    }
  }
  if (!target) return false;
  target.focus();
  target.scrollIntoView({ block: "nearest" });
  return true;
}

/**
 * What every slide grid on a page shares, whatever it holds — one list or a list per deck: Ctrl + wheel resizes
 * the thumbnails, and the arrow keys move between cards (across lists too).
 */
export function SlideGridFrame({ view, onView, children }: { view: ViewSize; onView: (v: ViewSize) => void; children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  const latest = useRef({ view, onView });
  useEffect(() => { latest.current = { view, onView }; });

  // Ctrl + wheel resizes the thumbnails instead of zooming the page. Needs a non-passive listener to preventDefault.
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    let acc = 0;
    let last = 0;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      acc += e.deltaY;
      const now = performance.now();
      if (Math.abs(acc) < 60 || now - last < 140) return;
      last = now;
      const { view: v, onView: set } = latest.current;
      set(stepView(v, acc < 0 ? 1 : -1));
      acc = 0;
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(e.key)) return;
    const t = e.target as HTMLElement;
    if (!t.matches("[data-card-main]") || !root.current) return;
    if (moveFocus(root.current, t, e.key)) e.preventDefault();
  };

  return <div ref={root} onKeyDown={onKeyDown}>{children}</div>;
}

export function SlideCards({ items, view, selected, tags, ...handlers }: CardsProps) {
  const selecting = selected.size > 0;
  return (
    <div role="list" aria-label="Slides"
      className={view === "details" ? "space-y-2" : "grid gap-3"}
      style={view === "details" ? undefined : { gridTemplateColumns: `repeat(auto-fill, minmax(min(${CARD_MIN[view]}px, 100%), 1fr))` }}>
      {items.map(s => (
        <div role="listitem" key={s.id}>
          <SlideCard s={s} view={view} selected={selected.has(s.id)} selecting={selecting} tags={tags} {...handlers} />
        </div>
      ))}
    </div>
  );
}

export function SlideGrid({ items, view, onView, hasMore, loadingMore, onMore, ...cards }: Props) {
  const sentinel = useRef<HTMLDivElement>(null);
  const latest = useRef({ hasMore, loadingMore, onMore });
  useEffect(() => { latest.current = { hasMore, loadingMore, onMore }; });

  // Infinite scroll: load the next page as the end of the list comes near. "Load more" stays as the fallback.
  // Re-armed per page, so a sentinel still in view after a short page asks again.
  const count = items.length;
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver(entries => {
      const { hasMore: more, loadingMore: busy, onMore: next } = latest.current;
      if (entries.some(e => e.isIntersecting) && more && !busy) next();
    }, { rootMargin: "600px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [count]);

  return (
    <SlideGridFrame view={view} onView={onView}>
      <SlideCards items={items} view={view} {...cards} />
      <div ref={sentinel} className="flex h-16 items-center justify-center">
        {loadingMore ? <Spinner className="text-muted" />
          : hasMore && <Button size="sm" variant="ghost" onClick={onMore}>Load more</Button>}
      </div>
    </SlideGridFrame>
  );
}
