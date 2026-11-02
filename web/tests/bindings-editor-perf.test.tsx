import { appendFileSync } from "node:fs";

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";

import type { Binding, RunSignal } from "../src/contracts";
import { resetDiagnosticsStore, useDiagnosticsStore } from "../src/diagnostics/store";
import { resetRunStore } from "../src/plot/runStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";
import { WINDOW_ROWS, windowRows } from "../src/viewer/BindingsEditor";
import DockViewer from "../src/viewer/DockViewer";

/**
 * Rendering cost of the 3D View's binding table on a large model (an aircraft or a humanoid: hundreds of
 * bindings, thousands of signals). The guards run always: no signal option lists in the DOM while the
 * fields are closed, one binding object replaced per edit, and only the rows near the view rendered in a
 * table longer than WINDOW_ROWS. The benchmark prints open time, DOM size and the time of one edit for a
 * bigger model when `BGSIM_BENCH=1` (jsdom: compare runs with each other, not with a browser):
 *
 *   $env:BGSIM_BENCH="1"; npx vitest run tests/bindings-editor-perf.test.tsx
 *
 * `BGSIM_BENCH_BINDINGS` and `BGSIM_BENCH_SIGNALS` set the size (default 400 bindings, 3000 signals),
 * `BGSIM_BENCH_OUT` a file to append the result line to (Vitest keeps a passing test's console quiet).
 */

/** A chain of `n` links with a box each and `n - 1` revolute joints. */
function chainSdf(n: number): string {
  const links = Array.from(
    { length: n },
    (_, k) => `<link name="l${String(k)}"><pose>${String(k)} 0 0 0 0 0</pose><visual name="v${String(k)}"><geometry><box><size>0.5 0.1 0.1</size></box></geometry></visual></link>`,
  );
  const joints = Array.from(
    { length: n - 1 },
    (_, k) => `<joint name="j${String(k + 1)}" type="revolute"><parent>l${String(k)}</parent><child>l${String(k + 1)}</child><axis><xyz>0 0 1</xyz></axis></joint>`,
  );
  return `<?xml version="1.0"?><sdf version="1.9"><model name="big">${links.join("")}${joints.join("")}</model></sdf>`;
}

const LINKS = 64;

/** Signals `Plant/B<k>/x[1..]` with units, one in eight without. */
function signalIds(n: number): string[] {
  return Array.from({ length: n }, (_, k) => `Plant/Body${String(Math.floor(k / 10))}/q[${String((k % 10) + 1)}]`);
}

/** Half pose bindings (7 signals) on links, half joint positions (1 signal), like the aircraft examples. */
function bigBindings(n: number, ids: readonly string[]): Binding[] {
  return Array.from({ length: n }, (_, k): Binding => {
    if (k % 2 === 0) {
      const base = (k * 7) % (ids.length - 7);
      return { target: `link:l${String(k % LINKS)}`, property: "pose", signal: ids.slice(base, base + 7) as [string, ...string[]] };
    }
    return { target: `joint:j${String((k % (LINKS - 1)) + 1)}`, property: "position", signal: ids[k % ids.length] ?? "" };
  });
}

const engines: NullEngine[] = [];
function createEngine(): NullEngine {
  const e = new NullEngine({ renderWidth: 64, renderHeight: 64, textureSize: 64, deterministicLockstep: false, lockstepMaxSteps: 1, useHighPrecisionMatrix: true });
  engines.push(e);
  return e;
}

function openModel(bindings: Binding[], ids: readonly string[]): void {
  useDiagnosticsStore.setState({
    signals: ids.map((id, k) => ({ id, unit: k % 8 === 0 ? null : k % 2 === 0 ? "1" : "m", kind: "observed", path: "Plant", type: "Real" }) as unknown as RunSignal),
  });
  const doc = createEmptyModel("Big");
  doc.scene = { file: "scenes/big.sdf" };
  doc.bindings = bindings;
  useDocumentStore.getState().openDocument("p", "Big", doc);
}

beforeEach(() => {
  resetDiagnosticsStore();
  resetDocumentStore();
  resetRunStore();
  localStorage.clear();
  const sdf = chainSdf(LINKS);
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => (String(input).endsWith("big.sdf") ? Promise.resolve(new Response(sdf, { status: 200 })) : Promise.resolve(new Response("not found", { status: 404 })))),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  engines.length = 0;
});

interface Cost {
  readonly openMs: number;
  readonly nodes: number;
  readonly options: number;
  readonly editMs: number;
}

/** Opens the model in the 3D View and the binding table; returns the time the table took to open. */
async function openTable(nBindings: number, nSignals: number): Promise<number> {
  const ids = signalIds(nSignals);
  openModel(bigBindings(nBindings, ids), ids);
  render(<DockViewer active createEngine={createEngine} />);
  await waitFor(() => expect(screen.getByTestId("scene-view").dataset["state"]).toBe("loaded"), { timeout: 30_000 });
  // the playback bar comes with the built scene
  const toggle = await screen.findByTestId("bindings-toggle", {}, { timeout: 30_000 });
  const t0 = performance.now();
  fireEvent.click(toggle);
  return performance.now() - t0;
}

