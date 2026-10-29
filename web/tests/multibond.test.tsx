/**
 * W-MB1 (plan 7.4): the 2-stroke planar / 3-stroke spatial bundle.
 *
 * The pure geometry is tested without a DOM (stroke count, offset side and
 * length, miters, the causal bar). The edge renderer is rendered with the
 * xyflow provider so the label layer, and with it the frame pill, exists; the
 * canvas-level behaviour (adopted domains and frames from `model.check`) is
 * covered by the Playwright `multibond` spec against the fake worker.
 */

import { render } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { ReactFlowProvider, Position, useStoreApi } from "@xyflow/react";
import { useEffect, useRef, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import type { DomainName } from "../src/contracts/catalog";
import type { Catalog } from "../src/contracts/catalog";
import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Model } from "../src/contracts/model";
import { useDiagnosticsStore, resetDiagnosticsStore } from "../src/diagnostics/store";
import { buildDiagram, type DiagramFlow } from "../src/editor/buildFlow";
import type { ConnectionVisual } from "../src/editor/connectionAnalysis";
import { decorateFlow } from "../src/editor/edges/decorateFlow";
import type { EditorEdgeData } from "../src/editor/edges/EditorEdges";
import {
  BondEdge,
  FRAME_BADGE_OFFSET,
  MultiBond,
  frameBadgePosition,
} from "../src/editor/edges/EditorEdges";
import {
  bundleCausalBar,
  midpoint,
  multibondBundleHalf,
  multibondComponents,
  multibondOffsets,
  multibondPath,
  multibondStrokes,
  offsetPolyline,
  type Point,
} from "../src/editor/geometry";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import {
  createConnection,
  createEmptyModel,
  createNodeFromBlock,
} from "../src/state/modelFactory";

function pathLength(points: readonly Point[]): number {
  let total = 0;
  for (let index = 1; index < points.length; index += 1) {
    const from = points[index - 1];
    const to = points[index];
    if (from === undefined || to === undefined) {
      continue;
    }
    total += Math.hypot(to.x - from.x, to.y - from.y);
  }
  return total;
}

function distanceToLine(point: Point, from: Point, to: Point): number {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.hypot(dx, dy);
  return Math.abs(dx * (from.y - point.y) - (from.x - point.x) * dy) / length;
}

describe("multibond stroke count", () => {
  it("is the model dimension: Planar two, Spatial three, scalar one", () => {
    expect(multibondStrokes("Planar")).toBe(2);
    expect(multibondStrokes("Spatial")).toBe(3);
    for (const domain of [
      "Electrical",
      "Translation",
      "Rotation",
      "Hydraulic",
      "Generic",
    ] as const) {
      expect(multibondStrokes(domain), domain).toBe(1);
    }
    expect(multibondStrokes(null)).toBe(1);
    expect(multibondStrokes("Rotational")).toBe(1);
    // The count is not the port size: Planar has 3 components, Spatial 6.
    expect(multibondComponents("Planar")).toBe(3);
    expect(multibondComponents("Spatial")).toBe(6);
    expect(multibondComponents("Electrical")).toBe(1);
  });

  it("spaces the strokes as plan 7.2 says", () => {
    expect(multibondOffsets(2)).toEqual([-2.1, 2.1]);
    expect(multibondOffsets(3)).toEqual([-4.2, 0, 4.2]);
    expect(multibondOffsets(1)).toEqual([0]);
    expect(multibondBundleHalf(2)).toBeCloseTo(2.1 + 0.75, 12);
    expect(multibondBundleHalf(3)).toBeCloseTo(4.2 + 0.75, 12);
  });

  it("spaces the D=6 Spatial bundle at [-gap, 0, +gap] and leaves D=3 at two strokes", () => {
    // Spatial has six components but three strokes, at the full gap.
    expect(multibondStrokes("Spatial")).toBe(3);
    expect(multibondComponents("Spatial")).toBe(6);
    expect(multibondOffsets(multibondStrokes("Spatial"))).toEqual([-4.2, 0, 4.2]);
    expect(multibondBundleHalf(3)).toBeCloseTo(4.95, 12);

    // Planar has three components and still draws two strokes, half a gap out.
    expect(multibondStrokes("Planar")).toBe(2);
    expect(multibondComponents("Planar")).toBe(3);
    expect(multibondOffsets(multibondStrokes("Planar"))).toEqual([-2.1, 2.1]);
    expect(multibondBundleHalf(2)).toBeCloseTo(2.85, 12);
  });
});

