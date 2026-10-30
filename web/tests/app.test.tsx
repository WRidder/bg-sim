/**
 * The layout shell of plan 7.2. Besides "it renders", this file probes the
 * DOM contract of react-resizable-panels 4.14.8 that src/app/app.css depends
 * on: `<div data-group>`, `<div data-panel>` and
 * `<div role="separator" data-separator>` (see the .d.ts comments in
 * node_modules/react-resizable-panels/dist/react-resizable-panels.d.ts).
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/app/App";
import { resetCatalogStore } from "../src/library/catalogStore";
import { resetDocumentStore } from "../src/state/documentStore";
import { resetSessionCache } from "../src/state/session";

/**
 * The shell now mounts the W1.1 diagram tab and library, which start a session
 * request. Keep that request pending: these tests assert the shell's chrome and
 * loading states, not the network.
 */
beforeEach(() => {
  // A project in the URL selects the editor; without one the app shows the start page.
  window.history.replaceState(null, "", "/?project=demo&model=Model1");
  resetDocumentStore();
  resetCatalogStore();
  resetSessionCache();
  vi.stubGlobal("fetch", () => new Promise(() => {}));
});

describe("layout shell", () => {
  it("renders the top bar, the three columns and the bottom dock", () => {
    render(<App />);

    expect(screen.getByTestId("app-shell")).toBeTruthy();
    expect(screen.getByTestId("top-bar")).toBeTruthy();
    expect(screen.getByTestId("left-panel")).toBeTruthy();
    expect(screen.getByTestId("center-tabs")).toBeTruthy();
    expect(screen.getByTestId("inspector-panel")).toBeTruthy();
    expect(screen.getByTestId("bottom-dock")).toBeTruthy();
  });

  it("builds the shell from three resizable groups", () => {
    const { container } = render(<App />);

    // rows (main/dock), columns (library/center/inspector), left column (library/tree)
    expect(container.querySelectorAll("[data-group]")).toHaveLength(3);
    // main, library, center, inspector, library-section, tree-section, dock
    expect(container.querySelectorAll("[data-panel]")).toHaveLength(7);
    // one in the rows group, two in the columns group, one in the left column
    expect(container.querySelectorAll('[role="separator"]')).toHaveLength(4);
    expect(container.querySelectorAll(".splitter")).toHaveLength(4);
  });

  it("shows guidance in every panel before a project is open (plan 7.8)", async () => {
    render(<App />);

    for (const title of [
      "Loading the library…",
      "No model open. Open a project to see its blocks and subsystems here.",
      "Opening the model…",
      "Nothing selected",
      "No run data",
    ]) {
      expect(await screen.findByText(title)).toBeTruthy();
    }
  });

  it("labels the toolbar controls and keeps Run and Stop disabled", () => {
    render(<App />);

    const run = screen.getByRole("button", { name: "Run simulation" });
    const stop = screen.getByRole("button", { name: "Stop simulation" });
    expect((run as HTMLButtonElement).disabled).toBe(true);
    expect((stop as HTMLButtonElement).disabled).toBe(true);

    expect(screen.getByLabelText("t_end")).toBeTruthy();
    expect(screen.getByLabelText("solver")).toBeTruthy();
    expect(screen.getByLabelText("tol")).toBeTruthy();
  });

  it("switches the centre tabs by click and by arrow key", async () => {
    render(<App />);

    const diagram = screen.getByRole("tab", { name: "Diagram" });
    const code = screen.getByRole("tab", { name: "Code" });
    expect(diagram.getAttribute("aria-selected")).toBe("true");

    fireEvent.click(code);
    expect(code.getAttribute("aria-selected")).toBe("true");
    // The code tab is a lazy chunk; under a loaded full-suite run its first import can exceed
    // the default 1 s wait.
    expect(await screen.findByText("No source open", {}, { timeout: 5000 })).toBeTruthy();

    fireEvent.keyDown(code, { key: "ArrowLeft" });
    expect(diagram.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("Opening the model…")).toBeTruthy();
  });

  it("renders every dock tab and shows the Plots panel first", async () => {
    render(<App />);

    for (const name of ["Plots", "3D View", "Diagnostics", "Signals", "Log"]) {
      expect(screen.getByRole("tab", { name })).toBeTruthy();
    }
    expect(screen.getByRole("tab", { name: "Plots" }).getAttribute("aria-selected")).toBe("true");
    expect(await screen.findByText("No run data")).toBeTruthy();
  });
});
