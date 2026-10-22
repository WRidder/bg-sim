/**
 * W2.1 inline interfaces (plan 7.7): `block.check` owns the port list of an
 * inline node, the canvas reads it through `interfaceForNode`, and a
 * connection whose port disappeared is marked immediately instead of waiting
 * for the next `model.check` E101.
 */

import { beforeEach, describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model, ModelConnection, ModelNode } from "../src/contracts/model";
import { buildDiagram } from "../src/editor/buildFlow";
import {
  INLINE_ICON,
  interfaceForNode,
  missingPortFor,
  type NodeInterface,
} from "../src/editor/nodeInterface";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import {
  publishInlineInterface,
  resetInlineInterfaces,
} from "../src/code/inlineInterfaces";
import { createEmptyModel } from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;
const index = buildCatalogIndex(catalog);

function inlineNode(source = "@block Equation begin\nend\n"): ModelNode {
  return {
    id: "n1",
    name: "Equation1",
    block: { inline: { source } },
    position: { x: 40, y: 40 },
    rotation: 0,
    flipX: false,
    params: {},
    constants: {},
    starts: {},
    ui: { showLabel: true, color: null },
  };
}

function gainNode(): ModelNode {
  return {
    id: "n2",
    name: "Gain1",
    block: { ref: "stdlib:continuous/Gain" },
    position: { x: 320, y: 40 },
    rotation: 0,
    flipX: false,
    params: { k: "1.0" },
    constants: {},
    starts: {},
    ui: { showLabel: true, color: null },
  };
}

function signalConnection(): ModelConnection {
  return {
    id: "c1",
    kind: "signal",
    from: { node: "n1", port: "y" },
    to: { node: "n2", port: "u" },
    route: [],
    label: null,
  };
}

function model(nodes: ModelNode[], connections: ModelConnection[]): Model {
  const document = createEmptyModel("Inline", "0.1.0");
  document.diagram.nodes = nodes;
  document.diagram.connections = connections;
  return document;
}

function iface(ports: NodeInterface["ports"]): NodeInterface {
  return {
    title: "Equation",
    icon: INLINE_ICON,
    ports,
    isJunction: false,
    ref: null,
    junction: null,
  };
}

const U = { name: "u", kind: "input" as const, domain: "Generic" as const, type: "Real" as const, size: [], unit: null };
const Y = { name: "y", kind: "output" as const, domain: "Generic" as const, type: "Real" as const, size: [], unit: null };

beforeEach(() => {
  resetInlineInterfaces();
});

describe("inline node interfaces", () => {
  it("draws the ports a block.check interface declares", () => {
    const node = inlineNode();
    expect(interfaceForNode(node, index).ports).toEqual([]);

    publishInlineInterface("n1", "@block Equation begin\nend\n", iface([U, Y]));
    expect(interfaceForNode(node, index).ports.map((port) => port.name)).toEqual(["u", "y"]);
  });

  it("keeps the last good interface when a later check has errors", () => {
    const node = inlineNode();
    publishInlineInterface("n1", "good", iface([U, Y]));
    publishInlineInterface("n1", "broken =", null);
    expect(interfaceForNode(node, index).ports.map((port) => port.name)).toEqual(["u", "y"]);
  });

  it("marks a connection to a port that the new interface lost", () => {
    const document = model([inlineNode(), gainNode()], [signalConnection()]);
    publishInlineInterface("n1", "with y", iface([U, Y]));
    const before = buildDiagram(document, index, { nodes: [], connections: [] });
    expect(before.edges[0]?.data?.missingPorts).toEqual([]);

    publishInlineInterface("n1", "without y", iface([U]));
    const after = buildDiagram(document, index, { nodes: [], connections: [] });
    expect(after.edges[0]?.data?.missingPorts).toEqual(["y"]);
    expect(after.edges[0]?.data?.missingPorts).toContain("y");
  });

  it("does not blame ports before the first check", () => {
    const document = model([inlineNode(), gainNode()], [signalConnection()]);
    const flow = buildDiagram(document, index, { nodes: [], connections: [] });
    expect(flow.edges[0]?.data?.missingPorts).toEqual([]);
    expect(missingPortFor(inlineNode(), interfaceForNode(inlineNode(), index), "y")).toBeNull();
  });
});