describe("offsetPolyline", () => {
  it("offsets a horizontal segment to the left of travel and keeps its length", () => {
    const offset = offsetPolyline(
      [
        { x: 0, y: 0 },
        { x: 100, y: 0 },
      ],
      4.2,
    );
    expect(offset).toHaveLength(2);
    expect(offset[0]?.x).toBeCloseTo(0, 12);
    expect(offset[0]?.y).toBeCloseTo(-4.2, 12);
    expect(offset[1]?.x).toBeCloseTo(100, 12);
    expect(offset[1]?.y).toBeCloseTo(-4.2, 12);
    expect(Math.abs(pathLength(offset) - 100)).toBeLessThan(1e-6);
  });

  it("offsets a vertical segment to the left of travel and keeps its length", () => {
    const offset = offsetPolyline(
      [
        { x: 0, y: 0 },
        { x: 0, y: 100 },
      ],
      4.2,
    );
    expect(offset[0]?.x).toBeCloseTo(4.2, 12);
    expect(offset[0]?.y).toBeCloseTo(0, 12);
    expect(offset[1]?.x).toBeCloseTo(4.2, 12);
    expect(offset[1]?.y).toBeCloseTo(100, 12);
    expect(Math.abs(pathLength(offset) - 100)).toBeLessThan(1e-6);

    const right = offsetPolyline(
      [
        { x: 0, y: 0 },
        { x: 0, y: 100 },
      ],
      -4.2,
    );
    expect(right[0]?.x).toBeCloseTo(-4.2, 12);
  });

  it("preserves the length of a straight polyline with a collinear waypoint", () => {
    const offset = offsetPolyline(
      [
        { x: 0, y: 0 },
        { x: 40, y: 0 },
        { x: 100, y: 0 },
      ],
      -3,
    );
    expect(offset.map((point) => point.y)).toEqual([3, 3, 3]);
    expect(Math.abs(pathLength(offset) - 100)).toBeLessThan(1e-6);
  });

  it("miters a 90 degree waypoint on the average normal", () => {
    const corner = { x: 100, y: 0 };
    const offset = offsetPolyline(
      [
        { x: 0, y: 0 },
        corner,
        { x: 100, y: 100 },
      ],
      4.2,
    );
    expect(offset).toHaveLength(3);
    const miter = offset[1];
    expect(miter).toBeDefined();
    // The intersection of y = -4.2 and x = 100 + 4.2.
    expect(miter?.x).toBeCloseTo(104.2, 9);
    expect(miter?.y).toBeCloseTo(-4.2, 9);
    expect(Math.hypot((miter?.x ?? 0) - corner.x, (miter?.y ?? 0) - corner.y)).toBeCloseTo(
      4.2 * Math.SQRT2,
      9,
    );
    // Both offset lines are at exactly the requested distance.
    expect(distanceToLine(miter!, { x: 0, y: 0 }, corner)).toBeCloseTo(4.2, 9);
    expect(distanceToLine(miter!, corner, { x: 100, y: 100 })).toBeCloseTo(4.2, 9);
  });

  it("miters a 135 degree waypoint without a spike", () => {
    const diagonal = Math.SQRT1_2;
    const corner = { x: 100, y: 0 };
    const next = { x: 100 + diagonal * 60, y: diagonal * 60 };
    const offset = offsetPolyline([{ x: 0, y: 0 }, corner, next], 4.2);
    const miter = offset[1];
    expect(miter).toBeDefined();
    expect(miter?.y).toBeCloseTo(-4.2, 9);
    // Half the 45 degree turn: the miter is d / cos(22.5 degrees).
    expect(miter?.x).toBeCloseTo(100 + 4.2 * Math.tan(Math.PI / 8), 9);
    expect(Math.hypot((miter?.x ?? 0) - corner.x, (miter?.y ?? 0) - corner.y)).toBeCloseTo(
      4.2 / Math.cos(Math.PI / 8),
      9,
    );
    expect(distanceToLine(miter!, corner, next)).toBeCloseTo(4.2, 9);
  });

  it("clamps the miter at a hairpin", () => {
    const corner = { x: 100, y: 0 };
    const offset = offsetPolyline(
      [
        { x: 0, y: 0 },
        corner,
        { x: 0.01, y: 0.02 },
      ],
      4.2,
    );
    const miter = offset[1];
    expect(miter).toBeDefined();
    expect(
      Math.hypot((miter?.x ?? 0) - corner.x, (miter?.y ?? 0) - corner.y),
    ).toBeLessThanOrEqual(4 * 4.2 + 1e-9);
  });

  it("stays finite for a zero-length or degenerate polyline", () => {
    const repeated = offsetPolyline(
      [
        { x: 5, y: 5 },
        { x: 5, y: 5 },
      ],
      4.2,
    );
    expect(repeated).toEqual([{ x: 5, y: 5 }]);
    expect(offsetPolyline([], 4.2)).toEqual([]);
    expect(offsetPolyline([{ x: Number.NaN, y: 0 }], 4.2)).toEqual([]);
    const single = offsetPolyline([{ x: 2, y: 3 }], 4.2);
    expect(single).toEqual([{ x: 2, y: 3 }]);
    for (const point of [...repeated, ...single]) {
      expect(Number.isFinite(point.x)).toBe(true);
      expect(Number.isFinite(point.y)).toBe(true);
    }
  });
});

