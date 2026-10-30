import { Plus } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { humanize, libApi, type LibTag } from "../../lib/library";
import { cn } from "../../lib/util";
import { inputClass } from "../ui";

const norm = (s: string) => s.trim().toLowerCase();

/** The existing tag a typed text means — by label, slug or alias — if there is one. */
export function matchTag(text: string, tags: LibTag[]): LibTag | undefined {
  const n = norm(text);
  const slug = n.replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return tags.find(t => norm(t.label) === n || t.slug === slug || t.aliases.some(a => norm(a) === n));
}

/** The slug for a typed tag: the existing one, or a new tag created on the spot. */
export async function ensureTag(text: string, tags: LibTag[]): Promise<string> {
  const hit = matchTag(text, tags);
  if (hit) return hit.slug;
  return (await libApi.createTag(text.trim(), "topic")).slug;
}

/**
 * A tag box with suggestions from the vocabulary. Enter picks the highlighted suggestion, or — with
 * `allowCreate` — whatever was typed, which becomes a new tag.
 */
export function TagInput({ tags, exclude = [], onPick, allowCreate = true, placeholder = "Add a tag…", autoFocus, className }: {
  tags: LibTag[]; exclude?: string[]; onPick: (text: string, tag?: LibTag) => void;
  allowCreate?: boolean; placeholder?: string; autoFocus?: boolean; className?: string;
}) {
  const id = useId();
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const matches = useMemo(() => {
    const n = norm(text);
    const skip = new Set(exclude);
    return tags
      .filter(t => t.approved && !skip.has(t.slug))
      .filter(t => !n || norm(t.label).includes(n) || t.slug.includes(n) || t.aliases.some(a => norm(a).includes(n)))
      .sort((a, b) => (norm(a.label).startsWith(n) ? 0 : 1) - (norm(b.label).startsWith(n) ? 0 : 1) || b.count - a.count)
      .slice(0, 8);
  }, [tags, exclude, text]);
  const exact = text.trim() ? matchTag(text, tags) : undefined;
  const canCreate = allowCreate && !!text.trim() && !exact;
  const count = matches.length + (canCreate ? 1 : 0);

  const pick = (i: number) => {
    const t = matches[i];
    if (t) onPick(t.label, t);
    else if (canCreate) onPick(text.trim(), undefined);
    else return;
    setText("");
    setHi(0);
  };

  return (
    <div className={cn("relative", className)}>
      <input value={text} autoFocus={autoFocus} placeholder={placeholder}
        role="combobox" aria-expanded={open && count > 0} aria-controls={`${id}-list`} aria-autocomplete="list"
        aria-activedescendant={open && count > 0 ? `${id}-${hi}` : undefined}
        onChange={e => { setText(e.target.value); setHi(0); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={e => {
          if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setHi(h => Math.min(count - 1, h + 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setHi(h => Math.max(0, h - 1)); }
          else if (e.key === "Enter") {
            e.preventDefault();
            // An exact match wins over the highlighted row, so typing a full name always means that tag.
            if (exact && !exclude.includes(exact.slug)) { onPick(exact.label, exact); setText(""); setHi(0); }
            else pick(hi);
          } else if (e.key === "Escape" && open && text) { e.stopPropagation(); setOpen(false); }
        }}
        className={cn(inputClass, "h-8 text-[13px]")} />
      {open && count > 0 && (
        <ul id={`${id}-list`} role="listbox"
          className="absolute left-0 right-0 top-full z-50 mt-1 max-h-64 overflow-auto rounded-xl border border-line bg-surface p-1 shadow-card">
          {matches.map((t, i) => (
            <li key={t.slug} id={`${id}-${i}`} role="option" aria-selected={i === hi}
              onMouseDown={e => { e.preventDefault(); pick(i); }} onMouseEnter={() => setHi(i)}
              className={cn("flex cursor-pointer items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-[13px]", i === hi && "bg-surface-2")}>
              <span className="truncate font-semibold">{t.label}</span>
              <span className="shrink-0 text-[11px] text-muted">{humanize(t.facet)} · {t.count}</span>
            </li>
          ))}
          {canCreate && (
            <li id={`${id}-${matches.length}`} role="option" aria-selected={hi === matches.length}
              onMouseDown={e => { e.preventDefault(); pick(matches.length); }} onMouseEnter={() => setHi(matches.length)}
              className={cn("flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13px] text-accent", hi === matches.length && "bg-surface-2")}>
              <Plus className="size-3.5" />Create “{text.trim()}”
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
