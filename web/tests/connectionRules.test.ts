/**
 * The compatibility rules (plan 5.5/5.6 ported to TypeScript).
 *
 * Every refusal is asserted against its exact tooltip sentence, because the
 * sentence is the user-facing part of the rule (plan 7.3).
 */

import { describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog, ValueType } from "../src/contracts/catalog";
import type { Model, ModelConnection, ModelNode } from "../src/contracts/model";
import {
  checkConnection,
  CONNECTION_MESSAGES,
  connectionKindFor,
  domainLetter,
  type PortDescriptor,
} from "../src/editor/connectionRules";
import { interfaceForNode, portDescriptor } from "../src/editor/nodeInterface";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import {
  createConnection,
  createEmptyModel,
  createJunctionNode,
  createNodeFromBlock,
} from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;
const index = buildCatalogIndex(catalog);

let idCounter = 0;
function nextId(prefix = "n"): string {
  idCounter += 1;
  return `${prefix}${idCounter}`;
}

function nodeFor(blockName: string, name = blockName): ModelNode {
  const block = index.blocksByName.get(blockName);
  if (block === undefined) {
    throw new Error(`catalog has no block ${blockName}`);
  }
  return createNodeFromBlock(block, { x: 0, y: 0 }, nextId(), name);
}

function junction(kind: "0" | "1"): ModelNode {
  return createJunctionNode(kind, { x: 0, y: 0 }, nextId(), `Junction${kind}`);
}

function descriptor(node: ModelNode, portName: string | null): PortDescriptor {
  const port = portDescriptor(node, interfaceForNode(node, index), portName);
  if (port === null) {
    throw new Error(`node ${node.name} has no port ${String(portName)}`);
  }
  return port;
}

function modelWith(nodes: ModelNode[], connections: ModelConnection[] = []): Model {
  const model = createEmptyModel("Rules");
  model.diagram.nodes = nodes;
  model.diagram.connections = connections;
  return model;
}

function signal(
  type: ValueType,
  direction: "input" | "output",
  options: { node?: string; name?: string; size?: number[] } = {},
): PortDescriptor {
  return {
    nodeId: options.node ?? (direction === "output" ? "source" : "target"),
    portName: options.name ?? (direction === "output" ? "y" : "u"),
    isJunction: false,
    kind: "signal",
    direction,
    domain: "Generic",
    type,
    size: options.size ?? [],
    unit: null,
  };
}

function power(
  domain: PortDescriptor["domain"],
  options: { node?: string; name?: string; size?: number[]; junction?: boolean } = {},
): PortDescriptor {
  return {
    nodeId: options.node ?? "power",
    portName: options.junction === true ? null : (options.name ?? "p"),
    isJunction: options.junction ?? false,
    kind: "power",
    direction: null,
    domain,
    type: null,
    size: options.size ?? [],
    unit: null,
  };
}

