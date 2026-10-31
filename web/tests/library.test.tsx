/**
 * The library browser and its typed drag payload (plan 7.2/3.2).
 */

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { LibraryBrowser } from "../src/library/LibraryBrowser";
import { LibrarySettings } from "../src/library/LibrarySettings";
import { LibraryViewToggle } from "../src/library/LibraryViewToggle";
import { resetHelpStore, useHelpStore } from "../src/app/helpStore";
import {
  EXPANDED_KEY,
  HIDDEN_KEY,
  VIEW_KEY,
  resetLibraryPrefs,
} from "../src/library/libraryPrefs";
import { expandLibraryGroups } from "./libraryHelpers";
import {
  BLOCK_DRAG_MIME,
  parseDragPayload,
  payloadForBlock,
  payloadForShape,
  readDragPayload,
  SHAPE_DRAG_MIME,
  writeDragPayload,
} from "../src/library/dnd";
import { registerShapeAdder, resetShapeRequests } from "../src/editor/shapeRequests";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;

function fakeDataTransfer() {
  const data = new Map<string, string>();
  return {
    data,
    transfer: {
      effectAllowed: "none",
      setData(format: string, value: string) {
        data.set(format, value);
      },
      getData(format: string) {
        return data.get(format) ?? "";
      },
    } as unknown as DataTransfer,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  resetLibraryPrefs();
  resetCatalogStore();
  useCatalogStore.getState().setCatalog(catalog);
});

describe("library browser", () => {
  it("renders the catalog groups plus the junction group", () => {
    const { container } = render(<LibraryBrowser />);
    const groups = [...container.querySelectorAll(".library-group")].map(
      (group) => group.getAttribute("data-testid"),
    );
    expect(groups).toEqual([
      "library-group-Bond graph",
      "library-group-Sources and sinks",
      "library-group-Continuous",
      "library-group-Electrical",
      "library-group-Translation",
      "library-group-Rotation",
      "library-group-Converters and sensors",
      "library-group-Junctions",
      "library-group-Shapes",
    ]);
  });

  it("lists all 36 catalog blocks, both junctions and the five shapes once every category is open", () => {
    render(<LibraryBrowser />);
    expandLibraryGroups();
    expect(screen.getAllByTestId(/^library-item-/)).toHaveLength(43);
    expect(screen.getByTestId("library-count").textContent).toBe("43");
    expect(screen.getByTestId("library-item-DCMotor")).toBeTruthy();
    expect(screen.getByTestId("library-item-junction-0")).toBeTruthy();
    expect(screen.getByTestId("library-item-junction-1")).toBeTruthy();
  });

  it("filters by name while typing", () => {
    render(<LibraryBrowser />);
    const search = screen.getByTestId("library-search");
    fireEvent.change(search, { target: { value: "motor" } });
    expect(screen.getAllByTestId(/^library-item-/)).toHaveLength(1);
    expect(screen.getByTestId("library-item-DCMotor")).toBeTruthy();
    expect(screen.getByTestId("library-count").textContent).toBe("1");
  });

  it("searches descriptions and refs too, and shows an empty result", () => {
    render(<LibraryBrowser />);
    const search = screen.getByTestId("library-search");
    fireEvent.change(search, { target: { value: "converters/dcmotor" } });
    expect(screen.getByTestId("library-item-DCMotor")).toBeTruthy();

    fireEvent.change(search, { target: { value: "no-such-block" } });
    expect(screen.queryAllByTestId(/^library-item-/)).toHaveLength(0);
    expect(screen.getByTestId("library-empty").textContent).toContain("no-such-block");
  });

  it("shows the parameter and port summary in the details", () => {
    render(<LibraryBrowser />);
    expandLibraryGroups();
    const item = screen.getByTestId("library-item-DCMotor");
    fireEvent.click(within(item).getByRole("button"));
    expect(within(item).getByText(/Permanent-magnet DC motor/)).toBeTruthy();
    expect(within(item).getByText("2.0")).toBeTruthy();
    expect(within(item).getByText("k_t")).toBeTruthy();
    const portTexts = [...item.querySelectorAll(".library-item__ports li")].map(
      (line) => line.textContent ?? "",
    );
    expect(portTexts.some((text) => text.includes("shaft · power"))).toBe(true);
    expect(portTexts.some((text) => text.includes("housing · power"))).toBe(true);
  });

  it("renders bond-graph letters in a serif glyph and iconic blocks as SVG", () => {
    render(<LibraryBrowser />);
    expandLibraryGroups();
    const capacitor = screen.getByTestId("library-item-C");
    expect(capacitor.querySelector(".bond-letter")?.textContent).toBe("C");
    const motor = screen.getByTestId("library-item-DCMotor");
    expect(motor.querySelector("svg[data-icon='conv-dc-motor']")).toBeTruthy();
  });

  it("shows a loading state when no catalog is loaded", () => {
    resetCatalogStore();
    useCatalogStore.getState().setLoading();
    render(<LibraryBrowser />);
    expect(screen.getByTestId("library-loading").textContent).toContain("Loading the library");
  });
});

