/**
 * W1.2 acceptance (plan 7.2, 7.4 and the work package): the inspector edits
 * parameters, constants, names and starts through the document store, so undo
 * restores the document; rename collisions and catalog bounds are refused with
 * a message; multiple selections and connection selections get a summary.
 */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog, CatalogBlock } from "../src/contracts/catalog";
import type { Diagnostic } from "../src/contracts/diagnostic";
import type { Model, ModelNode } from "../src/contracts/model";
import { resetDiagnosticsStore, useDiagnosticsStore } from "../src/diagnostics/store";
import { Inspector } from "../src/inspector/Inspector";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import {
  resetDocumentStore,
  useDocumentStore,
} from "../src/state/documentStore";
import {
  createConnection,
  createEmptyModel,
  createNodeFromBlock,
} from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;

function block(name: string): CatalogBlock {
  const entry = catalog.blocks.find((blockEntry) => blockEntry.name === name);
  if (entry === undefined) {
    throw new Error(`the catalog has no block ${name}`);
  }
  return entry;
}

function node(name: string, id: string, instance = name): ModelNode {
  return createNodeFromBlock(block(name), { x: 0, y: 0 }, id, instance);
}

function open(nodes: readonly ModelNode[], connections: Model["diagram"]["connections"] = []): Model {
  const doc = createEmptyModel("InspectorTest");
  doc.diagram.nodes = [...nodes];
  doc.diagram.connections = [...connections];
  useDocumentStore.getState().openDocument("demo", "InspectorTest", doc);
  return doc;
}

function docNode(id: string): ModelNode | undefined {
  return useDocumentStore.getState().doc?.diagram.nodes.find((entry) => entry.id === id);
}

function input(testId: string): HTMLInputElement {
  return screen.getByTestId(testId) as HTMLInputElement;
}

beforeEach(() => {
  resetDocumentStore();
  resetCatalogStore();
  resetDiagnosticsStore();
  useCatalogStore.getState().setCatalog(catalog);
});

