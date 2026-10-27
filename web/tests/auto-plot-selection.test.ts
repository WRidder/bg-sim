/**
 * Automatic plot selection: a node shows its own recorded signals; a bond
 * shows its effort/flow/power; a signal wire shows the source signal.
 */

import { describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import modelJson from "../../contracts/fixtures/model/valid/model.dcmotor.bondgraph.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model } from "../src/contracts/model";
import { autoPlotSelection } from "../src/plot/autoPlotSelection";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import {
  createConnection,
  createEmptyModel,
  createNodeFromBlock,
} from "../src/state/modelFactory";
import { runManifest, runSignal } from "./plotFixtures";

const catalog = catalogJson as unknown as Catalog;
const index = buildCatalogIndex(catalog);
const doc = modelJson as unknown as Model;
const signals = [
  runSignal("IL/w", { kind: "output", path: "IL" }),
  runSignal("IL/p.e", { kind: "port", path: "IL" }),
  runSignal("IL/p.f", { kind: "port", path: "IL" }),
  runSignal("IL/x", { kind: "state", path: "IL" }),
  runSignal("R1/p.e", { kind: "port", path: "R1" }),
  runSignal("Se1/p.e", { kind: "port", path: "Se1" }),
  runSignal("Se1/p.f", { kind: "port", path: "Se1" }),
  runSignal("Se1/p.P", { kind: "power", path: "Se1" }),
];
const manifest = runManifest(signals);

function block(name: string) {
  const entry = index.blocksByName.get(name);
  if (entry === undefined) {
    throw new Error(`no block ${name}`);
  }
  return entry;
}

describe("autoPlotSelection", () => {
  it("plots every recorded signal of the selected node", () => {
    const selection = autoPlotSelection(
      doc,
      [],
      { nodes: ["n4"], connections: [] },
      manifest,
    );
    expect(selection?.label).toBe("IL");
    expect(selection?.signalIds).toEqual([
      "IL/w",
      "IL/p.e",
      "IL/p.f",
      "IL/x",
    ]);
  });

  it("plots e, f and P for a selected power bond", () => {
    const selection = autoPlotSelection(
      doc,
      [],
      { nodes: [], connections: ["c1"] },
      manifest,
    );
    expect(selection?.label).toContain("Se1/p");
    expect(selection?.signalIds).toEqual([
      "Se1/p.e",
      "Se1/p.f",
      "Se1/p.P",
    ]);
  });

  it("plots the source output for a selected signal wire", () => {
    const model = createEmptyModel("SignalWire");
    const source = createNodeFromBlock(block("Constant"), { x: 0, y: 0 }, "n1", "Cmd");
    const gain = createNodeFromBlock(block("Gain"), { x: 300, y: 0 }, "n2", "Gain1");
    model.diagram.nodes = [source, gain];
    model.diagram.connections = [
      createConnection("c1", "signal", { node: "n1", port: "y" }, { node: "n2", port: "u" }),
    ];
    const selection = autoPlotSelection(
      model,
      [],
      { nodes: [], connections: ["c1"] },
      runManifest([runSignal("Cmd/y", { kind: "output", path: "Cmd" })]),
    );
    expect(selection?.signalIds).toEqual(["Cmd/y"]);
  });

  it("prefers the first selected node and returns null with no selection", () => {
    const node = autoPlotSelection(
      doc,
      [],
      { nodes: ["n4", "n3"], connections: ["c1"] },
      manifest,
    );
    expect(node?.label).toBe("IL");
    expect(
      autoPlotSelection(doc, [], { nodes: [], connections: [] }, manifest),
    ).toBeNull();
  });

  it("returns an empty selection for a node with no recorded signals", () => {
    const selection = autoPlotSelection(
      doc,
      [],
      { nodes: ["n3"], connections: [] },
      runManifest([runSignal("Other/x", { path: "Other" })]),
    );
    expect(selection?.label).toBe("R1");
    expect(selection?.signalIds).toEqual([]);
  });
});