describe("multibondPath and the bundle causal bar", () => {
  it("builds a polyline through the offset points", () => {
    expect(
      multibondPath(
        [
          { x: 0, y: 0 },
          { x: 100, y: 0 },
        ],
        0,
      ),
    ).toBe("M 0 0 L 100 0");
    expect(
      multibondPath(
        [
          { x: 0, y: 0 },
          { x: 100, y: 0 },
        ],
        2,
      ),
    ).toBe("M 0 -2 L 100 -2");
  });

  it("spans the whole bundle and stays perpendicular to the bond", () => {
    const bar = bundleCausalBar({ x: 0, y: 0 }, { x: 100, y: 0 }, 4.95);
    expect(bar.x1).toBeCloseTo(100, 12);
    expect(bar.y1).toBeCloseTo(7.95, 12);
    expect(bar.x2).toBeCloseTo(100, 12);
    expect(bar.y2).toBeCloseTo(-7.95, 12);
    const span = Math.hypot(bar.x2 - bar.x1, bar.y2 - bar.y1);
    expect(span).toBeCloseTo(2 * (4.95 + 3), 12);
    // The bond runs along +x, so the bar's direction has no x component.
    expect(bar.x2 - bar.x1).toBeCloseTo(0, 12);
  });
});

// ----------------------------------------------------------------- rendering

const HORIZONTAL: EditorEdgeData = {
  kind: "bond",
  domain: "Planar",
  baseDomain: "Planar",
  signalType: null,
  route: [],
  sourceAnchor: { point: { x: 0, y: 0 }, side: "right" },
  targetAnchor: { point: { x: 200, y: 0 }, side: "left" },
  wireHub: null,
  label: "p",
  unitFactor: null,
  causalStroke: "to",
  frame: null,
  missingPorts: [],
  snap: true,
};

