/**
 * W2.2: subsystem grouping and path-aware editing.
 *
 * * `groupSelectionIntoSubsystem` moves only the selected nodes and the
 *   connections inside them, exposes cut connections as ports with
 *   identifier-safe unique names, and rebases the nested diagram;
 * * the store commits the grouping as one undo entry and routes edits through
 *   `activePath` so entering a subsystem edits its nested diagram.
 */

import { beforeEach, describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model, ModelConnection, ModelNode } from "../src/contracts/model";
import { groupSelectionIntoSubsystem } from "../src/editor/subsystemGroup";
import { interfaceForNode } from "../src/editor/nodeInterface";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import {
  createConnection,
  createEmptyModel,
  createNodeFromBlock,
} from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;
const index = buildCatalogIndex(catalog);

function block(name: string) {
  const entry = index.blocksByName.get(name);
  if (entry === undefined) {
    throw new Error(`catalog has no block ${name}`);
  }
  return entry;
}

function node(name: string, blockName: string, x: number, y: number, id: string): ModelNode {
  return createNodeFromBlock(block(blockName), { x, y }, id, name);
}

/**
 * n1 Motor (outside), n2 Gain source (outside), n3 Ground, n4 Damp1,
 * n5 FixHousing, n6 Gain2, n7 Gain3 (all inside).
 */
function groupingModel(): Model {
  const model = createEmptyModel("Grouping");
  model.diagram.nodes = [
    node("Motor1", "DCMotor", 0, 0, "n1"),
    node("Gain1", "Gain", 300, 0, "n2"),
    node("Ground1", "Ground", 0, 200, "n3"),
    node("Damp1", "RotationalDamper", 300, 200, "n4"),
    node("FixHousing", "FixedShaft", 500, 200, "n5"),
    node("Gain2", "Gain", 300, 60, "n6"),
    node("Gain3", "Gain", 500, 60, "n7"),
    node("VoltageSource1", "VoltageSource", 0, 400, "n8"),
  ];
  const connections: ModelConnection[] = [
    // power crossing into Ground1
    createConnection("c1", "wire", { node: "n1", port: "n" }, { node: "n3", port: "p" }),
    // power crossing out of Damp1
    createConnection("c2", "wire", { node: "n1", port: "shaft" }, { node: "n4", port: "a" }),
    // power entirely inside
    createConnection("c3", "wire", { node: "n4", port: "b" }, { node: "n5", port: "a" }),
    // signal crossing into Gain2
    createConnection("c4", "signal", { node: "n2", port: "y" }, { node: "n6", port: "u" }),
    // signal entirely inside
    createConnection("c5", "signal", { node: "n6", port: "y" }, { node: "n7", port: "u" }),
    // a second crossing to the same internal port: the port names must differ
    createConnection("c6", "wire", { node: "n8", port: "p" }, { node: "n3", port: "p" }),
  ];
  model.diagram.connections = connections;
  return model;
}

const SELECTED = ["n3", "n4", "n5", "n6", "n7"];

