/**
 * The Equations manager (inspector, nothing selected) and the Σ decoration of
 * driven inspector fields: add/rename/edit globals in the table, live values
 * and cycle errors, "used by" click-through, the Equations view, name
 * completion in a block parameter and the evaluated readout.
 */

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog, CatalogBlock } from "../src/contracts/catalog";
import type { ModelNode } from "../src/contracts/model";
import { resetDiagnosticsStore } from "../src/diagnostics/store";
import { Inspector } from "../src/inspector/Inspector";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { resetRunStore } from "../src/plot/runStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel, createNodeFromBlock } from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;

function block(name: string): CatalogBlock {
  const entry = catalog.blocks.find((candidate) => candidate.name === name);
  if (entry === undefined) {
    throw new Error(`no block ${name}`);
  }
  return entry;
}

function openModel(): void {
  const doc = createEmptyModel("Springy");
  const spring: ModelNode = createNodeFromBlock(block("Spring"), { x: 0, y: 0 }, "n1", "Spring1");
  doc.diagram.nodes = [spring];
  useDocumentStore.getState().openDocument("demo", "Springy", doc);
}

function input(testId: string): HTMLInputElement {
  return screen.getByTestId(testId) as HTMLInputElement;
}

function type(testId: string, text: string): void {
  const field = input(testId);
  fireEvent.focus(field);
  fireEvent.change(field, { target: { value: text, selectionStart: text.length } });
  fireEvent.keyDown(field, { key: "Enter" });
}

const globals = () => useDocumentStore.getState().doc?.parameters ?? [];

beforeEach(() => {
  resetDocumentStore();
  resetCatalogStore();
  resetDiagnosticsStore();
  resetRunStore();
  useCatalogStore.getState().setCatalog(catalog);
  openModel();
});