describe("library categories", () => {
  function toggleOf(name: string): HTMLElement {
    return screen.getByTestId(`library-group-toggle-${name}`);
  }

  it("starts with every category collapsed, showing its name and block count", () => {
    render(<LibraryBrowser />);
    const toggles = screen.getAllByTestId(/^library-group-toggle-/);
    expect(toggles).toHaveLength(9);
    for (const toggle of toggles) {
      expect(toggle.getAttribute("aria-expanded")).toBe("false");
    }
    expect(screen.queryAllByTestId(/^library-item-/)).toHaveLength(0);
    expect(toggleOf("Bond graph").textContent).toMatch(/Bond graph\s*\d+/);
    expect(within(toggleOf("Junctions")).getByText("2")).toBeTruthy();
    expect(within(toggleOf("Shapes")).getByText("5")).toBeTruthy();
    // The total still counts every entry, collapsed or not.
    expect(screen.getByTestId("library-count").textContent).toBe("43");
  });

  it("expands and collapses one category from its header", () => {
    render(<LibraryBrowser />);
    fireEvent.click(toggleOf("Converters and sensors"));
    expect(toggleOf("Converters and sensors").getAttribute("aria-expanded")).toBe("true");
    const group = screen.getByTestId("library-group-Converters and sensors");
    expect(within(group).getByTestId("library-item-DCMotor")).toBeTruthy();
    expect(screen.queryByTestId("library-item-C")).toBeNull();

    fireEvent.click(toggleOf("Converters and sensors"));
    expect(screen.queryByTestId("library-item-DCMotor")).toBeNull();
  });

  it("remembers the expanded categories in localStorage", () => {
    const first = render(<LibraryBrowser />);
    fireEvent.click(toggleOf("Bond graph"));
    fireEvent.click(toggleOf("Junctions"));
    expect(JSON.parse(window.localStorage.getItem(EXPANDED_KEY) ?? "[]")).toEqual([
      "Bond graph",
      "Junctions",
    ]);
    first.unmount();

    resetLibraryPrefs();
    render(<LibraryBrowser />);
    expect(toggleOf("Bond graph").getAttribute("aria-expanded")).toBe("true");
    expect(toggleOf("Junctions").getAttribute("aria-expanded")).toBe("true");
    expect(toggleOf("Electrical").getAttribute("aria-expanded")).toBe("false");
    expect(screen.getByTestId("library-item-junction-1")).toBeTruthy();
  });

  it("survives unreadable storage", () => {
    window.localStorage.setItem(EXPANDED_KEY, "{not json");
    resetLibraryPrefs();
    render(<LibraryBrowser />);
    expect(toggleOf("Bond graph").getAttribute("aria-expanded")).toBe("false");
  });

  it("opens the categories with a match while searching and restores the saved state after", () => {
    render(<LibraryBrowser />);
    fireEvent.click(toggleOf("Bond graph"));
    const search = screen.getByTestId("library-search");

    fireEvent.change(search, { target: { value: "motor" } });
    expect(toggleOf("Converters and sensors").getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("library-item-DCMotor")).toBeTruthy();
    expect(screen.queryByTestId("library-group-Bond graph")).toBeNull();

    // A category collapsed during a search stays collapsed until the query changes.
    fireEvent.click(toggleOf("Converters and sensors"));
    expect(screen.queryByTestId("library-item-DCMotor")).toBeNull();
    fireEvent.change(search, { target: { value: "moto" } });
    expect(screen.getByTestId("library-item-DCMotor")).toBeTruthy();

    fireEvent.change(search, { target: { value: "" } });
    expect(toggleOf("Converters and sensors").getAttribute("aria-expanded")).toBe("false");
    expect(toggleOf("Bond graph").getAttribute("aria-expanded")).toBe("true");
    expect(screen.queryByTestId("library-item-DCMotor")).toBeNull();
    expect(JSON.parse(window.localStorage.getItem(EXPANDED_KEY) ?? "[]")).toEqual(["Bond graph"]);
  });
});

