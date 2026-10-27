/**
 * Ctrl-drag target resolution: dropping on a block body selects the first
 * compatible port, while an explicit port drop still wins.
 */

import { describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model } from "../src/contracts/model";
import { descriptorForPort } from "../src/editor/nodeInterface";
import {
  firstCompatiblePort,
  noAutoTargetMessage,
} from "../src/editor/quickConnectTarget";
import { buildCatalogIndex } from "../src/library/catalogIndex";
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

function port(model: Model, nodeId: string, name: string) {
  const descriptor = descriptorForPort(model.diagram.nodes, index, nodeId, name);
  if (descriptor === null) {
    throw new Error(`no port ${nodeId}/${name}`);
  }
  return descriptor;
}

describe("firstCompatiblePort", () => {
  it("picks the first available signal input on a block body", () => {
    const model = createEmptyModel("AutoSignal");
    const source = createNodeFromBlock(block("Constant"), { x: 0, y: 0 }, "n1", "Cmd");
    const gain = createNodeFromBlock(block("Gain"), { x: 260, y: 0 }, "n2", "Gain1");
    model.diagram.nodes = [source, gain];
    const origin = port(model, "n1", "y");

    const target = firstCompatiblePort(model, index, "n2", origin);
    expect(target?.nodeId).toBe("n2");
    expect(target?.portName).toBe("u");
    expect(target?.kind).toBe("signal");
  });

  it("picks the first free power port and skips a port that already has a bond", () => {
    const model = createEmptyModel("AutoPower");
    const source = createNodeFromBlock(block("Se"), { x: 0, y: 0 }, "n1", "Se1");
    const other = createNodeFromBlock(block("Se"), { x: 0, y: 160 }, "n3", "Se2");
    const motor = createNodeFromBlock(block("DCMotor"), { x: 300, y: 0 }, "n2", "Motor1");
    model.diagram.nodes = [source, other, motor];
    const origin = port(model, "n1", "p");

    expect(firstCompatiblePort(model, index, "n2", origin)?.portName).toBe("p");

    model.diagram.connections = [
      createConnection("c1", "bond", { node: "n3", port: "p" }, { node: "n2", port: "p" }),
    ];
    expect(firstCompatiblePort(model, index, "n2", origin)?.portName).toBe("n");
  });

  it("returns the junction descriptor when the target is a junction", () => {
    const model = createEmptyModel("AutoJunction");
    const source = createNodeFromBlock(block("Se"), { x: 0, y: 0 }, "n1", "Se1");
    const junction = {
      ...createNodeFromBlock(block("Se"), { x: 200, y: 0 }, "n2", "J1"),
      block: { junction: "0" as const },
    };
    model.diagram.nodes = [source, junction];
    const target = firstCompatiblePort(model, index, "n2", port(model, "n1", "p"));
    expect(target?.isJunction).toBe(true);
    expect(target?.portName).toBeNull();
  });

  it("returns null when the block has no compatible port", () => {
    const model = createEmptyModel("AutoRefuse");
    const source = createNodeFromBlock(block("Constant"), { x: 0, y: 0 }, "n1", "Cmd");
    const motor = createNodeFromBlock(block("DCMotor"), { x: 300, y: 0 }, "n2", "Motor1");
    model.diagram.nodes = [source, motor];
    const origin = port(model, "n1", "y");

    expect(firstCompatiblePort(model, index, "n2", origin)).toBeNull();
    expect(noAutoTargetMessage(origin)).toContain("input");
  });

  it("returns null when every compatible input already has a source", () => {
    const model = createEmptyModel("AutoFull");
    const a = createNodeFromBlock(block("Constant"), { x: 0, y: 0 }, "n1", "A");
    const b = createNodeFromBlock(block("Constant"), { x: 0, y: 120 }, "n2", "B");
    const gain = createNodeFromBlock(block("Gain"), { x: 300, y: 0 }, "n3", "Gain1");
    model.diagram.nodes = [a, b, gain];
    model.diagram.connections = [
      createConnection("c1", "signal", { node: "n1", port: "y" }, { node: "n3", port: "u" }),
    ];
    expect(firstCompatiblePort(model, index, "n3", port(model, "n2", "y"))).toBeNull();
  });
});