describe("create subsystem from selection", () => {
  it("moves only the selected nodes and the connections inside them", () => {
    const model = groupingModel();
    const result = groupSelectionIntoSubsystem({
      doc: model,
      index,
      nodeIds: SELECTED,
      id: "n9",
      name: "Subsystem1",
    });
    expect(result).not.toBeNull();
    if (result === null) {
      return;
    }

    // The parent keeps the two outside blocks plus the subsystem.
    expect(result.diagram.nodes.map((entry) => entry.name)).toEqual([
      "Motor1",
      "Gain1",
      "VoltageSource1",
      "Subsystem1",
    ]);
    expect(result.node.id).toBe("n9");
    expect(result.node.block).toHaveProperty("subsystem");
    expect(result.node.position).toEqual({ x: 320, y: 144 });

    const subsystem = result.node.block;
    if (!("subsystem" in subsystem)) {
      throw new Error("the new node is not a subsystem");
    }
    expect(subsystem.subsystem.diagram.nodes.map((entry) => entry.name)).toEqual([
      "Ground1",
      "Damp1",
      "FixHousing",
      "Gain2",
      "Gain3",
    ]);
    // The group's top-left is the nested origin.
    expect(subsystem.subsystem.diagram.nodes.map((entry) => entry.position)).toEqual([
      { x: 0, y: 140 },
      { x: 300, y: 140 },
      { x: 500, y: 140 },
      { x: 300, y: 0 },
      { x: 500, y: 0 },
    ]);
    expect(result.internalConnections.map((entry) => entry.id)).toEqual(["c3", "c5"]);

    // Every cut connection is rewritten to the subsystem and keeps its kind,
    // orientation and label; its outside route no longer applies.
    expect(result.diagram.connections).toHaveLength(4);
    const byId = new Map(result.diagram.connections.map((entry) => [entry.id, entry]));
    expect(byId.get("c1")?.to).toEqual({ node: "n9", port: "Ground1_p" });
    expect(byId.get("c1")?.from).toEqual({ node: "n1", port: "n" });
    expect(byId.get("c2")?.to).toEqual({ node: "n9", port: "Damp1_a" });
    expect(byId.get("c6")?.to).toEqual({ node: "n9", port: "Ground1_p2" });
    expect(byId.get("c4")?.to).toEqual({ node: "n9", port: "Gain2_u" });
    expect(byId.get("c4")?.from).toEqual({ node: "n2", port: "y" });
    for (const connection of result.diagram.connections) {
      expect(connection.route).toEqual([]);
    }

    expect(result.ports).toEqual([
      {
        name: "Ground1_p",
        kind: "power",
        domain: "Electrical",
        size: [],
        node: "n3",
        port: "p",
      },
      {
        name: "Damp1_a",
        kind: "power",
        domain: "Rotation",
        size: [],
        node: "n4",
        port: "a",
      },
      {
        name: "Gain2_u",
        kind: "signal",
        direction: "input",
        type: "Real",
        size: [],
        unit: null,
        node: "n6",
        port: "u",
      },
      {
        name: "Ground1_p2",
        kind: "power",
        domain: "Electrical",
        size: [],
        node: "n3",
        port: "p",
      },
    ]);
  });

  it("exposes an output with its direction and an internal route rebased", () => {
    const model = createEmptyModel("Output");
    model.diagram.nodes = [
      node("Gain1", "Gain", 100, 100, "n1"),
      node("Gain2", "Gain", 400, 100, "n2"),
      node("Gain3", "Gain", 700, 100, "n3"),
    ];
    const crossing = createConnection(
      "c1",
      "signal",
      { node: "n1", port: "y" },
      { node: "n2", port: "u" },
    );
    const internal = createConnection(
      "c2",
      "signal",
      { node: "n2", port: "y" },
      { node: "n3", port: "u" },
    );
    internal.route = [{ x: 600, y: 110 }];
    model.diagram.connections = [crossing, internal];

    const result = groupSelectionIntoSubsystem({
      doc: model,
      index,
      nodeIds: ["n2", "n3"],
      id: "n4",
      name: "Subsystem1",
    });
    if (result === null) {
      throw new Error("the grouping was refused");
    }
    expect(result.ports[0]).toMatchObject({
      name: "Gain2_u",
      kind: "signal",
      direction: "input",
    });
    // An internal signal port faces its internal input; an internal output
    // (the other end selected) exposes an output.
    expect(result.internalConnections[0]?.route).toEqual([{ x: 200, y: 10 }]);

    const outputModel = createEmptyModel("Output2");
    outputModel.diagram.nodes = [
      node("Gain1", "Gain", 100, 100, "n1"),
      node("Gain2", "Gain", 400, 100, "n2"),
    ];
    outputModel.diagram.connections = [
      createConnection("c9", "signal", { node: "n2", port: "y" }, { node: "n1", port: "u" }),
    ];
    const output = groupSelectionIntoSubsystem({
      doc: outputModel,
      index,
      nodeIds: ["n2"],
      id: "n3",
      name: "Subsystem1",
    });
    if (output === null) {
      throw new Error("the grouping was refused");
    }
    expect(output.ports[0]).toMatchObject({
      name: "Gain2_y",
      kind: "signal",
      direction: "output",
    });
    expect(output.diagram.connections[0]?.from).toEqual({ node: "n3", port: "Gain2_y" });
    expect(output.diagram.connections[0]?.to).toEqual({ node: "n1", port: "u" });
  });

  it("keeps subsystem ports visible through interfaceForNode", () => {
    const model = groupingModel();
    const result = groupSelectionIntoSubsystem({
      doc: model,
      index,
      nodeIds: SELECTED,
      id: "n9",
      name: "Subsystem1",
    });
    if (result === null) {
      throw new Error("the grouping was refused");
    }
    const iface = interfaceForNode(result.node, index);
    expect(iface.title).toBe("Subsystem");
    expect(iface.ports.map((port) => [port.name, port.kind, port.domain])).toEqual([
      ["Ground1_p", "power", "Electrical"],
      ["Damp1_a", "power", "Rotation"],
      ["Gain2_u", "input", "Generic"],
      ["Ground1_p2", "power", "Electrical"],
    ]);
  });
});

