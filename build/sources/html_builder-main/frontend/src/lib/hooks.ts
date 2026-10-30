import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api, type Lineage, type Project, type ProjectStatus, type Slide, type SlideStatus, type SlimProject, type Version, type VersionStatus } from "./api";
import { recount } from "./util";

/* ------------------------------------------------------------------ live events */

type ProjectEvent =
  | { type: "project"; status?: ProjectStatus; stage_note?: string; error?: string; deck_title?: string; renderer?: string }
  | { type: "slide"; slide_id: string; status?: SlideStatus; error?: string; approved_version_id?: string | null; included?: boolean }
  | { type: "version"; version_id: string; slide_id: string; lineage?: Lineage; status?: VersionStatus; stage_note?: string; score?: number | null }
  | { type: "slides" }
  /** The server's queue for this subscriber overflowed and dropped `dropped` events. Whatever is
   *  cached is stale by an unknown amount, so the only safe response is a full refetch. */
  | { type: "resync"; dropped?: number };

/** A version reaching one of these carries data (qa, notes, timestamps) the event doesn't. */
const NEEDS_FULL_FETCH: VersionStatus[] = ["ready", "failed", "cancelled"];

function parseEvent(data: string): ProjectEvent | null {
  try {
    const v: unknown = JSON.parse(data);
    if (v && typeof v === "object" && typeof (v as { type?: unknown }).type === "string") return v as ProjectEvent;
  } catch { /* malformed frame */ }
  return null;
}

function writeProject(qc: QueryClient, projectId: string, fn: (p: Project) => Project): boolean {
  const key = ["project", projectId];
  const cur = qc.getQueryData<Project>(key);
  if (!cur?.slides) return false; // nothing cached yet — the normal fetch will bring it
  qc.setQueryData(key, recount(fn(cur)));
  return true;
}

const mapSlide = (p: Project, id: string, fn: (s: Slide) => Slide): Project =>
  ({ ...p, slides: (p.slides ?? []).map(s => (s.id === id ? fn(s) : s)) });

/**
 * Apply an event to the cached project in place.
 * Returns true when the event is fully covered, false when a refetch is still required.
 */
function applyEvent(qc: QueryClient, projectId: string, ev: ProjectEvent): boolean {
  if (ev.type === "slides") return false;
  // An overflow sentinel: events were dropped, so no cache patch can be trusted — refetch everything.
  if (ev.type === "resync") return false;
  if (ev.type === "project") {
    // Scalars land immediately so the header never lags; `busy` and `counts`
    // still come from the server, so a status change also asks for a refetch.
    writeProject(qc, projectId, p => ({
      ...p,
      status: ev.status ?? p.status,
      stage_note: ev.stage_note ?? p.stage_note,
      error: ev.error ?? p.error,
      deck_title: ev.deck_title ?? p.deck_title,
      renderer: ev.renderer ?? p.renderer,
    }));
    return ev.status === undefined;
  }
  if (ev.type === "slide") {
    return writeProject(qc, projectId, p => mapSlide(p, ev.slide_id, s => ({
      ...s,
      status: ev.status ?? s.status,
      error: ev.error ?? s.error,
      approved_version_id: ev.approved_version_id !== undefined ? ev.approved_version_id : s.approved_version_id,
      included: ev.included ?? s.included,
    })));
  }
  // version
  const cur = qc.getQueryData<Project>(["project", projectId]);
  const known = cur?.slides?.some(s => s.versions.some(v => v.id === ev.version_id));
  if (!known) return false; // a brand-new version: only the full payload has it
  if (ev.status && NEEDS_FULL_FETCH.includes(ev.status)) return false;
  return writeProject(qc, projectId, p => mapSlide(p, ev.slide_id, s => ({
    ...s,
    versions: s.versions.map((v: Version) => (v.id === ev.version_id ? {
      ...v,
      status: ev.status ?? v.status,
      stage_note: ev.stage_note ?? v.stage_note,
      score: ev.score !== undefined ? ev.score : v.score,
    } : v)),
  })));
}

/**
 * Lay a slim payload over the cached full one.
 *
 * The slim route sends a strict subset of the full route's keys (a backend test enforces it), so
 * every level here is a plain spread: what slim omits — the spec's notes, the token ledger, the QA
 * detail, the parsed PowerPoint copy — is kept from the cached copy, which is still correct because
 * none of it can change without the version also changing status, and a status change already sends
 * the client back for the full payload.
 *
 * Returns null when the merge cannot be trusted: nothing cached yet, or the server knows about a
 * slide or version this client has never seen. Both mean "fetch the full thing instead".
 */
export function mergeSlim(cur: Project | undefined, slim: SlimProject): Project | null {
  if (!cur?.slides) return null;
  const slides = new Map(cur.slides.map(s => [s.id, s]));
  const merged: Slide[] = [];
  for (const s of slim.slides) {
    const was = slides.get(s.id);
    if (!was) return null;
    const versions = new Map(was.versions.map(v => [v.id, v]));
    const next: Version[] = [];
    for (const v of s.versions) {
      const prev = versions.get(v.id);
      if (!prev) return null;
      next.push({ ...prev, ...v, qa: { ...(prev.qa ?? {}), ...(v.qa ?? {}) } });
    }
    merged.push({ ...was, ...s, versions: next });
  }
  return { ...cur, ...slim, slim: false, slides: merged };
}