function edgeData(overrides: Partial<EditorEdgeData> = {}): EditorEdgeData {
  return { ...HORIZONTAL, ...overrides };
}

/**
 * A minimal root that gives `EdgeLabelRenderer` a `.react-flow__edgelabel-renderer`
 * to portal into. Without it xyflow drops the label layer in jsdom.
 */
function LabelLayer({ children }: { children: ReactNode }) {
  const store = useStoreApi();
  const root = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (root.current !== null) {
      store.setState({ domNode: root.current });
    }
  }, [store]);
  return (
    <div className="react-flow" ref={root}>
      <div className="react-flow__edgelabel-renderer" />
      <svg>{children}</svg>
    </div>
  );
}

function renderEdge(edge: ReactNode) {
  return render(
    <ReactFlowProvider>
      <LabelLayer>{edge}</LabelLayer>
    </ReactFlowProvider>,
  );
}

function domainOf(domain: DomainName): EditorEdgeData {
  return edgeData({ domain, baseDomain: domain });
}

describe("the multibond edge renderer", () => {
  it("draws two stroke paths, one causal bar and the accessible label", () => {
    const { container } = renderEdge(
      <MultiBond id="c1" data={edgeData()} selected={false} />,
    );
    const group = container.querySelector('[data-testid="edge-c1"]');
    expect(group).not.toBeNull();
    expect(group?.getAttribute("data-multibond-strokes")).toBe("2");
    expect(group?.getAttribute("aria-label")).toBe(
      "Planar multibond, 3 components, 2 strokes",
    );

    const strokes = container.querySelectorAll(".editor-edge__multibond-stroke");
    expect(strokes).toHaveLength(2);
    expect(strokes[0]?.getAttribute("data-offset")).toBe("-2.1");
    expect(strokes[1]?.getAttribute("data-offset")).toBe("2.1");
    expect(strokes[0]?.getAttribute("d")).not.toBe(strokes[1]?.getAttribute("d"));
    expect(strokes[0]?.getAttribute("stroke")).toBe("var(--domain-planar)");
    expect(strokes[0]?.getAttribute("stroke-width")).toBe("1.5");
    expect(strokes[0]?.getAttribute("fill")).toBe("none");

    // One half arrow per stroke, one causal bar across the bundle.
    expect(container.querySelectorAll(".editor-edge__multibond-arrow")).toHaveLength(2);
    const bars = container.querySelectorAll(".editor-edge__causal");
    expect(bars).toHaveLength(1);
    expect(bars[0]?.classList.contains("editor-edge__causal--bundle")).toBe(true);
    expect(bars[0]?.getAttribute("data-testid")).toBe("causal-stroke-c1");
    expect(bars[0]?.getAttribute("data-stroke-at")).toBe("to");

    // One selection halo around the centre path.
    const halo = container.querySelectorAll(".editor-edge__halo");
    expect(halo).toHaveLength(0);
  });

  it("draws one selection halo around the centre path", () => {
    const { container } = renderEdge(<MultiBond id="c6" data={edgeData()} selected />);
    const halos = container.querySelectorAll(".editor-edge__halo");
    expect(halos).toHaveLength(1);
    expect(halos[0]?.getAttribute("d")).toBe(
      multibondPath(
        [
          { x: 0, y: 0 },
          { x: 200, y: 0 },
        ],
        0,
      ),
    );
  });

  it("renders three strokes and six components for Spatial", () => {
    const { container } = renderEdge(
      <MultiBond id="c3" data={domainOf("Spatial")} selected={false} />,
    );
    const group = container.querySelector('[data-testid="edge-c3"]');
    expect(group?.getAttribute("data-multibond-strokes")).toBe("3");
    expect(group?.getAttribute("aria-label")).toBe(
      "Spatial multibond, 6 components, 3 strokes",
    );

    const strokes = container.querySelectorAll(".editor-edge__multibond-stroke");
    expect(strokes).toHaveLength(3);
    expect(
      [...strokes].map((stroke) => stroke.getAttribute("data-offset")),
    ).toEqual(["-4.2", "0", "4.2"]);
    const paths = new Set([...strokes].map((stroke) => stroke.getAttribute("d")));
    expect(paths.size).toBe(3);
    expect(strokes[0]?.getAttribute("stroke")).toBe("var(--domain-spatial)");
    expect(strokes[0]?.getAttribute("stroke-width")).toBe("1.5");

    // One half arrow per stroke, one causal bar across all three.
    expect(container.querySelectorAll(".editor-edge__multibond-arrow")).toHaveLength(3);
    const bars = container.querySelectorAll(".editor-edge__causal");
    expect(bars).toHaveLength(1);
    expect(bars[0]?.classList.contains("editor-edge__causal--bundle")).toBe(true);
    const span = Math.hypot(
      Number(bars[0]?.getAttribute("x2")) - Number(bars[0]?.getAttribute("x1")),
      Number(bars[0]?.getAttribute("y2")) - Number(bars[0]?.getAttribute("y1")),
    );
    // 2 * (bundleHalf + 3) with bundleHalf = gap + strokeWidth/2 = 4.95.
    expect(span).toBeCloseTo(15.9, 6);

    // The hit area is the scalar 18 px plus the bundle width, on the centre path.
    const hit = container.querySelector<SVGPathElement>("path.react-flow__edge-path");
    expect(hit?.style.stroke).toBe("transparent");
    expect(hit?.getAttribute("d")).toBe(
      multibondPath(
        [
          { x: 0, y: 0 },
          { x: 200, y: 0 },
        ],
        0,
      ),
    );
    const interaction = container.querySelector("path.react-flow__edge-interaction");
    expect(Number(interaction?.getAttribute("stroke-width"))).toBeCloseTo(
      18 + 2 * multibondBundleHalf(3),
      12,
    );
  });

  it("keeps the scalar bond at one path and no bundle bar", () => {
    const { container } = renderEdge(
      <BondEdge
        id="c2"
        data={edgeData({ domain: "Electrical", baseDomain: "Electrical", frame: "Drive/shaft" })}
        selected
        type="bond"
        source="n1"
        target="n2"
        selectable
        deletable={false}
        animated={false}
        style={{}}
        sourceX={0}
        sourceY={0}
        targetX={200}
        targetY={0}
        sourcePosition={Position.Right}
        targetPosition={Position.Left}
      />,
    );
    const group = container.querySelector('[data-testid="edge-c2"]');
    expect(group?.getAttribute("data-multibond-strokes")).toBeNull();
    expect(container.querySelectorAll(".editor-edge__multibond-stroke")).toHaveLength(0);
    expect(container.querySelectorAll(".editor-edge__causal--bundle")).toHaveLength(0);
    expect(container.querySelectorAll("path.react-flow__edge-path")).toHaveLength(1);
    expect(container.querySelectorAll(".editor-edge__half-arrow")).toHaveLength(1);
    expect(container.querySelector('[data-testid="causal-stroke-c2"]')).not.toBeNull();
    // The frame pill belongs to every bond, not only to a bundle.
    expect(container.querySelector('[data-testid="frame-badge-c2"]')?.textContent).toBe(
      "frame: Drive/shaft",
    );
  });
});

