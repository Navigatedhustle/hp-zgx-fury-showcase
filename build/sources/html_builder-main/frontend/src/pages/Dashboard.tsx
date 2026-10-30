import { useQuery } from "@tanstack/react-query";
import { BarChart3, Cpu, Gauge, ShieldCheck, Zap } from "lucide-react";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { TopBar } from "../components/AppShell";
import { Badge, Empty, Spinner } from "../components/ui";
import { api, type Usage } from "../lib/api";
import { cn } from "../lib/util";

/**
 * Measured slide usage and selected-price scenarios. Every model call is in the usage ledger (backend/app/usage.py); this prices the
 * same tokens at public cloud list prices (backend/app/pricing.json). Meant to sit open in its own tab during a
 * demo, so it polls on its own and keeps polling in the background.
 */

const RANGES = [["1", "24 hours"], ["7", "7 days"], ["30", "30 days"], ["", "All time"]] as const;
const STAGES: Record<string, string> = {
  outline: "Outline drafting", plan: "Planning", generate: "Slide generation", repair: "Repairs",
  critic: "Critic (vision)", ab: "A/B judge", judge: "Eval judge", probe: "Probes", other: "Other",
};

const compact = (n: number) =>
  n >= 1e9 ? `${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e4 ? `${Math.round(n / 1e3)}K`
    : n >= 1e3 ? `${(n / 1e3).toFixed(1)}K` : `${n}`;
const money = (n: number) =>
  n === 0 ? "$0" : n < 0.01 ? "<$0.01" : n < 1000 ? `$${n.toFixed(2)}` : `$${Math.round(n).toLocaleString()}`;

interface Comparator { id: string; name: string; sub: string }

function comparators(u: Usage): Comparator[] {
  return [
    ...u.frontier.map(f => ({ id: f.id, name: f.name, sub: `${f.vendor} · $${f.input} in / $${f.output} out per 1M` })),
  ];
}

function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => { if (e) setW(e.contentRect.width); });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function Card({ title, sub, children, className }: { title?: string; sub?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn("min-w-0 rounded-2xl border border-line bg-surface p-5 shadow-card", className)}>
      {title && <h2 className="text-[15px] font-bold tracking-tight">{title}</h2>}
      {sub && <p className="mt-0.5 text-[13px] text-muted">{sub}</p>}
      <div className={title ? "mt-4" : ""}>{children}</div>
    </section>
  );
}

function Stat({ icon, label, value, detail }: { icon: ReactNode; label: string; value: string; detail: string }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-5 shadow-card">
      <div className="flex items-center gap-2 text-[13px] font-semibold text-muted">
        <span className="text-accent">{icon}</span>{label}
      </div>
      <div className="mt-2 text-[28px] font-bold leading-none tracking-tight">{value}</div>
      <div className="mt-2 text-[12.5px] text-muted">{detail}</div>
    </div>
  );
}

/** One bar per cloud option, plus local-cost methodology. A single series, so one colour and no legend. */
function CompareBars({ u, pick, onPick }: { u: Usage; pick: string; onPick: (id: string) => void }) {
  const rows = comparators(u).map(c => ({ ...c, cost: u.totals.costs[c.id] ?? 0 }));
  const max = Math.max(...rows.map(r => r.cost), 1e-9);
  return (
    <div className="space-y-2.5" role="list">
      {rows.map(r => (
        <button key={r.id} role="listitem" onClick={() => onPick(r.id)} title={r.sub}
          className={cn("grid w-full grid-cols-[minmax(120px,190px)_1fr] items-center gap-3 rounded-lg px-2 py-1.5 text-left hover:bg-surface-2",
            pick === r.id && "bg-accent-soft/60")}>
          <span className="min-w-0">
            <span className="block truncate text-[13.5px] font-semibold">{r.name}</span>
            <span className="block truncate text-[11.5px] text-muted">{r.sub}</span>
          </span>
          <span className="grid grid-cols-[1fr_72px] items-center gap-2">
            <span className="block h-5">
              <span className="block h-full rounded-r bg-accent transition-[width] duration-500"
                style={{ width: `${(r.cost / max) * 100}%`, minWidth: r.cost > 0 ? 3 : 0 }} />
            </span>
            <span className="whitespace-nowrap text-[13px] font-semibold tabular-nums">{money(r.cost)}</span>
          </span>
        </button>
      ))}
      <div className="grid grid-cols-[minmax(120px,190px)_1fr] items-center gap-3 border-t border-line-2 px-2 pt-3">
        <span>
          <span className="block text-[13.5px] font-semibold">Your GB300</span>
          <span className="block text-[11.5px] text-muted">{u.endpoints.author.model}{u.endpoints.review.model !== u.endpoints.author.model ? ` + ${u.endpoints.review.model}` : ""}</span>
        </span>
        <span className="text-[13px] font-semibold text-good">Local costs require operator assumptions</span>
      </div>
    </div>
  );
}

/** Cumulative cloud-equivalent spend, one point per day. */
function Cumulative({ u, pick }: { u: Usage; pick: string }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const H = 200, P = { l: 56, r: 16, t: 12, b: 26 };
  const pts = u.daily.reduce<{ day: string; v: number; tokens: number }[]>(
    (acc, d) => [...acc, { day: d.day, v: (acc.at(-1)?.v ?? 0) + (d.costs[pick] ?? 0), tokens: d.total_tokens }], []);
  const first = pts[0], last = pts.at(-1);
  const max = Math.max(...pts.map(p => p.v), 1e-9);
  const niceMax = (() => { const e = 10 ** Math.floor(Math.log10(max)); return Math.ceil(max / e) * e; })();
  const iw = Math.max(0, w - P.l - P.r), ih = H - P.t - P.b;
  const x = (i: number) => P.l + (pts.length <= 1 ? iw / 2 : (i / (pts.length - 1)) * iw);
  const y = (v: number) => P.t + ih - (v / niceMax) * ih;
  const line = pts.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.v)}`).join("");
  const area = pts.length > 1 ? `${line}L${x(pts.length - 1)},${y(0)}L${x(0)},${y(0)}Z` : "";
  const ticks = [0, 0.5, 1].map(f => f * niceMax);
  const h = hover != null ? pts[hover] : null;
  return (
    <div ref={ref} className="relative">
      {w > 0 && (
        <svg width={w} height={H} role="img" aria-label="Cumulative cloud-equivalent cost by day"
          onMouseLeave={() => setHover(null)}
          onMouseMove={e => {
            const r = e.currentTarget.getBoundingClientRect();
            const i = pts.length <= 1 ? 0 : Math.round(((e.clientX - r.left - P.l) / iw) * (pts.length - 1));
            setHover(Math.max(0, Math.min(pts.length - 1, i)));
          }}>
          {ticks.map(t => (
            <g key={t}>
              <line x1={P.l} x2={w - P.r} y1={y(t)} y2={y(t)} stroke="var(--line-2)" strokeWidth={1} />
              <text x={P.l - 8} y={y(t) + 4} textAnchor="end" className="fill-faint text-[11px] tabular-nums">{money(t)}</text>
            </g>
          ))}
          {first && last && <>
            <text x={x(0)} y={H - 6} textAnchor={pts.length > 1 ? "start" : "middle"} className="fill-faint text-[11px]">{first.day}</text>
            {pts.length > 1 && <text x={x(pts.length - 1)} y={H - 6} textAnchor="end" className="fill-faint text-[11px]">{last.day}</text>}
          </>}
          {area && <path d={area} fill="var(--accent)" opacity={0.1} />}
          {pts.length > 1 && <path d={line} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />}
          {h && hover != null && <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={P.t + ih} stroke="var(--line)" strokeWidth={1} />}
          {(() => {
            const i = hover ?? pts.length - 1;
            const p = pts[i];
            return p && <circle cx={x(i)} cy={y(p.v)} r={5} fill="var(--accent)" stroke="var(--surface)" strokeWidth={2} />;
          })()}
        </svg>
      )}
      {h && hover != null && (
        <div className="pointer-events-none absolute top-0 rounded-lg border border-line bg-surface px-3 py-2 text-[12px] shadow-card"
          style={{ left: Math.min(Math.max(x(hover) - 80, 0), w - 160), width: 160 }}>
          <div className="font-semibold">{h.day}</div>
          <div className="text-muted">Running total <span className="font-semibold text-ink tabular-nums">{money(h.v)}</span></div>
          <div className="text-muted">That day <span className="tabular-nums">{compact(h.tokens)} tokens</span></div>
        </div>
      )}
    </div>
  );
}

