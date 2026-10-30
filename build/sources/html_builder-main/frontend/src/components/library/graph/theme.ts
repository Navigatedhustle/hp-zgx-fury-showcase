import { useEffect, useState } from "react";
import type { GraphNodeType } from "../../../lib/library";

/** The app's tokens, read off `:root` — sigma draws on a canvas, so it needs real colours, not `var()`. */
export interface GraphColors {
  node: Record<GraphNodeType, string>;
  /** The same, faded towards the background: what everything outside a highlight turns into. */
  dim: Record<GraphNodeType, string>;
  edge: string; edgeDim: string; edgeHot: string;
  ink: string; muted: string; surface: string; canvas: string; line: string; accent: string;
}

type Rgb = [number, number, number];

function parse(c: string): Rgb | null {
  const s = c.trim();
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(s)?.[1];
  if (hex) {
    const h = hex.length === 3 ? [...hex].map(x => x + x).join("") : hex;
    return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)) as Rgb;
  }
  const rgb = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i.exec(s);
  return rgb ? [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])] : null;
}

/** `a` moved `t` of the way to `b` (opaque, so WebGL needs no blending to dim). */
export function mix(a: string, b: string, t: number): string {
  const x = parse(a), y = parse(b);
  if (!x || !y) return a;
  const c = x.map((v, i) => Math.round(v + ((y[i] ?? v) - v) * t));
  return `#${c.map(v => v.toString(16).padStart(2, "0")).join("")}`;
}

function read(): GraphColors {
  const cs = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback;
  const surface = v("--surface", "#ffffff");
  const dark = document.documentElement.classList.contains("dark");
  const node: Record<GraphNodeType, string> = {
    slide: v("--muted", "#5a6376"),
    project: v("--accent", "#024ad8"),
    tag: v("--good", "#0b8f5e"),
    entity: v("--warn", "#a8660a"),
  };
  const fade = dark ? 0.78 : 0.82;
  const line = v("--line", "#d9dee8");
  return {
    node,
    dim: {
      slide: mix(node.slide, surface, fade), project: mix(node.project, surface, fade),
      tag: mix(node.tag, surface, fade), entity: mix(node.entity, surface, fade),
    },
    edge: line,
    edgeDim: mix(line, surface, 0.6),
    edgeHot: v("--faint", "#8a93a6"),
    ink: v("--ink", "#0e1422"), muted: v("--muted", "#5a6376"), surface, canvas: v("--canvas", "#edf0f5"),
    line, accent: node.project,
  };
}

/** The graph's colours, re-read whenever the theme flips (the `dark` class on `<html>`). */
export function useGraphColors(): GraphColors {
  const [colors, setColors] = useState(read);
  useEffect(() => {
    const obs = new MutationObserver(() => setColors(read()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style", "data-theme"] });
    return () => obs.disconnect();
  }, []);
  return colors;
}

export const TYPE_LABEL: Record<GraphNodeType, string> = { slide: "Slides", project: "Projects", tag: "Tags", entity: "Mentions" };
export const TYPE_SINGULAR: Record<GraphNodeType, string> = { slide: "Slide", project: "Project", tag: "Tag", entity: "Mention" };
