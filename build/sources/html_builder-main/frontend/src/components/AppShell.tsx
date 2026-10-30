import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { BarChart3, Library, Monitor, Moon, Sun } from "lucide-react";
import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import { useHealth, useTheme } from "../lib/hooks";
import { cn } from "../lib/util";
import { Tip } from "./ui";

export function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5 rounded-md" aria-label="Deck Builder home">
      <img src="/showcase-assets/hp.svg" className="size-9 bg-white p-1.5 rounded-sm" alt="HP" />
      <span className="text-[15px] font-bold tracking-tight">Presentation Creator</span>
    </Link>
  );
}

function ModelStatus() {
  const { data, isError, isLoading } = useHealth();
  const llm = data?.llm;
  const review = data?.review;
  const split = !!data?.split;
  // With two servers the banner is only green when both answer: a deck can be authored without the critic,
  // but it ships unreviewed, and that is worth seeing before the run rather than in the QA report after it.
  const ok = !!llm?.ok && (!split || !!review?.ok);
  const half = !!llm?.ok && split && !review?.ok;
  const label = isLoading ? "Checking model…" : isError ? "Server offline"
    : llm?.mock ? "Offline mock model" : half ? "Critic unreachable" : ok ? "GB300 connected" : "GB300 unreachable";
  const line = (e: typeof llm) =>
    `${e?.model}${e?.max_model_len ? ` · ${Math.round(e.max_model_len / 1000)}k context` : ""}`;
  const detail = isError
    ? "The Deck Builder server isn't responding. Start it with run.ps1."
    : llm?.mock
      ? "LLM_MOCK is on: slides are built from templates, not by the model."
      : half
        ? `Authoring on ${llm?.model} is up, but the review model at ${review?.base_url} is not — ${review?.error || "no response"}. Slides will generate without a critic or an A/B verdict.`
        : ok
          ? split
            ? `Author ${line(llm)} · Review ${line(review)}${review?.vision ? " · vision on" : " · text only"}`
            : `${line(llm)}${review?.vision ? " · vision on" : " · text only"}`
          : `${llm?.base_url} — ${llm?.error || "no response"}. Check Tailscale, then retry.`;
  const dot = isLoading ? "bg-faint" : isError || !llm?.ok ? "bg-bad" : llm?.mock || half ? "bg-warn" : "bg-good";
  return (
    <Tip label={detail} side="bottom">
      {/* Below xl the project steps need the room: the badge shrinks to its dot, the words stay in the tooltip. */}
      <div role="status" aria-label={label}
        className="flex h-8 shrink-0 items-center gap-2 rounded-lg border border-line bg-surface px-2.5 text-xs font-semibold text-muted xl:px-3">
        <span className={cn("size-2 rounded-full", dot)} />
        <span className="hidden whitespace-nowrap xl:inline">{label}</span>
      </div>
    </Tip>
  );
}

function ThemeMenu() {
  const [theme, setTheme] = useTheme();
  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;
  return (
    <Dropdown.Root>
      <Dropdown.Trigger aria-label="Theme" className="flex size-8 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink">
        <Icon className="size-4" />
      </Dropdown.Trigger>
      <Dropdown.Portal>
        <Dropdown.Content align="end" sideOffset={6} className="z-50 min-w-36 rounded-xl border border-line bg-surface p-1 shadow-card">
          {([["light", "Light", Sun], ["dark", "Dark", Moon], ["system", "Match system", Monitor]] as const).map(([k, l, I]) => (
            <Dropdown.Item key={k} onSelect={() => setTheme(k)}
              className={cn("flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-sm outline-none data-[highlighted]:bg-surface-2", theme === k && "font-semibold text-accent")}>
              <I className="size-4" />{l}
            </Dropdown.Item>
          ))}
        </Dropdown.Content>
      </Dropdown.Portal>
    </Dropdown.Root>
  );
}

export function TopBar({ children }: { children?: ReactNode }) {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-canvas/90 backdrop-blur">
      <div className="flex h-14 items-center gap-4 px-4 sm:px-6">
        <a href="http://localhost:8080" className="text-xs text-accent">← All experiences</a><Logo />
        <div className="flex min-w-0 flex-1 items-center gap-3">{children}</div>
        <ModelStatus />
        <NavLink to="/library" aria-label="Slide library" className={({ isActive }) => cn("flex h-8 shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-semibold hover:bg-surface-2 hover:text-ink",
          isActive ? "bg-surface-2 text-ink" : "text-muted")}>
          <Library className="size-4" /><span className="hidden lg:inline">Library</span>
        </NavLink>
        <Tip label="Usage and scenario costs" side="bottom">
          <Link to="/dashboard" aria-label="Usage and scenario costs" target="_blank" rel="noopener"
            className="flex size-8 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink">
            <BarChart3 className="size-4" />
          </Link>
        </Tip>
        <ThemeMenu />
      </div>
    </header>
  );
}
