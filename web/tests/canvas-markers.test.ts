/**
 * W1.3 (plan 7.3): the canvas decorations applied from the diagnostics-owned
 * layer. The markup mirrors what xyflow renders; the test asserts the exact
 * attributes the stylesheet and the end-to-end tests depend on.
 */

import { afterEach, describe, expect, it } from "vitest";

import type { Diagnostic } from "../src/contracts/diagnostic";
import type { DomainName } from "../src/contracts/catalog";
import type { Model } from "../src/contracts/model";
import {
  applyEdgeDomain,
  collectConnectionMarkers,
  collectNodeMarkers,
  decorateCanvas,
  domainDash,
  domainToken,
  formatUnitFactor,
} from "../src/diagnostics/canvasMarkers";
import { createEmptyModel } from "../src/state/modelFactory";

function modelWithNodes(): Model {
  const doc = createEmptyModel("M");
  doc.diagram.nodes = [
    {
      id: "n3",
      name: "Motor1",
      block: { ref: "stdlib:converters/DCMotor" },
      position: { x: 0, y: 0 },
      rotation: 0,
      flipX: false,
      params: {},
      constants: {},
      starts: {},
      ui: { showLabel: true, color: null },
    },
    {
      id: "n9",
      name: "LUT1",
      block: { ref: "stdlib:bondgraph/R" },
      position: { x: 300, y: 0 },
      rotation: 0,
      flipX: false,
      params: {},
      constants: {},
      starts: {},
      ui: { showLabel: true, color: null },
    },
  ];
  doc.diagram.connections = [
    {
      id: "c9",
      kind: "bond",
      from: { node: "n3", port: "p" },
      to: { node: "n9", port: "p" },
      route: [],
      label: null,
    },
    {
      id: "c2",
      kind: "signal",
      from: { node: "n3", port: "p" },
      to: { node: "n9", port: "p" },
      route: [],
      label: null,
    },
  ];
  return doc;
}

function diagnostic(overrides: Partial<Diagnostic>): Diagnostic {
  return {
    code: "E103",
    severity: "error",
    message: "unbalanced system: 14 unknowns, 13 equations",
    hint: null,
    path: "Plant/Motor1",
    block: null,
    scope: null,
    source: null,
    node: "n3",
    connection: null,
    ...overrides,
  };
}

