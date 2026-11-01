import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";

import type { Binding, ModeShapeBinding, RunSignal } from "../src/contracts";
import { resetDiagnosticsStore, useDiagnosticsStore } from "../src/diagnostics/store";
import { resetRunStore } from "../src/plot/runStore";
import { BuiltScene } from "../src/scene/build";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";
import DockViewer from "../src/viewer/DockViewer";
import { useExaggerationStore } from "../src/viewer/exaggeration";
import { modalGlb } from "./modalGlb";

const SDF = `<?xml version="1.0"?>
<sdf version="1.9"><model name="flex">
  <link name="body">
    <visual name="bracket"><geometry><mesh><uri>bracket.glb</uri></mesh></geometry></visual>
    <visual name="cap"><geometry><box><size>0.1 0.1 0.1</size></box></geometry></visual>
  </link>
</model></sdf>`;
const MODES = 6;

const engines: NullEngine[] = [];
function createEngine(): NullEngine {
  const e = new NullEngine({ renderWidth: 64, renderHeight: 64, textureSize: 64, deterministicLockstep: false, lockstepMaxSteps: 1, useHighPrecisionMatrix: true });
  engines.push(e);
  return e;
}

function openModel(bindings: Binding[]): void {
  const doc = createEmptyModel("Flex");
  doc.scene = { file: "scenes/flex.sdf" };
  doc.bindings = bindings;
  useDocumentStore.getState().openDocument("p", "Flex", doc);
}

function bindings(): readonly Binding[] {
  return useDocumentStore.getState().doc?.bindings ?? [];
}

function withSignals(ids: string[]): void {
  useDiagnosticsStore.setState({ signals: ids.map((id) => ({ id, unit: "m", kind: "observed", path: "P/Body", type: "Real" }) as unknown as RunSignal) });
}

beforeEach(() => {
  resetDiagnosticsStore();
  resetDocumentStore();
  resetRunStore();
  localStorage.clear();
  useExaggerationStore.setState({ byModel: {} });
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const u = String(input);
      if (u.endsWith("flex.sdf")) return Promise.resolve(new Response(SDF, { status: 200 }));
      if (u.endsWith("bracket.glb")) return Promise.resolve(new Response(modalGlb(MODES), { status: 200 }));
      return Promise.resolve(new Response("not found", { status: 404 }));
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  engines.length = 0;
});

async function mount(): Promise<void> {
  render(<DockViewer active createEngine={createEngine} />);
  await waitFor(() => expect(screen.getByTestId("scene-view").dataset["state"]).toBe("loaded"));
}

function select(testId: string, value: string): void {
  fireEvent.change(screen.getByTestId(testId), { target: { value } });
}

const BRACKET: ModeShapeBinding = { target: "visual:bracket", property: "mode-shapes", signal: ["P/Body/eta[1]"] };

describe("mode-shapes bindings in the 3D View", () => {
  it("shows the exaggeration badge for a mode-shapes binding and hands the factor to the scene", async () => {
    const spy = vi.spyOn(BuiltScene.prototype, "setExaggeration");
    openModel([BRACKET]);
    await mount();
    expect(screen.getByTestId("deformation-badge").dataset["factor"]).toBe("1");
    select("deformation-exaggeration", "1000");
    expect(spy).toHaveBeenLastCalledWith(1000);
  });

  it("adds a binding to a mesh, filling eta[1..n] from a block up to the mesh's morph targets", async () => {
    withSignals([...Array.from({ length: 8 }, (_, k) => `P/Body/eta[${String(k + 1)}]`), "P/Body/pose[1]"]);
    openModel([]);
    await mount();
    fireEvent.click(screen.getByTestId("bindings-toggle"));
    select("add-property", "mode-shapes");
    const targets = [...(screen.getByTestId("add-target") as HTMLSelectElement).options].map((o) => o.value);
    expect(targets).toEqual(["", "visual:bracket"]);
    select("add-target", "visual:bracket");
    // the block records 8 coordinates, the mesh has 6 mode shapes
    select("add-signal-fill", "P/Body");
    expect((screen.getByTestId("add-signal-add-mode") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId("add-binding"));
    expect(bindings()).toEqual([
      { target: "visual:bracket", property: "mode-shapes", signal: Array.from({ length: MODES }, (_, k) => `P/Body/eta[${String(k + 1)}]`) },
    ]);
    expect(screen.getByTestId("binding-mesh-modes-0").textContent).toBe(`mesh: ${String(MODES)} mode shapes`);
    // a mode-shapes binding has a gain but no offset
    expect(screen.getByTestId("binding-gain-0")).toBeTruthy();
    expect(screen.queryByTestId("binding-offset-0")).toBeNull();
    expect(screen.getByTestId("binding-row-0").dataset["invalid"]).toBeUndefined();
    fireEvent.click(screen.getByTestId("binding-signal-0-remove-mode"));
    expect((bindings()[0] as ModeShapeBinding).signal).toHaveLength(MODES - 1);
  });

  it("reports a primitive target and more coordinates than morph targets in the row", async () => {
    const seven = Array.from({ length: 7 }, (_, k) => `P/Body/eta[${String(k + 1)}]`) as ModeShapeBinding["signal"];
    openModel([{ ...BRACKET, signal: seven }, { ...BRACKET, target: "visual:cap" }]);
    await mount();
    fireEvent.click(screen.getByTestId("bindings-toggle"));
    expect(screen.getByTestId("binding-problem-0").textContent).toMatch(/E304.*has 6 morph targets/);
    expect(screen.getByTestId("binding-problem-1").textContent).toMatch(/E301.*box, not a mesh/);
  });
});
