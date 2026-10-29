/**
 * Keyboard shortcuts, the `?` overlay, the block help dialog and modal focus
 * handling (W5.4). The shortcuts owned by other panels (Ctrl+Z, Ctrl+Enter,
 * Space in the 3D view) have their own tests; this file covers the shell's.
 */

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import { BlockHelp } from "../src/app/BlockHelp";
import { resetHelpStore, useHelpStore } from "../src/app/helpStore";
import { SHORTCUT_GROUPS } from "../src/app/shortcuts";
import { ShortcutsOverlay } from "../src/app/ShortcutsOverlay";
import { TopBar } from "../src/app/TopBar";
import { useAppShortcuts } from "../src/app/useAppShortcuts";
import type { Catalog } from "../src/contracts/catalog";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { LibraryBrowser } from "../src/library/LibraryBrowser";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;

function Shell() {
  useAppShortcuts();
  return (
    <>
      <LibraryBrowser />
      <ShortcutsOverlay />
      <BlockHelp />
    </>
  );
}

beforeEach(() => {
  resetHelpStore();
  resetDocumentStore();
  resetCatalogStore();
  useCatalogStore.getState().setCatalog(catalog);
  window.history.replaceState(null, "", "/?project=demo&model=Model1");
});

describe("shortcuts overlay", () => {
  it("opens with ? and closes with ? or Escape", () => {
    render(<Shell />);
    expect(screen.queryByTestId("shortcuts-overlay")).toBeNull();

    fireEvent.keyDown(document.body, { key: "?", shiftKey: true });
    const overlay = screen.getByTestId("shortcuts-overlay");
    expect(overlay.getAttribute("role")).toBe("dialog");
    expect(overlay.getAttribute("aria-modal")).toBe("true");

    fireEvent.keyDown(document.body, { key: "?", shiftKey: true });
    expect(screen.queryByTestId("shortcuts-overlay")).toBeNull();

    fireEvent.keyDown(document.body, { key: "?" });
    expect(screen.getByTestId("shortcuts-overlay")).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByTestId("shortcuts-overlay")).toBeNull();
  });

  it("lists the shortcuts the app implements", () => {
    render(<Shell />);
    fireEvent.keyDown(document.body, { key: "?" });
    const overlay = screen.getByTestId("shortcuts-overlay");
    const text = overlay.textContent ?? "";
    for (const description of [
      "Run the model",
      "Open a project, model or sample",
      "Focus the library search",
      "Undo",
      "Play or pause",
    ]) {
      expect(text).toContain(description);
    }
    expect(SHORTCUT_GROUPS.flatMap((group) => group.entries)).not.toHaveLength(0);
  });

  it("does not open while typing in a field", () => {
    render(<Shell />);
    const search = screen.getByTestId("library-search");
    search.focus();
    fireEvent.keyDown(search, { key: "?" });
    expect(screen.queryByTestId("shortcuts-overlay")).toBeNull();
  });

  it("traps Tab inside the dialog and returns focus to the opener on close", () => {
    render(
      <>
        <button type="button" data-testid="opener">
          opener
        </button>
        <Shell />
      </>,
    );
    const opener = screen.getByTestId("opener");
    opener.focus();
    act(() => useHelpStore.getState().setShortcutsOpen(true));

    const overlay = screen.getByTestId("shortcuts-overlay");
    expect(document.activeElement).toBe(overlay);

    const close = within(overlay).getByTestId("shortcuts-close");
    // Tab from the last (only) focusable element wraps to itself, never leaves the dialog.
    close.focus();
    fireEvent.keyDown(close, { key: "Tab" });
    expect(overlay.contains(document.activeElement)).toBe(true);
    fireEvent.keyDown(close, { key: "Tab", shiftKey: true });
    expect(overlay.contains(document.activeElement)).toBe(true);

    act(() => useHelpStore.getState().setShortcutsOpen(false));
    expect(document.activeElement).toBe(opener);
  });
});

