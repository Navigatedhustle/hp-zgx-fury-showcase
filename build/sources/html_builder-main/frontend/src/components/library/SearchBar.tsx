import { HelpCircle, Search, X } from "lucide-react";
import { forwardRef } from "react";
import { cn } from "../../lib/util";
import { Kbd, Tip } from "../ui";

const SYNTAX: [string, string][] = [
  ['"exact phrase"', "words in this order"],
  ["project:zgx", "only this project"],
  ["tag:pricing", "slides with this tag"],
  ["type:chart", "this kind of slide"],
  ["deck:roadmap", "decks whose title matches"],
  ["is:fav", "favourites only"],
  ["-word", "leave out slides with it"],
];

export const SearchBar = forwardRef<HTMLInputElement, { value: string; onChange: (v: string) => void; busy?: boolean; className?: string }>(
  function SearchBar({ value, onChange, busy, className }, ref) {
    return (
      <div className={cn("relative flex min-w-0 flex-1 items-center", className)}>
        <Search className={cn("pointer-events-none absolute left-3 size-4 text-faint", busy && "animate-pulse text-accent")} />
        <input ref={ref} type="search" value={value} onChange={e => onChange(e.target.value)}
          onKeyDown={e => { if (e.key === "Escape" && value) { e.preventDefault(); onChange(""); } }}
          placeholder="Search slides — words, numbers, project:x, tag:x, is:fav"
          aria-label="Search slides" aria-keyshortcuts="/"
          className="h-10 w-full rounded-xl border border-line bg-surface pl-9 pr-20 text-[14px] text-ink placeholder:text-faint focus:border-accent focus:outline-none [&::-webkit-search-cancel-button]:hidden" />
        <div className="absolute right-2 flex items-center gap-1">
          {value ? (
            <button aria-label="Clear search" onClick={() => onChange("")} className="flex size-6 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-ink"><X className="size-3.5" /></button>
          ) : <span className="hidden sm:inline-flex"><Kbd>/</Kbd></span>}
          <Tip side="bottom" label={
            <span className="block py-0.5">
              <span className="mb-1 block font-bold">Search syntax</span>
              {SYNTAX.map(([k, v]) => <span key={k} className="block"><code className="font-semibold">{k}</code> — {v}</span>)}
              <span className="mt-1 block opacity-80">Words match the start of words: “gen” finds “generative”.</span>
            </span>
          }>
            <button aria-label="Search syntax" className="flex size-6 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-ink"><HelpCircle className="size-4" /></button>
          </Tip>
        </div>
      </div>
    );
  });