describe("the frame badge", () => {
  it("shows the pill on hover and selection only, never without a frame", () => {
    const withoutFrame = renderEdge(<MultiBond id="c4" data={edgeData()} selected={false} />);
    const group = withoutFrame.container.querySelector('[data-testid="edge-c4"]');
    expect(group).not.toBeNull();
    fireEvent.mouseEnter(group!);
    expect(withoutFrame.container.querySelector('[data-testid="frame-badge-c4"]')).toBeNull();
    withoutFrame.unmount();

    const withFrame = renderEdge(
      <MultiBond id="c4" data={edgeData({ frame: "Arm1/body" })} selected={false} />,
    );
    expect(withFrame.container.querySelector('[data-testid="frame-badge-c4"]')).toBeNull();
    const hovered = withFrame.container.querySelector('[data-testid="edge-c4"]');
    fireEvent.mouseEnter(hovered!);
    const badge = withFrame.container.querySelector('[data-testid="frame-badge-c4"]');
    expect(badge).not.toBeNull();
    expect(badge?.textContent).toBe("frame: Arm1/body");
    expect(badge?.getAttribute("data-frame")).toBe("Arm1/body");
    fireEvent.mouseLeave(hovered!);
    expect(withFrame.container.querySelector('[data-testid="frame-badge-c4"]')).toBeNull();
    withFrame.unmount();

    const selected = renderEdge(
      <MultiBond id="c4" data={edgeData({ frame: "Arm1/body" })} selected />,
    );
    expect(selected.container.querySelector('[data-testid="frame-badge-c4"]')).not.toBeNull();
  });

  it("sits above the bundle centre, clear of the label and unit badge", () => {
    const data = edgeData({ frame: "Arm1/body", label: "p", unitFactor: "×0.001" });
    const { container } = renderEdge(<MultiBond id="c5" data={data} selected />);
    const pill = container.querySelector<HTMLElement>('[data-testid="frame-badge-c5"]');
    const chip = container.querySelector<HTMLElement>(".editor-edge__label");
    expect(pill).not.toBeNull();
    expect(chip).not.toBeNull();
    expect(container.querySelector('[data-testid="unit-badge-c5"]')).not.toBeNull();

    const centre = midpoint(data.sourceAnchor.point, data.targetAnchor.point);
    const position = frameBadgePosition(data);
    expect(position.x).toBeCloseTo(centre.x, 12);
    expect(position.y).toBeCloseTo(centre.y - 10 - FRAME_BADGE_OFFSET, 12);
    expect(position.y).toBeLessThan(centre.y);
    // The chip is at centre.y - 10; the pill is a full offset above it.
    expect(FRAME_BADGE_OFFSET).toBeGreaterThan(15);
    expect(pill?.style.transform).toContain(`${position.y}px`);
    const pillY = Number(/translate\([^)]*px, (-?[\d.]+)px\)$/.exec(pill?.style.transform ?? "")?.[1]);
    const chipY = Number(/translate\([^)]*px, (-?[\d.]+)px\)$/.exec(chip?.style.transform ?? "")?.[1]);
    expect(Number.isFinite(pillY)).toBe(true);
    expect(Number.isFinite(chipY)).toBe(true);
    expect(pillY).toBeLessThan(chipY);
    expect(chipY - pillY).toBeGreaterThanOrEqual(20);
  });
});