export interface ProjectLink {
  /** The SSE stream is open. */
  connected: boolean;
  /** It has been down long enough to be worth telling the user about. */
  reconnecting: boolean;
}

/**
 * Subscribe to server-sent progress for a project.
 * Most events are applied straight to the cached project; only events carrying
 * data the frame doesn't include (a new version, a finished one, a structural
 * change) trigger a debounced refetch of the full payload.
 */
export function useProjectEvents(projectId: string | undefined): ProjectLink {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    let es: EventSource | null = null;
    let retry: number | undefined;
    let deckTimer: number | undefined;
    let listTimer: number | undefined;

    // Ask for the slim payload and merge it in; fall back to a full invalidation when the merge
    // can't be trusted (nothing cached, an unseen slide or version, or the request failed). During
    // a generation this is the request the SSE stream fires dozens of times, and it is the reason
    // the slim route exists at all.
    const refetchProject = () => {
      window.clearTimeout(deckTimer);
      deckTimer = window.setTimeout(() => {
        const key = ["project", projectId];
        const full = () => qc.invalidateQueries({ queryKey: key });
        if (!qc.getQueryData<Project>(key)?.slides) { void full(); return; }
        api.projectSlim(projectId)
          .then(slim => {
            const next = mergeSlim(qc.getQueryData<Project>(key), slim);
            if (next) qc.setQueryData(key, recount(next));
            else void full();
          })
          .catch(() => void full());
      }, 250);
    };
    const refetchList = () => {
      window.clearTimeout(listTimer);
      listTimer = window.setTimeout(() => qc.invalidateQueries({ queryKey: ["projects"] }), 1500);
    };
    const onUpdate = (e: MessageEvent<string>) => {
      const ev = parseEvent(e.data);
      if (!ev || !applyEvent(qc, projectId, ev)) refetchProject();
      refetchList();
    };
    const open = () => {
      es = new EventSource(`/api/projects/${projectId}/events`);
      es.addEventListener("hello", () => { setConnected(true); refetchProject(); });
      es.addEventListener("update", onUpdate);
      es.onerror = () => {
        setConnected(false);
        es?.close();
        retry = window.setTimeout(open, 3000);
      };
    };
    open();
    return () => {
      es?.close();
      window.clearTimeout(retry);
      window.clearTimeout(deckTimer);
      window.clearTimeout(listTimer);
    };
  }, [projectId, qc]);

  // Grace period so a routine reconnect doesn't flash a warning at the user.
  useEffect(() => {
    const t = window.setTimeout(() => setReconnecting(!connected), connected ? 0 : 2000);
    return () => window.clearTimeout(t);
  }, [connected]);

  return { connected, reconnecting };
}

/* ------------------------------------------------------------------ misc */

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    // /api/health makes a live call to the GB300 over Tailscale, so poll rarely
    // and never while the tab is in the background.
    refetchInterval: 120_000,
    refetchIntervalInBackground: false,
    staleTime: 60_000,
    retry: false,
  });
}

export function useTheme(): [string, (t: "light" | "dark" | "system") => void] {
  const [theme, setTheme] = useState<string>(() => {
    try { return localStorage.getItem("theme") || "dark"; } catch { return "dark"; }
  });
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => document.documentElement.classList.toggle("dark", theme === "dark" || (theme === "system" && mq.matches));
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);
  return [theme, (t) => { setTheme(t); try { localStorage.setItem("theme", t); } catch { /* ignore */ } }];
}

/**
 * Window-level keyboard shortcut. The handler is held in a ref, so it always
 * sees fresh props without a hand-maintained dependency array.
 */
export function useKey(handler: (e: KeyboardEvent) => void) {
  const latest = useRef(handler);
  useEffect(() => { latest.current = handler; });
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      latest.current(e);
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);
}

/** Shortcuts the deck runtime may hand back to the builder. */
const FORWARDED = new Set(["j", "J", "k", "K", "1", "2", "o", "O", "c", "C", "?"]);

/**
 * Keyboard focus inside a preview iframe would otherwise swallow the builder's
 * shortcuts. The deck runtime forwards the keys it doesn't use as
 * `{type:"hpdeck", event:"key", key, code, shiftKey, ctrlKey, metaKey, altKey}`;
 * they are re-dispatched here so `useKey` handlers see them unchanged.
 */
export function useFrameKeys() {
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.origin !== window.location.origin || !e.source || e.source === window) return;
      const d = e.data as Record<string, unknown> | null;
      if (!d || d.type !== "hpdeck" || d.event !== "key" || typeof d.key !== "string") return;
      if (d.ctrlKey || d.metaKey || d.altKey) return;
      if (!FORWARDED.has(d.key)) return;
      window.dispatchEvent(new KeyboardEvent("keydown", {
        key: d.key,
        code: typeof d.code === "string" ? d.code : "",
        shiftKey: !!d.shiftKey,
        bubbles: true,
        cancelable: true,
      }));
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, []);
}
