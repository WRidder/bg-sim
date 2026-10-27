/**
 * Canvas geometry and diagram analysis: port layout, domain adoption through
 * bonds, wire nodes with 3+ ports, drag compatibility and the SVG shapes of
 * plan 7.3.
 */

import { describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import modelJson from "../../contracts/fixtures/model/valid/model.dcmotor.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model } from "../src/contracts/model";
import { analyseDiagram, dragCompatibility } from "../src/editor/connectionAnalysis";
import { buildDiagram, bondLabelSide } from "../src/editor/buildFlow";
import { portKey } from "../src/editor/connectionRules";
import {
  BOND_NODE_SIZE,
  COMPACT_NODE_SIZE,
  JUNCTION_BOND_GAP,
  JUNCTION_RADIUS,
  NODE_HALF_SHIFT,
  arrowHeadPath,
  causalStrokePath,
  connectionAnchors,
  halfArrowPath,
  hubPath,
  isCompactBlock,
  layoutNode,
  nearestSourcePort,
  nodeLayout,
  nodeLayouts,
  orthogonalPath,
  rightAngleMarker,
  snapRouteVertex,
  splitPorts,
} from "../src/editor/geometry";
import { INLINE_ICON, interfaceForBlock, interfaceForNode, portDescriptor } from "../src/editor/nodeInterface";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import {
  createConnection,
  createEmptyModel,
  createJunctionNode,
  createNodeFromBlock,
} from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;
const index = buildCatalogIndex(catalog);
const dcMotor = modelJson as unknown as Model;

function block(name: string) {
  const entry = index.blocksByName.get(name);
  if (entry === undefined) {
    throw new Error(`no block ${name}`);
  }
  return entry;
}

describe("port layout", () => {
  it("puts signal inputs left, outputs right and splits power ports in half", () => {
    const motor = interfaceForBlock(block("DCMotor"));
    const { left, right } = splitPorts(motor.ports);
    expect(left.map((port) => port.name)).toEqual(["p", "n"]);
    expect(right.map((port) => port.name)).toEqual(["shaft", "housing"]);

    const gain = interfaceForBlock(block("Gain"));
    const gainSplit = splitPorts(gain.ports);
    expect(gainSplit.left.map((port) => port.name)).toEqual(["u"]);
    expect(gainSplit.right.map((port) => port.name)).toEqual(["y"]);
  });

  it("sizes a compact square for its ports and places anchors on the edges", () => {
    const motor = interfaceForBlock(block("DCMotor"));
    const layout = layoutNode(motor);
    expect(COMPACT_NODE_SIZE).toBe(60);
    expect(COMPACT_NODE_SIZE / 20).toBe(3); // three editor grid cells
    expect(layout.width).toBe(COMPACT_NODE_SIZE);
    expect(layout.height).toBe(COMPACT_NODE_SIZE);
    expect(layout.ports.get("p")?.side).toBe("left");
    expect(layout.ports.get("n")?.x).toBe(0);
    expect(layout.ports.get("shaft")?.side).toBe("right");
    expect(layout.ports.get("shaft")?.x).toBe(COMPACT_NODE_SIZE);
    expect(layout.ports.get("p")?.y).toBeGreaterThan(0);
    expect(layout.ports.get("shaft")?.y).toBeGreaterThan(0);
    expect(layout.ports.get("p")?.y).toBeLessThan(COMPACT_NODE_SIZE);
    expect(isCompactBlock(motor)).toBe(true);
    expect(isCompactBlock({ ...motor, icon: INLINE_ICON })).toBe(false);
    expect(isCompactBlock({ ...motor, icon: "bg-se" })).toBe(false);
  });

  it("gives a junction a 40 px circle and no port map", () => {
    const model = createEmptyModel("Junction");
    const junction = {
      ...createNodeFromBlock(block("C"), { x: 0, y: 0 }, "n1", "C1"),
      block: { junction: "0" as const },
    };
    model.diagram.nodes = [junction];
    const layout = nodeLayout(junction, index);
    expect(layout.width).toBe(40);
    expect(layout.height).toBe(40);
    expect(layout.ports.size).toBe(0);
    expect(interfaceForNode(junction, index).isJunction).toBe(true);
  });

  it("leaves a gap between a junction rim and its bond", () => {
    const model = createEmptyModel("JunctionGap");
    const junction = createJunctionNode("0", { x: 0, y: 0 }, "j1", "J1");
    const inertia = createNodeFromBlock(block("I"), { x: 220, y: 0 }, "n2", "I1");
    model.diagram.nodes = [junction, inertia];
    model.diagram.connections = [
      createConnection("c1", "bond", { node: "j1" }, { node: "n2", port: "p" }),
    ];
    const connection = model.diagram.connections[0];
    if (connection === undefined) {
      throw new Error("missing connection");
    }
    const { source } = connectionAnchors(model, index, connection);
    const centre = { x: 20 + NODE_HALF_SHIFT, y: 20 + NODE_HALF_SHIFT };
    expect(
      Math.hypot(source.point.x - centre.x, source.point.y - centre.y),
    ).toBeCloseTo(JUNCTION_RADIUS + JUNCTION_BOND_GAP, 6);
  });

  it("faces a bond-graph port toward the bond and hangs the name off the letter", () => {    const source = createNodeFromBlock(block("Se"), { x: 0, y: 0 }, "n1", "Se1");
    const inertia = createNodeFromBlock(block("I"), { x: 300, y: 0 }, "n2", "I1");
    const model = createEmptyModel("BondGraphLook");
    model.diagram.nodes = [source, inertia];
    model.diagram.connections = [
      createConnection("c1", "bond", { node: "n1", port: "p" }, { node: "n2", port: "p" }),
    ];

    const layouts = nodeLayouts(model, index);
    const se = layouts.get("n1");
    expect(BOND_NODE_SIZE).toBe(40);
    expect(BOND_NODE_SIZE / 20).toBe(2); // two editor grid cells
    expect(se?.width).toBe(BOND_NODE_SIZE);
    expect(se?.height).toBe(BOND_NODE_SIZE);
    expect(se?.ports.get("p")).toEqual({
      side: "right",
      x: BOND_NODE_SIZE,
      y: BOND_NODE_SIZE / 2,
    });
    expect(layouts.get("n2")?.ports.get("p")?.side).toBe("left");

    const flow = buildDiagram(model, index, { nodes: [], connections: [] });
    const data = flow.nodes[0]?.data as { bond: boolean; labelSide: string };
    expect(data.bond).toBe(true);
    expect(data.labelSide).not.toBe("right");
    expect(nodeLayout(source, index, model).ports.get("p")?.side).toBe("right");
  });

  it("moves the letter's name away from a port that leaves through the bottom", () => {
    const source = createNodeFromBlock(block("Se"), { x: 0, y: 0 }, "n1", "Se1");
    const inertia = createNodeFromBlock(block("I"), { x: 0, y: 220 }, "n2", "I1");
    const model = createEmptyModel("VerticalBond");
    model.diagram.nodes = [source, inertia];
    model.diagram.connections = [
      createConnection("c1", "bond", { node: "n1", port: "p" }, { node: "n2", port: "p" }),
    ];
    const flow = buildDiagram(model, index, { nodes: [], connections: [] });
    const data = flow.nodes[0]?.data as { labelSide: string };
    expect(nodeLayouts(model, index).get("n1")?.ports.get("p")?.side).toBe("bottom");
    expect(data.labelSide).toBe("top");
  });

  it("orders ports along an edge by where their peers sit, avoiding crossed inputs", () => {
    const motor = createNodeFromBlock(block("DCMotor"), { x: 400, y: 200 }, "n3", "Motor");
    const top = createNodeFromBlock(block("Se"), { x: 0, y: 0 }, "n1", "Top");
    const bottom = createNodeFromBlock(block("Se"), { x: 0, y: 600 }, "n2", "Bottom");
    const model = createEmptyModel("PortOrder");
    model.diagram.nodes = [top, bottom, motor];
    model.diagram.connections = [
      // Deliberately connect the top source to `n` and the bottom to `p`; the
      // layout must put `n` above `p`, not follow the interface order.
      createConnection("c1", "bond", { node: "n1", port: "p" }, { node: "n3", port: "n" }),
      createConnection("c2", "bond", { node: "n2", port: "p" }, { node: "n3", port: "p" }),
    ];

    const layout = nodeLayouts(model, index).get("n3");
    const p = layout?.ports.get("p");
    const n = layout?.ports.get("n");
    expect(p).toBeDefined();
    expect(n).toBeDefined();
    if (p === undefined || n === undefined) {
      return;
    }
    expect(p.side).toBe("left");
    expect(n.side).toBe("left");
    expect(n.y).toBeLessThan(p.y);
  });

  it("parks free ports at the ends so a single connected port stays centred", () => {
    const motor = createNodeFromBlock(block("DCMotor"), { x: 400, y: 200 }, "n2", "Motor");
    const source = createNodeFromBlock(block("Se"), { x: 0, y: 200 }, "n1", "Source");
    const model = createEmptyModel("FreePorts");
    model.diagram.nodes = [source, motor];
    model.diagram.connections = [
      createConnection("c1", "bond", { node: "n1", port: "p" }, { node: "n2", port: "p" }),
    ];

    const layout = nodeLayouts(model, index).get("n2");
    const p = layout?.ports.get("p");
    const n = layout?.ports.get("n");
    expect(p).toBeDefined();
    expect(n).toBeDefined();
    if (p === undefined || n === undefined) {
      return;
    }
    // One connection on this edge stays at the exact midpoint; the free `n`
    // port vacates that slot and parks near the top.
    expect(p.y).toBe(COMPACT_NODE_SIZE / 2);
    expect(n.y).not.toBe(p.y);
    expect(n.y).toBeLessThan(p.y);
  });

  it("snaps routing vertices to the double-resolution route grid", () => {
    expect(snapRouteVertex({ x: 11, y: 29 })).toEqual({ x: 10, y: 30 });
    expect(snapRouteVertex({ x: 31, y: 49 })).toEqual({ x: 30, y: 50 });
    expect(snapRouteVertex({ x: 21, y: 19 })).toEqual({ x: 20, y: 20 });
    expect(snapRouteVertex({ x: 10, y: 30 })).toEqual({ x: 10, y: 30 });
    expect(snapRouteVertex({ x: 0, y: 0 })).toEqual({ x: 0, y: 0 });
  });

  it("picks the source port nearest the Ctrl press", () => {
    const motor = interfaceForBlock(block("DCMotor"));
    const layout = layoutNode(motor);
    const shaft = layout.ports.get("shaft");
    if (shaft === undefined) {
      throw new Error("no shaft port");
    }
    expect(
      nearestSourcePort(motor, layout, { x: 0, y: 0 }, { x: shaft.x, y: shaft.y }),
    ).toBe("shaft");

    const gain = interfaceForBlock(block("Gain"));
    const gainLayout = layoutNode(gain);
    expect(
      nearestSourcePort(gain, gainLayout, { x: 0, y: 0 }, { x: 0, y: 0 }),
    ).toBe("y");
  });

  it("moves the letter's name out of the way of a neighbouring element", () => {
    const se = interfaceForBlock(block("Se"));
    const layout = layoutNode(se, new Map([["p", "right"]]));
    const anchor = { name: "Se1", position: { x: 0, y: 0 } };
    expect(bondLabelSide(anchor, layout, [])).toBe("bottom");
    const below = { x: -30, y: 56, w: 120, h: 90 };
    expect(bondLabelSide(anchor, layout, [below])).not.toBe("bottom");
  });
});

describe("diagram analysis", () => {
  it("colours the DC motor fixture: wires, the signal and adopted domains", () => {
    const analysis = analyseDiagram(dcMotor, index);
    expect(analysis.connections.get("c1")?.signalType).toBe("Real");
    expect(analysis.connections.get("c2")?.domain).toBe("Electrical");
    expect(analysis.connections.get("c3")?.domain).toBe("Electrical");
    expect(analysis.connections.get("c4")?.domain).toBe("Rotation");
    expect(analysis.connections.get("c5")?.domain).toBe("Rotation");
    expect(analysis.connections.get("c6")?.domain).toBe("Rotation");
    expect(analysis.connections.get("c7")?.domain).toBe("Electrical");
    // c3 and c7 meet at Ground.p, so that wire node has three ports and a dot;
    // the other four wires are simple two-port connections.
    expect(analysis.connections.get("c3")?.wireHub).not.toBeNull();
    expect(analysis.connections.get("c7")?.wireHub).toEqual(
      analysis.connections.get("c3")?.wireHub,
    );
    for (const id of ["c2", "c4", "c5", "c6"]) {
      expect(analysis.connections.get(id)?.wireHub, id).toBeNull();
    }
    expect(analysis.portDomains.get(portKey({ nodeId: "n3", portName: "shaft" }))).toBe(
      "Rotation",
    );
    expect(analysis.portDomains.get(portKey({ nodeId: "n3", portName: "p" }))).toBe("Electrical");
  });

  it("adopts the concrete domain through a bond and draws the Generic port in it", () => {
    const source = createNodeFromBlock(block("Se"), { x: 0, y: 0 }, "n1", "Se1");
    const resistor = createNodeFromBlock(block("Resistor"), { x: 200, y: 0 }, "n2", "R1");
    const model = createEmptyModel("Adopt");
    model.diagram.nodes = [source, resistor];
    model.diagram.connections = [
      createConnection("c1", "bond", { node: "n1", port: "p" }, { node: "n2", port: "p" }),
    ];
    const analysis = analyseDiagram(model, index);
    expect(analysis.connections.get("c1")?.domain).toBe("Electrical");
    expect(analysis.portDomains.get(portKey({ nodeId: "n1", portName: "p" }))).toBe("Electrical");
  });

  it("marks a bond island with two concrete domains as Generic", () => {
    const source = createNodeFromBlock(block("Se"), { x: 0, y: 0 }, "n1", "Se1");
    const resistor = createNodeFromBlock(block("Resistor"), { x: 200, y: 0 }, "n2", "R1");
    const spring = createNodeFromBlock(block("Spring"), { x: 400, y: 0 }, "n3", "Spring1");
    const model = createEmptyModel("Mixed");
    model.diagram.nodes = [source, resistor, spring];
    model.diagram.connections = [
      createConnection("c1", "bond", { node: "n1", port: "p" }, { node: "n2", port: "p" }),
      createConnection("c2", "bond", { node: "n1", port: "p" }, { node: "n3", port: "a" }),
    ];
    const analysis = analyseDiagram(model, index);
    expect(analysis.connections.get("c1")?.domain).toBe("Generic");
    expect(analysis.connections.get("c2")?.domain).toBe("Generic");
  });

  it("puts a shared dot on a wire node with three ports", () => {
    const source = createNodeFromBlock(block("VoltageSource"), { x: 0, y: 0 }, "n1", "V1");
    const resistor = createNodeFromBlock(block("Resistor"), { x: 240, y: 0 }, "n2", "R1");
    const ground = createNodeFromBlock(block("Ground"), { x: 0, y: 200 }, "n3", "G1");
    const model = createEmptyModel("WireNode");
    model.diagram.nodes = [source, resistor, ground];
    model.diagram.connections = [
      createConnection("c1", "wire", { node: "n1", port: "p" }, { node: "n2", port: "p" }),
      createConnection("c2", "wire", { node: "n1", port: "p" }, { node: "n3", port: "p" }),
    ];
    const analysis = analyseDiagram(model, index);
    const hub = analysis.connections.get("c1")?.wireHub;
    expect(hub).not.toBeNull();
    expect(analysis.connections.get("c2")?.wireHub).toEqual(hub);
    expect(analysis.connections.get("c1")?.domain).toBe("Electrical");
  });

  it("reports drag compatibility per port", () => {
    const source = createNodeFromBlock(block("VoltageSource"), { x: 0, y: 0 }, "n1", "V1");
    const motor = createNodeFromBlock(block("DCMotor"), { x: 240, y: 0 }, "n2", "M1");
    const model = createEmptyModel("Drag");
    model.diagram.nodes = [source, motor];
    const origin = portDescriptor(
      source,
      interfaceForNode(source, index),
      "p",
    );
    if (origin === null) {
      throw new Error("missing origin");
    }
    const states = dragCompatibility(model, index, origin);
    expect(states.get(portKey({ nodeId: "n2", portName: "p" }))).toBe("compatible");
    expect(states.get(portKey({ nodeId: "n2", portName: "shaft" }))).toBe("incompatible");
    expect(states.get(portKey({ nodeId: "n1", portName: "n" }))).toBe("incompatible");
    expect(states.get(portKey({ nodeId: "n1", portName: "p" }))).toBe("origin");
  });
});

describe("xyflow node types", () => {
  it("renders a subsystem as its own node type with its exposed ports", () => {
    const model = createEmptyModel("Subsystem");
    const host = createNodeFromBlock(block("C"), { x: 0, y: 0 }, "n1", "Plant");
    host.block = {
      subsystem: {
        ports: [
          {
            name: "shaft",
            kind: "power",
            domain: "Rotation",
            size: [],
            node: "n2",
            port: "a",
          },
          {
            name: "speed",
            kind: "signal",
            direction: "output",
            type: "Real",
            size: [],
            unit: "rad/s",
            node: "n3",
            port: "y",
          },
        ],
        diagram: { nodes: [], connections: [] },
      },
    };
    model.diagram.nodes = [host];
    const flow = buildDiagram(model, index, { nodes: [], connections: [] });
    expect(flow.nodes).toHaveLength(1);
    expect(flow.nodes[0]?.type).toBe("subsystem");
    const data = flow.nodes[0]?.data as { interface: { ports: unknown[] } };
    expect(data.interface.ports).toHaveLength(2);
  });
});

describe("anchors and paths", () => {
  it("anchors a bond just outside the circle edge of a junction", () => {
    const model = createEmptyModel("Anchor");
    const junction = createNodeFromBlock(block("C"), { x: 100, y: 100 }, "n1", "C1");
    junction.block = { junction: "0" };
    const resistor = createNodeFromBlock(block("Resistor"), { x: 300, y: 100 }, "n2", "R1");
    model.diagram.nodes = [junction, resistor];
    const bond = createConnection(
      "c1",
      "bond",
      { node: "n1" },
      { node: "n2", port: "p" },
    );
    model.diagram.connections = [bond];
    const anchors = connectionAnchors(model, index, bond);
    const centre = { x: 120 + NODE_HALF_SHIFT, y: 120 + NODE_HALF_SHIFT };
    const distance = Math.hypot(
      anchors.source.point.x - centre.x,
      anchors.source.point.y - centre.y,
    );
    expect(distance).toBeCloseTo(JUNCTION_RADIUS + JUNCTION_BOND_GAP, 5);
    expect(anchors.source.point.x).toBeGreaterThan(centre.x);
    expect(anchors.source.side).toBe("right");
    expect(anchors.target.point.x).toBe(300);
  });

  it("routes wires orthogonally and draws one half arrow and one causal bar", () => {
    const path = orthogonalPath(
      { point: { x: 10, y: 10 }, side: "right" },
      { point: { x: 210, y: 110 }, side: "left" },
    );
    expect(path).toContain("H");
    expect(path).toContain("V");
    expect(path).not.toContain("L");

    const star = hubPath({ x: 0, y: 0 }, { x: 50, y: 50 }, { x: 100, y: 0 });
    expect(star).toBe("M 0 0 H 50 V 50 H 100 V 0");

    const half = halfArrowPath({ x: 0, y: 0 }, { x: 100, y: 0 });
    expect(half.startsWith("M 100 0 L")).toBe(true);
    const arrow = arrowHeadPath({ x: 100, y: 0 }, { x: 0, y: 0 });
    expect(arrow.startsWith("M 0 0 L")).toBe(true);
    expect(arrow.endsWith("Z")).toBe(true);
    const stroke = causalStrokePath({ x: 50, y: 0 }, { x: 100, y: 0 });
    expect(stroke).toMatch(/^M 50 (?:6|-6) L 50 (?:-6|6)$/);
  });

  it("marks a right-angle corner with a square inside the wedge", () => {
    // An exact corner: up to the previous point, right to the next one.
    expect(
      rightAngleMarker({ x: 0, y: 0 }, { x: 0, y: 40 }, { x: 40, y: 40 }),
    ).toBe("M 0 30 L 10 30 L 10 40");

    // A hand-dragged corner a hair off square still counts; a shallow corner
    // does not, and neither does a straight or degenerate one.
    expect(
      rightAngleMarker({ x: -100, y: 1 }, { x: 0, y: 0 }, { x: 0, y: 40 }),
    ).not.toBeNull();
    expect(
      rightAngleMarker({ x: -100, y: 5 }, { x: 0, y: 0 }, { x: 0, y: 40 }),
    ).toBeNull();
    expect(
      rightAngleMarker({ x: 0, y: 0 }, { x: 50, y: 0 }, { x: 100, y: 0 }),
    ).toBeNull();
    expect(
      rightAngleMarker({ x: 10, y: 10 }, { x: 10, y: 10 }, { x: 30, y: 10 }),
    ).toBeNull();
  });
});
