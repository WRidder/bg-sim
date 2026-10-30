/**
 * Subsystem port terminal shapes: the kind reads from the outline, not the
 * colour.
 *
 * * an input is an arrow tag pointing into the diagram (its point on the side
 *   the boundary wire leaves from, a notch on the outer side);
 * * an output is an arrow tag pointing out of it (flat on the wire side);
 * * a power port is a symmetric hexagon;
 * * the direction follows the wire side, also for a terminal placed on the
 *   other side of its port;
 * * the boundary wire carries an arrowhead (signals) or the bond half arrow
 *   (power) at the right end, and its terminal end meets the point or the
 *   flat edge.
 */

import { describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import fixtureJson from "../../contracts/fixtures/model/valid/model.subsystem-port-ui.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model } from "../src/contracts/model";
import { buildDiagram } from "../src/editor/buildFlow";
import { boundaryMark } from "../src/editor/edges/BoundaryEdge";
import type { Anchor, Side } from "../src/editor/geometry";
import type { TerminalNodeData } from "../src/editor/nodes/PortTerminal";
import {
  pointDepth,
  terminalInsets,
  terminalOutline,
  terminalShape,
  terminalVertices,
} from "../src/editor/nodes/terminalShape";
import { activeModel } from "../src/editor/subsystemPath";
import { subsystemBoundary, terminalId, TERMINAL_HEIGHT } from "../src/editor/subsystemBoundary";
import { buildCatalogIndex } from "../src/library/catalogIndex";

const index = buildCatalogIndex(catalogJson as unknown as Catalog);
const NONE = { nodes: [], connections: [] };
const SIDES: Side[] = ["left", "right", "top", "bottom"];
const OPPOSITE: Record<Side, Side> = { left: "right", right: "left", top: "bottom", bottom: "top" };

function fixture(): Model {
  return JSON.parse(JSON.stringify(fixtureJson)) as Model;
}

/** The point of the outline furthest out on `side`, and how many vertices lie on that edge. */
function extreme(vertices: { x: number; y: number }[], side: Side) {
  const key = side === "left" || side === "right" ? "x" : "y";
  const values = vertices.map((v) => v[key]);
  const target = side === "left" || side === "top" ? Math.min(...values) : Math.max(...values);
  const on = vertices.filter((v) => Math.abs(v[key] - target) < 1e-6);
  return { target, on };
}

describe("terminalShape", () => {
  it("points an input toward its wire, notched on the outer side", () => {
    expect(terminalShape("input", "right")).toEqual({ kind: "input", point: "right", notch: "left" });
    expect(terminalShape("input", "left")).toEqual({ kind: "input", point: "left", notch: "right" });
    // On a top or bottom edge the point is short and the outer side flat.
    expect(terminalShape("input", "top")).toEqual({ kind: "input", point: "top", notch: null });
    expect(terminalShape("input", "bottom")).toEqual({ kind: "input", point: "bottom", notch: null });
  });

  it("points an output away from its wire, flat on the wire side", () => {
    expect(terminalShape("output", "left")).toEqual({ kind: "output", point: "right", notch: null });
    expect(terminalShape("output", "right")).toEqual({ kind: "output", point: "left", notch: null });
    expect(terminalShape("output", "top")).toEqual({ kind: "output", point: "bottom", notch: null });
    expect(terminalShape("output", "bottom")).toEqual({ kind: "output", point: "top", notch: null });
  });

  it("gives a power port no direction on any side", () => {
    for (const side of SIDES) {
      expect(terminalShape("power", side)).toEqual({ kind: "power", point: null, notch: null });
    }
  });

  it("reads left to right in the default places (inputs left, outputs right)", () => {
    // An input on the left sends its wire right; an output on the right takes it from the left.
    expect(terminalShape("input", "right").point).toBe("right");
    expect(terminalShape("output", "left").point).toBe("right");
  });
});

describe("terminal outlines", () => {
  const width = 120;
  const height = TERMINAL_HEIGHT;

  it("puts an input's point on the wire side at mid height and a notch opposite", () => {
    for (const side of ["left", "right"] as const) {
      const vertices = terminalVertices(terminalShape("input", side), width, height);
      const tip = extreme(vertices, side);
      expect(tip.on).toHaveLength(1);
      expect(tip.on[0]!.y).toBe(height / 2);
      // The notch: a vertex at mid height set in from the outer edge.
      const outer = extreme(vertices, OPPOSITE[side]);
      expect(outer.on).toHaveLength(2);
      const notch = vertices.find((v) => v.y === height / 2 && v !== tip.on[0]);
      expect(notch).toBeDefined();
      expect(Math.abs(notch!.x - outer.target)).toBe(pointDepth(height) / 2);
    }
  });

  it("gives an output a flat wire side and its point on the far side", () => {
    for (const handleSide of ["left", "right"] as const) {
      const vertices = terminalVertices(terminalShape("output", handleSide), width, height);
      // Flat: the two corners on the wire side, nothing at mid height there.
      expect(extreme(vertices, handleSide).on).toHaveLength(2);
      const tip = extreme(vertices, OPPOSITE[handleSide]);
      expect(tip.on).toHaveLength(1);
      expect(tip.on[0]!.y).toBe(height / 2);
    }
  });

  it("draws a short point in the middle of a top or bottom edge", () => {
    for (const side of ["top", "bottom"] as const) {
      const vertices = terminalVertices(terminalShape("input", side), width, height);
      const tip = extreme(vertices, side);
      expect(tip.on).toHaveLength(1);
      expect(tip.on[0]!.x).toBe(width / 2);
    }
    const out = terminalVertices(terminalShape("output", "top"), width, height);
    expect(extreme(out, "bottom").on).toHaveLength(1);
    expect(extreme(out, "top").on).toHaveLength(2);
  });

  it("draws a power port as a mirror-symmetric hexagon", () => {
    const vertices = terminalVertices(terminalShape("power", "left"), width, height);
    expect(vertices).toHaveLength(6);
    const mirrored = vertices.map((v) => ({ x: width - v.x, y: v.y }));
    for (const v of mirrored) {
      expect(vertices.some((w) => Math.abs(w.x - v.x) < 1e-9 && w.y === v.y)).toBe(true);
    }
    expect(extreme(vertices, "left").on).toHaveLength(1);
    expect(extreme(vertices, "right").on).toHaveLength(1);
    // The same hexagon whichever side the wire leaves from.
    expect(terminalOutline(terminalShape("power", "top"), width, height)).toBe(
      terminalOutline(terminalShape("power", "right"), width, height),
    );
  });

  it("stays inside the node box", () => {
    for (const kind of ["input", "output", "power"] as const) {
      for (const side of SIDES) {
        for (const v of terminalVertices(terminalShape(kind, side), width, height)) {
          expect(v.x).toBeGreaterThanOrEqual(0);
          expect(v.x).toBeLessThanOrEqual(width);
          expect(v.y).toBeGreaterThanOrEqual(0);
          expect(v.y).toBeLessThanOrEqual(height);
        }
      }
    }
  });

  it("pads the text clear of the point and the notch", () => {
    const depth = pointDepth(height);
    const input = terminalInsets(terminalShape("input", "right"), height);
    expect(input.right).toBeGreaterThan(depth);
    expect(input.left).toBeGreaterThan(depth / 2);
    const output = terminalInsets(terminalShape("output", "left"), height);
    expect(output.right).toBeGreaterThan(depth);
    const power = terminalInsets(terminalShape("power", "left"), height);
    expect(power.left).toBe(power.right);
    expect(power.left).toBeGreaterThan(depth);
    const below = terminalInsets(terminalShape("input", "bottom"), height);
    expect(below.bottom).toBeGreaterThan(0);
    expect(below.top).toBe(0);
  });
});

describe("boundary wire marks", () => {
  const terminal: Anchor = { point: { x: 0, y: 0 }, side: "right" };
  const internal: Anchor = { point: { x: 100, y: 40 }, side: "left" };

  it("puts an input's arrowhead at the internal port, pointing into it", () => {
    const mark = boundaryMark("input", terminal, internal);
    expect(mark).toMatchObject({ kind: "arrow", at: "internal" });
    expect(mark.d.startsWith("M 100 40 ")).toBe(true);
  });

  it("puts an output's arrowhead at the terminal, pointing into it", () => {
    const outputTerminal: Anchor = { point: { x: 200, y: 40 }, side: "left" };
    const outputInternal: Anchor = { point: { x: 100, y: 40 }, side: "right" };
    const mark = boundaryMark("output", outputTerminal, outputInternal);
    expect(mark).toMatchObject({ kind: "arrow", at: "terminal" });
    // Tip on the terminal, base 9 px back toward the wire.
    expect(mark.d).toBe("M 200 40 L 191 44.5 L 191 35.5 Z");
  });

  it("puts the bond half arrow at the internal port of a power wire", () => {
    const mark = boundaryMark("power", terminal, internal);
    expect(mark).toMatchObject({ kind: "half-arrow", at: "internal" });
    expect(mark.d.startsWith("M 100 40 L 90 ")).toBe(true);
  });
});

describe("terminals in the inner flow", () => {
  it("draws the fixture's input as a tag toward V1 and vc as a hexagon", () => {
    const model = fixture();
    const view = activeModel(model, ["plant"])!;
    const boundary = subsystemBoundary(model, ["plant"], index);
    const flow = buildDiagram(view, index, NONE, null, true, boundary);
    const u = flow.nodes.find((node) => node.id === terminalId("u"))!;
    const uData = u.data as TerminalNodeData;
    expect(uData.handleSide).toBe("right");
    expect(terminalShape(uData.kind, uData.handleSide).point).toBe("right");
    const vc = flow.nodes.find((node) => node.id === terminalId("vc"))!.data as TerminalNodeData;
    expect(terminalShape(vc.kind, vc.handleSide).point).toBeNull();

    // The wire's terminal end is the point of the tag.
    const wire = flow.boundaryEdges!.find((edge) => edge.id === "boundary:u")!;
    const tip = extreme(terminalVertices(terminalShape("input", "right"), uData.width, uData.height), "right").on[0]!;
    expect(Math.abs(wire.data!.terminal.point.x - (u.position.x + tip.x))).toBeLessThanOrEqual(1);
    expect(wire.data!.terminal.point.y).toBe(u.position.y + tip.y);
  });

  it("turns an input placed on the far side of its port to point back at it", () => {
    const model = fixture();
    const plant = model.diagram.nodes.find((node) => node.id === "plant")!;
    if (!("subsystem" in plant.block)) {
      throw new Error("no Plant subsystem");
    }
    // V1.u is on V1's left edge; put the terminal well to the right of V1.
    plant.block.subsystem.ports[0]!.ui = { position: { x: 400, y: 60 } };
    const view = activeModel(model, ["plant"])!;
    const flow = buildDiagram(view, index, NONE, null, true, subsystemBoundary(model, ["plant"], index));
    const u = flow.nodes.find((node) => node.id === terminalId("u"))!.data as TerminalNodeData;
    expect(u.handleSide).toBe("left");
    expect(terminalShape(u.kind, u.handleSide)).toEqual({ kind: "input", point: "left", notch: "right" });
  });
});