describe("multibond domain consistency", () => {
  function bondFlow(base: DomainName): DiagramFlow {
    return {
      nodes: [],
      edges: [
        {
          id: "c1",
          type: "bond",
          source: "n1",
          target: "n2",
          data: edgeData({ domain: base, baseDomain: base }),
        },
      ],
      analysis: {
        connections: new Map<string, ConnectionVisual>(),
        portDomains: new Map<string, DomainName>(),
      },
    };
  }

  it("never turns a Planar bond into a 3-stroke Spatial one", () => {
    const flow = decorateFlow(bondFlow("Planar"), {
      domains: { c1: "Spatial" },
      causality: {},
      unitFactors: {},
    });
    expect(flow.edges[0]?.data?.domain).toBe("Planar");
    expect(multibondStrokes(flow.edges[0]!.data!.domain)).toBe(2);
  });

  it("never turns a Spatial bond into a 2-stroke Planar one", () => {
    const flow = decorateFlow(bondFlow("Spatial"), {
      domains: { c1: "Planar" },
      causality: {},
      unitFactors: {},
    });
    expect(flow.edges[0]?.data?.domain).toBe("Spatial");
    expect(multibondStrokes(flow.edges[0]!.data!.domain)).toBe(3);
  });

  it("never lets a check result replace a Spatial bond with a scalar or Generic domain", () => {
    // Without the tightening this check result would turn the 3-stroke bundle
    // into a 1-stroke scalar bond (Rotation) or a Generic bond.
    for (const reported of ["Rotation", "Generic"] as const) {
      const flow = decorateFlow(bondFlow("Spatial"), {
        domains: { c1: reported },
        causality: {},
        unitFactors: {},
      });
      expect(flow.edges[0]?.data?.domain, reported).toBe("Spatial");
      expect(multibondStrokes(flow.edges[0]!.data!.domain), reported).toBe(3);
    }
  });

  it("never lets a check result turn a Rotation bond into a Spatial one", () => {
    const flow = decorateFlow(bondFlow("Rotation"), {
      domains: { c1: "Spatial" },
      causality: {},
      unitFactors: {},
    });
    expect(flow.edges[0]?.data?.domain).toBe("Rotation");
    expect(multibondStrokes(flow.edges[0]!.data!.domain)).toBe(1);
  });

  it("still lets a Generic port adopt a concrete multibond domain", () => {
    const flow = decorateFlow(bondFlow("Generic"), {
      domains: { c1: "Spatial" },
      causality: {},
      unitFactors: {},
    });
    expect(flow.edges[0]?.data?.domain).toBe("Spatial");
    expect(multibondStrokes(flow.edges[0]!.data!.domain)).toBe(3);
  });
});

