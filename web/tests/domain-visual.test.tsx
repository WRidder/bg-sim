/**
 * W2.3 (plan 7.3): the pure visual-language helpers, the legend content and
 * the hover label formatting. The DOM overlays themselves are covered by the
 * Playwright domain-visual spec against the real worker.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model } from "../src/contracts/model";
import { buildDiagram } from "../src/editor/buildFlow";
import { causalBarMidpoint, causalStrokeBar } from "../src/editor/edges/causalStroke";
import { causalityStrokeAt, decorateFlow } from "../src/editor/edges/decorateFlow";
import { unitFactorLabel } from "../src/editor/edges/units";
import { CanvasLegend, LEGEND_DOMAINS, LEGEND_KEYS } from "../src/editor/legend";
import { hoverTargetFromElement } from "../src/editor/ports/HoverReadout";
import {
  nearestSampleIndex,
  powerHoverRows,
  powerHoverSignalIds,
  powerUnits,
  signalHoverRow,
  valueAtNearestSample,
} from "../src/editor/ports/hoverValues";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import {
  createConnection,
  createEmptyModel,
  createJunctionNode,
  createNodeFromBlock,
} from "../src/state/modelFactory";

const index = buildCatalogIndex(catalogJson as unknown as Catalog);

function block(name: string) {
  const entry = index.blocksByName.get(name);
  if (entry === undefined) {
    throw new Error(`no block ${name}`);
  }
  return entry;
}

describe("causal strokes", () => {
  it("draws one perpendicular bar at the requested end", () => {
    const to = causalStrokeBar({ x: 0, y: 0 }, { x: 100, y: 0 }, "to");
    expect(to).not.toBeNull();
    expect(causalBarMidpoint(to!)).toEqual({ x: 85, y: 0 });
    expect(to!.x1).toBe(to!.x2);
    expect(Math.abs(to!.y1 - to!.y2)).toBe(14);

    const from = causalStrokeBar({ x: 0, y: 0 }, { x: 100, y: 0 }, "from");
    expect(causalBarMidpoint(from!)).toEqual({ x: 7, y: 0 });

    expect(causalStrokeBar({ x: 0, y: 0 }, { x: 100, y: 0 }, null)).toBeNull();
    expect(causalStrokeBar({ x: 2, y: 2 }, { x: 2, y: 2 }, "to")).toBeNull();
  });

  it("rejects a malformed causality entry", () => {
    expect(causalityStrokeAt({ strokeAt: "to" })).toBe("to");
    expect(causalityStrokeAt({ strokeAt: "from" })).toBe("from");
    expect(causalityStrokeAt(null)).toBeNull();
    expect(causalityStrokeAt({ strokeAt: "sideways" as "to" })).toBeNull();
  });
});

describe("unit-factor badges", () => {
  it("shows nothing for 1.0 and formats a real conversion", () => {
    expect(unitFactorLabel(1)).toBeNull();
    expect(unitFactorLabel(0.001)).toBe("×0.001");
    expect(unitFactorLabel(1000)).toBe("×1000");
    expect(unitFactorLabel(1e-9)).toBe("×1e-9");
    expect(unitFactorLabel(Number.NaN)).toBeNull();
    expect(unitFactorLabel(undefined)).toBeNull();
  });
});

describe("decorating the flow", () => {
  function fixture(): Model {
    const source = createNodeFromBlock(block("Se"), { x: 0, y: 0 }, "n1", "Se1");
    const capacitor = createNodeFromBlock(block("C"), { x: 260, y: 0 }, "n2", "C1");
    const gain = createNodeFromBlock(block("Gain"), { x: 0, y: 200 }, "n3", "G1");
    const sink = createNodeFromBlock(block("Gain"), { x: 260, y: 200 }, "n4", "G2");
    const junction = createJunctionNode("1", { x: 260, y: 100 }, "n5", "J1");
    const model = createEmptyModel("Decorated");
    model.diagram.nodes = [source, capacitor, gain, sink, junction];
    model.diagram.connections = [
      createConnection("c1", "bond", { node: "n1", port: "p" }, { node: "n2", port: "p" }),
      createConnection("c2", "signal", { node: "n3", port: "y" }, { node: "n4", port: "u" }),
      createConnection("c3", "bond", { node: "n1", port: "p" }, { node: "n5" }),
    ];
    return model;
  }

  it("puts worker domains, strokes and factors on the right element kinds", () => {
    const model = fixture();
    const base = buildDiagram(model, index, { nodes: [], connections: [] });
    const flow = decorateFlow(base, {
      domains: { c1: "Electrical", c2: "Electrical", c3: "Electrical" },
      causality: { c1: { strokeAt: "to" }, c3: { strokeAt: "from" } },
      unitFactors: { c1: 0.001, c2: 0.001, c3: 1.0 },
    });

    const c1 = flow.edges.find((edge) => edge.id === "c1");
    expect(c1?.data?.domain).toBe("Electrical");
    expect(c1?.data?.causalStroke).toBe("to");
    expect(c1?.data?.unitFactor).toBeNull();

    const c2 = flow.edges.find((edge) => edge.id === "c2");
    expect(c2?.data?.unitFactor).toBe("×0.001");
    expect(c2?.data?.causalStroke).toBeNull();

    const c3 = flow.edges.find((edge) => edge.id === "c3");
    expect(c3?.data?.causalStroke).toBe("from");
    expect(c3?.data?.unitFactor).toBeNull();

    const source = flow.nodes.find((node) => node.id === "n1");
    expect(source?.data).toMatchObject({
      portDomains: { p: "Electrical" },
    });
  });

  it("drops a check result back to the client analysis when cleared", () => {
    const model = fixture();
    const base = buildDiagram(model, index, { nodes: [], connections: [] });
    // The editor rebuilds from `buildDiagram` before applying an empty check,
    // so the client-side domain is what a cleared result restores.
    decorateFlow(base, {
      domains: { c1: "Electrical" },
      causality: { c1: { strokeAt: "to" } },
      unitFactors: { c2: 0.001 },
    });
    const cleared = decorateFlow(base, {
      domains: {},
      causality: {},
      unitFactors: {},
    });
    const c1 = cleared.edges.find((edge) => edge.id === "c1");
    expect(c1?.data?.domain).toBe("Generic");
    expect(c1?.data?.causalStroke).toBeNull();
    expect(cleared.edges.find((edge) => edge.id === "c2")?.data?.unitFactor).toBeNull();
  });
});

describe("hover values", () => {
  it("finds the nearest sample and handles the edges", () => {
    const time = new Float64Array([0, 1, 2, 3]);
    expect(nearestSampleIndex(time, -1)).toBe(0);
    expect(nearestSampleIndex(time, 0.1)).toBe(0);
    expect(nearestSampleIndex(time, 1.4)).toBe(1);
    expect(nearestSampleIndex(time, 1.6)).toBe(2);
    expect(nearestSampleIndex(time, 99)).toBe(3);
    expect(nearestSampleIndex(new Float64Array(0), 1)).toBe(-1);
    expect(nearestSampleIndex(time, Number.NaN)).toBe(0);

    const values = new Float64Array([10, 20, 30, 40]);
    expect(valueAtNearestSample(time, values, 1.6)).toBe(30);
    expect(valueAtNearestSample(time, undefined, 1)).toBeNull();
  });

  it("names the e/f/P signals under a subsystem path", () => {
    expect(powerHoverSignalIds("", "R1", "p")).toEqual({
      e: "R1/p.e",
      f: "R1/p.f",
      P: "R1/p.P",
    });
    expect(powerHoverSignalIds("Bondgraph", "C1", "p")).toEqual({
      e: "Bondgraph/C1/p.e",
      f: "Bondgraph/C1/p.f",
      P: "Bondgraph/C1/p.P",
    });
  });

  it("computes P = e·f and formats the values with manifest units", () => {
    const rows = powerHoverRows(2, 3, { e: "V", f: "A", P: "W" });
    expect(rows.map((row) => [row.key, row.label, row.value, row.unit])).toEqual([
      ["e", "e", "2", "V"],
      ["f", "f", "3", "A"],
      ["P", "P = e·f", "6", "W"],
    ]);
    expect(powerHoverRows(null, null)).toEqual([
      { key: "e", label: "e", value: "—", unit: "" },
      { key: "f", label: "f", value: "—", unit: "" },
      { key: "P", label: "P = e·f", value: "—", unit: "" },
    ]);
    expect(
      powerUnits(
        { e: "Bondgraph/C1/p.e", f: "Bondgraph/C1/p.f", P: "Bondgraph/C1/p.P" },
        [
          [
            { id: "Bondgraph/C1/p.e", unit: "V" },
            { id: "Bondgraph/C1/p.f", unit: "A" },
            { id: "Bondgraph/C1/p.P", unit: "W" },
          ],
        ],
      ),
    ).toEqual({ e: "V", f: "A", P: "W" });
    expect(signalHoverRow(0.005, "m")).toEqual({
      key: "value",
      label: "value",
      value: "0.005",
      unit: "m",
    });
    expect(signalHoverRow(null, null)).toEqual({
      key: "value",
      label: "value",
      value: "—",
      unit: "",
    });
  });

  it("resolves the hover target from the edge and port DOM hooks", () => {
    const canvas = document.createElement("div");
    canvas.innerHTML = `
      <svg class="react-flow__edges">
        <g data-testid="edge-bc4" data-kind="bond">
          <path class="react-flow__edge-path"></path>
        </g>
        <g data-testid="edge-c1" data-kind="signal">
          <path class="react-flow__edge-path"></path>
        </g>
      </svg>
      <div data-port="p" data-node-id="b5" data-kind="power"><span id="glyph"></span></div>
      <div data-port="" data-node-id="j1" data-kind="power"></div>
    `;
    const bond = canvas.querySelector('[data-testid="edge-bc4"] path');
    expect(hoverTargetFromElement(bond)).toMatchObject({
      key: "bond:bc4",
      kind: "bond",
      connectionId: "bc4",
      power: true,
    });
    const signal = canvas.querySelector('[data-testid="edge-c1"] path');
    expect(hoverTargetFromElement(signal)).toMatchObject({
      key: "signal:c1",
      kind: "signal",
      power: false,
    });
    expect(hoverTargetFromElement(canvas.querySelector("#glyph"))).toMatchObject({
      key: "port:b5:p",
      kind: "port",
      nodeId: "b5",
      port: "p",
      power: true,
    });
    expect(hoverTargetFromElement(canvas.querySelector('[data-node-id="j1"]'))).toBeNull();
    expect(hoverTargetFromElement(null)).toBeNull();
  });
});

describe("canvas legend", () => {
  it("lists every domain, including Planar, with Generic dashed", () => {
    expect(LEGEND_DOMAINS.map((entry) => entry.label)).toEqual([
      "Electrical",
      "Translation",
      "Rotation",
      "Hydraulic",
      "Generic",
      "Planar",
    ]);
    expect(LEGEND_DOMAINS.find((entry) => entry.id === "Generic")?.dashed).toBe(true);
    expect(LEGEND_DOMAINS.find((entry) => entry.id === "Electrical")?.token).toBe(
      "var(--domain-electrical)",
    );
  });

  it("carries the port glyph, causal-stroke and unit-badge keys", () => {
    expect(LEGEND_KEYS.map((entry) => entry.id)).toEqual([
      "power",
      "in",
      "out",
      "causal",
      "unit",
    ]);
    expect(LEGEND_KEYS.find((entry) => entry.id === "causal")?.description).toContain(
      "effort is the input",
    );
    expect(LEGEND_KEYS.find((entry) => entry.id === "unit")?.description).toContain("0.001");
  });

  it("renders an accessible group with every key", () => {
    render(<CanvasLegend />);
    const legend = screen.getByRole("group", { name: /canvas legend/i });
    expect(within(legend).getByTestId("legend-domain-Electrical").textContent).toContain(
      "Electrical",
    );
    expect(within(legend).getByTestId("legend-causal").textContent).toContain("causal");
    expect(within(legend).getByTestId("legend-unit").textContent).toContain("×0.001");
    expect(within(legend).getByTestId("legend-power").textContent).toContain("power");
    expect(within(legend).getByTestId("legend-in").textContent).toContain("in");
    expect(within(legend).getByTestId("legend-out").textContent).toContain("out");
  });
});
