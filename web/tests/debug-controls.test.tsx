/**
 * The run bar debug controls (W4.1): enablement per debug state, shortcuts,
 * the status text, and the gutter breakpoint popover.
 */

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RunBar } from "../src/app/RunBar";
import { SHORTCUT_GROUPS } from "../src/app/shortcuts";
import { BreakpointPopover, parseHitCount } from "../src/code/breakpointsPopover";
import type { PausedInfo } from "../src/contracts/debug";
import { resetBreakpointStore, useBreakpointStore } from "../src/debug/breakpointStore";
import { resetDebugStore, useDebugStore } from "../src/debug/debugStore";
import { resetRunStore, useRunStore } from "../src/plot/runStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

const paused: PausedInfo = {
  runId: "r1",
  t: 0.4123,
  tick: 41,
  reason: "breakpoint",
  breakpointId: "bp1",
  location: {
    path: "Ctrl",
    ref: "project:LQGController",
    scope: "@discrete",
    range: { line: 14, col: 1, endLine: 14, endCol: 9 },
  },
  frame: null,
  diagnostics: [],
};

function button(name: string): HTMLButtonElement {
  return screen.getByRole("button", { name }) as HTMLButtonElement;
}

let calls: { url: string; method: string; body: unknown }[] = [];

beforeEach(() => {
  window.localStorage.clear();
  resetDocumentStore();
  resetRunStore();
  resetBreakpointStore();
  resetDebugStore();
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      calls.push({
        url,
        method: init?.method ?? "GET",
        body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null,
      });
      return Promise.resolve(new Response(JSON.stringify({ ok: true, breakpoints: [] }), { status: 200 }));
    }),
  );
});

afterEach(() => {
  resetDocumentStore();
  resetRunStore();
  resetBreakpointStore();
  resetDebugStore();
});

function openModel(): void {
  useDocumentStore.getState().openDocument("project", "Model1", createEmptyModel("Model1"));
}