describe("the store groups with one undo entry", () => {
  beforeEach(() => {
    resetDocumentStore();
  });

  it("names subsystems uniquely and restores the document on undo", () => {
    useDocumentStore.getState().openDocument("demo", "Grouping", groupingModel());
    const before = useDocumentStore.getState().doc;
    const pastBefore = useDocumentStore.getState().past.length;

    useDocumentStore.getState().setSelection(SELECTED, []);
    const first = useDocumentStore.getState().createSubsystem(index);
    expect(first).toEqual({ ok: true });
    expect(useDocumentStore.getState().past).toHaveLength(pastBefore + 1);

    const after = useDocumentStore.getState().doc;
    const subsystem = after?.diagram.nodes.find((entry) => entry.name === "Subsystem1");
    expect(subsystem).toBeDefined();
    expect(useDocumentStore.getState().selection.nodes).toEqual([subsystem?.id]);

    useDocumentStore.getState().undo();
    expect(useDocumentStore.getState().doc).toEqual(before);
    expect(useDocumentStore.getState().past).toHaveLength(pastBefore);

    // A second grouping after undo gets the free name again; a fresh group
    // beside it gets Subsystem2.
    useDocumentStore.getState().redo();
    const other = useDocumentStore
      .getState()
      .doc?.diagram.nodes.find((entry) => entry.name === "Motor1");
    if (other === undefined) {
      throw new Error("Motor1 is missing");
    }
    useDocumentStore.getState().setSelection([other.id], []);
    useDocumentStore.getState().createSubsystem(index);
    expect(
      useDocumentStore.getState().doc?.diagram.nodes.map((entry) => entry.name),
    ).toContain("Subsystem2");
  });

  it("refuses an empty selection without touching the document", () => {
    useDocumentStore.getState().openDocument("demo", "Grouping", groupingModel());
    const before = useDocumentStore.getState().doc;
    const result = useDocumentStore.getState().createSubsystem(index);
    expect(result.ok).toBe(false);
    expect(useDocumentStore.getState().doc).toEqual(before);
    expect(useDocumentStore.getState().past).toHaveLength(0);
  });
});

