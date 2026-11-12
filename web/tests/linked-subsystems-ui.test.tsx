/**
 * Library subsystems in the editor's panels: the inspector of an instance (which
 * definition, the pinned values, the ones this instance sets, reset, detach),
 * Make reusable on an ordinary subsystem, the pin on a parameter inside, the
 * breadcrumb banner, the acknowledgement before a shared port is deleted, the
 * badge data on a diagram node and removing a definition from the library.
 */

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog, CatalogBlock } from "../src/contracts/catalog";
import type { Model, ModelNode } from "../src/contracts/model";
import { resetDiagnosticsStore } from "../src/diagnostics/store";
import { buildDiagram } from "../src/editor/buildFlow";
import {
  PortDeleteConfirm,
  requestSubsystemPortDelete,
  usePortDeleteStore,
} from "../src/editor/PortDeleteConfirm";
import { SubsystemBreadcrumbs } from "../src/editor/SubsystemBreadcrumbs";
import { Inspector } from "../src/inspector/Inspector";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { LibraryItemMenu } from "../src/library/LibraryItemMenu";
import { linkedDefinition, readPin } from "../src/library/linkedSubsystems";
import { resetRunStore } from "../src/plot/runStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;
const index = buildCatalogIndex(catalog);

function node(id: string, name: string, block: ModelNode["block"], extra: Partial<ModelNode> = {}): ModelNode {
  return { id, name, block, position: { x: 0, y: 0 }, ...extra };
}

function robot(): Model {
  const doc = createEmptyModel("Robot", "0.1.0");
  doc.diagram.nodes = [
    node("n1", "Act1", {
      subsystem: {
        ports: [{ name: "shaft", kind: "power", domain: "Generic", size: [1], node: "a1", port: "junction" }],
        diagram: {
          nodes: [
            node("a1", "hub", { junction: "1" }),
            node("a2", "rotor", { ref: "stdlib:bondgraph/I" }, { params: { i: "0.02" } }),
            node("a3", "damper", { ref: "stdlib:bondgraph/R" }, { params: { r: "0.1" } }),
          ],
          connections: [
            { id: "b1", kind: "bond", from: { node: "a1" }, to: { node: "a2", port: "p" } },
            { id: "b2", kind: "bond", from: { node: "a1" }, to: { node: "a3", port: "p" } },
          ],
        },
      },
    }),
    node("n2", "Load", { ref: "stdlib:bondgraph/R" }, { params: { r: "1.0" } }),
  ];
  doc.diagram.connections = [
    { id: "c1", kind: "bond", from: { node: "n1", port: "shaft" }, to: { node: "n2", port: "p" } },
  ];
  return doc;
}

const ACTUATOR_BLOCK = { ref: "project:Actuator", name: "Actuator", subsystem: true, parameters: [] } as unknown as CatalogBlock;

const store = () => useDocumentStore.getState();
const doc = (): Model => store().doc as Model;
const top = (name: string): ModelNode => doc().diagram.nodes.find((entry) => entry.name === name) as ModelNode;
const inner = (name: string) => {
  const found = top(name);
  if (!("subsystem" in found.block)) {
    throw new Error(`${name} is not a subsystem`);
  }
  return found.block.subsystem.diagram;
};

/** `Act1` made reusable as `Actuator`, with a second instance `Act2`. */
function twoActuators(): string {
  store().openDocument("demo", "Robot", robot());
  store().makeSubsystemReusable("n1", "Actuator", []);
  const id = store().addBlock(ACTUATOR_BLOCK, { x: 300, y: 0 }) as string;
  store().renameNode(id, "Act2");
  return id;
}

beforeEach(() => {
  resetDocumentStore();
  resetCatalogStore();
  resetDiagnosticsStore();
  resetRunStore();
  usePortDeleteStore.getState().close();
  useCatalogStore.getState().setCatalog(catalog);
});

