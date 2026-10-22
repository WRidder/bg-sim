/**
 * The Signals tab (plan 7.5): renders the manifest's tree, filters it, and
 * double-clicking a row adds the signal to the active plot panel.
 */

import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SignalBrowser } from "../src/plot/SignalBrowser";
import { resetRunStore, useRunStore } from "../src/plot/runStore";
import { runManifest, runSignal } from "./plotFixtures";

const SIGNALS = [
  runSignal("Synthetic/sine", { unit: "V", kind: "output", path: "Synthetic" }),
  runSignal("Synthetic/step", { unit: "V", kind: "output", path: "Synthetic" }),
  runSignal("Synthetic/counter", {
    unit: null,
    kind: "state",
    type: "Int",
    path: "Synthetic",
  }),
  runSignal("Synthetic/flag", {
    unit: null,
    kind: "algebraic",
    type: "Bool",
    path: "Synthetic",
  }),
];

beforeEach(() => {
  resetRunStore();
  useRunStore.setState({
    runId: "run-test",
    manifest: runManifest(SIGNALS),
    status: "done",
  });
  vi.stubGlobal("fetch", () => new Promise(() => {}));
});

afterEach(() => {
  resetRunStore();
  vi.unstubAllGlobals();
});

describe("SignalBrowser", () => {
  it("lists every recorded signal with its unit and kind", () => {
    render(<SignalBrowser />);

    expect(screen.getByTestId("signal-browser")).toBeTruthy();
    expect(screen.getAllByTestId("signal-item")).toHaveLength(4);
    expect(screen.getByTestId("signal-count").textContent).toBe("4/4");

    const sine = document.querySelector('[data-signal-id="Synthetic/sine"]');
    expect(sine).not.toBeNull();
    expect(sine?.getAttribute("data-kind")).toBe("output");
    expect(within(sine as HTMLElement).getByText("V")).toBeTruthy();
    expect(within(sine as HTMLElement).getByText("sine")).toBeTruthy();

    const counter = document.querySelector(
      '[data-signal-id="Synthetic/counter"]',
    );
    expect(within(counter as HTMLElement).getByText("—")).toBeTruthy();
    expect(within(counter as HTMLElement).getByText("Int")).toBeTruthy();
  });

  it("filters the tree by signal name or unit", () => {
    render(<SignalBrowser />);
    const search = screen.getByTestId("signal-search");

    fireEvent.change(search, { target: { value: "sine" } });
    expect(screen.getAllByTestId("signal-item")).toHaveLength(1);
    expect(screen.getByTestId("signal-count").textContent).toBe("1/4");

    fireEvent.change(search, { target: { value: "rad/s" } });
    expect(screen.getByTestId("signal-no-match")).toBeTruthy();

    fireEvent.change(search, { target: { value: "" } });
    expect(screen.getAllByTestId("signal-item")).toHaveLength(4);
  });

  it("adds a signal to the active panel on double-click", () => {
    render(<SignalBrowser />);
    const sine = document.querySelector(
      '[data-signal-id="Synthetic/sine"]',
    ) as HTMLElement;

    fireEvent.doubleClick(sine);

    const state = useRunStore.getState();
    expect(state.panels[0]?.signals).toEqual(["Synthetic/sine"]);
    expect(state.notice).toMatch(/Added Synthetic\/sine to Panel 1/);
    expect(sine.className).toMatch(/is-plotted/);
  });

  it("adds a signal with the row's + button and with Enter", () => {
    render(<SignalBrowser />);
    const step = document.querySelector(
      '[data-signal-id="Synthetic/step"]',
    ) as HTMLElement;
    const button = within(step).getByRole("button", {
      name: "Add Synthetic/step to Panel 1",
    });
    fireEvent.click(button);

    const flag = document.querySelector(
      '[data-signal-id="Synthetic/flag"]',
    ) as HTMLElement;
    fireEvent.keyDown(flag, { key: "Enter" });

    expect(useRunStore.getState().panels[0]?.signals).toEqual([
      "Synthetic/step",
      "Synthetic/flag",
    ]);
  });
});