describe("connection kinds (plan 5.5)", () => {
  it("links two concrete electrical ports as a wire", () => {
    const source = nodeFor("VoltageSource");
    const ground = nodeFor("Ground");
    const result = checkConnection(
      modelWith([source, ground]),
      descriptor(source, "p"),
      descriptor(ground, "p"),
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.kind).toBe("wire");
      expect(result.domain).toBe("Electrical");
    }
  });

  it("links a Generic port to a concrete port as a bond and adopts the domain", () => {
    const source = nodeFor("Se");
    const resistor = nodeFor("Resistor");
    const result = checkConnection(
      modelWith([source, resistor]),
      descriptor(source, "p"),
      descriptor(resistor, "p"),
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.kind).toBe("bond");
      expect(result.domain).toBe("Electrical");
    }
  });

  it("links a junction to a concrete port as a bond", () => {
    const zero = junction("0");
    const resistor = nodeFor("Resistor");
    const result = checkConnection(
      modelWith([zero, resistor]),
      descriptor(zero, null),
      descriptor(resistor, "p"),
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.kind).toBe("bond");
      expect(result.domain).toBe("Electrical");
    }
  });

  it("links two junctions as a dimensionless bond", () => {
    const zero = junction("0");
    const one = junction("1");
    const result = checkConnection(
      modelWith([zero, one]),
      descriptor(zero, null),
      descriptor(one, null),
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.kind).toBe("bond");
      expect(result.domain).toBe("Generic");
    }
  });

  it("links an output to an input as a signal", () => {
    const step = nodeFor("Step");
    const source = nodeFor("VoltageSource");
    const result = checkConnection(
      modelWith([step, source]),
      descriptor(step, "y"),
      descriptor(source, "u"),
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.kind).toBe("signal");
      expect(result.from.portName).toBe("y");
      expect(result.to.portName).toBe("u");
    }
  });

  it("normalises a drag that started at the input", () => {
    const step = nodeFor("Step");
    const source = nodeFor("VoltageSource");
    const result = checkConnection(
      modelWith([step, source]),
      descriptor(source, "u"),
      descriptor(step, "y"),
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.from.portName).toBe("y");
      expect(result.to.portName).toBe("u");
    }
  });

  it("reports the connection kind without a document", () => {
    expect(connectionKindFor(power("Generic"), power("Rotation"))).toBe("bond");
    expect(connectionKindFor(power("Rotation"), power("Rotation"))).toBe("wire");
    expect(connectionKindFor(power("Generic", { junction: true }), power("Electrical"))).toBe(
      "bond",
    );
    expect(connectionKindFor(power("Electrical"), signal("Real", "input"))).toBeNull();
  });
});

