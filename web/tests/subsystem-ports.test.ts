/**
 * Subsystem port terminals: the interface of a subsystem, seen and edited
 * from inside it.
 *
 * * placement: inputs left, outputs right, power on the outside block's side,
 *   in the outside order; `ui.position` wins; the "+ kind" ghosts;
 * * the outside-connection lookup and its terminal text;
 * * the flow: one terminal per port, a boundary wire to the internal port and
 *   a badge on that port;
 * * the store commands (expose, rename, delete, move, reveal), each one undo step.
 */

import { beforeEach, describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import fixtureJson from "../../contracts/fixtures/model/valid/model.subsystem-port-ui.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model, ModelSubsystemPort } from "../src/contracts/model";
import { applySelection, buildDiagram } from "../src/editor/buildFlow";
import { descriptorForPort, interfaceForNode } from "../src/editor/nodeInterface";
import { activeModel } from "../src/editor/subsystemPath";
import {
  contentBox,
  ghostId,
  outsideText,
  placeTerminals,
  subsystemBoundary,
  TERMINAL_GAP,
  terminalId,
} from "../src/editor/subsystemBoundary";
import { exposeIssue, proposePortName } from "../src/editor/subsystemPorts";
import type { TerminalNodeData } from "../src/editor/nodes/PortTerminal";
import type { BlockNodeData } from "../src/editor/nodes/BlockNode";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import {
  resetDocumentStore,
  subsystemPortDeleteImpact,
  useDocumentStore,
} from "../src/state/documentStore";
import { createConnection, createNodeFromBlock } from "../src/state/modelFactory";

const index = buildCatalogIndex(catalogJson as unknown as Catalog);
const NONE = { nodes: [], connections: [] };

function fixture(): Model {
  return JSON.parse(JSON.stringify(fixtureJson)) as Model;
}

function block(name: string) {
  const entry = index.blocksByName.get(name);
  if (entry === undefined) {
    throw new Error(`the catalog has no block ${name}`);
  }
  return entry;
}

function plantPorts(doc: Model): ModelSubsystemPort[] {
  const plant = doc.diagram.nodes.find((node) => node.id === "plant");
  if (plant === undefined || !("subsystem" in plant.block)) {
    throw new Error("no Plant subsystem");
  }
  return plant.block.subsystem.ports;
}

function plantInner(doc: Model) {
  const plant = doc.diagram.nodes.find((node) => node.id === "plant");
  if (plant === undefined || !("subsystem" in plant.block)) {
    throw new Error("no Plant subsystem");
  }
  return plant.block.subsystem.diagram;
}

function open(doc: Model = fixture()): void {
  resetDocumentStore();
  useDocumentStore.getState().openDocument("demo", "Ports", doc);
  expect(useDocumentStore.getState().enterSubsystem("plant")).toBe(true);
}

function store() {
  return useDocumentStore.getState();
}

function doc(): Model {
  const value = store().doc;
  if (value === null) {
    throw new Error("no document");
  }
  return value;
}

function descriptor(nodeId: string, port: string | null) {
  const inner = activeModel(doc(), store().activePath);
  const result = inner === null ? null : descriptorForPort(inner.diagram.nodes, index, nodeId, port);
  if (result === null) {
    throw new Error(`no port ${nodeId}.${port}`);
  }
  return result;
}

beforeEach(() => resetDocumentStore());

describe("terminal placement", () => {
  const box = { x: 0, y: 0, w: 400, h: 200 };
  const widths = new Map([
    ["a", 90],
    ["b", 90],
    ["y", 100],
    ["p", 80],
    ["q", 80],
  ]);
  const signal = (name: string, direction: "input" | "output"): ModelSubsystemPort => ({
    name,
    kind: "signal",
    direction,
    type: "Real",
    size: [],
    unit: null,
    node: "n1",
    port: name,
  });
  const power = (name: string): ModelSubsystemPort => ({
    name,
    kind: "power",
    domain: "Electrical",
    size: [1],
    node: "n2",
    port: name,
  });

  it("puts inputs on the left, outputs on the right and power on the outside side", () => {
    const ports = [signal("a", "input"), signal("y", "output"), power("p"), power("q")];
    const outer = new Map([
      ["a", { side: "left" as const, offset: 40 }],
      ["y", { side: "right" as const, offset: 40 }],
      ["p", { side: "left" as const, offset: 70 }],
      ["q", { side: "bottom" as const, offset: 80 }],
    ]);
    const { terminals } = placeTerminals({ ports, outer }, box, widths);
    const a = terminals.get("a");
    const y = terminals.get("y");
    const p = terminals.get("p");
    const q = terminals.get("q");
    expect(a?.side).toBe("left");
    expect(a?.position.x).toBe(box.x - TERMINAL_GAP - 90);
    expect(y?.side).toBe("right");
    expect(y?.position.x).toBe(box.x + box.w + TERMINAL_GAP);
    expect(p?.side).toBe("left");
    // The power port on the bottom of the outside block sits below the content.
    expect(q?.side).toBe("bottom");
    expect(q?.position.y).toBeGreaterThan(box.y + box.h);
    // a and p share the left edge, in the outside order (a above p).
    expect(a!.position.y).toBeLessThan(p!.position.y);
    expect(a?.stored).toBe(false);
  });

  it("stacks one edge in the outside block's order and centres it on the content", () => {
    const ports = [signal("a", "input"), signal("b", "input")];
    const outer = new Map([
      ["a", { side: "left" as const, offset: 90 }],
      ["b", { side: "left" as const, offset: 30 }],
    ]);
    const { terminals } = placeTerminals({ ports, outer }, box, widths);
    const a = terminals.get("a")!;
    const b = terminals.get("b")!;
    expect(b.position.y).toBeLessThan(a.position.y);
    const middle = (a.position.y + b.position.y) / 2 + a.height / 2;
    expect(middle).toBeCloseTo(box.y + box.h / 2, 5);
  });

  it("keeps a stored ui.position and leaves it out of the stack", () => {
    const stored: ModelSubsystemPort = { ...signal("a", "input"), ui: { position: { x: -500, y: 33 } } };
    const ports = [stored, signal("b", "input")];
    const { terminals } = placeTerminals({ ports, outer: new Map() }, box, widths);
    expect(terminals.get("a")).toMatchObject({ position: { x: -500, y: 33 }, stored: true });
    // b alone on the left edge: centred.
    const b = terminals.get("b")!;
    expect(b.position.y + b.height / 2).toBeCloseTo(box.h / 2, 5);
  });

  it("puts the + input ghost on the left and + output / + power on the right", () => {
    const { ghosts } = placeTerminals({ ports: [], outer: new Map() }, box, widths);
    expect(ghosts.get("input")!.x).toBeLessThan(box.x);
    expect(ghosts.get("output")!.x).toBeGreaterThan(box.x + box.w);
    expect(ghosts.get("power")!.y).toBeGreaterThan(ghosts.get("output")!.y);
  });

  it("boxes the content, and an empty diagram still gets a box", () => {
    expect(contentBox([{ x: 10, y: 20, w: 30, h: 40 }, { x: 100, y: 0, w: 10, h: 10 }])).toEqual({
      x: 10,
      y: 0,
      w: 100,
      h: 60,
    });
    expect(contentBox([]).w).toBeGreaterThan(0);
  });
});

describe("outside connections", () => {
  it("names where each exposed port goes in the parent diagram", () => {
    const model = fixture();
    const boundary = subsystemBoundary(model, ["plant"], index);
    expect(boundary).not.toBeNull();
    expect(boundary!.nodeName).toBe("Plant");
    expect(boundary!.outside.get("u")).toEqual([{ connectionId: "c1", peer: "Step1.y" }]);
    expect(boundary!.outside.get("vc")).toEqual([{ connectionId: "c2", peer: "R2.p" }]);
    expect(outsideText("input", boundary!.outside.get("u")!)).toBe("← Step1.y");
    expect(outsideText("power", boundary!.outside.get("vc")!)).toBe("↔ R2.p");
    // The outside block's edges: the signal input on the left.
    expect(boundary!.outer.get("u")?.side).toBe("left");
  });

  it("shows the first connection plus +N, and unconnected without any", () => {
    const links = [
      { connectionId: "c1", peer: "PD.q" },
      { connectionId: "c2", peer: "Log.u" },
      { connectionId: "c3", peer: "Scope.u" },
    ];
    expect(outsideText("output", links)).toBe("→ PD.q +2");
    expect(outsideText("output", [])).toBe("unconnected");
  });

  it("is null at the root", () => {
    expect(subsystemBoundary(fixture(), [], index)).toBeNull();
  });
});

describe("the inner flow", () => {
  it("has one terminal per port, a boundary wire and a badge on the internal port", () => {
    const model = fixture();
    const view = activeModel(model, ["plant"])!;
    const boundary = subsystemBoundary(model, ["plant"], index);
    const flow = buildDiagram(view, index, NONE, null, true, boundary);
    const terminals = flow.nodes.filter((node) => node.type === "terminal");
    expect(terminals.map((node) => node.id)).toEqual([terminalId("u"), terminalId("vc")]);
    const u = terminals[0]!.data as TerminalNodeData;
    expect(u).toMatchObject({ kind: "input", outside: "← Step1.y", mapsTo: "V1.u", connected: true });
    // ui.position is used as is.
    expect(terminals[0]!.position).toEqual({ x: -140, y: 60 });
    const vc = terminals[1]!.data as TerminalNodeData;
    expect(vc).toMatchObject({ kind: "power", domain: "Electrical", mapsTo: "C1.p" });
    expect(flow.boundaryEdges?.map((edge) => [edge.source, edge.target, edge.targetHandle])).toEqual([
      [terminalId("u"), "p1", "u"],
      [terminalId("vc"), "p3", "p"],
    ]);
    const v1 = flow.nodes.find((node) => node.id === "p1")!.data as BlockNodeData;
    expect(v1.exposed).toEqual({ u: "u" });
    const r1 = flow.nodes.find((node) => node.id === "p2")!.data as BlockNodeData;
    expect(r1.exposed).toEqual({});
    expect(flow.nodes.filter((node) => node.type === "terminalGhost").map((node) => node.id)).toEqual([
      ghostId("input"),
      ghostId("output"),
      ghostId("power"),
    ]);
  });

  it("selects a terminal through applySelection like any node", () => {
    const model = fixture();
    const view = activeModel(model, ["plant"])!;
    const flow = buildDiagram(view, index, NONE, null, true, subsystemBoundary(model, ["plant"], index));
    const selected = applySelection(flow, { nodes: [terminalId("u")], connections: [] }, new WeakMap());
    expect(selected.nodes.find((node) => node.id === terminalId("u"))?.selected).toBe(true);
    // Unchanged elements keep their objects.
    expect(selected.nodes.find((node) => node.id === "p1")).toBe(flow.nodes.find((node) => node.id === "p1"));
    expect(selected.boundaryEdges).toBe(flow.boundaryEdges);
  });

  it("has no terminals at the root", () => {
    const flow = buildDiagram(fixture(), index, NONE);
    expect(flow.nodes.some((node) => node.type === "terminal")).toBe(false);
    expect(flow.boundaryEdges).toBeUndefined();
  });
});

describe("exposing an internal port", () => {
  it("adds a port shaped like the internal one, on the outer block too, as one undo step", () => {
    const model = fixture();
    // An unconnected Gain inside the subsystem.
    plantInner(model).nodes.push(createNodeFromBlock(block("Gain"), { x: 40, y: 300 }, "p9", "K1"));
    open(model);
    const before = store().past.length;
    const result = store().exposeSubsystemPort(index, descriptor("p9", "y"));
    expect(result).toEqual({ ok: true, name: "y" });
    expect(store().past.length).toBe(before + 1);
    const port = plantPorts(doc()).find((entry) => entry.name === "y");
    expect(port).toMatchObject({ kind: "signal", direction: "output", type: "Real", node: "p9", port: "y" });
    // The outer block's interface has it at once.
    const plant = doc().diagram.nodes.find((node) => node.id === "plant")!;
    expect(interfaceForNode(plant, index).ports.map((entry) => entry.name)).toContain("y");
    // The new terminal is selected for a rename.
    expect(store().selection.nodes).toEqual([terminalId("y")]);

    // The input of the same block: `u` is taken, so the node name qualifies it.
    expect(store().exposeSubsystemPort(index, descriptor("p9", "u"), "input")).toEqual({
      ok: true,
      name: "K1_u",
    });
    store().undo();
    store().undo();
    expect(plantPorts(doc()).map((entry) => entry.name)).toEqual(["u", "vc"]);
  });

  it("proposes the port name, made unique with the node name", () => {
    const ports = plantPorts(fixture());
    expect(proposePortName(ports, "K1", "y")).toBe("y");
    expect(proposePortName(ports, "K1", "u")).toBe("K1_u");
    expect(proposePortName([...ports, { ...ports[0]!, name: "K1_u" }], "K1", "u")).toBe("K1_u2");
    expect(proposePortName(ports, "J1", null)).toBe("J1");
  });

  it("takes a power port's domain and size from the internal port", () => {
    const model = fixture();
    plantInner(model).nodes.push(createNodeFromBlock(block("Resistor"), { x: 40, y: 300 }, "p9", "R9"));
    open(model);
    expect(store().exposeSubsystemPort(index, descriptor("p9", "n"), "power")).toEqual({ ok: true, name: "n" });
    expect(plantPorts(doc()).at(-1)).toEqual({
      name: "n",
      kind: "power",
      domain: "Electrical",
      size: [1],
      node: "p9",
      port: "n",
    });
  });

  it("exposes a junction with the junction face", () => {
    const model = fixture();
    plantInner(model).nodes.push({
      id: "p9",
      name: "J0",
      block: { junction: "0" },
      position: { x: 0, y: 0 },
    });
    open(model);
    expect(store().exposeSubsystemPort(index, descriptor("p9", null))).toEqual({ ok: true, name: "J0" });
    expect(plantPorts(doc()).at(-1)).toMatchObject({ kind: "power", domain: "Generic", node: "p9", port: "junction" });
  });

  it("refuses an exposed port, a driven input, a bonded power port and the wrong + kind", () => {
    const model = fixture();
    const inner = plantInner(model);
    inner.nodes.push(
      createNodeFromBlock(block("Gain"), { x: 0, y: 300 }, "p9", "K1"),
      createNodeFromBlock(block("Constant"), { x: 0, y: 400 }, "p10", "One"),
      createNodeFromBlock(block("C"), { x: 0, y: 500 }, "p11", "Cb"),
      { id: "p12", name: "J1", block: { junction: "1" }, position: { x: 0, y: 600 } },
    );
    inner.connections.push(
      createConnection("pc9", "signal", { node: "p10", port: "y" }, { node: "p9", port: "u" }),
      createConnection("pc10", "bond", { node: "p11", port: "p" }, { node: "p12" }),
    );
    open(model);
    const refuse = (nodeId: string, port: string | null, wanted?: "input" | "output" | "power") =>
      store().exposeSubsystemPort(index, descriptor(nodeId, port), wanted);
    expect(refuse("p1", "u").error).toBe("V1.u is already exposed as u.");
    expect(refuse("p9", "u").error).toMatch(/^K1\.u already has a source inside the subsystem \(One\.y\)/);
    expect(refuse("p11", "p").error).toMatch(/^Cb\.p already has a bond inside the subsystem/);
    expect(refuse("p9", "y", "input").error).toBe(
      "+ input exposes a signal input; K1.y is a signal output.",
    );
    // A wired power port can be exposed: wires join into one node.
    expect(refuse("p2", "n").ok).toBe(true);
    // The junction keeps any number of bonds.
    expect(refuse("p12", null).ok).toBe(true);
  });

  it("refuses at the root", () => {
    resetDocumentStore();
    store().openDocument("demo", "Ports", fixture());
    const step = descriptorForPort(doc().diagram.nodes, index, "n1", "y")!;
    expect(store().exposeSubsystemPort(index, step).ok).toBe(false);
  });

  it("checks the same rules without the store", () => {
    const model = fixture();
    const inner = activeModel(model, ["plant"])!;
    const v1u = descriptorForPort(inner.diagram.nodes, index, "p1", "u")!;
    expect(exposeIssue(inner.diagram, plantPorts(model), v1u)).toBe("V1.u is already exposed as u.");
    expect(exposeIssue(inner.diagram, [], v1u, "input")).toBeNull();
  });
});

describe("renaming an exposed port", () => {
  it("renames the port and the outside connections in one undo step", () => {
    open();
    store().setSelection([terminalId("u")], []);
    const before = store().past.length;
    expect(store().renameSubsystemPort("u", "v_ref")).toEqual({ ok: true });
    expect(store().past.length).toBe(before + 1);
    expect(plantPorts(doc()).map((port) => port.name)).toEqual(["v_ref", "vc"]);
    expect(doc().diagram.connections.find((c) => c.id === "c1")?.to).toEqual({ node: "plant", port: "v_ref" });
    // The selection follows the terminal.
    expect(store().selection.nodes).toEqual([terminalId("v_ref")]);
    store().undo();
    expect(plantPorts(doc()).map((port) => port.name)).toEqual(["u", "vc"]);
    expect(doc().diagram.connections.find((c) => c.id === "c1")?.to).toEqual({ node: "plant", port: "u" });
  });

  it("refuses an invalid or taken name", () => {
    open();
    expect(store().renameSubsystemPort("u", "vc").error).toBe('The subsystem already has a port named "vc".');
    expect(store().renameSubsystemPort("u", "2x").error).toMatch(/^Port names start with a letter/);
    expect(store().renameSubsystemPort("u", "").error).toBe("Enter a port name.");
    expect(store().past.length).toBe(0);
  });

  it("follows into a port one level up that exposes this one", () => {
    // Wrap the fixture's root content in an Outer subsystem exposing Plant.u.
    const model = fixture();
    const inner = JSON.parse(JSON.stringify(model.diagram)) as Model["diagram"];
    inner.connections = inner.connections.filter((connection) => connection.id !== "c1");
    inner.nodes = inner.nodes.filter((node) => node.id !== "n1");
    model.diagram = {
      nodes: [
        {
          id: "outer",
          name: "Outer",
          block: {
            subsystem: {
              ports: [
                { name: "drive", kind: "signal", direction: "input", type: "Real", size: [], unit: null, node: "plant", port: "u" },
              ],
              diagram: inner,
            },
          },
          position: { x: 0, y: 0 },
        },
      ],
      connections: [],
    };
    resetDocumentStore();
    store().openDocument("demo", "Nested", model);
    store().enterSubsystem("outer");
    store().enterSubsystem("plant");
    expect(store().renameSubsystemPort("u", "w")).toEqual({ ok: true });
    const outer = doc().diagram.nodes[0]!;
    expect("subsystem" in outer.block && outer.block.subsystem.ports[0]?.port).toBe("w");
    // Deleting it is refused while Outer exposes it.
    expect(store().deleteSubsystemPorts(["w"]).error).toBe(
      "w is exposed again by Outer as drive; delete that port first.",
    );
  });
});

describe("deleting an exposed port", () => {
  it("removes the port and its outside connections (and their probe links) in one undo step", () => {
    const model = fixture();
    model.diagram.probes = [
      {
        id: "s1",
        name: "Scope",
        kind: "block",
        position: { x: 0, y: 0 },
        panelPosition: { x: 0, y: 0 },
        size: { width: 380, height: 240 },
        open: false,
        links: [{ id: "pl1", connection: "c1", signals: ["Step1/y"] }],
        panels: [],
      },
    ];
    open(model);
    expect(subsystemPortDeleteImpact(doc(), ["plant"], ["u"]).map((c) => c.id)).toEqual(["c1"]);
    const before = store().past.length;
    expect(store().deleteSubsystemPorts(["u"])).toEqual({ ok: true });
    expect(store().past.length).toBe(before + 1);
    expect(plantPorts(doc()).map((port) => port.name)).toEqual(["vc"]);
    expect(doc().diagram.connections.map((c) => c.id)).toEqual(["c2", "c3"]);
    expect(doc().diagram.probes?.[0]?.links).toEqual([]);
    store().undo();
    expect(plantPorts(doc()).map((port) => port.name)).toEqual(["u", "vc"]);
    expect(doc().diagram.connections.map((c) => c.id)).toEqual(["c1", "c2", "c3"]);
    expect(doc().diagram.probes?.[0]?.links).toHaveLength(1);
  });

  it("deletes selected terminals together with the rest of the selection", () => {
    open();
    store().setSelection([terminalId("vc"), "p4"], []);
    expect(store().selection.nodes).toEqual([terminalId("vc"), "p4"]);
    store().deleteSelection();
    expect(plantPorts(doc()).map((port) => port.name)).toEqual(["u"]);
    expect(plantInner(doc()).nodes.map((node) => node.id)).not.toContain("p4");
    expect(doc().diagram.connections.map((c) => c.id)).toEqual(["c1", "c3"]);
    store().undo();
    expect(plantPorts(doc()).map((port) => port.name)).toEqual(["u", "vc"]);
    expect(plantInner(doc()).nodes.map((node) => node.id)).toContain("p4");
  });

  it("drops a deleted terminal from the selection, and undo of a create drops it too", () => {
    open();
    store().setSelection([terminalId("vc")], []);
    store().deleteSubsystemPorts(["vc"]);
    expect(store().selection.nodes).toEqual([]);
    // A terminal id is not selectable at the root.
    store().leaveSubsystem();
    store().setSelection([terminalId("u")], []);
    expect(store().selection.nodes).toEqual([]);
  });
});

describe("moving a terminal and revealing its outside connection", () => {
  it("stores ui.position; a drag is one undo step", () => {
    open();
    store().beginGesture("node-drag");
    store().setSubsystemPortPositions({ vc: { x: 700, y: 10 } });
    store().setSubsystemPortPositions({ vc: { x: 720.04, y: 20 } });
    store().endGesture();
    expect(plantPorts(doc())[1]?.ui).toEqual({ position: { x: 720, y: 20 } });
    store().undo();
    expect(plantPorts(doc())[1]?.ui).toBeUndefined();
  });

  it("leaves the subsystem and selects the outside connections", () => {
    open();
    expect(store().revealSubsystemPort("vc")).toEqual({ nodeId: "plant", connections: ["c2"] });
    expect(store().activePath).toEqual([]);
    expect(store().selection).toEqual({ nodes: [], connections: ["c2"] });
  });

  it("selects the subsystem node when the port is unconnected", () => {
    const model = fixture();
    model.diagram.connections = model.diagram.connections.filter((c) => c.id !== "c2");
    open(model);
    expect(store().revealSubsystemPort("vc")).toEqual({ nodeId: "plant", connections: [] });
    expect(store().selection).toEqual({ nodes: ["plant"], connections: [] });
  });
});
