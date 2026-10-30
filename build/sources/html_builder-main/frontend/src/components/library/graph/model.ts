import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import FA2Layout from "graphology-layout-forceatlas2/worker";
import type { NodeHoverDrawingFunction, NodeLabelDrawingFunction } from "sigma/rendering";
import type { GraphEdgeType, GraphNode, GraphNodeType, LibGraph } from "../../../lib/library";
import type { GraphColors } from "./theme";

export interface NodeAttrs {
  label: string; x: number; y: number; size: number;
  /** Not `type`: sigma reads that as the name of a node program. */
  kind: GraphNodeType; degree: number; forceLabel: boolean;
}
export interface EdgeAttrs { kind: GraphEdgeType; size: number }
export type LibGraphology = Graph<NodeAttrs, EdgeAttrs>;
type Point = { x: number; y: number };

/** Where every node last settled, across scope changes and visits to the tab — a refetch never reshuffles the map. */
const placed = new Map<string, Point>();

/** A stable pseudo-random number in [-1, 1) per string, so a first layout starts the same way every time. */
function seeded(s: string, salt: number): number {
  let h = 2166136261 ^ salt;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return ((h >>> 0) / 2 ** 32) * 2 - 1;
}

function sizeOf(n: GraphNode): number {
  const d = Math.max(0, n.degree);
  if (n.type === "slide") return 3.5;
  if (n.type === "project") return Math.min(26, 9 + 2.4 * Math.sqrt(d));
  return Math.min(18, 4.5 + 1.7 * Math.sqrt(d));
}

/** Hubs whose label is always drawn: every project, and the best-connected tags and mentions. */
const FORCED_HUBS = 30;

/** The API graph as graphology, reusing settled positions. `fresh` counts nodes that still need a place. */
export function buildGraph(data: LibGraph): { graph: LibGraphology; fresh: number } {
  const graph: LibGraphology = new Graph<NodeAttrs, EdgeAttrs>({ type: "undirected", multi: false, allowSelfLoops: false });
  const hubs = data.nodes.filter(n => n.type === "tag" || n.type === "entity").sort((a, b) => b.degree - a.degree);
  const forced = new Set(hubs.slice(0, FORCED_HUBS).map(n => n.id));
  const spread = Math.max(10, Math.sqrt(data.nodes.length) * 8);
  let fresh = 0;
  for (const n of data.nodes) {
    if (graph.hasNode(n.id)) continue;
    const at = placed.get(n.id);
    if (!at) fresh++;
    graph.addNode(n.id, {
      label: n.label || graphKeyLabel(n), kind: n.type, degree: n.degree, size: sizeOf(n),
      forceLabel: n.type === "project" || forced.has(n.id),
      x: at?.x ?? seeded(n.id, 1) * spread, y: at?.y ?? seeded(n.id, 2) * spread,
    });
  }
  for (const e of data.edges) {
    if (e.source === e.target || !graph.hasNode(e.source) || !graph.hasNode(e.target)) continue;
    graph.mergeEdge(e.source, e.target, { kind: e.type, size: 0.6 });
  }
  // A newcomer starts beside a neighbour that already has a place, so it slots in instead of flying across.
  if (fresh && fresh < graph.order) {
    graph.forEachNode(id => {
      if (placed.has(id)) return;
      const anchor = graph.neighbors(id).map(nb => placed.get(nb)).find(Boolean);
      if (anchor) graph.mergeNodeAttributes(id, { x: anchor.x + seeded(id, 3) * 2, y: anchor.y + seeded(id, 4) * 2 });
    });
  }
  return { graph, fresh };
}

const graphKeyLabel = (n: GraphNode) => n.id.replace(/^[spte]:/, "");

export function remember(graph: LibGraphology) {
  graph.forEachNode((id, a) => placed.set(id, { x: a.x, y: a.y }));
}

const reducedMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * ForceAtlas2: a short synchronous pass so the first frame is already shaped, then the web worker refines it
 * while the user watches (or, with reduced motion or no workers, the rest synchronously). Returns a cancel.
 */