describe("library quick settings", () => {
  function renderPanel() {
    return render(
      <>
        <LibrarySettings />
        <LibraryBrowser />
      </>,
    );
  }

  function openSettings(): HTMLElement {
    fireEvent.click(screen.getByRole("button", { name: "Library settings" }));
    return screen.getByRole("dialog", { name: "Library settings" });
  }

  it("opens from the cog with a checkbox per category and closes on Escape", () => {
    renderPanel();
    const cog = screen.getByRole("button", { name: "Library settings" });
    expect(cog.getAttribute("aria-expanded")).toBe("false");
    const dialog = openSettings();
    expect(cog.getAttribute("aria-expanded")).toBe("true");
    const boxes = within(dialog).getAllByRole("checkbox");
    expect(boxes).toHaveLength(9);
    expect(within(dialog).getByLabelText("Shapes")).toBeTruthy();
    expect(boxes.every((box) => (box as HTMLInputElement).checked)).toBe(true);
    // Focus moves into the popover (the checked view radio), and Escape returns it to the cog.
    expect(document.activeElement).toBe(within(dialog).getByRole("radio", { name: "List" }));

    fireEvent.keyDown(document.activeElement ?? window, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Library settings" })).toBeNull();
    expect(document.activeElement).toBe(cog);
  });

  it("closes on a press outside the popover", () => {
    renderPanel();
    openSettings();
    fireEvent.pointerDown(screen.getByTestId("library-search"));
    expect(screen.queryByTestId("library-settings-popover")).toBeNull();
  });

  it("hides a category from the list and the search, persists it, and shows all again", () => {
    renderPanel();
    const converterCount = Number(
      screen
        .getByTestId("library-group-toggle-Converters and sensors")
        .querySelector(".library-group__count")?.textContent,
    );
    expect(converterCount).toBeGreaterThan(0);
    const dialog = openSettings();
    fireEvent.click(within(dialog).getByLabelText("Converters and sensors"));
    fireEvent.click(within(dialog).getByLabelText("Junctions"));

    expect(screen.queryByTestId("library-group-Converters and sensors")).toBeNull();
    expect(screen.queryByTestId("library-group-Junctions")).toBeNull();
    expect(JSON.parse(window.localStorage.getItem(HIDDEN_KEY) ?? "[]")).toEqual([
      "Converters and sensors",
      "Junctions",
    ]);
    expect(screen.getByTestId("library-count").textContent).toBe(String(43 - 2 - converterCount));

    fireEvent.change(screen.getByTestId("library-search"), { target: { value: "motor" } });
    expect(screen.queryByTestId("library-item-DCMotor")).toBeNull();
    expect(screen.getByTestId("library-empty").textContent).toMatch(/library settings/);
    fireEvent.change(screen.getByTestId("library-search"), { target: { value: "" } });

    // Still hidden after the preferences are read back from storage.
    act(() => resetLibraryPrefs());
    expect(screen.queryByTestId("library-group-Converters and sensors")).toBeNull();

    fireEvent.click(within(dialog).getByRole("button", { name: "Show all" }));
    expect(screen.getByTestId("library-group-Converters and sensors")).toBeTruthy();
    expect(screen.getByTestId("library-group-Junctions")).toBeTruthy();
    expect(JSON.parse(window.localStorage.getItem(HIDDEN_KEY) ?? "[]")).toEqual([]);
  });

  it("tells the user when every category is hidden", () => {
    renderPanel();
    const dialog = openSettings();
    for (const box of within(dialog).getAllByRole("checkbox")) {
      fireEvent.click(box);
    }
    expect(screen.queryAllByTestId(/^library-group-toggle-/)).toHaveLength(0);
    expect(screen.getByTestId("library-all-hidden").textContent).toMatch(/hidden/);
  });

  it("expands and collapses every shown category at once", () => {
    renderPanel();
    const dialog = openSettings();
    fireEvent.click(within(dialog).getByLabelText("Electrical"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Expand all" }));
    const toggles = screen.getAllByTestId(/^library-group-toggle-/);
    expect(toggles).toHaveLength(8);
    expect(toggles.every((toggle) => toggle.getAttribute("aria-expanded") === "true")).toBe(true);
    expect(screen.getAllByTestId(/^library-item-/).length).toBeGreaterThan(20);
    expect(JSON.parse(window.localStorage.getItem(EXPANDED_KEY) ?? "[]")).not.toContain("Electrical");

    fireEvent.click(within(dialog).getByRole("button", { name: "Collapse all" }));
    expect(screen.queryAllByTestId(/^library-item-/)).toHaveLength(0);
    expect(JSON.parse(window.localStorage.getItem(EXPANDED_KEY) ?? "[]")).toEqual([]);
  });
});

describe("library list and grid views", () => {
  function renderPanel() {
    return render(
      <>
        <LibraryViewToggle />
        <LibrarySettings />
        <LibraryBrowser />
      </>,
    );
  }

  function viewButton(name: "List view" | "Grid view"): HTMLElement {
    return screen.getByRole("button", { name });
  }

  beforeEach(() => resetHelpStore());

  it("defaults to the list view with the list button pressed", () => {
    renderPanel();
    expect(viewButton("List view").getAttribute("aria-pressed")).toBe("true");
    expect(viewButton("Grid view").getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByTestId("library-browser").getAttribute("data-view")).toBe("list");
  });

  it("switches to the grid, persists the choice, and reads it back", () => {
    const first = renderPanel();
    fireEvent.click(viewButton("Grid view"));
    expect(viewButton("Grid view").getAttribute("aria-pressed")).toBe("true");
    expect(viewButton("List view").getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByTestId("library-browser").getAttribute("data-view")).toBe("grid");
    expect(window.localStorage.getItem(VIEW_KEY)).toBe("grid");
    first.unmount();

    resetLibraryPrefs();
    renderPanel();
    expect(screen.getByTestId("library-browser").getAttribute("data-view")).toBe("grid");
    fireEvent.click(viewButton("List view"));
    expect(window.localStorage.getItem(VIEW_KEY)).toBe("list");
    expect(screen.getByTestId("library-browser").getAttribute("data-view")).toBe("list");
  });

  it("ignores an unknown stored view", () => {
    window.localStorage.setItem(VIEW_KEY, "mosaic");
    resetLibraryPrefs();
    renderPanel();
    expect(viewButton("List view").getAttribute("aria-pressed")).toBe("true");
  });

  it("offers the same choice in the quick settings", () => {
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Library settings" }));
    const dialog = screen.getByRole("dialog", { name: "Library settings" });
    const grid = within(dialog).getByRole("radio", { name: "Grid" });
    fireEvent.click(grid);
    expect((grid as HTMLInputElement).checked).toBe(true);
    expect(viewButton("Grid view").getAttribute("aria-pressed")).toBe("true");
    expect(window.localStorage.getItem(VIEW_KEY)).toBe("grid");
    fireEvent.click(viewButton("List view"));
    expect((within(dialog).getByRole("radio", { name: "List" }) as HTMLInputElement).checked).toBe(
      true,
    );
  });

  it("renders tiles with only the icon and the name, keeping the entry testids", () => {
    renderPanel();
    fireEvent.click(viewButton("Grid view"));
    expandLibraryGroups();
    expect(screen.getAllByTestId(/^library-item-/)).toHaveLength(43);
    for (const list of document.querySelectorAll(".library-group__list")) {
      expect(list.classList.contains("library-group__list--grid")).toBe(true);
    }

    const motor = screen.getByTestId("library-item-DCMotor");
    expect(motor.getAttribute("draggable")).toBe("true");
    expect(motor.getAttribute("data-ref")).toMatch(/dcmotor/i);
    expect(motor.querySelector("svg[data-icon='conv-dc-motor']")).toBeTruthy();
    expect(motor.querySelector(".library-item__label")?.textContent).toBe("DCMotor");
    // The full name and description sit in the tooltip.
    expect(motor.getAttribute("title")).toMatch(/^DCMotor — Permanent-magnet DC motor/);
    // No summary, chevron, parameters or ports: besides the icon, the tile holds the name alone.
    const button = within(motor).getByRole("button");
    expect([...button.children].map((child) => child.className)).toEqual([
      "library-item__icon library-item__icon--tile",
      "library-item__label",
    ]);
    expect(button.getAttribute("aria-expanded")).toBeNull();
    expect(motor.querySelector(".library-item__summary, .library-item__details")).toBeNull();

    fireEvent.click(button);
    expect(motor.querySelector(".library-item__details")).toBeNull();
    expect(useHelpStore.getState().blockRef).toBe(motor.getAttribute("data-ref"));

    const junction = screen.getByTestId("library-item-junction-0");
    expect(junction.querySelector(".library-item__label")?.textContent).toBe("Junction 0");
    expect(junction.querySelector(".library-item__summary")).toBeNull();
    expect(junction.getAttribute("title")).toMatch(/equal efforts/);
  });

  it("drags a tile with the same payload as the list entry", () => {
    renderPanel();
    fireEvent.click(viewButton("Grid view"));
    expandLibraryGroups();
    const { transfer, data } = fakeDataTransfer();
    fireEvent.dragStart(screen.getByTestId("library-item-DCMotor"), { dataTransfer: transfer });
    expect(parseDragPayload(data.get(BLOCK_DRAG_MIME))).toEqual({
      kind: "block",
      ref: screen.getByTestId("library-item-DCMotor").getAttribute("data-ref"),
    });
    const junction = fakeDataTransfer();
    fireEvent.dragStart(screen.getByTestId("library-item-junction-1"), {
      dataTransfer: junction.transfer,
    });
    expect(readDragPayload(junction.transfer)).toEqual({ kind: "junction", junction: "1" });
  });

  it("keeps search, collapse and hidden categories working in the grid", () => {
    renderPanel();
    fireEvent.click(viewButton("Grid view"));
    fireEvent.change(screen.getByTestId("library-search"), { target: { value: "motor" } });
    expect(screen.getAllByTestId(/^library-item-/)).toHaveLength(1);
    expect(screen.getByTestId("library-item-DCMotor").classList).toContain("library-item--tile");

    fireEvent.click(screen.getByTestId("library-group-toggle-Converters and sensors"));
    expect(screen.queryByTestId("library-item-DCMotor")).toBeNull();
    fireEvent.change(screen.getByTestId("library-search"), { target: { value: "" } });

    fireEvent.click(screen.getByRole("button", { name: "Library settings" }));
    const dialog = screen.getByRole("dialog", { name: "Library settings" });
    fireEvent.click(within(dialog).getByLabelText("Junctions"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Expand all" }));
    expect(screen.queryByTestId("library-item-junction-0")).toBeNull();
    expect(screen.getByTestId("library-item-DCMotor")).toBeTruthy();
  });
});

describe("library shapes", () => {
  function renderPanel() {
    return render(
      <>
        <LibraryViewToggle />
        <LibrarySettings />
        <LibraryBrowser />
      </>,
    );
  }

  function itemIds(): string[] {
    return screen
      .queryAllByTestId(/^library-item-/)
      .map((item) => item.getAttribute("data-testid") ?? "");
  }

  const ALL_SHAPES = [
    "library-item-shape-rectangle",
    "library-item-shape-roundedRectangle",
    "library-item-shape-ellipse",
    "library-item-shape-line",
    "library-item-shape-arrow",
  ];

  beforeEach(() => {
    resetHelpStore();
    resetShapeRequests();
  });

  it("lists the five shapes last, collapsed by default, with a glyph, the label and a description", () => {
    renderPanel();
    const toggles = screen.getAllByTestId(/^library-group-toggle-/);
    expect(toggles.at(-1)?.getAttribute("data-testid")).toBe("library-group-toggle-Shapes");
    expect(toggles.at(-1)?.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(screen.getByTestId("library-group-toggle-Shapes"));
    expect(JSON.parse(window.localStorage.getItem(EXPANDED_KEY) ?? "[]")).toEqual(["Shapes"]);
    expect(itemIds()).toEqual(ALL_SHAPES);

    const rect = screen.getByTestId("library-item-shape-rectangle");
    expect(rect.getAttribute("draggable")).toBe("true");
    expect(rect.getAttribute("data-shape")).toBe("rectangle");
    expect(rect.getAttribute("data-ref")).toBeNull();
    expect(rect.querySelector("svg[data-shape-glyph='rectangle']")).toBeTruthy();
    expect(rect.querySelector(".library-item__name")?.textContent).toBe("Rectangle");
    expect(rect.querySelector(".library-item__summary")?.textContent).toBe(
      "Background drawing, ignored by simulation",
    );
    expect(screen.getByTestId("library-item-shape-roundedRectangle").textContent).toContain(
      "Rounded rectangle",
    );
    // The shapes are a library category only: the catalog index (block help, completion, the
    // model tree, the canvas) has no Shapes group and no shape blocks.
    const index = useCatalogStore.getState().index;
    expect(index?.groups.map((group) => group.name)).not.toContain("Shapes");
    expect(index?.blocksByName.has("Rectangle")).toBe(false);
  });

  it("shows icon and label only in the grid", () => {
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Grid view" }));
    fireEvent.click(screen.getByTestId("library-group-toggle-Shapes"));
    const arrow = screen.getByTestId("library-item-shape-arrow");
    expect(arrow.classList).toContain("library-item--tile");
    const button = within(arrow).getByRole("button");
    expect([...button.children].map((child) => child.className)).toEqual([
      "library-item__icon library-item__icon--tile",
      "library-item__label",
    ]);
    expect(button.getAttribute("aria-haspopup")).toBeNull();
    expect(arrow.querySelector(".library-item__label")?.textContent).toBe("Arrow");
    expect(arrow.getAttribute("title")).toMatch(/^Arrow — Background drawing/);
  });

  it("matches a search on shape and on the kind names", () => {
    renderPanel();
    const search = screen.getByTestId("library-search");
    fireEvent.change(search, { target: { value: "shape" } });
    expect(itemIds()).toEqual(ALL_SHAPES);
    expect(screen.getAllByTestId(/^library-group-toggle-/)).toHaveLength(1);
    fireEvent.change(search, { target: { value: "rect" } });
    expect(itemIds()).toEqual([
      "library-item-shape-rectangle",
      "library-item-shape-roundedRectangle",
    ]);
    fireEvent.change(search, { target: { value: "Ellipse" } });
    expect(itemIds()).toEqual(["library-item-shape-ellipse"]);
    fireEvent.change(search, { target: { value: "motor" } });
    expect(screen.queryByTestId("library-group-Shapes")).toBeNull();
  });

  it("hides and shows the category from the quick settings, and expands and collapses it with all", () => {
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Library settings" }));
    const dialog = screen.getByRole("dialog", { name: "Library settings" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Expand all" }));
    expect(screen.getByTestId("library-group-toggle-Shapes").getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByTestId("library-item-shape-line")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Collapse all" }));
    expect(screen.queryByTestId("library-item-shape-line")).toBeNull();

    fireEvent.click(within(dialog).getByLabelText("Shapes"));
    expect(screen.queryByTestId("library-group-Shapes")).toBeNull();
    expect(JSON.parse(window.localStorage.getItem(HIDDEN_KEY) ?? "[]")).toEqual(["Shapes"]);
    expect(screen.getByTestId("library-count").textContent).toBe("38");
    fireEvent.change(screen.getByTestId("library-search"), { target: { value: "shape" } });
    expect(screen.queryAllByTestId(/^library-item-shape-/)).toHaveLength(0);
    fireEvent.change(screen.getByTestId("library-search"), { target: { value: "" } });
    fireEvent.click(within(dialog).getByLabelText("Shapes"));
    expect(screen.getByTestId("library-group-Shapes")).toBeTruthy();
  });

  it("drags a shape with its own MIME type in both views", () => {
    renderPanel();
    fireEvent.click(screen.getByTestId("library-group-toggle-Shapes"));
    for (const view of ["List view", "Grid view"] as const) {
      fireEvent.click(screen.getByRole("button", { name: view }));
      const { transfer, data } = fakeDataTransfer();
      fireEvent.dragStart(screen.getByTestId("library-item-shape-ellipse"), { dataTransfer: transfer });
      expect(data.has(BLOCK_DRAG_MIME)).toBe(false);
      expect(parseDragPayload(data.get(SHAPE_DRAG_MIME))).toEqual({ kind: "shape", shape: "ellipse" });
      expect(readDragPayload(transfer)).toEqual({ kind: "shape", shape: "ellipse" });
      expect(transfer.effectAllowed).toBe("copy");
    }
  });

  it("adds the shape in the middle of the canvas on a click or Enter, in both views", () => {
    useDocumentStore.getState().openDocument("demo", "Shapes", createEmptyModel("Shapes"));
    const adder = vi.fn();
    registerShapeAdder(adder);
    renderPanel();
    fireEvent.click(screen.getByTestId("library-group-toggle-Shapes"));
    fireEvent.click(within(screen.getByTestId("library-item-shape-line")).getByRole("button"));
    expect(adder).toHaveBeenLastCalledWith("line");
    fireEvent.click(screen.getByRole("button", { name: "Grid view" }));
    fireEvent.click(within(screen.getByTestId("library-item-shape-rectangle")).getByRole("button"));
    expect(adder).toHaveBeenLastCalledWith("rectangle");
    expect(useHelpStore.getState().blockRef).toBeNull();
    resetDocumentStore();
  });
});

describe("drag payload", () => {
  it("round-trips a shape through its own MIME type and never reads it as a block", () => {
    const { transfer, data } = fakeDataTransfer();
    writeDragPayload(transfer, payloadForShape("roundedRectangle"));
    expect(data.has(BLOCK_DRAG_MIME)).toBe(false);
    expect(data.get("text/plain")).toBe("shape:roundedRectangle");
    expect(readDragPayload(transfer)).toEqual({ kind: "shape", shape: "roundedRectangle" });
    expect(parseDragPayload('{"kind":"shape","shape":"star"}')).toBeNull();
    // A text-only drag of the fallback is not mistaken for a catalog ref.
    const plain = fakeDataTransfer();
    plain.transfer.setData("text/plain", "shape:rectangle");
    expect(readDragPayload(plain.transfer)).toBeNull();
  });

  it("round-trips a block ref through the typed MIME type", () => {
    const se = catalog.blocks.find((block) => block.name === "Se");
    if (se === undefined) {
      throw new Error("catalog has no Se block");
    }
    const { transfer, data } = fakeDataTransfer();
    writeDragPayload(transfer, payloadForBlock(se));
    expect(data.get(BLOCK_DRAG_MIME)).toContain("stdlib:");
    expect(data.get("text/plain")).toBe(se.ref);
    expect(readDragPayload(transfer)).toEqual({ kind: "block", ref: se.ref });
  });

  it("round-trips a junction", () => {
    const { transfer } = fakeDataTransfer();
    writeDragPayload(transfer, { kind: "junction", junction: "1" });
    expect(readDragPayload(transfer)).toEqual({ kind: "junction", junction: "1" });
  });

  it("ignores a malformed payload", () => {
    expect(parseDragPayload("not json")).toBeNull();
    expect(parseDragPayload('{"kind":"block"}')).toBeNull();
    expect(parseDragPayload('{"kind":"junction","junction":"2"}')).toBeNull();
    expect(parseDragPayload(null)).toBeNull();
    const { transfer } = fakeDataTransfer();
    expect(readDragPayload(transfer)).toBeNull();
  });
});