function canvasFixture(): HTMLElement {
  const canvas = document.createElement("div");
  canvas.setAttribute("data-testid", "canvas-surface");
  canvas.innerHTML = `
    <div class="react-flow">
      <div class="react-flow__renderer">
        <div class="react-flow__viewport" style="transform: translate(0px,0px) scale(1)">
          <div class="react-flow__nodes">
            <div class="block-node" data-testid="diagram-node" data-node-id="n3" title="Motor1 (DC motor)">
              <span class="block-node__name">Motor1</span>
            </div>
            <div class="junction-node" data-testid="diagram-node" data-node-id="n9" title="0 junction (Junction0)">0</div>
          </div>
          <svg class="react-flow__edges">
            <g data-testid="edge-c9" data-kind="bond" data-domain="Generic">
              <path class="react-flow__edge-path" style="stroke: var(--domain-generic); stroke-dasharray: 4 3;"></path>
              <path class="editor-edge__half-arrow" stroke="var(--domain-generic)"></path>
            </g>
            <g data-testid="edge-c2" data-kind="signal" data-signal-type="Real" data-domain="Generic">
              <path class="react-flow__edge-path" style="stroke: var(--signal-real);"></path>
            </g>
          </svg>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(canvas);
  return canvas;
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("canvas diagnostics", () => {
  it("outlines the node, lists its messages and adds the count badge", () => {
    const canvas = canvasFixture();
    const doc = modelWithNodes();
    const diagnostics = [
      diagnostic({ code: "E103", node: "n3" }),
      diagnostic({ code: "W201", severity: "warning", message: "derivative causality", node: "n3" }),
    ];

    const summary = decorateCanvas(canvas, doc, {
      diagnostics,
      domains: { c9: "Electrical" },
      unitFactors: { c2: 0.001 },
      causality: { c9: { strokeAt: "to" } },
    });

    const motor = canvas.querySelector('[data-node-id="n3"]');
    expect(motor?.getAttribute("data-diagnostic-severity")).toBe("error");
    expect(motor?.getAttribute("data-diagnostic-count")).toBe("2");
    expect(motor?.getAttribute("data-diagnostic-messages")).toContain("E103");
    expect(motor?.getAttribute("title")).toContain("E103");
    expect(motor?.getAttribute("title")).toContain("W201");

    const unaffected = canvas.querySelector('[data-node-id="n9"]');
    expect(unaffected?.hasAttribute("data-diagnostic-severity")).toBe(false);
    expect(unaffected?.getAttribute("title")).toBe("0 junction (Junction0)");

    expect(summary.nodes).toBe(1);
    expect(summary.factors).toEqual([{ connectionId: "c2", label: "×0.001" }]);
    expect(summary.edgeMarkers).toEqual([]);
    expect(summary.causalStrokes).toEqual([{ connectionId: "c9", strokeAt: "to" }]);
  });

  it("puts the adopted domain on power edges and leaves signal styling alone", () => {
    const canvas = canvasFixture();
    const doc = modelWithNodes();
    decorateCanvas(canvas, doc, {
      diagnostics: [diagnostic({ code: "E102", node: "n3", connection: "c9" })],
      domains: { c9: "Electrical" },
      unitFactors: {},
      causality: {},
    });

    const edge = canvas.querySelector('[data-testid="edge-c9"]');
    expect(edge?.getAttribute("data-domain")).toBe("Electrical");
    expect(edge?.getAttribute("data-bgsim-base-domain")).toBe("Generic");
    expect(edge?.getAttribute("data-bgsim-applied-domain")).toBe("Electrical");
    expect(edge?.getAttribute("data-diagnostic-severity")).toBe("error");
    const path = edge?.querySelector<SVGPathElement>(".react-flow__edge-path");
    expect(path?.style.getPropertyValue("stroke")).toContain("--domain-electrical");
    expect(path?.style.getPropertyValue("stroke-dasharray")).toBe("none");
    const barb = edge?.querySelector(".editor-edge__half-arrow");
    expect(barb?.getAttribute("stroke")).toBe("var(--domain-electrical)");

    const signal = canvas.querySelector('[data-testid="edge-c2"]');
    expect(signal?.getAttribute("data-domain")).toBe("Generic");
    expect(signal?.querySelector<SVGPathElement>(".react-flow__edge-path")?.style.getPropertyValue("stroke")).toBe(
      "var(--signal-real)",
    );
  });

  it("restores the client-side colouring when the check result is cleared", () => {
    const canvas = canvasFixture();
    const doc = modelWithNodes();
    decorateCanvas(canvas, doc, {
      diagnostics: [diagnostic({ code: "E102", node: null, connection: "c9" })],
      domains: { c9: "Electrical" },
      unitFactors: {},
      causality: {},
    });

    const cleared = decorateCanvas(canvas, doc, {
      diagnostics: [],
      domains: {},
      unitFactors: {},
      causality: {},
    });

    const edge = canvas.querySelector('[data-testid="edge-c9"]');
    expect(edge?.getAttribute("data-domain")).toBe("Generic");
    expect(edge?.hasAttribute("data-diagnostic-severity")).toBe(false);
    const path = edge?.querySelector<SVGPathElement>(".react-flow__edge-path");
    expect(path?.style.getPropertyValue("stroke")).toContain("--domain-generic");
    expect(path?.style.getPropertyValue("stroke-dasharray")).toBe("4 3");
    expect(cleared.factors).toEqual([]);
    expect(cleared.edgeMarkers).toEqual([]);

    const motor = canvas.querySelector('[data-node-id="n3"]');
    expect(motor?.hasAttribute("data-diagnostic-severity")).toBe(false);
    expect(motor?.getAttribute("title")).toBe("Motor1 (DC motor)");
  });

  it("maps every domain name to its design token", () => {
    const expected: Array<[DomainName, string]> = [
      ["Electrical", "var(--domain-electrical)"],
      ["Translation", "var(--domain-translation)"],
      ["Rotation", "var(--domain-rotation)"],
      ["Hydraulic", "var(--domain-hydraulic)"],
      ["Generic", "var(--domain-generic)"],
      ["Planar", "var(--domain-planar)"],
      ["Spatial", "var(--domain-spatial)"],
    ];
    for (const [domain, token] of expected) {
      expect(domainToken(domain)).toBe(token);
    }
    expect(domainDash("Generic")).toBe("4 3");
    expect(domainDash("Electrical")).toBe("none");
    expect(formatUnitFactor(0.001)).toBe("×0.001");
    expect(formatUnitFactor(1000)).toBe("×1000");
    expect(formatUnitFactor(1e-9)).toBe("×1e-9");
  });

  it("groups diagnostics by node and connection, with errors winning", () => {
    const doc = modelWithNodes();
    const nodeMarkers = collectNodeMarkers(doc, [
      diagnostic({ severity: "warning", code: "W201", node: "n3" }),
      diagnostic({ severity: "error", code: "E103", node: "n3" }),
      diagnostic({ severity: "info", code: "I001", node: "n3" }),
      diagnostic({ code: "E901", node: "n9" }),
    ]);
    expect(nodeMarkers.get("n3")).toMatchObject({ severity: "error", count: 2 });
    expect(nodeMarkers.get("n9")).toMatchObject({ severity: "error", count: 1 });

    const connectionMarkers = collectConnectionMarkers(doc, [
      diagnostic({ severity: "warning", code: "W202", node: null, connection: "c9" }),
      diagnostic({ severity: "error", code: "E102", node: null, connection: "c9" }),
      diagnostic({ severity: "error", code: "E1", node: null, connection: "missing" }),
    ]);
    expect(connectionMarkers.get("c9")).toMatchObject({ severity: "error", count: 2 });
    expect(connectionMarkers.has("missing")).toBe(false);
  });

  it("keeps a multibond's hit path invisible when it applies the domain", () => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.innerHTML = `
      <g data-testid="edge-c4" data-kind="bond" data-domain="Planar" data-multibond-strokes="2">
        <path class="react-flow__edge-path" style="stroke: transparent;"></path>
        <path class="editor-edge__multibond-stroke" stroke="var(--domain-planar)"></path>
        <path class="editor-edge__multibond-stroke" stroke="var(--domain-planar)"></path>
        <path class="editor-edge__half-arrow editor-edge__multibond-arrow" stroke="var(--domain-planar)"></path>
      </g>`;
    const edge = svg.querySelector('[data-testid="edge-c4"]');
    expect(edge).not.toBeNull();
    expect(applyEdgeDomain(edge!, "Planar" as DomainName)).toBe("Planar");
    // Painting the hit path would draw a third stroke between the two.
    const hit = edge?.querySelector<SVGPathElement>(".react-flow__edge-path");
    expect(hit?.style.getPropertyValue("stroke")).toBe("transparent");
    expect(edge?.querySelector(".editor-edge__half-arrow")?.getAttribute("stroke")).toBe(
      "var(--domain-planar)",
    );
  });
});