describe("debug controls", () => {
  it("offers a Debug button that needs an open model", () => {
    render(<RunBar />);
    expect(button("Debug the model").disabled).toBe(true);
    expect(screen.queryByTestId("debug-controls")).toBeNull();
    act(() => openModel());
    expect(button("Debug the model").disabled).toBe(false);
    expect(button("Debug the model").title).toContain("F5");
  });

  it("enables Continue and the steps only while paused, Pause only while running", () => {
    openModel();
    render(<RunBar />);
    act(() => useDebugStore.getState().begin("r1"));
    expect(screen.getByTestId("debug-controls")).toBeTruthy();
    expect(button("Continue").disabled).toBe(true);
    expect(button("Pause").disabled).toBe(false);
    expect(button("Step statement").disabled).toBe(true);
    expect(button("Step tick").disabled).toBe(true);
    expect(button("More step commands").disabled).toBe(true);
    expect(button("Run to time").disabled).toBe(true);

    act(() => useDebugStore.getState().applyPaused(paused));
    expect(button("Continue").disabled).toBe(false);
    expect(button("Pause").disabled).toBe(true);
    expect(button("Step statement").disabled).toBe(false);
    expect(button("Continue").title).toBe("Continue (F5)");
    expect(button("Step statement").title).toBe("Step statement (F10)");
    expect(button("Step tick").title).toBe("Step tick (F11)");
    expect(button("Pause").title).toContain("while the run is going");
  });

  it("shows the pause in the status and lists the shortcuts", () => {
    openModel();
    render(<RunBar />);
    act(() => {
      useDebugStore.getState().begin("r1");
      useDebugStore.getState().applyPaused(paused);
    });
    // The run store stays "running" for a paused run; the debug store drives the text.
    act(() => useRunStore.setState({ status: "running", runId: "r1" }));
    const status = screen.getByTestId("run-status");
    expect(status.textContent).toBe("Paused at t = 0.4123 s: LQGController line 14 (Ctrl)");
    expect(status.getAttribute("data-status")).toBe("paused");
    act(() => useDebugStore.getState().applyResumed("r1"));
    expect(status.textContent).not.toContain("Paused");
    const keys = SHORTCUT_GROUPS.find((group) => group.title === "Debugging")?.entries.map((entry) =>
      entry.keys.map((combo) => combo.join("+")).join("/"),
    );
    expect(keys).toEqual(["F5", "Shift+F5", "F6", "F10", "F11", "F9"]);
  });

  it("sends step, continue and pause commands on the shortcuts", async () => {
    openModel();
    render(<RunBar />);
    act(() => {
      useDebugStore.getState().begin("r1");
      useDebugStore.getState().applyPaused(paused);
    });
    calls = [];
    fireEvent.keyDown(window, { key: "F10" });
    fireEvent.keyDown(window, { key: "F11" });
    fireEvent.keyDown(window, { key: "F5" });
    await vi.waitFor(() => expect(calls).toHaveLength(3));
    expect(calls.map((call) => [call.url, call.body])).toEqual([
      ["/api/runs/r1/debug/step", { granularity: "statement" }],
      ["/api/runs/r1/debug/step", { granularity: "tick" }],
      ["/api/runs/r1/debug/continue", {}],
    ]);

    act(() => useDebugStore.getState().applyResumed("r1"));
    calls = [];
    fireEvent.keyDown(window, { key: "F6" });
    // Steps and F5 do nothing while the run is going.
    fireEvent.keyDown(window, { key: "F10" });
    fireEvent.keyDown(window, { key: "F5" });
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]?.url).toBe("/api/runs/r1/debug/pause");
  });

  it("runs to a time from the number field and rejects a bad one", async () => {
    openModel();
    render(<RunBar />);
    act(() => {
      useDebugStore.getState().begin("r1");
      useDebugStore.getState().applyPaused(paused);
    });
    calls = [];
    const input = screen.getByLabelText("Run to time (s)") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "abc" } });
    fireEvent.click(button("Run to time"));
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(calls).toHaveLength(0);

    fireEvent.change(input, { target: { value: "0.75" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toMatchObject({ url: "/api/runs/r1/debug/runTo", body: { t: 0.75 } });
  });

  it("offers Step event and Step solver step in the menu", async () => {
    openModel();
    render(<RunBar />);
    act(() => {
      useDebugStore.getState().begin("r1");
      useDebugStore.getState().applyPaused(paused);
    });
    calls = [];
    fireEvent.click(button("More step commands"));
    fireEvent.click(screen.getByRole("menuitem", { name: "Step solver step" }));
    await vi.waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]?.body).toEqual({ granularity: "solverStep" });
    expect(screen.queryByRole("menu")).toBeNull();
  });
});

describe("breakpoint popover", () => {
  it("parses the hit count", () => {
    expect(parseHitCount("")).toEqual({ ok: true, value: null });
    expect(parseHitCount(" 3 ")).toEqual({ ok: true, value: 3 });
    expect(parseHitCount("0")).toEqual({ ok: false });
    expect(parseHitCount("1.5")).toEqual({ ok: false });
    expect(parseHitCount("x")).toEqual({ ok: false });
  });

  it("edits the condition and hit count, and removes the breakpoint", () => {
    useBreakpointStore.getState().loadModel("project/Model1");
    const id = useBreakpointStore.getState().toggleLine("project:LQGController", 41) as string;
    const onClose = vi.fn();
    render(<BreakpointPopover id={id} point={{ x: 10, y: 10 }} onClose={onClose} />);

    fireEvent.change(screen.getByTestId("bp-condition"), { target: { value: "k == 5" } });
    fireEvent.change(screen.getByTestId("bp-hit-count"), { target: { value: "x" } });
    fireEvent.click(screen.getByTestId("bp-apply"));
    expect(screen.getByRole("alert").textContent).toContain("whole number");
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.change(screen.getByTestId("bp-hit-count"), { target: { value: "3" } });
    fireEvent.click(screen.getByTestId("bp-apply"));
    expect(useBreakpointStore.getState().breakpoints[0]).toMatchObject({ condition: "k == 5", hitCount: 3 });
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("bp-enabled"));
    expect(useBreakpointStore.getState().breakpoints[0]?.enabled).toBe(false);

    fireEvent.click(screen.getByTestId("bp-remove"));
    expect(useBreakpointStore.getState().breakpoints).toHaveLength(0);
  });
});