export function runLayout(graph: LibGraphology, fresh: number, onDone: () => void): () => void {
  if (graph.order === 0) { onDone(); return () => {}; }
  if (fresh === 0) { onDone(); return () => {}; }
  const share = fresh / graph.order;
  const settings = {
    ...forceAtlas2.inferSettings(graph),
    barnesHutOptimize: graph.order > 300,
    adjustSizes: false,
    gravity: 1,
    scalingRatio: graph.order > 500 ? 8 : 4,
  };
  const big = graph.order > 1000;
  if (reducedMotion() || typeof Worker === "undefined") {
    forceAtlas2.assign(graph, { settings, iterations: Math.round((big ? 120 : 260) * Math.max(0.3, share)) });
    remember(graph);
    onDone();
    return () => {};
  }
  forceAtlas2.assign(graph, { settings, iterations: big ? 15 : 40 });
  let layout: FA2Layout<NodeAttrs, EdgeAttrs> | null = null;
  try {
    layout = new FA2Layout<NodeAttrs, EdgeAttrs>(graph, { settings });
    layout.start();
  } catch {
    // A blocked worker (strict CSP): finish synchronously instead.
    forceAtlas2.assign(graph, { settings, iterations: big ? 100 : 200 });
    remember(graph);
    onDone();
    return () => {};
  }
  const ms = Math.round(Math.min(5000, 1200 + graph.order * 1.6) * Math.max(0.35, share));
  const stop = () => {
    if (!layout) return;
    layout.kill();
    layout = null;
    remember(graph);
  };
  const t = window.setTimeout(() => { stop(); onDone(); }, ms);
  return () => { window.clearTimeout(t); stop(); };
}

/* ------------------------------------------------------------------ drawing */

const ellipsis = (s: string, max: number) => (s.length > max ? `${s.slice(0, max - 1).trimEnd()}…` : s);
const kindOf = (d: object): GraphNodeType | undefined => (d as { kind?: GraphNodeType }).kind;

/** Labels with a halo in the background colour, so they stay readable across edges. */
export function labelDrawer(c: GraphColors): NodeLabelDrawingFunction<NodeAttrs, EdgeAttrs> {
  return (ctx, data, settings) => {
    if (!data.label) return;
    const slide = kindOf(data) === "slide";
    const size = slide ? settings.labelSize - 1 : settings.labelSize;
    ctx.font = `${slide ? 500 : 700} ${size}px ${settings.labelFont}`;
    const text = ellipsis(data.label, slide ? 44 : 32);
    const x = data.x + data.size + 4, y = data.y + size / 3;
    ctx.lineJoin = "round";
    ctx.lineWidth = 3.5;
    ctx.strokeStyle = c.surface;
    ctx.strokeText(text, x, y);
    ctx.fillStyle = slide ? c.muted : c.ink;
    ctx.fillText(text, x, y);
  };
}

/** Hover / highlight: a ring in the node's colour and, for hubs, the label on a card. Slides get an HTML card instead. */
export function hoverDrawer(c: GraphColors): NodeHoverDrawingFunction<NodeAttrs, EdgeAttrs> {
  return (ctx, data, settings) => {
    const kind = kindOf(data);
    ctx.beginPath();
    ctx.arc(data.x, data.y, data.size + 3, 0, Math.PI * 2);
    ctx.lineWidth = 2;
    ctx.strokeStyle = data.color;
    ctx.stroke();
    if (kind === "slide" || !data.label) return;
    const size = settings.labelSize + 1;
    ctx.font = `700 ${size}px ${settings.labelFont}`;
    const text = ellipsis(data.label, 48);
    const w = ctx.measureText(text).width + 16, h = size + 12;
    const x = data.x + data.size + 6, y = data.y - h / 2;
    ctx.save();
    ctx.shadowColor = "rgba(0, 0, 0, 0.18)";
    ctx.shadowBlur = 10;
    ctx.shadowOffsetY = 2;
    ctx.beginPath();
    ctx.roundRect(x, y, w, h, 6);
    ctx.fillStyle = c.surface;
    ctx.fill();
    ctx.restore();
    ctx.lineWidth = 1;
    ctx.strokeStyle = c.line;
    ctx.stroke();
    ctx.fillStyle = c.ink;
    ctx.fillText(text, x + 8, data.y + size / 3);
  };
}
