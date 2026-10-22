/**
 * The document store (plan 7.4): ten-operation undo/redo, the 200-entry
 * history, gesture coalescing, copy/paste renaming, bond reversal, and a
 * selection that is never part of the history.
 */

import { beforeEach, describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model } from "../src/contracts/model";
import { interfaceForNode, portDescriptor } from "../src/editor/nodeInterface";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import {
  HISTORY_LIMIT,
  resetDocumentStore,
  useDocumentStore,
} from "../src/state/documentStore";
import {
  createConnection,
  createEmptyModel,
  createJunctionNode,
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

function openEmpty(): void {
  useDocumentStore.getState().openDocument("demo", "StoreTest", createEmptyModel("StoreTest"));
}

function descriptor(nodeId: string, portName: string | null) {
  const state = useDocumentStore.getState();
  const node = state.doc?.diagram.nodes.find((entry) => entry.id === nodeId);
  if (node === undefined) {
    throw new Error(`no node ${nodeId}`);
  }
  const result = portDescriptor(node, interfaceForNode(node, index), portName);
  if (result === null) {
    throw new Error(`no port ${String(portName)} on ${nodeId}`);
  }
  return result;
}

beforeEach(() => {
  resetDocumentStore();
  openEmpty();
});

describe("undo and redo", () => {
  it("undoes and redoes ten operations", () => {
    const names = ["Se", "C", "I", "R", "Gain", "Sum", "Mass", "Spring", "Inertia", "DCMotor"];
    for (const [position, name] of names.entries()) {
      useDocumentStore.getState().addBlock(block(name), { x: position * 10, y: 0 });
    }
    const store = useDocumentStore.getState();
    expect(store.doc?.diagram.nodes).toHaveLength(10);
    expect(store.past).toHaveLength(10);

    for (let step = 0; step < 10; step += 1) {
      useDocumentStore.getState().undo();
    }
    expect(useDocumentStore.getState().doc?.diagram.nodes).toHaveLength(0);
    expect(useDocumentStore.getState().past).toHaveLength(0);
    expect(useDocumentStore.getState().future).toHaveLength(10);

    for (let step = 0; step < 10; step += 1) {
      useDocumentStore.getState().redo();
    }
    const nodes = useDocumentStore.getState().doc?.diagram.nodes ?? [];
    expect(nodes.map((node) => node.name)).toEqual(names);
    expect(useDocumentStore.getState().past).toHaveLength(10);
    expect(useDocumentStore.getState().future).toHaveLength(0);
  });

  it("coalesces a node drag into one history entry", () => {
    const id = useDocumentStore.getState().addBlock(block("Gain"), { x: 10, y: 10 });
    expect(id).not.toBeNull();
    const store = useDocumentStore.getState();
    expect(store.past).toHaveLength(1);

    store.beginGesture("node-drag");
    useDocumentStore.getState().setNodePositions({ [id ?? ""]: { x: 20, y: 15 } });
    useDocumentStore.getState().setNodePositions({ [id ?? ""]: { x: 40, y: 30 } });
    useDocumentStore.getState().setNodePositions({ [id ?? ""]: { x: 60, y: 45 } });
    useDocumentStore.getState().endGesture();

    expect(useDocumentStore.getState().past).toHaveLength(2);
    const moved = useDocumentStore
      .getState()
      .doc?.diagram.nodes.find((node) => node.id === id);
    expect(moved?.position).toEqual({ x: 60, y: 45 });

    useDocumentStore.getState().undo();
    const back = useDocumentStore.getState().doc?.diagram.nodes.find((node) => node.id === id);
    expect(back?.position).toEqual({ x: 10, y: 10 });

    useDocumentStore.getState().redo();
    const again = useDocumentStore.getState().doc?.diagram.nodes.find((node) => node.id === id);
    expect(again?.position).toEqual({ x: 60, y: 45 });
  });

  it("caps the history at 200 entries", () => {
    const blocks = ["Se", "C", "I", "R", "Gain"];
    for (let index = 0; index < HISTORY_LIMIT + 5; index += 1) {
      useDocumentStore
        .getState()
        .addBlock(block(blocks[index % blocks.length] ?? "Gain"), { x: index, y: 0 });
    }
    expect(useDocumentStore.getState().past).toHaveLength(HISTORY_LIMIT);
    for (let step = 0; step < HISTORY_LIMIT; step += 1) {
      useDocumentStore.getState().undo();
    }
    expect(useDocumentStore.getState().doc?.diagram.nodes).toHaveLength(5);
  });

  it("keeps selection and the clipboard out of the history", () => {
    const id = useDocumentStore.getState().addBlock(block("C"), { x: 0, y: 0 });
    const store = useDocumentStore.getState();
    expect(store.past).toHaveLength(1);
    store.setSelection([id ?? ""], []);
    expect(useDocumentStore.getState().past).toHaveLength(1);
    useDocumentStore.getState().copySelection();
    expect(useDocumentStore.getState().past).toHaveLength(1);
    expect(useDocumentStore.getState().clipboard.nodes).toHaveLength(1);

    useDocumentStore.getState().undo();
    expect(useDocumentStore.getState().doc?.diagram.nodes).toHaveLength(0);
    expect(useDocumentStore.getState().selection.nodes).toHaveLength(0);
  });
});

describe("connections", () => {
  it("adds a wire and deletes it with its node in one step", () => {
    useDocumentStore.getState().addBlock(block("DCMotor"), { x: 0, y: 0 });
    useDocumentStore.getState().addBlock(block("FixedShaft"), { x: 200, y: 0 });
    const [motor, fixed] = useDocumentStore.getState().doc?.diagram.nodes ?? [];
    if (motor === undefined || fixed === undefined) {
      throw new Error("nodes missing");
    }
    const result = useDocumentStore
      .getState()
      .connect(descriptor(motor.id, "shaft"), descriptor(fixed.id, "a"));
    expect(result).toMatchObject({ ok: true, kind: "wire" });
    expect(useDocumentStore.getState().doc?.diagram.connections).toHaveLength(1);

    useDocumentStore.getState().setSelection([motor.id], []);
    useDocumentStore.getState().deleteSelection();
    expect(useDocumentStore.getState().doc?.diagram.nodes).toHaveLength(1);
    expect(useDocumentStore.getState().doc?.diagram.connections).toHaveLength(0);

    useDocumentStore.getState().undo();
    expect(useDocumentStore.getState().doc?.diagram.nodes).toHaveLength(2);
    expect(useDocumentStore.getState().doc?.diagram.connections).toHaveLength(1);
  });

  it("returns the exact refusal from the rule engine", () => {
    useDocumentStore.getState().addBlock(block("VoltageSource"), { x: 0, y: 0 });
    useDocumentStore.getState().addBlock(block("DCMotor"), { x: 200, y: 0 });
    const [source, motor] = useDocumentStore.getState().doc?.diagram.nodes ?? [];
    if (source === undefined || motor === undefined) {
      throw new Error("nodes missing");
    }
    const result = useDocumentStore
      .getState()
      .connect(descriptor(source.id, "p"), descriptor(motor.id, "shaft"));
    expect(result).toEqual({
      ok: false,
      reason: "Electrical port cannot connect to Rotation; use a converter (DC motor, EM converter)",
    });
    expect(useDocumentStore.getState().doc?.diagram.connections).toHaveLength(0);
  });

  it("reverses a bond and its route", () => {
    const source = createNodeFromBlock(block("Se"), { x: 0, y: 0 }, "n1", "Se1");
    const capacitor = createNodeFromBlock(block("C"), { x: 200, y: 0 }, "n2", "C1");
    const bond = createConnection(
      "c1",
      "bond",
      { node: "n1", port: "p" },
      { node: "n2", port: "p" },
    );
    bond.route = [
      { x: 80, y: 20 },
      { x: 140, y: 20 },
    ];
    const model: Model = createEmptyModel("Reverse");
    model.diagram.nodes = [source, capacitor];
    model.diagram.connections = [bond];
    useDocumentStore.getState().openDocument("demo", "Reverse", model);

    useDocumentStore.getState().reverseConnection("c1");
    const reversed = useDocumentStore.getState().doc?.diagram.connections[0];
    expect(reversed?.from).toEqual({ node: "n2", port: "p" });
    expect(reversed?.to).toEqual({ node: "n1", port: "p" });
    expect(reversed?.route).toEqual([
      { x: 140, y: 20 },
      { x: 80, y: 20 },
    ]);

    useDocumentStore.getState().undo();
    expect(useDocumentStore.getState().doc?.diagram.connections[0]?.from).toEqual({
      node: "n1",
      port: "p",
    });
  });
});

describe("copy and paste", () => {
  it("renames instances and remaps the internal connection", () => {
    useDocumentStore.getState().addBlock(block("DCMotor"), { x: 0, y: 0 });
    useDocumentStore.getState().addBlock(block("FixedShaft"), { x: 200, y: 0 });
    const [motor, fixed] = useDocumentStore.getState().doc?.diagram.nodes ?? [];
    if (motor === undefined || fixed === undefined) {
      throw new Error("nodes missing");
    }
    useDocumentStore.getState().connect(descriptor(motor.id, "shaft"), descriptor(fixed.id, "a"));
    useDocumentStore.getState().setSelection([motor.id, fixed.id], []);
    useDocumentStore.getState().copySelection();
    useDocumentStore.getState().paste();

    const doc = useDocumentStore.getState().doc;
    expect(doc?.diagram.nodes.map((node) => node.name)).toEqual([
      "DCMotor",
      "FixedShaft",
      "DCMotor2",
      "FixedShaft2",
    ]);
    expect(doc?.diagram.connections).toHaveLength(2);
    const pastedMotor = doc?.diagram.nodes.find((node) => node.name === "DCMotor2");
    const pastedFixed = doc?.diagram.nodes.find((node) => node.name === "FixedShaft2");
    const pastedConnection = doc?.diagram.connections[1];
    expect(pastedConnection?.from.node).toBe(pastedMotor?.id);
    expect(pastedConnection?.to.node).toBe(pastedFixed?.id);
    expect(pastedConnection?.id).not.toBe(doc?.diagram.connections[0]?.id);
    expect(pastedMotor?.position).toEqual({ x: 24, y: 24 });

    useDocumentStore.getState().undo();
    expect(useDocumentStore.getState().doc?.diagram.nodes).toHaveLength(2);
    expect(useDocumentStore.getState().doc?.diagram.connections).toHaveLength(1);
  });

  it("picks the next free number when the copy name is taken", () => {
    useDocumentStore.getState().addBlock(block("Gain"), { x: 0, y: 0 });
    const first = useDocumentStore.getState().doc?.diagram.nodes[0];
    if (first === undefined) {
      throw new Error("node missing");
    }
    useDocumentStore.getState().setSelection([first.id], []);
    useDocumentStore.getState().copySelection();
    useDocumentStore.getState().paste();
    useDocumentStore.getState().paste();
    expect(useDocumentStore.getState().doc?.diagram.nodes.map((node) => node.name)).toEqual([
      "Gain",
      "Gain2",
      "Gain3",
    ]);
  });
});

describe("transforms and save state", () => {
  it("rotates and flips the selection, both undoable", () => {
    const id = useDocumentStore.getState().addBlock(block("C"), { x: 0, y: 0 });
    useDocumentStore.getState().setSelection([id ?? ""], []);
    useDocumentStore.getState().rotateSelection();
    useDocumentStore.getState().flipSelection();
    let node = useDocumentStore.getState().doc?.diagram.nodes[0];
    expect(node?.rotation).toBe(90);
    expect(node?.flipX).toBe(true);

    useDocumentStore.getState().undo();
    node = useDocumentStore.getState().doc?.diagram.nodes[0];
    expect(node?.rotation).toBe(90);
    expect(node?.flipX).toBe(false);

    useDocumentStore.getState().undo();
    node = useDocumentStore.getState().doc?.diagram.nodes[0];
    expect(node?.rotation).toBe(0);
  });

  it("does not rotate a junction", () => {
    const id = useDocumentStore.getState().addJunction("0", { x: 0, y: 0 });
    useDocumentStore.getState().setSelection([id ?? ""], []);
    useDocumentStore.getState().rotateSelection();
    const node = useDocumentStore.getState().doc?.diagram.nodes[0];
    expect(node?.rotation).toBe(0);
    expect(node?.block).toEqual({ junction: "0" });
  });

  it("tracks dirty state against the saved revision", () => {
    expect(useDocumentStore.getState().saveState).toBe("saved");
    useDocumentStore.getState().addBlock(block("C"), { x: 0, y: 0 });
    expect(useDocumentStore.getState().saveState).toBe("dirty");
    expect(useDocumentStore.getState().revision).toBe(1);

    useDocumentStore.getState().setSaving();
    useDocumentStore.getState().setSaved(1);
    expect(useDocumentStore.getState().saveState).toBe("saved");

    useDocumentStore.getState().addBlock(block("R"), { x: 100, y: 0 });
    expect(useDocumentStore.getState().saveState).toBe("dirty");
    useDocumentStore.getState().setSaved(1);
    expect(useDocumentStore.getState().saveState).toBe("dirty");
    expect(useDocumentStore.getState().savedRevision).toBe(1);
  });

  it("marks a newly created model dirty so auto-save creates its file", () => {
    useDocumentStore
      .getState()
      .openDocument("demo", "NewModel", createEmptyModel("NewModel"), { persisted: false });
    expect(useDocumentStore.getState().saveState).toBe("dirty");
    expect(useDocumentStore.getState().savedRevision).toBe(-1);
    expect(useDocumentStore.getState().revision).toBe(0);
  });

  it("keeps a junction's document shape", () => {
    const id = useDocumentStore.getState().addJunction("1", { x: 12, y: 34 });
    const node = useDocumentStore.getState().doc?.diagram.nodes[0];
    expect(node?.id).toBe(id);
    expect(node?.name).toBe("Junction1");
    expect(node?.position).toEqual({ x: 12, y: 34 });
    expect(node?.params).toEqual({});
    expect(node?.starts).toEqual({});
    expect(node?.ui).toEqual({ showLabel: true, color: null });
  });
});

describe("model factories", () => {
  it("writes every optional field so the backend round-trips it", () => {
    const model = createEmptyModel("RoundTrip");
    expect(model.format).toBe("bgsim.model");
    expect(model.language).toBe("0.1.0");
    expect(model.diagram).toEqual({
      nodes: [],
      connections: [],
      subsystemPorts: [],
      annotations: [],
    });
    expect(model.plots).toEqual([]);
    expect(model.scene).toBeNull();
    expect(model.bindings).toEqual([]);
    expect(model.settings.output).toEqual({ mode: "points", points: 5000 });
    expect(createJunctionNode("0", { x: 0, y: 0 }, "n1", "Junction0").block).toEqual({
      junction: "0",
    });
  });
});
