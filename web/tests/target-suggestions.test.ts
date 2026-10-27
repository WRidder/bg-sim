/**
 * Drop-on-empty suggestions: only compatible elements are offered, and the
 * order favours the block the dragged element is already wired to.
 */

import { describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model } from "../src/contracts/model";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import { checkConnection, type PortDescriptor } from "../src/editor/connectionRules";
import { descriptorForPort } from "../src/editor/nodeInterface";
import {
  filterSuggestions,
  junctionDescriptor,
  suggestTargets,
  type TargetSuggestion,
} from "../src/editor/suggestTargets";
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
    throw new Error(`no block ${name}`);
  }
  return entry;
}

function port(model: Model, nodeId: string, name: string | null): PortDescriptor {
  const descriptor = descriptorForPort(model.diagram.nodes, index, nodeId, name);
  if (descriptor === null) {
    throw new Error(`no port ${nodeId}/${String(name)}`);
  }
  return descriptor;
}

function names(suggestions: readonly TargetSuggestion[]): string[] {
  return suggestions.map((suggestion) => suggestion.name);
}

/** The descriptor the automatic connection would use after adding the block. */
function targetFor(model: Model, suggestion: TargetSuggestion): PortDescriptor {
  if (suggestion.kind === "junction") {
    return junctionDescriptor("new");
  }
  const node = createNodeFromBlock(suggestion.block, { x: 0, y: 0 }, "new", "New");
  return port({ ...model, diagram: { ...model.diagram, nodes: [...model.diagram.nodes, node] } }, "new", suggestion.portName);
}

describe("suggestTargets", () => {
  it("offers signal inputs for an output, ranked towards the signal path", () => {
    const model = createEmptyModel("SignalOut");
    model.diagram.nodes = [
      createNodeFromBlock(block("Constant"), { x: 0, y: 0 }, "n1", "Cmd"),
    ];
    const suggestions = suggestTargets(model, index, port(model, "n1", "y"));

    expect(suggestions.length).toBeGreaterThan(0);
    expect(names(suggestions)).toContain("Gain");
    expect(names(suggestions)).toContain("Integrator");
    // Sum's input is a vector, so the scalar output cannot drive it.
    expect(names(suggestions)).not.toContain("Sum");
    // A pure signal block outranks a power element that has a modulation input.
    expect(names(suggestions).indexOf("Gain")).toBeLessThan(names(suggestions).indexOf("MSe"));
    expect(suggestions[0]?.name).toBe("Gain");
    expect(suggestions.every((suggestion) => suggestion.portKind === "input")).toBe(true);
  });

  it("offers outputs for an input, with sources first", () => {
    const model = createEmptyModel("SignalIn");
    model.diagram.nodes = [
      createNodeFromBlock(block("Gain"), { x: 0, y: 0 }, "n1", "Gain1"),
    ];
    const suggestions = suggestTargets(model, index, port(model, "n1", "u"));

    expect(names(suggestions)).toContain("Constant");
    expect(suggestions[0]?.name).toBe("Constant");
    expect(suggestions.every((suggestion) => suggestion.portKind === "output")).toBe(true);
  });

  it("offers only power ports and junctions for a bond", () => {
    const model = createEmptyModel("Bond");
    model.diagram.nodes = [
      createNodeFromBlock(block("Se"), { x: 0, y: 0 }, "n1", "Se1"),
    ];
    const suggestions = suggestTargets(model, index, port(model, "n1", "p"));

    expect(names(suggestions)).toContain("R");
    expect(names(suggestions)).toContain("Junction 0");
    expect(names(suggestions)).toContain("Junction 1");
    // A signal-only block cannot take a bond.
    expect(names(suggestions)).not.toContain("Constant");
    for (const suggestion of suggestions) {
      if (suggestion.kind === "block") {
        expect(suggestion.portKind).toBe("power");
      }
    }
  });

  it("prefers the concrete domain when the dragged port has one", () => {
    const model = createEmptyModel("Concrete");
    model.diagram.nodes = [
      createNodeFromBlock(block("DCMotor"), { x: 0, y: 0 }, "n1", "Motor1"),
    ];
    const suggestions = suggestTargets(model, index, port(model, "n1", "p"));

    expect(suggestions[0]?.name).toBe("Resistor");
    const voltage = suggestions.find((suggestion) => suggestion.name === "VoltageSource");
    expect(voltage?.domain).toBe("Electrical");
  });

  it("puts the element the dragged port is already wired to first", () => {
    const model = createEmptyModel("Wired");
    const source = createNodeFromBlock(block("Constant"), { x: 0, y: 0 }, "n1", "Cmd");
    const supply = createNodeFromBlock(block("VoltageSource"), { x: 300, y: 0 }, "n2", "V1");
    model.diagram.nodes = [source, supply];
    model.diagram.connections = [
      createConnection("c1", "signal", { node: "n1", port: "y" }, { node: "n2", port: "u" }),
    ];

    const suggestions = suggestTargets(model, index, port(model, "n1", "y"));
    expect(suggestions[0]?.name).toBe("VoltageSource");
  });

  it("every suggestion can actually connect once the element is added", () => {
    const signalOut = createEmptyModel("CheckOut");
    signalOut.diagram.nodes = [
      createNodeFromBlock(block("Constant"), { x: 0, y: 0 }, "n1", "Cmd"),
    ];
    const signalIn = createEmptyModel("CheckIn");
    signalIn.diagram.nodes = [
      createNodeFromBlock(block("Gain"), { x: 0, y: 0 }, "n1", "Gain1"),
    ];
    const bond = createEmptyModel("CheckBond");
    bond.diagram.nodes = [
      createNodeFromBlock(block("DCMotor"), { x: 0, y: 0 }, "n1", "Motor1"),
    ];

    const scenarios: { model: Model; origin: PortDescriptor }[] = [
      { model: signalOut, origin: port(signalOut, "n1", "y") },
      { model: signalIn, origin: port(signalIn, "n1", "u") },
      { model: bond, origin: port(bond, "n1", "p") },
    ];

    for (const { model, origin } of scenarios) {
      for (const suggestion of suggestTargets(model, index, origin)) {
        const target = targetFor(model, suggestion);
        expect(
          checkConnection(model, origin, target).ok,
          `${suggestion.name} should connect`,
        ).toBe(true);
      }
    }
  });
});

describe("filterSuggestions", () => {
  function signalOut() {
    const model = createEmptyModel("Filter");
    model.diagram.nodes = [
      createNodeFromBlock(block("Constant"), { x: 0, y: 0 }, "n1", "Cmd"),
    ];
    return { model, items: suggestTargets(model, index, port(model, "n1", "y")) };
  }

  it("returns everything for an empty query", () => {
    const { items } = signalOut();
    expect(filterSuggestions(items, "   ")).toHaveLength(items.length);
  });

  it("matches the block name and the port hint", () => {
    const { items } = signalOut();
    const gain = filterSuggestions(items, "gain");
    expect(names(gain)).toContain("Gain");
    expect(names(gain)).not.toContain("Integrator");

    // Descriptions are searchable too: MSe is the modulated effort source.
    const modulated = filterSuggestions(items, "modulated effort");
    expect(names(modulated)).toContain("MSe");
    expect(names(modulated)).not.toContain("Gain");
  });

  it("reports no match for an unknown query", () => {
    const { items } = signalOut();
    expect(filterSuggestions(items, "no-such-element")).toHaveLength(0);
  });
});
