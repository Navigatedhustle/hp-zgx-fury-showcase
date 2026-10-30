import { AlertTriangle, Check, CircleAlert, FileText, Minus, Star, Trash2, Undo2 } from "lucide-react";
import { useState } from "react";
import type { Fact, Finding, Slide, SlidePatchBody, Version } from "../lib/api";
import { cn, fidelityFindings, keyFacts } from "../lib/util";
import { Badge, IconButton, Tip } from "./ui";

/**
 * The fact ledger, in the two places it means something different.
 *
 * In the plan view it is a *contract*: these are the figures and names the source slide asserts, and the
 * ones marked prominent must end up on the designed slide rather than in its speaker notes. Showing it
 * before generation is the point — a bad extraction is cheap to fix here and expensive to discover in a
 * finished deck, and the user is the only one who knows that a figure in the source footer is a document
 * reference rather than a claim.
 *
 * In the review view the same contract carries what actually happened, read out of the version's fidelity
 * findings. The distinction the colours draw is the one the backend draws: a value the slide *changed* is
 * a different kind of failure from one it merely dropped.
 */

const TIER_HINT: Record<Fact["tier"], string> = {
  key: "Carries the slide's message, so it must be on the slide itself — not only in the speaker notes.",
  supporting: "Supporting detail. It has to survive onto the slide or into its speaker notes.",
};

const ORIGIN_HINT: Record<string, string> = {
  table: "read straight out of the PowerPoint table",
  chart: "read out of the chart's data, not off its picture",
  title: "from the slide title",
  notes: "from the speaker notes",
  llm: "added by the planner",
  text: "from the slide's text",
  doc: "from one of your reference documents — cited in the slide's sources",
};

function FactChip({ fact }: { fact: Fact }) {
  const isKey = fact.tier === "key";
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-1.5 rounded-md px-2 py-1 text-[12px] leading-tight ring-1",
      isKey ? "bg-accent-soft text-accent ring-accent/25" : "bg-surface-2 text-muted ring-line-2")}>
      {isKey && <Star className="size-3 shrink-0 fill-current" />}
      {fact.origin === "doc" && <FileText className="size-3 shrink-0" aria-label="from a reference document" />}
      <span className="shrink-0 font-mono font-bold tabular-nums">{fact.raw}</span>
      {fact.label && fact.label !== fact.raw && <span className="truncate opacity-75">{fact.label}</span>}
    </span>
  );
}

/** The contract, before anything is generated — and the one place it can be corrected. */
export function FactContract({ slide, locked, onPatch }: {
  slide: Slide; locked?: boolean; onPatch?: (body: SlidePatchBody) => void;
}) {
  const [open, setOpen] = useState(false);
  const facts = slide.facts ?? [];
  const key = keyFacts(facts);
  if (!facts.length) return null;
  const editable = !locked && !!onPatch;
  const shown = open ? facts : key.length ? key : facts.slice(0, 4);
  const patch = (p: { id: string; tier?: Fact["tier"]; drop?: boolean }) => onPatch?.({ facts: [p] });

  return (
    <div className="rounded-lg border border-line-2">
      <div className="flex items-center gap-2 px-2 py-1">
        <button type="button" onClick={() => setOpen(o => !o)} aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-2 text-left text-[11px] font-bold uppercase tracking-wide text-muted hover:text-ink">
          Facts
          <span className="truncate font-medium normal-case tracking-normal text-faint">
            {key.length
              ? `${key.length} on the slide, ${facts.length - key.length} supporting`
              : `${facts.length} to keep`}
          </span>
        </button>
        {slide.facts_edited && (
          <>
            <Badge tone="accent">Edited</Badge>
            {editable && (
              <IconButton label="Go back to the facts read from the PowerPoint" onClick={() => onPatch?.({ reset_facts: true })}>
                <Undo2 className="size-3.5" />
              </IconButton>
            )}
          </>
        )}
        <button type="button" onClick={() => setOpen(o => !o)}
          className="text-[11px] font-semibold text-muted hover:text-ink">{open ? "Show less" : "Show all"}</button>
      </div>

      {!open && (
        <div className="flex flex-wrap gap-1.5 px-2 pb-2">
          {shown.map(f => (
            <Tip key={f.id} label={`${TIER_HINT[f.tier]} (${ORIGIN_HINT[f.origin] ?? f.origin})`}>
              <span><FactChip fact={f} /></span>
            </Tip>
          ))}
        </div>
      )}

      {open && (
        <div className="space-y-2 px-2 pb-2">
          <ul className="space-y-1">
            {facts.map(f => (
              <li key={f.id} className="flex items-center gap-1.5">
                <Tip label={ORIGIN_HINT[f.origin] ?? f.origin}><span className="min-w-0"><FactChip fact={f} /></span></Tip>
                {editable && (
                  <span className="ml-auto flex shrink-0 items-center">
                    <IconButton
                      label={f.tier === "key"
                        ? "Make this supporting — it may then sit in the speaker notes"
                        : "Mark as the slide's message — it must then be visible on the slide"}
                      onClick={() => patch({ id: f.id, tier: f.tier === "key" ? "supporting" : "key" })}>
                      <Star className={cn("size-3.5", f.tier === "key" && "fill-current text-accent")} />
                    </IconButton>
                    <IconButton label="Not a fact this deck has to carry" onClick={() => patch({ id: f.id, drop: true })}>
                      <Trash2 className="size-3.5" />
                    </IconButton>
                  </span>
                )}
              </li>
            ))}
          </ul>
          <p className="text-[11px] leading-snug text-faint">
            Every value here is kept exactly as the source states it — never reworded, rounded or re-scaled. How
            each one is presented is up to the design. Starred facts must be visible on the slide; the rest may
            move into the speaker notes. Strike out anything that is a document reference rather than a claim.
          </p>
        </div>
      )}
    </div>
  );
}

/** What became of the contract, after the slide was rendered and checked. */
export function FactReport({ slide, version }: { slide?: Slide; version: Version }) {
  const findings = fidelityFindings(version);
  const facts = slide?.facts ?? [];
  if (!findings.length) {
    if (!facts.length) return null;
    return (
      <p className="flex items-center gap-1.5 text-[13px] text-good">
        <Check className="size-4 shrink-0" />
        All {facts.length} source {facts.length === 1 ? "fact is" : "facts are"} on this slide or in its notes.
      </p>
    );
  }
  return <ul className="space-y-1.5">{findings.map((f, i) => <FidelityRow key={i} finding={f} />)}</ul>;
}

const ICON: Record<string, typeof Check> = {
  "fidelity-changed": AlertTriangle,
  "fidelity-invented": CircleAlert,
  "fidelity-key": FileText,
  fidelity: Minus,
};

function FidelityRow({ finding }: { finding: Finding }) {
  const Icon = ICON[finding.code] ?? Minus;
  return (
    <li className={cn("flex items-start gap-1.5 text-[13px] leading-snug",
      finding.fatal ? "text-bad" : finding.severity === "error" ? "text-warn" : "text-muted")}>
      <Icon className="mt-0.5 size-4 shrink-0" />
      <span>{finding.fatal && <b className="mr-1">Not shippable:</b>}{finding.message}</span>
    </li>
  );
}
