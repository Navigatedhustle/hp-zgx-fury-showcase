import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CircleStop, WifiOff } from "lucide-react";
import { Suspense, lazy } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { TopBar } from "../components/AppShell";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { ShortcutsButton } from "../components/Shortcuts";
import { Badge, Button, Empty, IconButton, Spinner, Tip, type Tone } from "../components/ui";
import { api, type Project } from "../lib/api";
import { useFrameKeys, useProjectEvents } from "../lib/hooks";
import { cn, hasWorkInFlight, projectStatusText } from "../lib/util";

const WriteView = lazy(() => import("./WriteView"));
const PlanView = lazy(() => import("./PlanView"));
const ReviewView = lazy(() => import("./ReviewView"));
const ExportView = lazy(() => import("./ExportView"));

const tone = (p: Project): Tone =>
  p.status === "error" ? "bad" : p.status === "complete" ? "good" : p.status === "reviewing" ? "warn" : p.status === "ready" ? "idle" : "busy";

function ViewLoading() {
  return <div className="flex h-full items-center justify-center text-muted"><Spinner className="size-5" /></div>;
}

export default function ProjectPage() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const loc = useLocation();
  const qc = useQueryClient();
  const link = useProjectEvents(id);
  useFrameKeys();
  const { data: p, isLoading, isError, error } = useQuery({
    // Always the full payload. The cheap slim one belongs to the SSE-driven refetch
    // (`useProjectEvents`), which knows what it already has; this query is both the first load and
    // the answer to every `invalidateQueries` after a mutation, so it has to be the whole truth.
    queryKey: ["project", id], queryFn: () => api.project(id),
    // Poll whenever anything is still being produced. Project status alone is
    // not enough: a revise leaves the project in `reviewing`, which would drop
    // the fallback exactly when a lost SSE stream matters most. Full on purpose,
    // for the same reason: this interval exists for when events were missed.
    refetchInterval: q => (hasWorkInFlight(q.state.data) ? 4000 : false),
  });
  const cancel = useMutation({
    mutationFn: () => api.cancel(id),
    onSuccess: r => { toast.success(r.cancelled ? "Stopped. Finished designs are kept." : "Nothing was running"); qc.invalidateQueries({ queryKey: ["project", id] }); },
  });

  if (isError) {
    return (
      <div className="min-h-full"><TopBar />
        <Empty icon={<ArrowLeft className="size-5" />} title="Couldn't open this project" body={(error as Error).message}
          action={<Button onClick={() => nav("/")}>Back to your decks</Button>} />
      </div>
    );
  }

  const c = p?.counts;
  const busy = !!p && (p.busy || ["composing", "ingesting", "planning", "generating"].includes(p.status) || (c?.generating ?? 0) > 0);
  const imported = !!p && !["uploaded", "composing", "ingesting", "planning"].includes(p.status);
  const hasDesigns = !!p?.slides?.some(s => s.versions.length > 0);
  // A composed deck gains a step in front: its content is written here rather than extracted.
  const composed = p?.source === "composed";
  const tabs = [
    ...(composed ? [{ to: "write", label: "Write", enabled: true, count: c ? `${c.slides} slides` : "" }] : []),
    { to: "plan", label: "Plan", enabled: !composed || !!p?.slides?.some(s => s.plan?.pattern), count: c ? `${c.included} slides` : "" },
    { to: "review", label: "Review", enabled: imported && hasDesigns, count: c && hasDesigns ? `${c.approved}/${c.included} approved` : "" },
    { to: "export", label: "Export", enabled: imported && hasDesigns, count: "" },
  ];
  const navClass = ({ isActive }: { isActive: boolean }) => cn(
    "flex h-8 items-center gap-2 whitespace-nowrap rounded-lg px-3 text-sm font-semibold transition-colors",
    isActive ? "bg-ink text-canvas" : "text-muted hover:text-ink");

  return (
    <div className="flex h-full flex-col">
      <TopBar>
        <span className="h-5 w-px bg-line" />
        <IconButton label="All decks" onClick={() => nav("/")}><ArrowLeft className="size-4" /></IconButton>
        {isLoading || !p ? <div className="shimmer-light h-5 w-48 rounded" /> : (
          <div className="flex min-w-0 items-center gap-3">
            <h1 className="truncate text-[15px] font-bold">{p.deck_title || p.name}</h1>
            {/* Idle, the status only repeats what the steps show, so on narrow screens the title gets the room;
                while work runs it carries live progress and always stays. */}
            <span className={cn("shrink-0", !busy && "hidden lg:inline-flex")}>
              <Badge tone={tone(p)} pulse={busy}>{p.stage_note && busy ? p.stage_note : projectStatusText[p.status]}</Badge>
            </span>
            {link.reconnecting && (
              <Tip label="Lost the live progress connection. Retrying every few seconds; the page keeps refreshing in the meantime.">
                <span><Badge tone="warn" pulse><WifiOff className="size-3" />Reconnecting…</Badge></span>
              </Tip>
            )}
          </div>
        )}
        <nav className="ml-auto hidden shrink-0 items-center gap-1 rounded-xl border border-line bg-surface p-1 md:flex" aria-label="Project steps">
          {tabs.map((t, i) => t.enabled ? (
            <NavLink key={t.to} to={t.to} className={navClass}>
              <span className="text-xs opacity-60">{i + 1}</span>{t.label}
              {t.count && <span className="hidden text-xs font-medium opacity-70 xl:inline">{t.count}</span>}
            </NavLink>
          ) : (
            <span key={t.to} className="flex h-8 cursor-not-allowed items-center gap-2 whitespace-nowrap rounded-lg px-3 text-sm font-semibold text-faint" title="Available after slides are designed">
              <span className="text-xs opacity-60">{i + 1}</span>{t.label}
            </span>
          ))}
        </nav>
        <ShortcutsButton />
        {busy && !["ingesting", "planning", "composing"].includes(p?.status ?? "") && (
          <Button size="sm" variant="ghost" icon={<CircleStop className="size-4" />} loading={cancel.isPending} onClick={() => cancel.mutate()}>Stop</Button>
        )}
      </TopBar>
      {/* Compact step nav for narrow windows, where the bar above is hidden. */}
      <nav className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-line bg-surface px-3 py-1.5 md:hidden" aria-label="Project steps">
        {tabs.map((t, i) => t.enabled ? (
          <NavLink key={t.to} to={t.to} className={navClass}>
            <span className="text-xs opacity-60">{i + 1}</span>{t.label}
          </NavLink>
        ) : (
          <span key={t.to} className="flex h-8 cursor-not-allowed items-center gap-2 rounded-lg px-3 text-sm font-semibold text-faint">
            <span className="text-xs opacity-60">{i + 1}</span>{t.label}
          </span>
        ))}
      </nav>
      <div className="min-h-0 flex-1">
        {p && (
          <ErrorBoundary resetKey={loc.pathname}>
            <Suspense fallback={<ViewLoading />}>
              <Routes>
                <Route path="write" element={composed ? <WriteView project={p} /> : <Navigate to="../plan" replace />} />
                <Route path="plan" element={<PlanView project={p} />} />
                <Route path="review" element={<ReviewView project={p} />} />
                <Route path="export" element={<ExportView project={p} />} />
                <Route path="*" element={<Navigate to={composed && !p.slides?.some(s => s.plan?.pattern) ? "write" : "plan"} replace />} />
              </Routes>
            </Suspense>
          </ErrorBoundary>
        )}
      </div>
    </div>
  );
}