function Table({ head, rows, align }: { head: string[]; rows: ReactNode[][]; align?: ("l" | "r")[] }) {
  return (
    <div className="-mx-1 overflow-x-auto">
      <table className="w-full min-w-[420px] text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-[11.5px] font-semibold uppercase tracking-wide text-faint">
            {head.map((h, i) => <th key={h} className={cn("px-2 pb-2 font-semibold", align?.[i] === "r" && "text-right")}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, j) => (
            <tr key={j} className="border-b border-line-2 last:border-0">
              {r.map((c, i) => <td key={i} className={cn("px-2 py-2.5", align?.[i] === "r" && "text-right tabular-nums")}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Dashboard() {
  const [range, setRange] = useState<string>("");
  const [pick, setPick] = useState<string>("");
  const { data: u, isLoading, isError, error } = useQuery({
    queryKey: ["usage", range],
    queryFn: () => api.usage(range ? Number(range) : undefined),
    refetchInterval: 5000,
    refetchIntervalInBackground: true,
    placeholderData: prev => prev,
  });
  const comps = u ? comparators(u) : [];
  const sel = comps.find(c => c.id === pick) ?? comps[0];
  const t = u?.totals;

  return (
    <div className="min-h-full bg-canvas">
      <TopBar />

      <main className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-6">
        <Card title="Four experiences. Shared live telemetry." sub="This view preserves the slide ledger; shared totals count each physical call once.">
          <a href="http://localhost:8080/operator" className="font-bold text-accent">Open full-screen operator view and editable all-in cost scenarios ↗</a>
        </Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="flex items-center gap-2 text-[20px] font-extrabold tracking-tight"><BarChart3 className="size-5 text-accent" />Measured usage · Fury host</h1>
          <div className="flex rounded-lg border border-line bg-surface p-0.5" role="group" aria-label="Time range">
            {RANGES.map(([k, l]) => (
              <button key={k} onClick={() => setRange(k)} aria-pressed={range === k}
                className={cn("h-7 rounded-md px-2.5 text-xs font-semibold", range === k ? "bg-accent text-accent-ink" : "text-muted hover:text-ink")}>{l}</button>
            ))}
          </div>
        </div>
        {isLoading ? <div className="flex justify-center py-24 text-muted"><Spinner className="size-5" /></div>
          : isError || !u || !t || !sel ? <Empty icon={<BarChart3 className="size-5" />} title="Usage unavailable" body={(error as Error)?.message || "The server did not answer."} />
          : t.calls === 0 ? (
            <Card>
              <Empty icon={<BarChart3 className="size-5" />} title="No model calls yet"
                body={u.mock ? "The app is in mock mode, so no model runs and there is nothing to count. Start it without --mock to use the GB300."
                  : "Every call to the GB300 is logged here as it happens. Build a deck and watch this fill in."}
                action={<Link to="/" className="text-sm font-bold text-accent">Go to decks →</Link>} />
            </Card>
          ) : <>
            {/* the one headline number */}
            <Card>
              <div className="flex flex-wrap items-end justify-between gap-6">
                <div>
                  <div className="text-[13px] font-semibold text-muted">Example API spend for the same measured token volume</div>
                  <div className="mt-1 text-[56px] font-extrabold leading-none tracking-tight">{money(t.costs[sel.id] ?? 0)}</div>
                  <div className="mt-2 text-[14px] text-muted">
                    on <span className="font-semibold text-ink">{sel.name}</span> for {compact(t.total_tokens)} tokens across {t.calls.toLocaleString()} model calls
                    {t.decks ? ` and ${t.decks} deck${t.decks === 1 ? "" : "s"}` : ""}. <span className="font-semibold text-good">This is a pricing scenario, not net savings or equivalent model quality.</span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5" role="group" aria-label="Compare against">
                  {comps.map(c => (
                    <button key={c.id} onClick={() => setPick(c.id)}
                      className={cn("h-8 rounded-full border px-3 text-xs font-semibold",
                        sel.id === c.id ? "border-accent bg-accent text-accent-ink" : "border-line text-muted hover:text-ink")}>{c.name}</button>
                  ))}
                </div>
              </div>
            </Card>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Stat icon={<Cpu className="size-4" />} label="Tokens processed" value={compact(t.total_tokens)}
                detail={`${compact(t.prompt_tokens)} in · ${compact(t.completion_tokens)} out`} />
              <Stat icon={<ShieldCheck className="size-4" />} label="Inference location" value="Fury host"
                detail="Frankfurt browser access requires a working WAN link" />
              <Stat icon={<Zap className="size-4" />} label="Model calls" value={t.calls.toLocaleString()}
                detail={`${Math.round(t.seconds / 60).toLocaleString()} min of model time`} />
              <Stat icon={<Gauge className="size-4" />} label="Output speed" value={t.seconds ? `${Math.round(t.completion_tokens / t.seconds)} tok/s` : "—"}
                detail="Output tokens / request wall time, including queue wait" />
            </div>

            <div className="grid gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
              <Card title="Same measured token volume · scenario" sub={`Public list prices as of ${u.as_of}. Click a row to use it for the headline.`}>
                <CompareBars u={u} pick={sel.id} onPick={setPick} />
              </Card>
              <Card title="Cumulative scenario API spend" sub={`Running total on ${sel.name}`}>
                <Cumulative u={u} pick={sel.id} />
              </Card>
            </div>

            <Card title="Models in use" sub="Actual model calls on the Fury host. The shared author may also review its output; that is not independent assurance.">
              <Table align={["l", "l", "r", "r", "r", "r", "r", "r"]}
                head={["Model", "Role", "Calls", "Input", "Output", "Speed", "Median call", `On ${sel.name}`]}
                rows={u.models.map(m => [
                  <div key="m"><div className="font-semibold">{m.name}</div><div className="text-[11.5px] text-muted">{m.hf ? `${m.hf} · ` : ""}{m.model}</div></div>,
                  <div key="r" className="flex gap-1">{m.roles.map(r => <Badge key={r} tone={r === "review" ? "idle" : "busy"}>{r === "review" ? "Reviewer" : "Author"}</Badge>)}</div>,
                  m.calls.toLocaleString(), compact(m.prompt_tokens), compact(m.completion_tokens),
                  m.tok_s ? `${Math.round(m.tok_s)} tok/s` : "—", m.p50_s != null ? `${m.p50_s}s` : "—", money(m.costs[sel.id] ?? 0),
                ])} />
            </Card>

            <div className="grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
              <Card title="Per deck" sub="Selected-price scenarios for the same measured token volume">
                {u.decks.length === 0 ? <p className="text-[13px] text-muted">No deck work in this range.</p> : (
                  <Table align={["l", "r", "r", "r"]} head={["Deck", "Calls", "Tokens", `On ${sel.name}`]}
                    rows={u.decks.map(d => [
                      d.deleted ? <span key="d" className="text-muted">Deleted deck</span>
                        : <Link key="d" to={`/p/${d.project_id}`} className="font-semibold hover:text-accent">{d.title || "Untitled deck"}</Link>,
                      d.calls.toLocaleString(), compact(d.total_tokens), money(d.costs[sel.id] ?? 0),
                    ])} />
                )}
              </Card>
              <Card title="Where the tokens go" sub="By pipeline step">
                <Table align={["l", "r", "r"]} head={["Step", "Tokens", `On ${sel.name}`]}
                  rows={u.stages.map(s => [STAGES[s.stage] ?? s.stage, compact(s.total_tokens), money(s.costs[sel.id] ?? 0)])} />
              </Card>
            </div>

            <p className="px-1 text-[12px] leading-relaxed text-faint">
              Selected published high-capability text API scenario range, dated {u.as_of}. Tokenizers differ and model quality is not asserted equivalent.
              {" "}{t.cache_reported ? `${compact(t.cached_tokens)} local cached input tokens reported.` : "Local cached input usage is unknown; no estimated prefix count is shown as measured."}
              {" "}Local cache hits do not prove another provider would apply a billing discount. Default scenario rates treat cached input at the input rate.
              {" "}{u.unknown_usage_calls || 0} calls have unknown token usage and are excluded from measured token totals.
              {" "}Acquisition, amortization, electricity, hosting, network and operations belong in the separate editable operator scenario. Image economics are separate.
              {" "}<a href="http://localhost:8080/methodology" className="text-accent">Methodology and source prices ↗</a>.
            </p>
          </>}
      </main>
    </div>
  );
}