describe("path-aware editing", () => {
  beforeEach(() => {
    resetDocumentStore();
    useDocumentStore.getState().openDocument("demo", "Grouping", groupingModel());
  });

  function enterGroupedSubsystem(): string {
    const store = useDocumentStore.getState();
    store.setSelection(SELECTED, []);
    store.createSubsystem(index);
    const subsystem = useDocumentStore
      .getState()
      .doc?.diagram.nodes.find((entry) => entry.name === "Subsystem1");
    if (subsystem === undefined) {
      throw new Error("the subsystem was not created");
    }
    expect(useDocumentStore.getState().enterSubsystem(subsystem.id)).toBe(true);
    return subsystem.id;
  }

  it("edits inside the nested diagram without changing the root", () => {
    const subsystemId = enterGroupedSubsystem();
    expect(useDocumentStore.getState().activePath).toEqual([subsystemId]);
    expect(useDocumentStore.getState().selection).toEqual({ nodes: [], connections: [] });

    const rootBefore = useDocumentStore.getState().doc;
    const added = useDocumentStore.getState().addBlock(block("Gain"), { x: 40, y: 40 });
    expect(added).not.toBeNull();
    if (added === null) {
      throw new Error("the block was not added");
    }
    expect(useDocumentStore.getState().selection.nodes).toEqual([added]);
    expect(useDocumentStore.getState().doc?.diagram.nodes).toHaveLength(4);

    const nested = useDocumentStore
      .getState()
      .doc?.diagram.nodes.find((entry) => entry.name === "Subsystem1");
    if (nested === undefined || !("subsystem" in nested.block)) {
      throw new Error("the nested diagram is missing");
    }
    expect(
      nested.block.subsystem.diagram.nodes.map((entry) => entry.name),
    ).toContain("Gain");

    // Moving and renaming stay inside this diagram too.
    useDocumentStore.getState().setNodePositions({ [added]: { x: 44, y: 48 } });
    const nestedAfterMove = useDocumentStore
      .getState()
      .doc?.diagram.nodes.find((entry) => entry.name === "Subsystem1");
    if (nestedAfterMove === undefined || !("subsystem" in nestedAfterMove.block)) {
      throw new Error("the subsystem disappeared");
    }
    const moved = nestedAfterMove.block.subsystem.diagram.nodes.find(
      (entry) => entry.id === added,
    );
    expect(moved?.position).toEqual({ x: 44, y: 48 });
    expect(useDocumentStore.getState().renameNode(added, "NestedGain")).toEqual({
      ok: true,
    });

    useDocumentStore.getState().leaveSubsystem();
    expect(useDocumentStore.getState().activePath).toEqual([]);
    expect(
      useDocumentStore.getState().doc?.diagram.nodes.map((entry) => entry.id),
    ).toEqual(rootBefore?.diagram.nodes.map((entry) => entry.id));
    expect(useDocumentStore.getState().doc?.diagram.connections).toEqual(
      rootBefore?.diagram.connections,
    );

    // Re-entering shows the edit; undoing the three nested edits (rename,
    // move, add) restores the nested diagram and keeps the path.
    expect(useDocumentStore.getState().enterSubsystem(subsystemId)).toBe(true);
    useDocumentStore.getState().undo();
    useDocumentStore.getState().undo();
    useDocumentStore.getState().undo();
    expect(useDocumentStore.getState().activePath).toEqual([subsystemId]);
    const nestedAfterUndo = useDocumentStore
      .getState()
      .doc?.diagram.nodes.find((entry) => entry.id === subsystemId);
    if (nestedAfterUndo === undefined || !("subsystem" in nestedAfterUndo.block)) {
      throw new Error("the subsystem disappeared");
    }
    expect(
      nestedAfterUndo.block.subsystem.diagram.nodes.some((entry) => entry.id === added),
    ).toBe(false);
  });

  it("clamps the path when undo removes the entered subsystem", () => {
    const subsystemId = enterGroupedSubsystem();
    // Undo the grouping while inside it: the path can no longer resolve.
    useDocumentStore.getState().undo();
    expect(useDocumentStore.getState().activePath).toEqual([]);
    expect(
      useDocumentStore.getState().doc?.diagram.nodes.some((entry) => entry.id === subsystemId),
    ).toBe(false);
  });
});
