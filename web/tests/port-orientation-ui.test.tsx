/**
 * What the user sees of port orientation (plan/PORT_ORIENTATION_PLAN.md WP-O4, O8, O14): the port tooltip,
 * the block inspector's port list, the bond inspector, and the "Reverse bond direction" menu item.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { ReactFlowProvider, type NodeProps } from "@xyflow/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog, OrientationDecl } from "../src/contracts/catalog";
import type { Model, ModelConnection, ModelNode } from "../src/contracts/model";
import { buildDiagram } from "../src/editor/buildFlow";
import { BlockNode, type BlockNodeType } from "../src/editor/nodes/BlockNode";
import { ReverseBondItem } from "../src/editor/ReverseBondItem";
import { checkReverse, REVERSE_JUNCTION_NOTE } from "../src/editor/reverseBond";
import { Inspector } from "../src/inspector/Inspector";
import { resetDiagnosticsStore } from "../src/diagnostics/store";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { resetRunStore } from "../src/plot/runStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import {
  createConnection,
  createEmptyModel,
  createJunctionNode,
  createNodeFromBlock,
} from "../src/state/modelFactory";

const DECLARATIONS: Record<string, OrientationDecl[]> = {
  Se: [{ ports: ["p"], kind: "out" }],
  C: [{ ports: ["p"], kind: "in" }],
  TF: [{ ports: ["p1", "p2"], kind: "through" }],
};

const base = catalogJson as unknown as Catalog;
const catalog: Catalog = {
  ...base,
  blocks: base.blocks.map((entry) => ({ ...entry, orientation: DECLARATIONS[entry.name] ?? [] })),
};
const index = buildCatalogIndex(catalog);

function node(name: string, id: string, instance = name): ModelNode {
  const entry = index.blocksByName.get(name);
  if (entry === undefined) {
    throw new Error(`catalog has no block ${name}`);
  }
  return createNodeFromBlock(entry, { x: 0, y: 0 }, id, instance);
}

function open(nodes: ModelNode[], connections: ModelConnection[] = []): Model {
  const doc = createEmptyModel("OrientationUi");
  doc.diagram.nodes = nodes;
  doc.diagram.connections = connections;
  useDocumentStore.getState().openDocument("demo", "OrientationUi", doc);
  return doc;
}

beforeEach(() => {
  resetDocumentStore();
  resetCatalogStore();
  resetDiagnosticsStore();
  resetRunStore();
  useCatalogStore.getState().setCatalog(catalog);
});

function renderBlock(doc: Model, id: string) {
  const flow = buildDiagram(doc, index, { nodes: [], connections: [] });
  const found = flow.nodes.find((entry) => entry.id === id);
  const props = { id, data: found?.data, selected: false } as unknown as NodeProps<BlockNodeType>;
  return render(
    <ReactFlowProvider>
      <BlockNode {...props} />
    </ReactFlowProvider>,
  );
}

describe("the port tooltip", () => {
  it("names the orientation of a fixed port and a through pair, and nothing for any", () => {
    const doc = open([node("C", "c"), node("Se", "se"), node("TF", "tf"), node("De", "de")]);
    const c = renderBlock(doc, "c");
    expect(screen.getByTestId("port-c-p").getAttribute("title")).toBe(
      "p · power · Generic · orientation in",
    );
    expect(screen.getByTestId("port-c-p").getAttribute("data-orientation")).toBe("in");
    c.unmount();

    const se = renderBlock(doc, "se");
    expect(screen.getByTestId("port-se-p").getAttribute("title")).toContain("orientation out");
    se.unmount();

    const tf = renderBlock(doc, "tf");
    expect(screen.getByTestId("port-tf-p1").getAttribute("title")).toContain("orientation through p2");
    tf.unmount();

    renderBlock(doc, "de");
    expect(screen.getByTestId("port-de-p").getAttribute("title")).toBe("p · power · Generic");
    expect(screen.getByTestId("port-de-p").getAttribute("data-orientation")).toBe("any");
  });
});

describe("the block inspector's port list", () => {
  it("shows the orientation of a fixed port and leaves an any port alone", () => {
    open([node("C", "c"), node("De", "de")]);
    useDocumentStore.getState().setSelection(["c"], []);
    const { unmount } = render(<Inspector />);
    const row = screen.getByTestId("inspector-port-p-orientation");
    expect(row.getAttribute("data-orientation")).toBe("in");
    expect(row.textContent).toContain("in: a bond must end here");
    unmount();

    useDocumentStore.getState().setSelection(["de"], []);
    render(<Inspector />);
    expect(screen.queryByTestId("inspector-port-p-orientation")).toBeNull();
  });
});

describe("the bond inspector", () => {
  function selectBond(doc: Model, id: string): void {
    useDocumentStore.getState().openDocument("demo", "OrientationUi", doc);
    useDocumentStore.getState().setSelection([], [id]);
  }

  it("says why a bond cannot be reversed", () => {
    const se = node("Se", "se");
    const c = node("C", "c", "C1");
    const doc = open([se, c], [createConnection("c1", "bond", { node: "se", port: "p" }, { node: "c", port: "p" })]);
    selectBond(doc, "c1");
    render(<Inspector />);
    const note = screen.getByTestId("inspector-connection-reverse-c1");
    expect(note.getAttribute("data-reversible")).toBe("false");
    expect(note.textContent).toContain("the port `C1.p` is declared `in`: a bond must end there");
  });

  it("says what reversing a 0-1 junction bond does", () => {
    const zero = createJunctionNode("0", { x: 0, y: 0 }, "z", "Zero");
    const one = createJunctionNode("1", { x: 0, y: 0 }, "o", "One");
    const doc = open([zero, one], [createConnection("c1", "bond", { node: "z" }, { node: "o" })]);
    selectBond(doc, "c1");
    render(<Inspector />);
    const note = screen.getByTestId("inspector-connection-reverse-c1");
    expect(note.getAttribute("data-reversible")).toBe("true");
    expect(note.textContent?.toLowerCase()).toContain(
      "reverses the reference direction of everything behind this bond",
    );
  });
});

describe("the Reverse bond item of the context menu", () => {
  it("is disabled with a tooltip when the check refuses, and does nothing on click", () => {
    const onReverse = vi.fn();
    const se = node("Se", "se");
    const c = node("C", "c", "C1");
    const bond = createConnection("c1", "bond", { node: "se", port: "p" }, { node: "c", port: "p" });
    const doc = open([se, c], [bond]);
    const check = checkReverse(doc, index, bond);
    render(<ReverseBondItem check={check} onReverse={onReverse} />);
    const item = screen.getByTestId("reverse-bond");
    expect(item.getAttribute("aria-disabled")).toBe("true");
    expect(item.getAttribute("title")).toContain("the port `C1.p` is declared `in`: a bond must end there");
    expect(screen.getByTestId("reverse-bond-note").textContent).toContain("a bond must end there");
    fireEvent.click(item);
    expect(onReverse).not.toHaveBeenCalled();
  });

  it("stays enabled for a 0-1 bond, with the text of what it does", () => {
    const onReverse = vi.fn();
    render(<ReverseBondItem check={{ ok: true, note: REVERSE_JUNCTION_NOTE }} onReverse={onReverse} />);
    const item = screen.getByTestId("reverse-bond");
    expect(item.getAttribute("aria-disabled")).toBeNull();
    expect(item.getAttribute("title")?.toLowerCase()).toContain(
      "reverses the reference direction of everything behind this bond",
    );
    fireEvent.click(item);
    expect(onReverse).toHaveBeenCalledTimes(1);
  });

  it("is plain when nothing needs saying", () => {
    const onReverse = vi.fn();
    render(<ReverseBondItem check={{ ok: true, note: null }} onReverse={onReverse} />);
    expect(screen.getByTestId("reverse-bond").getAttribute("title")).toBeNull();
    expect(screen.queryByTestId("reverse-bond-note")).toBeNull();
    fireEvent.click(screen.getByTestId("reverse-bond"));
    expect(onReverse).toHaveBeenCalledTimes(1);
  });
});