describe("an ordinary subsystem", () => {
  it("is made reusable from the inspector", () => {
    store().openDocument("demo", "Robot", robot());
    store().setSelection(["n1"], []);
    render(<Inspector />);
    expect(screen.queryByTestId("inspector-linked")).toBeNull();
    expect(screen.getByTestId("inspector-save-library").textContent).toBe("Export as code block…");

    fireEvent.click(screen.getByTestId("inspector-make-reusable"));
    const name = screen.getByTestId("inspector-make-reusable-name") as HTMLInputElement;
    expect(name.value).toBe("Act");
    fireEvent.change(name, { target: { value: "2bad" } });
    expect((screen.getByTestId("inspector-make-reusable-create") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId("inspector-make-reusable-error").textContent).toContain("starts with a letter");
    fireEvent.change(name, { target: { value: "Actuator" } });
    fireEvent.click(screen.getByTestId("inspector-make-reusable-create"));

    expect(linkedDefinition(top("Act1"))).toBe("Actuator");
    expect(screen.getByTestId("inspector-linked").getAttribute("data-definition")).toBe("Actuator");
    expect(screen.getByTestId("inspector-linked-summary").textContent).toContain("1 instance in this model");
    expect(screen.getByTestId("inspector-linked-none")).toBeTruthy();
    expect(screen.queryByTestId("inspector-make-reusable")).toBeNull();
  });
});

describe("the inspector of an instance", () => {
  it("lists the pinned values, marks the ones set here and resets them", () => {
    const act2 = twoActuators();
    store().setDefinitionPin("Actuator", "params", "rotor/i", true);
    store().setDefinitionPin("Actuator", "params", "damper/r", true);
    store().setSelection([act2], []);
    render(<Inspector />);

    expect(screen.getByTestId("inspector-linked-summary").textContent).toContain("2 instances in this model");
    expect(screen.getByTestId("inspector-linked-changed").getAttribute("data-changed")).toBe("0");
    expect(screen.queryByTestId("inspector-linked-reset-all")).toBeNull();

    const field = screen.getByTestId("inspector-linked-params-rotor-i") as HTMLInputElement;
    expect(field.value).toBe("0.02");
    fireEvent.change(field, { target: { value: "0.08" } });
    fireEvent.keyDown(field, { key: "Enter" });

    expect(readPin(inner("Act2"), "params", "rotor/i")).toBe("0.08");
    expect(readPin(inner("Act1"), "params", "rotor/i")).toBe("0.02");
    expect(screen.getByTestId("inspector-linked-changed").getAttribute("data-changed")).toBe("1");
    expect(screen.getByTestId("inspector-linked-changed").textContent).toContain("1 of 2 pinned values");
    expect(screen.getByTestId("inspector-linked-params-rotor-i-changed")).toBeTruthy();
    expect(screen.queryByTestId("inspector-linked-params-damper-r-changed")).toBeNull();

    fireEvent.click(screen.getByTestId("inspector-linked-reset-all"));
    expect(readPin(inner("Act2"), "params", "rotor/i")).toBe("0.02");
    expect(screen.getByTestId("inspector-linked-changed").getAttribute("data-changed")).toBe("0");
  });

  it("detaches after a second click", () => {
    const act2 = twoActuators();
    store().setSelection([act2], []);
    render(<Inspector />);
    fireEvent.click(screen.getByTestId("inspector-detach"));
    expect(linkedDefinition(top("Act2"))).toBe("Actuator");
    fireEvent.click(screen.getByTestId("inspector-detach-confirm"));
    expect(linkedDefinition(top("Act2"))).toBeNull();
    expect(screen.queryByTestId("inspector-linked")).toBeNull();
  });
});

describe("inside a library subsystem", () => {
  it("a parameter is pinned from its field, and unpinning asks when an instance has its own value", () => {
    const act2 = twoActuators();
    store().enterSubsystem("n1");
    store().setSelection(["a2"], []);
    render(<Inspector />);

    const pin = screen.getByTestId("inspector-pin-params-i");
    expect(pin.getAttribute("data-pinned")).toBe("false");
    fireEvent.click(pin);
    expect(doc().definitions?.Actuator?.pins).toEqual({ params: ["rotor/i"] });
    expect(screen.getByTestId("inspector-pin-params-i").getAttribute("data-pinned")).toBe("true");
    expect(screen.getByTestId("inspector-pin-params-i").textContent).toContain("Act1");

    // No instance has its own value: one click unpins.
    fireEvent.click(screen.getByTestId("inspector-pin-params-i"));
    expect(doc().definitions?.Actuator?.pins).toBeUndefined();

    fireEvent.click(screen.getByTestId("inspector-pin-params-i"));
    act(() => {
      store().navigateToPath([]);
      store().setInstanceValue(act2, "params", "rotor/i", "0.08");
      store().enterSubsystem("n1");
      store().setSelection(["a2"], []);
    });
    fireEvent.click(screen.getByTestId("inspector-pin-params-i"));
    const confirm = screen.getByTestId("inspector-pin-params-i-confirm");
    expect(confirm.textContent).toContain("1 instance has a value of their own (Act2)");
    expect(doc().definitions?.Actuator?.pins).toEqual({ params: ["rotor/i"] });
    fireEvent.click(screen.getByTestId("inspector-pin-params-i-confirm-yes"));
    expect(doc().definitions?.Actuator?.pins).toBeUndefined();
    expect(readPin(inner("Act2"), "params", "rotor/i")).toBe("0.02");
  });

  it("has no pin outside a library subsystem", () => {
    store().openDocument("demo", "Robot", robot());
    store().setSelection(["n2"], []);
    render(<Inspector />);
    expect(screen.getByTestId("inspector-param-r")).toBeTruthy();
    expect(screen.queryByTestId("inspector-pin-params-r")).toBeNull();
  });

  it("the breadcrumbs say what an edit reaches", () => {
    twoActuators();
    render(<SubsystemBreadcrumbs />);
    expect(screen.queryByTestId("breadcrumb-shared")).toBeNull();
    store().enterSubsystem("n1");
    render(<SubsystemBreadcrumbs />);
    const shared = screen.getAllByTestId("breadcrumb-shared").pop() as HTMLElement;
    expect(shared.getAttribute("data-definition")).toBe("Actuator");
    expect(shared.textContent).toContain("2 instances");
    expect(screen.getAllByTestId("breadcrumb-1").pop()?.textContent).toBe("Act1 (Actuator)");
  });

  it("deleting a port always asks, and names every instance's connections", () => {
    twoActuators();
    store().enterSubsystem("n1");
    expect(requestSubsystemPortDelete(["shaft"], "ports")).toBeNull();
    render(<PortDeleteConfirm />);
    const dialog = screen.getByTestId("port-delete-dialog");
    expect(screen.getByTestId("port-delete-shared").textContent).toContain("library subsystem Actuator");
    expect(screen.getByTestId("port-delete-shared").textContent).toContain("2 instances in this model");
    expect(within(dialog).getByText("Act1.shaft → Load.p")).toBeTruthy();
    // Nothing is deleted until the dialog is confirmed.
    expect(doc().definitions?.Actuator?.ports).toHaveLength(1);
    fireEvent.click(screen.getByTestId("port-delete-confirm"));
    expect(doc().definitions?.Actuator?.ports).toEqual([]);
    expect(doc().diagram.connections).toEqual([]);
  });

  it("deleting an unconnected port of an ordinary subsystem does not ask", () => {
    const model = robot();
    model.diagram.connections = [];
    store().openDocument("demo", "Robot", model);
    store().enterSubsystem("n1");
    expect(requestSubsystemPortDelete(["shaft"], "ports")).toBeNull();
    expect(usePortDeleteStore.getState().request).toBeNull();
    const first = top("Act1");
    expect("subsystem" in first.block && first.block.subsystem.ports).toEqual([]);
  });
});

describe("on the diagram and in the library", () => {
  it("an instance carries its definition and its number of own values", () => {
    const act2 = twoActuators();
    store().setDefinitionPin("Actuator", "params", "rotor/i", true);
    store().setInstanceValue(act2, "params", "rotor/i", "0.08");
    const flow = buildDiagram(doc(), index, { nodes: [], connections: [] });
    const data = (id: string) => flow.nodes.find((entry) => entry.id === id)?.data as { linked: unknown };
    expect(data("n1").linked).toEqual({ definition: "Actuator", changed: 0 });
    expect(data(act2).linked).toEqual({ definition: "Actuator", changed: 1 });
    expect(data("n2").linked).toBeNull();
  });

  it("removing a definition asks first and leaves ordinary subsystems", () => {
    twoActuators();
    render(
      <LibraryItemMenu
        menu={{ x: 0, y: 0, ref: "project:Actuator", label: "Actuator", hasSource: true }}
        onClose={() => undefined}
      />,
    );
    expect(screen.queryByTestId("library-menu-source")).toBeNull();
    fireEvent.click(screen.getByTestId("library-menu-remove"));
    expect(screen.getByTestId("library-menu-remove-confirm").textContent).toContain(
      "Its 2 instances in this model become ordinary subsystems",
    );
    expect(doc().definitions?.Actuator).toBeDefined();
    fireEvent.click(screen.getByTestId("library-menu-remove-yes"));
    expect(doc().definitions?.Actuator).toBeUndefined();
    expect(linkedDefinition(top("Act1"))).toBeNull();
  });
});

describe("renaming a port of a library subsystem", () => {
  it("asks once, then renames it in every instance", () => {
    twoActuators();
    store().enterSubsystem("n1");
    store().setSelection(["terminal:shaft"], []);
    render(<Inspector />);
    const field = screen.getByTestId("inspector-port-name") as HTMLInputElement;
    fireEvent.change(field, { target: { value: "axle" } });
    fireEvent.keyDown(field, { key: "Enter" });
    expect(screen.getByTestId("inspector-port-name-error").textContent).toContain(
      "renames the port in all 2 instances of Actuator",
    );
    expect(doc().definitions?.Actuator?.ports.map((port) => port.name)).toEqual(["shaft"]);
    fireEvent.keyDown(field, { key: "Enter" });
    expect(doc().definitions?.Actuator?.ports.map((port) => port.name)).toEqual(["axle"]);
    const second = top("Act2");
    expect("subsystem" in second.block && second.block.subsystem.ports.map((port) => port.name)).toEqual([
      "axle",
    ]);
  });
});
