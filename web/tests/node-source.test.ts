// The Code tab request behind the inspector's "Open source" and the canvas menu's
// "Show source": a library block by its ref, an inline node as `inline:<id>`, nothing for
// a node without a source.

import { describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import type { ModelNode } from "../src/contracts/model";
import { useCodeSessionStore } from "../src/code/codeSession";
import { nodeSourceDetail, openNodeSource } from "../src/code/nodeSource";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import { createNodeFromBlock } from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;
const index = buildCatalogIndex(catalog);

function libraryNode(): ModelNode {
  const block = catalog.blocks.find((entry) => entry.name === "DCMotor");
  if (block === undefined) {
    throw new Error("the catalog has no DCMotor");
  }
  return createNodeFromBlock(block, { x: 0, y: 0 }, "n1", "Motor1");
}

describe("node source", () => {
  it("opens a library block by its ref", () => {
    const node = libraryNode();
    const detail = nodeSourceDetail(node, index);
    expect(detail).toEqual({ kind: "stdlib", ref: expect.stringMatching(/^stdlib:/) as string, line: 1, col: 1 });
    useCodeSessionStore.setState({ request: null });
    expect(openNodeSource(node, index)).toBe(true);
    expect(useCodeSessionStore.getState().request?.detail).toEqual(detail);
  });

  it("opens an inline node as inline:<id>", () => {
    const node = { ...libraryNode(), id: "n7", block: { inline: { source: "@block X begin\nend" } } } as unknown as ModelNode;
    expect(nodeSourceDetail(node, index)).toEqual({ kind: "inline", ref: "inline:n7", line: 1, col: 1 });
  });

  it("has nothing for a block the catalog does not know", () => {
    const node = libraryNode();
    expect(nodeSourceDetail(node, null)).toBeNull();
    useCodeSessionStore.setState({ request: null });
    expect(openNodeSource(node, null)).toBe(false);
    expect(useCodeSessionStore.getState().request).toBeNull();
  });
});