describe("the Equations manager", () => {
  it("is the inspector when nothing is selected and edits globals with live values", () => {
    render(<Inspector />);
    expect(screen.getByTestId("inspector-model").textContent).toContain("Springy");
    expect(screen.getByTestId("globals-empty")).toBeTruthy();

    fireEvent.click(screen.getByTestId("global-add"));
    expect(globals().map((entry) => entry.name)).toEqual(["p1"]);
    type("global-name-p1", "m");
    type("global-value-m", "2");
    fireEvent.click(screen.getByTestId("global-add"));
    type("global-name-p1", "k");
    type("global-value-k", "= 4*m");
    expect(globals()).toEqual([
      { name: "m", value: "2" },
      { name: "k", value: "4*m" },
    ]);
    expect(screen.getByTestId("global-result-k").textContent).toBe("8");

    // A cycle shows on the row; fixing it clears the error.
    type("global-value-m", "k / 4");
    expect(screen.getByTestId("global-error-m").textContent).toBe("Cycle: m → k → m.");
    expect(screen.getByTestId("global-error-k").textContent).toBe("Cycle: k → m → k.");
    type("global-value-m", "2");
    expect(screen.queryByTestId("global-error-m")).toBeNull();

    // A bad name is refused inline and the document keeps the old one.
    type("global-name-k", "2k");
    expect(screen.getByTestId("global-name-k-error").textContent).toContain("letter or underscore");
    expect(globals()[1]?.name).toBe("k");
  });

  it("decorates a driven block parameter, completes global names and renames through", () => {
    useDocumentStore.getState().addGlobalParameter({ name: "m", value: "2" });
    useDocumentStore.getState().addGlobalParameter({ name: "k", value: "4*m", unit: "N/m" });
    useDocumentStore.getState().addGlobalParameter({ name: "mu", value: "0.5" });
    render(<Inspector />);
    act(() => useDocumentStore.getState().setSelection(["n1"], []));

    // Completion: typing "m" offers `mu` with its value; Tab takes it.
    const field = input("inspector-param-k");
    fireEvent.focus(field);
    fireEvent.change(field, { target: { value: "2*", selectionStart: 2 } });
    expect(screen.queryByTestId("inspector-param-k-completions")).toBeNull();
    field.setSelectionRange(3, 3);
    fireEvent.change(field, { target: { value: "2*m" } });
    const list = screen.getByTestId("inspector-param-k-completions");
    expect(within(list).getByText("mu")).toBeTruthy();
    expect(within(list).getByText("= 0.5")).toBeTruthy();
    fireEvent.keyDown(field, { key: "Tab" });
    expect(field.value).toBe("2*mu");
    expect(screen.queryByTestId("inspector-param-k-completions")).toBeNull();
    fireEvent.keyDown(field, { key: "Escape" });

    type("inspector-param-k", "k");
    const node = () => useDocumentStore.getState().doc?.diagram.nodes[0];
    expect(node()?.params?.k).toBe("k");
    expect(screen.getByTestId("inspector-param-k-sigma").textContent).toBe("Σ");
    expect(screen.getByTestId("inspector-param-k-value").textContent).toBe("= 8 N/m");
    expect(input("inspector-param-k").title).toBe("Equation: k");

    // The min bound uses the evaluated value: -k is -8 < 0.
    const spring = input("inspector-param-k");
    fireEvent.change(spring, { target: { value: "-k" } });
    expect(screen.getByTestId("inspector-param-k-error").textContent).toContain("at least 0");
    fireEvent.keyDown(spring, { key: "Escape" });

    // A plain value has no Σ.
    type("inspector-param-x_free", "0.1");
    expect(screen.queryByTestId("inspector-param-x_free-sigma")).toBeNull();

    // Rename k -> stiffness from the table: the block follows, as one undo step.
    act(() => useDocumentStore.getState().setSelection([], []));
    fireEvent.click(screen.getByTestId("global-uses-k"));
    expect(screen.getByTestId("global-users-k").textContent).toContain("Spring1.k");
    type("global-name-k", "stiffness");
    expect(node()?.params?.k).toBe("stiffness");
    act(() => useDocumentStore.getState().undo());
    expect(node()?.params?.k).toBe("k");
    expect(globals()[1]?.name).toBe("k");
    act(() => useDocumentStore.getState().redo());

    // Deleting a used global is refused with the list of users.
    fireEvent.click(screen.getByTestId("global-delete-stiffness"));
    expect(screen.getByTestId("global-refusal-stiffness").textContent).toContain("Spring1.k");

    // Click-through from "used by" selects the block.
    fireEvent.click(screen.getByTestId("global-uses-stiffness"));
    fireEvent.click(screen.getByTestId("global-user-stiffness-Spring1.k"));
    expect(useDocumentStore.getState().selection.nodes).toEqual(["n1"]);
  });

  it("lists driven block values in the Equations view, editable in place", () => {
    useDocumentStore.getState().addGlobalParameter({ name: "m", value: "2" });
    useDocumentStore
      .getState()
      .setFieldExpression({ diagramPath: [], nodeId: "n1", kind: "param", key: "k" }, "500*m");
    render(<Inspector />);
    fireEvent.click(screen.getByTestId("equations-tab-equations"));
    expect(screen.getByTestId("equation-value-Spring1.k").textContent).toBe("1000");
    type("equation-expr-Spring1.k", "250*m");
    expect(useDocumentStore.getState().doc?.diagram.nodes[0]?.params?.k).toBe("250*m");
    expect(screen.getByTestId("equation-value-Spring1.k").textContent).toBe("500");

    fireEvent.click(screen.getByTestId("equations-tab-order"));
    expect(screen.getByTestId("globals-order").textContent).toContain("m = 2");

    fireEvent.click(screen.getByTestId("equations-tab-equations"));
    fireEvent.click(screen.getByTestId("equation-select-Spring1.k"));
    expect(useDocumentStore.getState().selection.nodes).toEqual(["n1"]);
  });

  it("opens the wide manager with unit and comment columns", () => {
    useDocumentStore.getState().addGlobalParameter({ name: "m", value: "2" });
    render(<Inspector />);
    fireEvent.click(screen.getByTestId("equations-open-dialog"));
    const dialog = screen.getByTestId("equations-dialog");
    expect(within(dialog).getByText("Unit")).toBeTruthy();
    type("dialog-global-unit-m", "kg");
    type("dialog-global-comment-m", "Base mass");
    expect(globals()[0]).toEqual({ name: "m", value: "2", unit: "kg", description: "Base mass" });
    fireEvent.click(screen.getByTestId("equations-dialog-close"));
    expect(screen.queryByTestId("equations-dialog")).toBeNull();
  });
});