describe("inspector fields", () => {
  it("renders parameters, units, bounds, ports and start values", () => {
    const motor = node("DCMotor", "n1", "Motor1");
    open([motor]);
    useDocumentStore.getState().setSelection(["n1"], []);
    render(<Inspector />);

    expect(screen.getByTestId("inspector-title").textContent).toBe("DCMotor");
    expect(screen.getByTestId("inspector-ref").textContent).toContain(
      "stdlib:converters/DCMotor",
    );
    expect(screen.getByTestId("inspector-description").textContent).toContain(
      "Permanent-magnet DC motor",
    );

    expect(input("inspector-param-R").value).toBe("2.0");
    expect(input("inspector-param-R").getAttribute("aria-invalid")).toBe("false");
    const rField = screen.getByTestId("inspector-param-R-field");
    expect(rField.textContent).toContain("Ohm");
    expect(rField.textContent).toContain("Winding resistance");
    expect(rField.textContent).toContain("min");
    expect(rField.textContent).toContain("default");

    // Five parameters on the DCMotor; the composite has no own variables
    // (its dynamic signals are observed aliases), so there are no start fields.
    expect(screen.queryByTestId("inspector-param-t_step")).toBeNull();
    expect(screen.getByRole("heading", { name: /Parameters/ }).textContent).toContain("5");
    expect(screen.queryByTestId("inspector-start-i")).toBeNull();

    // Ports carry the domain letter and read-only signal ids.
    expect(screen.getByTestId("inspector-port-p-letter").textContent).toBe("E");
    expect(screen.getByTestId("inspector-port-shaft-letter").textContent).toBe("R");
    expect(screen.getByTestId("inspector-signal-Motor1/shaft.f").textContent).toContain(
      "Motor1/shaft.f",
    );
    expect(screen.getByTestId("inspector-signal-Motor1/shaft.f").textContent).toContain(
      "rad/s",
    );
    expect(screen.getByTestId("inspector-signal-Motor1/p.e").textContent).toContain(
      "Motor1/p.e",
    );
    expect(screen.getByTestId("inspector-signal-Motor1/p.P").textContent).toContain(
      "Motor1/p.P",
    );
    expect(screen.getByText("This block has no constants.")).toBeTruthy();
  });

  it("commits a parameter edit and undo restores the document", () => {
    const motor = node("DCMotor", "n1", "Motor1");
    open([motor]);
    useDocumentStore.getState().setSelection(["n1"], []);
    render(<Inspector />);

    const field = input("inspector-param-R");
    fireEvent.change(field, { target: { value: "3.5" } });
    expect(field.value).toBe("3.5");
    expect(docNode("n1")?.params?.R).toBe("2.0");
    expect(useDocumentStore.getState().past).toHaveLength(0);

    fireEvent.blur(field);
    expect(docNode("n1")?.params?.R).toBe("3.5");
    expect(useDocumentStore.getState().past).toHaveLength(1);
    expect(useDocumentStore.getState().saveState).toBe("dirty");

    act(() => useDocumentStore.getState().undo());
    expect(docNode("n1")?.params?.R).toBe("2.0");
    expect(input("inspector-param-R").value).toBe("2.0");

    act(() => useDocumentStore.getState().redo());
    expect(docNode("n1")?.params?.R).toBe("3.5");
    expect(input("inspector-param-R").value).toBe("3.5");
  });

  it("shows an Int enumeration as a drop-down and stores the choice", () => {
    const custom = JSON.parse(JSON.stringify(catalog)) as Catalog;
    const gain = custom.blocks.find((entry) => entry.name === "Gain");
    if (gain === undefined) {
      throw new Error("the catalog has no Gain block");
    }
    gain.parameters.push({
      name: "mode",
      type: "Int",
      default: "1",
      unit: null,
      min: null,
      max: null,
      tunable: false,
      description: "Interpolation mode",
      options: ["hold", "linear"],
    });
    useCatalogStore.getState().setCatalog(custom);
    const gainNode = createNodeFromBlock(gain, { x: 0, y: 0 }, "n5", "Gain1");
    open([gainNode]);
    useDocumentStore.getState().setSelection(["n5"], []);
    render(<Inspector />);

    const select = screen.getByTestId("inspector-param-mode") as HTMLSelectElement;
    expect(select.tagName).toBe("SELECT");
    expect(select.value).toBe("1");
    expect(screen.getByTestId("inspector-param-mode-field").textContent).toContain(
      "Interpolation mode",
    );

    fireEvent.change(select, { target: { value: "2" } });
    expect(docNode("n5")?.params?.mode).toBe("2");

    act(() => useDocumentStore.getState().undo());
    expect(docNode("n5")?.params?.mode).toBe("1");
    expect((screen.getByTestId("inspector-param-mode") as HTMLSelectElement).value).toBe("1");
  });

  it("resets a parameter to its catalog default", () => {
    const motor = node("DCMotor", "n1", "Motor1");
    open([motor]);
    useDocumentStore.getState().setSelection(["n1"], []);
    render(<Inspector />);

    const field = input("inspector-param-R");
    fireEvent.change(field, { target: { value: "3.5" } });
    fireEvent.blur(field);
    expect(docNode("n1")?.params?.R).toBe("3.5");

    fireEvent.click(screen.getByTestId("inspector-param-R-reset"));
    expect(docNode("n1")?.params?.R).toBe("2.0");
    expect(input("inspector-param-R").value).toBe("2.0");
  });

  it("refuses a rename collision with a message and keeps the old name", () => {
    const motor = node("DCMotor", "n1", "Motor1");
    const capacitor = node("C", "n2", "Cap1");
    open([motor, capacitor]);
    useDocumentStore.getState().setSelection(["n1"], []);
    render(<Inspector />);

    const name = input("inspector-name");
    fireEvent.change(name, { target: { value: "Cap1" } });
    expect(name.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByTestId("inspector-name-error").textContent).toContain(
      'already has a block named "Cap1"',
    );

    fireEvent.keyDown(name, { key: "Enter" });
    expect(docNode("n1")?.name).toBe("Motor1");
    expect(useDocumentStore.getState().past).toHaveLength(0);

    fireEvent.change(name, { target: { value: "1bad" } });
    expect(screen.getByTestId("inspector-name-error").textContent).toContain(
      "Names start with a letter",
    );
    fireEvent.keyDown(name, { key: "Enter" });
    expect(docNode("n1")?.name).toBe("Motor1");

    fireEvent.change(name, { target: { value: "Motor2" } });
    expect(screen.queryByTestId("inspector-name-error")).toBeNull();
    fireEvent.keyDown(name, { key: "Enter" });
    expect(docNode("n1")?.name).toBe("Motor2");
    expect(input("inspector-name").value).toBe("Motor2");
    expect(screen.getByTestId("inspector-signal-Motor2/shaft.f").textContent).toContain(
      "Motor2/shaft.f",
    );
    expect(useDocumentStore.getState().past).toHaveLength(1);

    act(() => useDocumentStore.getState().undo());
    expect(docNode("n1")?.name).toBe("Motor1");
    expect(input("inspector-name").value).toBe("Motor1");
  });

  it("validates min and max bounds inline before committing", () => {
    const motor = node("DCMotor", "n1", "Motor1");
    open([motor]);
    useDocumentStore.getState().setSelection(["n1"], []);
    const { unmount } = render(<Inspector />);

    const field = input("inspector-param-R");
    fireEvent.change(field, { target: { value: "-1" } });
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByTestId("inspector-param-R-error").textContent).toBe(
      "Must be at least 0 Ohm.",
    );
    fireEvent.keyDown(field, { key: "Enter" });
    expect(docNode("n1")?.params?.R).toBe("2.0");
    expect(useDocumentStore.getState().past).toHaveLength(0);

    fireEvent.change(field, { target: { value: "0" } });
    expect(screen.queryByTestId("inspector-param-R-error")).toBeNull();
    fireEvent.blur(field);
    expect(docNode("n1")?.params?.R).toBe("0");

    // A catalog with a maximum proves the upper bound too.
    unmount();
    const bounded = JSON.parse(JSON.stringify(catalog)) as Catalog;
    const decl = bounded.blocks
      .find((entry) => entry.name === "DCMotor")
      ?.parameters.find((entry) => entry.name === "R");
    if (decl === undefined) {
      throw new Error("DCMotor has no R parameter");
    }
    decl.max = 3;
    useCatalogStore.getState().setCatalog(bounded);
    render(<Inspector />);
    const boundedField = input("inspector-param-R");
    fireEvent.change(boundedField, { target: { value: "4" } });
    expect(screen.getByTestId("inspector-param-R-error").textContent).toBe(
      "Must be at most 3 Ohm.",
    );
    fireEvent.keyDown(boundedField, { key: "Enter" });
    expect(docNode("n1")?.params?.R).toBe("0");
  });

  it("edits a start-value override and undoes it", () => {
    const inductor = node("Inductor", "n1", "L1");
    open([inductor]);
    useDocumentStore.getState().setSelection(["n1"], []);
    render(<Inspector />);

    const field = input("inspector-start-i");
    fireEvent.change(field, { target: { value: "0.5" } });
    fireEvent.blur(field);
    expect(docNode("n1")?.starts?.i).toBe("0.5");
    expect(screen.getByTestId("inspector-start-i-reset")).toBeTruthy();
    expect(screen.getByTestId("inspector-start-signal-i").textContent).toBe("L1/i");

    act(() => useDocumentStore.getState().undo());
    expect(docNode("n1")?.starts?.i).toBeUndefined();
    expect(input("inspector-start-i").value).toBe("");
    expect(input("inspector-start-i").placeholder).toBe("0.0");

    act(() => useDocumentStore.getState().redo());
    expect(docNode("n1")?.starts?.i).toBe("0.5");
    expect(input("inspector-start-i").value).toBe("0.5");
  });

  it("edits a structural constant as a number and undoes it", () => {
    const sum = node("Sum", "n1", "Sum1");
    open([sum]);
    useDocumentStore.getState().setSelection(["n1"], []);
    render(<Inspector />);

    expect(screen.getByTestId("inspector-structural-note").textContent).toContain(
      "Structural constants",
    );
    expect(input("inspector-constant-N").value).toBe("2");

    fireEvent.change(input("inspector-constant-N"), { target: { value: "2.5" } });
    expect(screen.getByTestId("inspector-constant-N-error").textContent).toContain(
      "whole number",
    );
    fireEvent.keyDown(input("inspector-constant-N"), { key: "Enter" });
    expect(docNode("n1")?.constants?.N).toBeUndefined();

    fireEvent.change(input("inspector-constant-N"), { target: { value: "3" } });
    fireEvent.blur(input("inspector-constant-N"));
    expect(docNode("n1")?.constants?.N).toBe(3);
    expect(typeof docNode("n1")?.constants?.N).toBe("number");

    act(() => useDocumentStore.getState().undo());
    expect(docNode("n1")?.constants?.N).toBeUndefined();
    expect(input("inspector-constant-N").value).toBe("2");
  });

  it("shows a summary for multiple blocks and for connections", () => {
    const motor = node("DCMotor", "n1", "Motor1");
    const capacitor = node("C", "n2", "Cap1");
    const connection = createConnection(
      "c1",
      "signal",
      { node: "n1", port: "shaft" },
      { node: "n2", port: "p" },
    );
    open([motor, capacitor], [connection]);
    render(<Inspector />);

    expect(screen.getByText("Nothing selected")).toBeTruthy();

    act(() => useDocumentStore.getState().setSelection(["n1", "n2"], []));
    const summary = screen.getByTestId("inspector-multi");
    expect(summary.textContent).toContain("2 blocks selected");
    expect(summary.textContent).toContain("Motor1");
    expect(summary.textContent).toContain("Cap1");

    act(() => useDocumentStore.getState().setSelection([], ["c1"]));
    expect(screen.getByTestId("inspector-connections").textContent).toContain(
      "1 connection selected",
    );

    act(() => useDocumentStore.getState().setSelection([], []));
    expect(screen.getByText("Nothing selected")).toBeTruthy();
  });

  it("shows the node's diagnostics when the check panel passes them in", () => {
    const motor = node("DCMotor", "n1", "Motor1");
    open([motor]);
    useDocumentStore.getState().setSelection(["n1"], []);
    const diagnostics: Diagnostic[] = [
      {
        code: "E102",
        severity: "error",
        message: "Winding resistance has unit V, expected Ohm",
        hint: "Use a resistance in ohms.",
        path: "Motor1",
        node: "n1",
      },
    ];
    render(<Inspector diagnostics={diagnostics} />);

    const entry = screen.getByTestId("inspector-diagnostic-E102");
    expect(entry.textContent).toContain("Winding resistance has unit V");
    expect(entry.textContent).toContain("Use a resistance in ohms.");
  });

  it("shows the live model-check result only while it matches the document", () => {
    const motor = node("DCMotor", "n1", "Motor1");
    open([motor]);
    useDocumentStore.getState().setSelection(["n1"], []);
    render(<Inspector />);
    expect(screen.queryByTestId("inspector-diagnostic-E102")).toBeNull();

    const revision = useDocumentStore.getState().revision;
    act(() => {
      useDiagnosticsStore.getState().applyResult(
        {
          diagnostics: [
            {
              code: "E102",
              severity: "error",
              message: "unit mismatch in parameter R",
              path: "Motor1",
              node: "n1",
            },
          ],
          domains: {},
          causality: {},
          unitFactors: {},
          signals: [],
          stats: { states: 2, equations: 2 },
        },
        revision,
      );
    });
    expect(screen.getByTestId("inspector-diagnostic-E102").textContent).toContain(
      "unit mismatch in parameter R",
    );

    // The next edit makes the check stale; it disappears until the loop answers.
    act(() => {
      useDocumentStore.getState().setNodeParam("n1", "R", "3.0");
    });
    expect(screen.queryByTestId("inspector-diagnostic-E102")).toBeNull();
  });

  it("opens the catalog source read-only", () => {
    const motor = node("DCMotor", "n1", "Motor1");
    open([motor]);
    useDocumentStore.getState().setSelection(["n1"], []);
    render(<Inspector />);

    const button = screen.getByTestId("inspector-open-source");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("inspector-source-text").textContent).toContain(
      "@block DCMotor begin",
    );
    expect(screen.getByTestId("inspector-source").textContent).toContain(
      "stdlib/converters/DCMotor.jl",
    );
    fireEvent.click(button);
    expect(screen.queryByTestId("inspector-source")).toBeNull();
  });

  it("keeps the documented empty state before a model is open", () => {
    render(<Inspector />);
    expect(screen.getByText("Nothing selected")).toBeTruthy();
  });
});
