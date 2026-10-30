/**
 * `applySelection` puts the selection on a diagram built without one. A
 * selection change must not rebuild the diagram, must keep the objects xyflow
 * already holds for unchanged elements, and must carry xyflow's measured size
 * on a changed node (a node without it is hidden, re-measured and, until
 * then, counted inside every selection rectangle), also after a rebuild.
 */

import { describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import {
  applySelection,
  buildDiagram,
  type DiagramFlow,
  type HeldNode,
  type SelectionOrigins,
} from "../src/editor/buildFlow";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import {
  createConnection,
  createEmptyModel,
  createNodeFromBlock,
} from "../src/state/modelFactory";

const index = buildCatalogIndex(catalogJson as unknown as Catalog);
const NONE = { nodes: [], connections: [] };

function flow(): DiagramFlow {
  const block = (name: string) => {
    const entry = index.blocksByName.get(name);
    if (entry === undefined) {
      throw new Error(`the catalog has no block ${name}`);
    }
    return entry;
  };
  const model = createEmptyModel("Selection");
  model.diagram.nodes = [
    createNodeFromBlock(block("DCMotor"), { x: 0, y: 0 }, "n1", "Motor1"),
    createNodeFromBlock(block("C"), { x: 200, y: 0 }, "n2", "Cap1"),
    createNodeFromBlock(block("C"), { x: 400, y: 0 }, "n3", "Cap2"),
  ];
  model.diagram.connections = [
    createConnection("c1", "signal", { node: "n1", port: "shaft" }, { node: "n2", port: "p" }),
  ];
  return buildDiagram(model, index, NONE);
}

/** A stand-in for xyflow's node lookup: it adopts what `applySelection` returns. */
function fakeXyflow() {
  const held = new Map<string, HeldNode>();
  return {
    held: (id: string) => held.get(id),
    adopt(next: DiagramFlow) {
      for (const node of next.nodes) {
        held.set(node.id, { node, measured: { width: 60, height: 40 } });
      }
    },
  };
}

describe("applySelection", () => {
  it("sets the flags and keeps unchanged elements", () => {
    const base = flow();
    const origins: SelectionOrigins = new WeakMap();
    const next = applySelection(base, { nodes: ["n2"], connections: ["c1"] }, origins);
    expect(next.nodes.map((node) => node.selected ?? false)).toEqual([false, true, false]);
    expect(next.nodes[0]).toBe(base.nodes[0]);
    expect(next.nodes[2]).toBe(base.nodes[2]);
    expect(next.nodes[1]).not.toBe(base.nodes[1]);
    expect(next.nodes[1]?.data).toBe(base.nodes[1]?.data);
    expect(next.edges[0]?.selected).toBe(true);
    // The analysis is shared: nothing was rebuilt.
    expect(next.analysis).toBe(base.analysis);
    // The same selection again gives the same edge copy.
    expect(applySelection(base, { nodes: [], connections: ["c1"] }, origins).edges[0]).toBe(
      next.edges[0],
    );
  });

  it("reuses the nodes xyflow holds and carries their measured size on a change", () => {
    const base = flow();
    const origins: SelectionOrigins = new WeakMap();
    const xyflow = fakeXyflow();
    const first = applySelection(base, { nodes: ["n1"], connections: [] }, origins, xyflow.held);
    xyflow.adopt(first);

    // Adding n2 changes only n2; n1 keeps the copy xyflow holds.
    const second = applySelection(
      base,
      { nodes: ["n1", "n2"], connections: [] },
      origins,
      xyflow.held,
    );
    expect(second.nodes[0]).toBe(first.nodes[0]);
    expect(second.nodes[2]).toBe(first.nodes[2]);
    expect(second.nodes[1]).not.toBe(first.nodes[1]);
    expect(second.nodes[1]?.selected).toBe(true);
    expect(second.nodes[1]?.measured).toEqual({ width: 60, height: 40 });
    xyflow.adopt(second);

    // Deselecting n1 gives a measured, unselected copy, not the bare node.
    const third = applySelection(base, { nodes: ["n2"], connections: [] }, origins, xyflow.held);
    expect(third.nodes[0]?.selected).toBe(false);
    expect(third.nodes[0]?.measured).toEqual({ width: 60, height: 40 });
    expect(third.nodes[1]).toBe(second.nodes[1]);
  });

  it("carries the measured size into a rebuilt diagram", () => {
    const origins: SelectionOrigins = new WeakMap();
    const xyflow = fakeXyflow();
    xyflow.adopt(applySelection(flow(), { nodes: ["n1"], connections: [] }, origins, xyflow.held));

    // After a document change the held nodes belong to an older flow.
    const rebuilt = flow();
    const next = applySelection(rebuilt, { nodes: ["n1"], connections: [] }, origins, xyflow.held);
    expect(next.nodes.map((node) => node.selected ?? false)).toEqual([true, false, false]);
    expect(next.nodes.map((node) => node.measured)).toEqual([
      { width: 60, height: 40 },
      { width: 60, height: 40 },
      { width: 60, height: 40 },
    ]);
    // The new data is the rebuilt one.
    expect(next.nodes[1]?.data).toBe(rebuilt.nodes[1]?.data);
    // A node xyflow has never measured is taken as built.
    expect(applySelection(rebuilt, NONE, new WeakMap()).nodes[1]).toBe(rebuilt.nodes[1]);
  });
});