describe("refusals with the exact tooltip text (plan 7.3)", () => {
  it("refuses a block connected to itself", () => {
    const source = nodeFor("VoltageSource");
    const result = checkConnection(
      modelWith([source]),
      descriptor(source, "p"),
      descriptor(source, "n"),
    );
    expect(result).toEqual({ ok: false, reason: "A block cannot connect to itself" });
  });

  it("refuses a junction connected to itself", () => {
    const zero = junction("0");
    const result = checkConnection(
      modelWith([zero]),
      descriptor(zero, null),
      descriptor(zero, null),
    );
    expect(result).toEqual({ ok: false, reason: "A junction cannot connect to itself" });
  });

  it("refuses a power port connected to a signal port", () => {
    const source = nodeFor("VoltageSource");
    const step = nodeFor("Step");
    const result = checkConnection(
      modelWith([source, step]),
      descriptor(source, "p"),
      descriptor(step, "y"),
    );
    expect(result).toEqual({
      ok: false,
      reason: "Power port cannot connect to a signal port; use a sensor or a source",
    });
  });

  it("refuses two outputs", () => {
    const step = nodeFor("Step");
    const constant = nodeFor("Constant");
    const result = checkConnection(
      modelWith([step, constant]),
      descriptor(step, "y"),
      descriptor(constant, "y"),
    );
    expect(result).toEqual({
      ok: false,
      reason: "Signal connections must run from an output to an input",
    });
  });

  it("refuses a second source on an input", () => {
    const step = nodeFor("Step");
    const constant = nodeFor("Constant");
    const source = nodeFor("VoltageSource");
    const existing = createConnection(
      "c1",
      "signal",
      { node: step.id, port: "y" },
      { node: source.id, port: "u" },
    );
    const result = checkConnection(
      modelWith([step, constant, source], [existing]),
      descriptor(constant, "y"),
      descriptor(source, "u"),
    );
    expect(result).toEqual({ ok: false, reason: "Input u already has a source" });
  });

  it("refuses Bool into Real", () => {
    const doc = createEmptyModel("Types");
    const result = checkConnection(doc, signal("Bool", "output"), signal("Real", "input"));
    expect(result).toEqual({
      ok: false,
      reason: "Bool cannot connect to Real; insert a Type conversion",
    });
  });

  it("refuses different signal sizes", () => {
    const doc = createEmptyModel("Sizes");
    const result = checkConnection(
      doc,
      signal("Real", "output", { size: [3] }),
      signal("Real", "input", { size: [2] }),
    );
    expect(result).toEqual({
      ok: false,
      reason: "Vec{3} cannot connect to Vec{2}; insert a Reshape",
    });
  });

  it("refuses Electrical into Rotation with the converter hint", () => {
    const source = nodeFor("VoltageSource");
    const motor = nodeFor("DCMotor");
    const result = checkConnection(
      modelWith([source, motor]),
      descriptor(source, "p"),
      descriptor(motor, "shaft"),
    );
    expect(result).toEqual({
      ok: false,
      reason: "Electrical port cannot connect to Rotation; use a converter (DC motor, EM converter)",
    });
  });

  it("uses the generic converter hint for other domain pairs", () => {
    const resistor = nodeFor("Resistor");
    const mass = nodeFor("Mass");
    const result = checkConnection(
      modelWith([resistor, mass]),
      descriptor(resistor, "p"),
      descriptor(mass, "a"),
    );
    expect(result).toEqual({
      ok: false,
      reason: "Electrical port cannot connect to Translation; use a converter block",
    });
  });

  it("refuses to mix the Planar and Spatial multibond domains (E102)", () => {
    // Regression guard: checkConnection already refused any two differing
    // concrete domains before W-MB2. This pins the E102 tooltip for the pair
    // the renderer guard protects; it is not a fail-without-change test.
    const planar = power("Planar", { node: "n1", name: "p", size: [3] });
    const spatial = power("Spatial", { node: "n2", name: "p", size: [6] });
    expect(checkConnection(modelWith([]), planar, spatial)).toEqual({
      ok: false,
      reason: "Planar port cannot connect to Spatial; use a converter block",
    });
    // The same pair, reversed, is refused the same way.
    expect(checkConnection(modelWith([]), spatial, planar)).toEqual({
      ok: false,
      reason: "Spatial port cannot connect to Planar; use a converter block",
    });
  });

  it("refuses the same pair twice", () => {
    const source = nodeFor("VoltageSource");
    const ground = nodeFor("Ground");
    const existing = createConnection(
      "c1",
      "wire",
      { node: source.id, port: "p" },
      { node: ground.id, port: "p" },
    );
    const result = checkConnection(
      modelWith([source, ground], [existing]),
      descriptor(source, "p"),
      descriptor(ground, "p"),
    );
    expect(result).toEqual({ ok: false, reason: "These ports are already connected" });
  });

  it("refuses a power port that already has a bond", () => {
    const source = nodeFor("Se");
    const capacitor = nodeFor("C");
    const resistor = nodeFor("Resistor");
    const existing = createConnection(
      "c1",
      "bond",
      { node: source.id, port: "p" },
      { node: capacitor.id, port: "p" },
    );
    const result = checkConnection(
      modelWith([source, capacitor, resistor], [existing]),
      descriptor(source, "p"),
      descriptor(resistor, "p"),
    );
    expect(result).toEqual({ ok: false, reason: "Port p already has a bond" });
  });

  it("refuses different power port sizes", () => {
    const doc = createEmptyModel("Power sizes");
    const result = checkConnection(
      doc,
      power("Electrical", { size: [3], node: "left" }),
      power("Electrical", { node: "right" }),
    );
    expect(result).toEqual({
      ok: false,
      reason: "Vec{3} power port cannot connect to Scalar power port; use matching sizes",
    });
  });

  it("never uses colour as the only cue: the domain letters are defined", () => {
    expect(domainLetter("Electrical")).toBe("E");
    expect(domainLetter("Translation")).toBe("T");
    expect(domainLetter("Rotation")).toBe("R");
    expect(domainLetter("Hydraulic")).toBe("H");
    expect(domainLetter("Generic")).toBe("G");
    expect(domainLetter("Planar")).toBe("P");
    expect(domainLetter("Spatial")).toBe("S");
  });

  it("keeps the message constants equal to what the rules return", () => {
    expect(CONNECTION_MESSAGES.self).toBe("A block cannot connect to itself");
    expect(CONNECTION_MESSAGES.source("u")).toBe("Input u already has a source");
    expect(CONNECTION_MESSAGES.type("Bool", "Real")).toBe(
      "Bool cannot connect to Real; insert a Type conversion",
    );
    expect(CONNECTION_MESSAGES.converter("Electrical", "Rotation")).toBe(
      "Electrical port cannot connect to Rotation; use a converter (DC motor, EM converter)",
    );
  });
});