describe("slash focuses the library search", () => {
  it("focuses and selects the search field", () => {
    render(<Shell />);
    fireEvent.keyDown(document.body, { key: "/" });
    expect(document.activeElement).toBe(screen.getByTestId("library-search"));
  });

  it("leaves a / typed into another field alone", () => {
    render(
      <>
        <input data-testid="other" />
        <Shell />
      </>,
    );
    const other = screen.getByTestId("other");
    other.focus();
    fireEvent.keyDown(other, { key: "/" });
    expect(document.activeElement).toBe(other);
  });
});

describe("Ctrl+O", () => {
  it("opens the Open dialog", () => {
    render(<TopBar theme="dark" onToggleTheme={() => {}} />);
    expect(screen.queryByTestId("open-dialog")).toBeNull();
    fireEvent.keyDown(window, { key: "o", ctrlKey: true });
    expect(screen.getByTestId("open-dialog")).toBeTruthy();
  });
});

describe("block help", () => {
  it("shows description, ports with units, and parameters with unit, default and bounds", () => {
    render(<Shell />);
    act(() => useHelpStore.getState().openBlockHelp("stdlib:electrical/Resistor"));

    const help = screen.getByTestId("block-help");
    expect(help.getAttribute("aria-modal")).toBe("true");
    expect(within(help).getByRole("heading", { level: 2, name: "Resistor" })).toBeTruthy();
    expect(within(help).getByTestId("block-help-description").textContent?.length).toBeGreaterThan(5);

    const ports = within(help).getByTestId("block-help-ports");
    expect(ports.textContent).toContain("Electrical");
    expect(ports.textContent).toMatch(/effort .*\[V\]/);

    const params = within(help).getByTestId("block-help-params");
    const header = within(params).getAllByRole("columnheader").map((cell) => cell.textContent);
    expect(header).toEqual(["Name", "Unit", "Default", "Min", "Max", "Description"]);
    const row = within(params).getByRole("row", { name: /^R\b/ });
    expect(row.textContent).toMatch(/ohm|Ω/i);
  });

  it("opens from the library item and from F1 for the selected block, and F1 without one shows shortcuts", () => {
    render(<Shell />);

    // The help button of an expanded library item.
    fireEvent.click(within(screen.getByTestId("library-item-DCMotor")).getByRole("button", { name: /DCMotor/ }));
    fireEvent.click(screen.getByRole("button", { name: "Help for DCMotor" }));
    expect(screen.getByTestId("block-help").getAttribute("data-ref")).toBe("stdlib:converters/DCMotor");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByTestId("block-help")).toBeNull();

    // F1 with nothing selected explains the shortcuts instead.
    fireEvent.keyDown(document.body, { key: "F1" });
    expect(screen.getByTestId("shortcuts-overlay")).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });

    // F1 with one selected block opens that block's help.
    const model = createEmptyModel("Model1", catalog.language);
    useDocumentStore.getState().openDocument("demo", "Model1", model, { persisted: false });
    const id = useDocumentStore.getState().addBlock(
      catalog.blocks.find((block) => block.name === "DCMotor")!,
      { x: 0, y: 0 },
    );
    expect(id).not.toBeNull();
    fireEvent.keyDown(document.body, { key: "F1" });
    expect(screen.getByTestId("block-help").getAttribute("data-ref")).toBe("stdlib:converters/DCMotor");
  });

  it("explains an unknown block and points to the next step", () => {
    render(<Shell />);
    act(() => useHelpStore.getState().openBlockHelp("project:Missing"));
    expect(screen.getByTestId("block-help").textContent).toMatch(/not in the current catalog/);
  });

  it("describes a junction", () => {
    render(<Shell />);
    act(() => useHelpStore.getState().openBlockHelp("junction:1"));
    expect(screen.getByTestId("block-help").textContent).toMatch(/common-flow/);
  });
});
