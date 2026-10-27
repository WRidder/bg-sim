/**
 * The drop-on-empty palette: filter box on top, compatible rows, mouse and
 * keyboard picking.
 */

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import type { PortDescriptor } from "../src/editor/connectionRules";
import { descriptorForPort } from "../src/editor/nodeInterface";
import { suggestTargets } from "../src/editor/suggestTargets";
import { TargetSuggestions } from "../src/editor/TargetSuggestions";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import { createEmptyModel, createNodeFromBlock } from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;
const index = buildCatalogIndex(catalog);

function setup() {
  const block = index.blocksByName.get("Constant");
  if (block === undefined) {
    throw new Error("no Constant block");
  }
  const model = createEmptyModel("Palette");
  model.diagram.nodes = [createNodeFromBlock(block, { x: 0, y: 0 }, "n1", "Cmd")];
  const origin = descriptorForPort(model.diagram.nodes, index, "n1", "y");
  if (origin === null) {
    throw new Error("no Constant output");
  }
  const items = suggestTargets(model, index, origin);
  const onPick = vi.fn();
  const onClose = vi.fn();
  render(
    <TargetSuggestions
      suggestions={items}
      origin={origin as PortDescriptor}
      x={40}
      y={60}
      onPick={onPick}
      onClose={onClose}
    />,
  );
  return { items, onPick, onClose };
}

describe("TargetSuggestions", () => {
  it("lists the compatible elements with a filter box on top", () => {
    const { items } = setup();
    expect(screen.getByTestId("target-suggestions-filter")).toBeDefined();
    expect(screen.getByTestId("target-suggestions-origin").textContent).toContain("output y");
    const options = within(screen.getByRole("listbox")).getAllByRole("option");
    expect(options).toHaveLength(items.length);
    expect(items[0]?.name).toBe("Gain");
  });

  it("filters by name as the query is typed", () => {
    setup();
    fireEvent.change(screen.getByTestId("target-suggestions-filter"), {
      target: { value: "gain" },
    });
    const options = within(screen.getByRole("listbox")).getAllByRole("option");
    expect(options.some((option) => option.textContent?.includes("Gain"))).toBe(true);
    expect(options.some((option) => option.textContent?.includes("Integrator"))).toBe(false);
  });

  it("shows an empty message when nothing matches", () => {
    setup();
    fireEvent.change(screen.getByTestId("target-suggestions-filter"), {
      target: { value: "no-such-element" },
    });
    expect(screen.getByTestId("target-suggestions-empty").textContent).toContain(
      "No compatible element matches",
    );
  });

  it("picks a row with the mouse", () => {
    const { items, onPick } = setup();
    const first = items[0];
    if (first === undefined) {
      throw new Error("no suggestion");
    }
    fireEvent.click(screen.getByTestId(`target-suggestion-${first.key}`));
    expect(onPick).toHaveBeenCalledWith(first);
  });

  it("moves with the arrow keys and picks with Enter", () => {
    const { items, onPick } = setup();
    const input = screen.getByTestId("target-suggestions-filter");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onPick).toHaveBeenCalledWith(items[1]);
  });

  it("closes on Escape", () => {
    const { onClose } = setup();
    fireEvent.keyDown(screen.getByTestId("target-suggestions-filter"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("explains when the port has no compatible element at all", () => {
    const origin: PortDescriptor = {
      nodeId: "n1",
      portName: "y",
      isJunction: false,
      kind: "signal",
      direction: "output",
      domain: "Generic",
      type: "Real",
      size: [],
      unit: null,
    };
    render(
      <TargetSuggestions
        suggestions={[]}
        origin={origin}
        x={0}
        y={0}
        onPick={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByTestId("target-suggestions-empty").textContent).toContain(
      "No library element can connect",
    );
  });
});
