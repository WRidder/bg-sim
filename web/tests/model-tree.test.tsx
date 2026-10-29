/**
 * W2.2: the model tree nests subsystem diagrams recursively and a row click
 * opens the owning diagram and selects the node (or enters the subsystem).
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model, ModelNode } from "../src/contracts/model";
import { ModelTree } from "../src/editor/ModelTree";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import {
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

function plain(blockName: string, x: number, y: number, id: string, name: string): ModelNode {
  return createNodeFromBlock(block(blockName), { x, y }, id, name);
}

function subsystemNode(
  id: string,
  name: string,
  position: { x: number; y: number },
  diagram: Model["diagram"],
): ModelNode {
  return {
    id,
    name,
    block: {
      subsystem: {
        ports: [
          {
            name: "Ground1_p",
            kind: "power",
            domain: "Electrical",
            size: [1],
            node: "g1",
            port: "p",
          },
        ],
        diagram,
      },
    },
    position,
    rotation: 0,
    flipX: false,
    params: {},
    constants: {},
    starts: {},
    ui: { showLabel: true, color: null },
  };
}

function nestedModel(): Model {
  const inner: Model["diagram"] = {
    nodes: [plain("Gain", 0, 0, "g2", "Gain1")],
    connections: [],
    subsystemPorts: [],
    annotations: [],
  };
  const middle: Model["diagram"] = {
    nodes: [
      plain("Ground", 0, 0, "g1", "Ground1"),
      subsystemNode("s2", "Inner", { x: 200, y: 0 }, inner),
    ],
    connections: [],
    subsystemPorts: [],
    annotations: [],
  };
  const model = createEmptyModel("Tree");
  model.diagram.nodes = [
    plain("DCMotor", 0, 200, "m1", "Motor1"),
    subsystemNode("s1", "Subsystem1", { x: 300, y: 200 }, middle),
  ];
  return model;
}

beforeEach(() => {
  resetDocumentStore();
  resetCatalogStore();
  useCatalogStore.getState().setCatalog(catalog);
  useDocumentStore.getState().openDocument("demo", "Tree", nestedModel());
});

describe("model tree subsystems", () => {
  it("nests children recursively and shows the exposed-port count", () => {
    render(<ModelTree />);

    expect(screen.getByTestId("tree-node-Motor1").getAttribute("data-depth")).toBe("0");
    const rootSubsystem = screen.getByTestId("tree-node-Subsystem1");
    expect(rootSubsystem.getAttribute("data-depth")).toBe("0");
    expect(rootSubsystem.getAttribute("data-subsystem")).toBe("true");
    expect(rootSubsystem.getAttribute("data-port-count")).toBe("1");
    expect(rootSubsystem.textContent).toContain("Subsystem · 1 ports");
    expect(screen.getByTestId("tree-node-Ground1").getAttribute("data-depth")).toBe("1");
    expect(screen.getByTestId("tree-node-Inner").getAttribute("data-depth")).toBe("1");
    expect(screen.getByTestId("tree-node-Gain1").getAttribute("data-depth")).toBe("2");
  });

  it("selects a nested row in its own diagram and enters a subsystem row", () => {
    render(<ModelTree />);

    fireEvent.click(screen.getByTestId("tree-node-Gain1"));
    expect(useDocumentStore.getState().activePath).toEqual(["s1", "s2"]);
    expect(useDocumentStore.getState().selection.nodes).toEqual(["g2"]);
    expect(
      screen.getByTestId("tree-node-Gain1").getAttribute("aria-current"),
    ).toBe("true");
    expect(
      screen.getByTestId("tree-node-Motor1").getAttribute("aria-current"),
    ).toBeNull();

    fireEvent.click(screen.getByTestId("tree-node-Subsystem1"));
    expect(useDocumentStore.getState().activePath).toEqual(["s1"]);
    expect(useDocumentStore.getState().selection).toEqual({ nodes: [], connections: [] });

    fireEvent.click(screen.getByTestId("tree-node-Ground1"));
    expect(useDocumentStore.getState().activePath).toEqual(["s1"]);
    expect(useDocumentStore.getState().selection.nodes).toEqual(["g1"]);
  });
});
