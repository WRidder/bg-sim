/**
 * The library browser and its typed drag payload (plan 7.2/3.2).
 */

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { LibraryBrowser } from "../src/library/LibraryBrowser";
import { LibrarySettings } from "../src/library/LibrarySettings";
import { EXPANDED_KEY, HIDDEN_KEY, resetLibraryPrefs } from "../src/library/libraryPrefs";
import { expandLibraryGroups } from "./libraryHelpers";
import {
  BLOCK_DRAG_MIME,
  parseDragPayload,
  payloadForBlock,
  readDragPayload,
  writeDragPayload,
} from "../src/library/dnd";

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
    ]);
  });

  it("lists all 36 catalog blocks and both junctions once every category is open", () => {
    render(<LibraryBrowser />);
    expandLibraryGroups();
    expect(screen.getAllByTestId(/^library-item-/)).toHaveLength(38);
    expect(screen.getByTestId("library-count").textContent).toBe("38");
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
    expect(toggles).toHaveLength(8);
    for (const toggle of toggles) {
      expect(toggle.getAttribute("aria-expanded")).toBe("false");
    }
    expect(screen.queryAllByTestId(/^library-item-/)).toHaveLength(0);
    expect(toggleOf("Bond graph").textContent).toMatch(/Bond graph\s*\d+/);
    expect(within(toggleOf("Junctions")).getByText("2")).toBeTruthy();
    // The total still counts every block, collapsed or not.
    expect(screen.getByTestId("library-count").textContent).toBe("38");
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
    expect(boxes).toHaveLength(8);
    expect(boxes.every((box) => (box as HTMLInputElement).checked)).toBe(true);
    // Focus moves into the popover, and Escape returns it to the cog.
    expect(document.activeElement).toBe(boxes[0]);

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
    expect(screen.getByTestId("library-count").textContent).toBe(String(38 - 2 - converterCount));

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
    expect(toggles).toHaveLength(7);
    expect(toggles.every((toggle) => toggle.getAttribute("aria-expanded") === "true")).toBe(true);
    expect(screen.getAllByTestId(/^library-item-/).length).toBeGreaterThan(20);
    expect(JSON.parse(window.localStorage.getItem(EXPANDED_KEY) ?? "[]")).not.toContain("Electrical");

    fireEvent.click(within(dialog).getByRole("button", { name: "Collapse all" }));
    expect(screen.queryAllByTestId(/^library-item-/)).toHaveLength(0);
    expect(JSON.parse(window.localStorage.getItem(EXPANDED_KEY) ?? "[]")).toEqual([]);
  });
});

describe("drag payload", () => {
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
