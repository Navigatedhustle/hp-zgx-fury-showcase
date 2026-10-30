import { SigmaContainer, useRegisterEvents, useSetSettings, useSigma } from "@react-sigma/core";
import { useEffect } from "react";
import type { Settings } from "sigma/settings";
import type { EdgeDisplayData, NodeDisplayData } from "sigma/types";
import type { GraphNodeType } from "../../../lib/library";
import { hoverDrawer, labelDrawer, runLayout, type EdgeAttrs, type LibGraphology, type NodeAttrs } from "./model";
import type { GraphColors } from "./theme";

export interface CanvasApi {
  zoomIn: () => void; zoomOut: () => void; reset: () => void;
  /** Move the camera so these nodes fill the view. */
  fit: (ids: string[]) => void;
}
export interface Hover { id: string; x: number; y: number }

/** Fixed for the container's life: SigmaContainer rebuilds sigma when this changes, so live changes go through setSettings. */
const SETTINGS: Partial<Settings<NodeAttrs, EdgeAttrs>> = {
  allowInvalidContainer: true,
  renderEdgeLabels: false,
  zIndex: true,
  labelFont: "Archivo, ui-sans-serif, system-ui, 'Segoe UI', sans-serif",
  labelSize: 12,
  labelWeight: "600",
  labelDensity: 0.5,
  labelGridCellSize: 110,
  // Slides (size 3.5) get labels once zoomed in a few steps; hubs much sooner.
  labelRenderedSizeThreshold: 8,
  minCameraRatio: 0.02,
  maxCameraRatio: 4,
  stagePadding: 36,
};

const motion = () => (typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 450);

interface Props {
  graph: LibGraphology; fresh: number; colors: GraphColors; hidden: ReadonlySet<GraphNodeType>;
  /** Highlighted neighbourhood: the hovered node wins over the focused one. */
  focus: string | null; hovered: string | null;
  /** While typing in search: the matches stay lit, the rest dims. */
  matches: ReadonlySet<string> | null;
  onHover: (h: Hover | null) => void; onClickNode: (id: string) => void; onClickStage: () => void;
  onApi: (api: CanvasApi | null) => void; onLayout: (running: boolean) => void;
}

export function GraphCanvas(props: Props) {
  return (
    <SigmaContainer<NodeAttrs, EdgeAttrs> graph={props.graph} settings={SETTINGS}
      className="!absolute inset-0 [&>.sigma-container]:size-full" style={{ position: "absolute", inset: 0, background: "transparent" }}>
      <Controller {...props} />
    </SigmaContainer>
  );
}

function Controller({ graph, fresh, colors, hidden, focus, hovered, matches, onHover, onClickNode, onClickStage, onApi, onLayout }: Props) {
  const sigma = useSigma<NodeAttrs, EdgeAttrs>();
  const register = useRegisterEvents<NodeAttrs, EdgeAttrs>();
  const setSettings = useSetSettings<NodeAttrs, EdgeAttrs>();

  useEffect(() => {
    register({
      enterNode: e => onHover({ id: e.node, x: e.event.x, y: e.event.y }),
      leaveNode: () => onHover(null),
      clickNode: e => onClickNode(e.node),
      clickStage: () => onClickStage(),
    });
  }, [register, onHover, onClickNode, onClickStage]);

  useEffect(() => {
    onLayout(true);
    const cancel = runLayout(graph, fresh, () => onLayout(false));
    return () => { cancel(); onLayout(false); };
  }, [graph, fresh, onLayout]);

  useEffect(() => {
    setSettings({ defaultDrawNodeLabel: labelDrawer(colors), defaultDrawNodeHover: hoverDrawer(colors) });
  }, [setSettings, colors]);

  useEffect(() => {
    const active = hovered ?? focus;
    let lit: Set<string> | null = null;
    if (active && graph.hasNode(active)) {
      lit = new Set([active]);
      graph.forEachNeighbor(active, nb => lit?.add(nb));
    }
    // A big neighbourhood would bury the map in slide titles: label its slides only when it is small.
    const labelSlides = !!lit && lit.size <= 24;
    const kindOf = (id: string) => graph.getNodeAttribute(id, "kind");
    setSettings({
      nodeReducer: (node, d) => {
        const res: Partial<NodeDisplayData> & Partial<NodeAttrs> = { ...d, color: colors.node[d.kind] };
        if (hidden.has(d.kind)) return { ...res, hidden: true };
        if (lit) {
          if (node === active) return { ...res, highlighted: true, forceLabel: true, zIndex: 3 };
          if (lit.has(node)) return { ...res, forceLabel: d.kind !== "slide" || labelSlides, zIndex: 2 };
          return { ...res, color: colors.dim[d.kind], label: "", forceLabel: false, zIndex: 0 };
        }
        if (matches) {
          if (matches.has(node)) return { ...res, forceLabel: true, zIndex: 2 };
          return { ...res, color: colors.dim[d.kind], label: "", forceLabel: false, zIndex: 0 };
        }
        return { ...res, zIndex: d.kind === "slide" ? 0 : 1 };
      },
      edgeReducer: (edge, d) => {
        const [s, t] = graph.extremities(edge);
        const res: Partial<EdgeDisplayData> = { ...d, color: colors.edge };
        if (hidden.has(kindOf(s)) || hidden.has(kindOf(t))) return { ...res, hidden: true };
        if (lit && active) {
          if (s === active || t === active) {
            const hub = kindOf(s) === "slide" ? t : s;
            return { ...res, color: colors.node[kindOf(hub)], size: 1.4, zIndex: 1 };
          }
          return { ...res, color: colors.edgeDim, zIndex: 0 };
        }
        if (matches) return { ...res, color: matches.has(s) || matches.has(t) ? colors.edgeHot : colors.edgeDim };
        return res;
      },
    });
  }, [setSettings, graph, colors, hidden, focus, hovered, matches]);

  useEffect(() => {
    const cam = sigma.getCamera();
    onApi({
      zoomIn: () => void cam.animatedZoom({ duration: motion() / 2 }),
      zoomOut: () => void cam.animatedUnzoom({ duration: motion() / 2 }),
      reset: () => void cam.animatedReset({ duration: motion() }),
      fit: ids => {
        const pts = ids.map(id => sigma.getNodeDisplayData(id)).filter((p): p is NodeDisplayData => !!p && !p.hidden);
        if (!pts.length) return;
        const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
        const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
        const ratio = pts.length === 1 ? Math.min(cam.ratio, 0.3) : Math.max(0.06, Math.min(1.1, Math.max(x1 - x0, y1 - y0) * 1.35));
        void cam.animate({ x: (x0 + x1) / 2, y: (y0 + y1) / 2, ratio }, { duration: motion() });
      },
    });
    return () => onApi(null);
  }, [sigma, onApi]);

  return null;
}