/** The row of the edit (rendered also in a windowed table). */
const EDITED = 10;

async function measure(nBindings: number, nSignals: number): Promise<Cost> {
  const openMs = await openTable(nBindings, nSignals);
  const editor = screen.getByTestId("bindings-editor");
  const nodes = editor.querySelectorAll("*").length;
  const options = editor.querySelectorAll("option, [role=option]").length;
  // one edit: the gain of a row, committed on Enter (one undo step, one store update)
  const gain = screen.getByTestId(`binding-gain-${String(EDITED)}`);
  const t1 = performance.now();
  act(() => {
    fireEvent.change(gain, { target: { value: "2" } });
    fireEvent.keyDown(gain, { key: "Enter" });
  });
  const editMs = performance.now() - t1;
  expect(useDocumentStore.getState().doc?.bindings?.[EDITED]?.gain).toBe(2);
  return { openMs, nodes, options, editMs };
}

function storedBindings(): readonly Binding[] {
  return useDocumentStore.getState().doc?.bindings ?? [];
}

function renderedRows(): number[] {
  return screen.queryAllByTestId(/^binding-row-\d+$/).map((r) => Number(r.dataset["testid"]?.slice("binding-row-".length)));
}

describe("the binding table on a large model", () => {
  it("keeps the DOM small with thousands of signals", async () => {
    const cost = await measure(60, 3000);
    expect(screen.getByTestId("bindings-editor").dataset["windowed"]).toBeUndefined();
    expect(renderedRows()).toHaveLength(60);
    // no signal field renders an option list until it is opened; the options left are the add form's
    // property and target lists
    expect(cost.options).toBeLessThanOrEqual(10 + LINKS);
    expect(cost.nodes).toBeLessThan(60 * 45);
  }, 60_000);

  it("edits a signal through the searchable field and keeps every other binding object", async () => {
    await openTable(60, 3000);
    const before = storedBindings();
    const field = screen.getByTestId("binding-signal-1");
    fireEvent.click(field);
    expect(screen.getByTestId("binding-signal-1-list").querySelectorAll("[role=option]").length).toBeLessThanOrEqual(30);
    fireEvent.change(field, { target: { value: "body250 q[4" } });
    fireEvent.keyDown(field, { key: "Enter" });
    const after = storedBindings();
    expect(after[1]?.signal).toBe("Plant/Body250/q[4]");
    expect(after.filter((b, i) => b !== before[i]).length).toBe(1);
    expect(screen.queryByTestId("binding-signal-1-list")).toBeNull();
  }, 60_000);

  it(`renders only the rows near the view of a table longer than ${String(WINDOW_ROWS)} rows`, async () => {
    await openTable(400, 3000);
    const editor = screen.getByTestId("bindings-editor");
    expect(editor.dataset["windowed"]).toBe("true");
    const first = renderedRows();
    expect(first[0]).toBe(0);
    expect(first.length).toBeLessThan(80);
    // scrolling brings later rows in; a focused row stays while it is out of view
    const gain = screen.getByTestId("binding-gain-2");
    act(() => {
      gain.focus();
    });
    act(() => {
      editor.scrollTop = 10_000;
      fireEvent.scroll(editor);
    });
    const later = renderedRows();
    expect(later).toContain(2);
    expect(later).not.toContain(0);
    expect(Math.min(...later.filter((i) => i !== 2))).toBeGreaterThan(50);
    expect(later.length).toBeLessThan(80);
    // the rows left out keep their place as empty rows of their height
    expect(editor.querySelectorAll(".bindings__gap").length).toBe(3);
  }, 60_000);

  it("windowRows keeps the rows near the view and the focused row, with the heights of the others", () => {
    const heights = Array<number>(100).fill(50);
    // view 2000..2500 px, 600 px around it: rows 27 to 62
    const slices = windowRows(heights, 2000, 500, 5);
    const rows = slices.flatMap((s) => (s.kind === "row" ? [s.index] : []));
    expect(rows).toEqual([5, ...Array.from({ length: 36 }, (_, k) => 27 + k)]);
    const gaps = slices.flatMap((s) => (s.kind === "gap" ? [s.height] : []));
    expect(gaps).toEqual([250, 21 * 50, 37 * 50]);
    expect(windowRows([], 0, 500, null)).toEqual([]);
  });

  it.runIf(process.env["BGSIM_BENCH"] === "1")(
    "benchmark: open, DOM size and one edit",
    async () => {
      const nb = Number(process.env["BGSIM_BENCH_BINDINGS"] ?? "400");
      const ns = Number(process.env["BGSIM_BENCH_SIGNALS"] ?? "3000");
      const cost = await measure(nb, ns);
      const line = `[bench] ${String(nb)} bindings x ${String(ns)} signals: open ${cost.openMs.toFixed(0)} ms, ${String(cost.nodes)} DOM nodes, ${String(cost.options)} options, edit ${cost.editMs.toFixed(0)} ms\n`;
      const out = process.env["BGSIM_BENCH_OUT"];
      if (out !== undefined) appendFileSync(out, line);
      else console.warn(line);
    },
    600_000,
  );
});
