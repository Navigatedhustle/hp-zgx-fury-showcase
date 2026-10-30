import { Keyboard } from "lucide-react";
import { useState } from "react";
import { useKey } from "../lib/hooks";
import { Dialog, IconButton, Kbd } from "./ui";

const GROUPS: { title: string; rows: [string[], string][] }[] = [
  {
    title: "Review",
    rows: [
      [["J", "↓"], "Next slide"],
      [["K", "↑"], "Previous slide"],
      [["1"], "Use the Cinematic design"],
      [["2"], "Use the Refined design"],
      [["O"], "Show or hide the original slide"],
      [["C"], "Jump to the comment box"],
    ],
  },
  {
    title: "Previews",
    rows: [
      [["→", "←"], "Step through a preview once it has focus"],
      [["Esc"], "Close a dialog or leave the comment box"],
    ],
  },
  {
    title: "Anywhere",
    rows: [[["?"], "Open this list"]],
  },
];

/** Keyboard help for the builder — the exported deck has its own `?` overlay. */
export function ShortcutsButton() {
  const [open, setOpen] = useState(false);
  useKey(e => {
    if (e.key === "?") { e.preventDefault(); setOpen(o => !o); }
  });
  return (
    <>
      <IconButton label="Keyboard shortcuts (?)" onClick={() => setOpen(true)}><Keyboard className="size-4" /></IconButton>
      <Dialog open={open} onOpenChange={setOpen} title="Keyboard shortcuts"
        description="Shortcuts work whenever you aren't typing in a box — including while a preview has focus.">
        <div className="space-y-5">
          {GROUPS.map(g => (
            <section key={g.title}>
              <h4 className="mb-2 text-sm font-bold">{g.title}</h4>
              <ul className="space-y-1.5">
                {g.rows.map(([keys, label]) => (
                  <li key={label} className="flex items-center gap-3 text-[13px]">
                    <span className="flex w-24 shrink-0 gap-1">{keys.map(k => <Kbd key={k}>{k}</Kbd>)}</span>
                    <span className="text-muted">{label}</span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </Dialog>
    </>
  );
}