describe("frame plumbing", () => {
  const index = buildCatalogIndex(catalogJson as unknown as Catalog);

  function bondModel(): Model {
    const source = createNodeFromBlock(
      index.blocksByName.get("Se")!,
      { x: 0, y: 0 },
      "n1",
      "Se1",
    );
    const capacitor = createNodeFromBlock(
      index.blocksByName.get("C")!,
      { x: 260, y: 0 },
      "n2",
      "C1",
    );
    const model = createEmptyModel("Framed");
    model.diagram.nodes = [source, capacitor];
    model.diagram.connections = [
      createConnection("c1", "bond", { node: "n1", port: "p" }, { node: "n2", port: "p" }),
    ];
    return model;
  }

  it("puts the worker's frames on the bond edge data", () => {
    const base = buildDiagram(bondModel(), index, { nodes: [], connections: [] });
    const flow = decorateFlow(base, {
      domains: { c1: "Planar" },
      causality: { c1: { strokeAt: "to" } },
      unitFactors: {},
      frames: { c1: "Arm1/body" },
    });
    const edge = flow.edges.find((entry) => entry.id === "c1");
    expect(edge?.data?.frame).toBe("Arm1/body");
    expect(edge?.data?.causalStroke).toBe("to");

    // A cleared result drops the badge back to none.
    const cleared = decorateFlow(base, {
      domains: {},
      causality: {},
      unitFactors: {},
      frames: {},
    });
    expect(cleared.edges.find((entry) => entry.id === "c1")?.data?.frame).toBeNull();
  });

  it("stores the frames a check result carries", () => {
    useDiagnosticsStore.getState().applyResult(
      {
        diagnostics: [],
        domains: { c1: "Planar" },
        causality: { c1: { strokeAt: "to" } },
        frames: { c1: "Arm1/body" },
        multibond: { c1: 2 },
        unitFactors: {},
        signals: [],
        stats: { states: 0, equations: 0 },
      },
      1,
    );
    expect(useDiagnosticsStore.getState().frames).toEqual({ c1: "Arm1/body" });
    resetDiagnosticsStore();
    expect(useDiagnosticsStore.getState().frames).toEqual({});
  });
});
