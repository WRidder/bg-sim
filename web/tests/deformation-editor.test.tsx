import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";
import { VertexBuffer } from "@babylonjs/core/Buffers/buffer";

import type { Binding, DeformationBinding } from "../src/contracts/model";
import { resetDiagnosticsStore } from "../src/diagnostics/store";
import { resetRunStore } from "../src/plot/runStore";
import { BuiltScene } from "../src/scene/build";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";
import { STRIPE_SHADE } from "../src/scene/beamMesh";
import DockViewer from "../src/viewer/DockViewer";
import { readExaggeration, useExaggerationStore } from "../src/viewer/exaggeration";

const here = path.dirname(fileURLToPath(import.meta.url));
const SDF = readFileSync(path.join(here, "fixtures", "scenes", "beam.sdf"), "utf8");

const engines: NullEngine[] = [];
function createEngine(): NullEngine {
  const e = new NullEngine({ renderWidth: 64, renderHeight: 64, textureSize: 64, deterministicLockstep: false, lockstepMaxSteps: 1, useHighPrecisionMatrix: true });
  engines.push(e);
  return e;
}

function openModel(bindings: Binding[], exaggeration?: 1 | 10 | 100 | 1000): void {
  const doc = createEmptyModel("Beam");
  doc.scene = exaggeration === undefined ? { file: "scenes/beam.sdf" } : { file: "scenes/beam.sdf", exaggeration };
  doc.bindings = bindings;
  useDocumentStore.getState().openDocument("p", "Beam", doc);
}

function bindings(): readonly Binding[] {
  return useDocumentStore.getState().doc?.bindings ?? [];
}

const TORSION: DeformationBinding = {
  target: "visual:beam_box",
  property: "deformation",
  family: "torsion",
  basis: "clamped-free",
  beam: { axis: "+x" },
  signal: ["B/eta_t[1]"],
};

beforeEach(() => {
  resetDiagnosticsStore();
  resetDocumentStore();
  resetRunStore();
  localStorage.clear();
  useExaggerationStore.setState({ byModel: {} });
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(String(input).endsWith("beam.sdf") ? new Response(SDF, { status: 200 }) : new Response("not found", { status: 404 })),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  engines.length = 0;
});

async function mount(): Promise<ReturnType<typeof render>> {
  const view = render(<DockViewer active createEngine={createEngine} />);
  await waitFor(() => expect(screen.getByTestId("scene-view").dataset["state"]).toBe("loaded"));
  return view;
}

function select(testId: string, value: string): void {
  fireEvent.change(screen.getByTestId(testId), { target: { value } });
}

describe("the deformation exaggeration in the 3D View", () => {
  it("shows only with deformation bindings, is stored per model, and reaches the scene", async () => {
    const spy = vi.spyOn(BuiltScene.prototype, "setExaggeration");
    openModel([TORSION]);
    await mount();
    const badge = screen.getByTestId("deformation-badge");
    expect(badge.dataset["factor"]).toBe("1");
    expect(within(badge).getByText("true scale")).toBeTruthy();
    expect(spy).toHaveBeenLastCalledWith(1);

    select("deformation-exaggeration", "100");
    expect(screen.getByTestId("deformation-badge").dataset["exaggerated"]).toBe("true");
    expect(within(screen.getByTestId("deformation-badge")).getByText("exaggerated")).toBeTruthy();
    expect(spy).toHaveBeenLastCalledWith(100);
    expect(readExaggeration("p/Beam")).toBe(100);
    // another model keeps its own factor
    expect(readExaggeration("p/Other")).toBe(1);
    // the bound torsion gives the beam mesh its stripes
    const mesh = engines[0]?.scenes[0]?.getMeshByName("visual:beam_box:beam");
    expect(mesh).toBeTruthy();
    const colours = mesh?.getVerticesData(VertexBuffer.ColorKind) ?? [];
    expect([...colours].some((c) => Math.abs(c - STRIPE_SHADE) < 1e-6)).toBe(true);
  });

  it("opens with the model's scene.exaggeration; a stored choice wins, and choosing the default again clears it", async () => {
    const spy = vi.spyOn(BuiltScene.prototype, "setExaggeration");
    openModel([TORSION], 10);
    const view = await mount();
    const badge = screen.getByTestId("deformation-badge");
    expect(badge.dataset["factor"]).toBe("10");
    expect(badge.dataset["exaggerated"]).toBe("true");
    await waitFor(() => expect(spy).toHaveBeenLastCalledWith(10));
    // nothing stored yet: the model's default is in charge
    expect(localStorage.getItem("bgsim.viewer.exaggeration.p/Beam")).toBeNull();
    // true scale is a choice of its own now, so it is stored
    select("deformation-exaggeration", "1");
    expect(screen.getByTestId("deformation-badge").dataset["factor"]).toBe("1");
    expect(readExaggeration("p/Beam", undefined, 10)).toBe(1);
    view.unmount();
    useExaggerationStore.setState({ byModel: {} });
    await mount();
    expect(screen.getByTestId("deformation-badge").dataset["factor"]).toBe("1");
    // back to the model's default: the entry goes, the model keeps the say
    select("deformation-exaggeration", "10");
    expect(localStorage.getItem("bgsim.viewer.exaggeration.p/Beam")).toBeNull();
  });

  it("has no badge without deformation bindings", async () => {
    openModel([]);
    await mount();
    expect(screen.queryByTestId("deformation-badge")).toBeNull();
  });
});

describe("deformation bindings in the binding table", () => {
  it("adds a two-mode torsion binding to a cylinder, offering only boxes and cylinders", async () => {
    openModel([]);
    await mount();
    fireEvent.click(screen.getByTestId("bindings-toggle"));
    select("add-property", "deformation");
    const targets = [...(screen.getByTestId("add-target") as HTMLSelectElement).options].map((o) => o.value);
    expect(targets).toEqual(["", "visual:clamp", "visual:beam_box", "visual:rod"]);
    select("add-target", "visual:rod");
    // a cylinder bends along its own axis
    expect((screen.getByTestId("add-axis") as HTMLSelectElement).value).toBe("+z");
    select("add-family", "torsion");
    select("add-basis", "free-free");
    expect((screen.getByTestId("add-binding") as HTMLButtonElement).disabled).toBe(true);
    select("add-signal-0", "B/eta_t[1]");
    fireEvent.click(screen.getByTestId("add-signal-add-mode"));
    expect((screen.getByTestId("add-binding") as HTMLButtonElement).disabled).toBe(true);
    select("add-signal-1", "B/eta_t[2]");
    fireEvent.click(screen.getByTestId("add-binding"));
    expect(bindings()).toEqual([
      { target: "visual:rod", property: "deformation", family: "torsion", basis: "free-free", beam: { axis: "+z" }, signal: ["B/eta_t[1]", "B/eta_t[2]"] },
    ]);
  });

  it("offers the linear basis for torsion only, with one twist signal", async () => {
    openModel([{ ...TORSION, signal: ["B/eta_t[1]", "B/eta_t[2]"] }]);
    await mount();
    fireEvent.click(screen.getByTestId("bindings-toggle"));
    const options = (id: string): string[] => [...(screen.getByTestId(id) as HTMLSelectElement).options].map((o) => o.value);
    expect(options("binding-basis-0")).toEqual(["clamped-free", "free-free", "linear"]);
    // linear keeps the first signal only and allows no second
    select("binding-basis-0", "linear");
    expect(bindings()[0]).toMatchObject({ basis: "linear", signal: ["B/eta_t[1]"] });
    expect((screen.getByTestId("binding-signal-0-add-mode") as HTMLButtonElement).disabled).toBe(true);
    // a bending family falls back to a modal basis
    select("binding-family-0", "bending-y");
    expect(bindings()[0]).toMatchObject({ family: "bending-y", basis: "clamped-free" });
    expect(options("binding-basis-0")).toEqual(["clamped-free", "free-free"]);

    // the add form: torsion + linear on the cylinder
    select("add-property", "deformation");
    select("add-target", "visual:rod");
    expect(options("add-basis")).toEqual(["clamped-free", "free-free"]);
    select("add-family", "torsion");
    select("add-basis", "linear");
    expect((screen.getByTestId("add-signal-add-mode") as HTMLButtonElement).disabled).toBe(true);
    select("add-signal-0", "B/eta_t[1]");
    fireEvent.click(screen.getByTestId("add-binding"));
    expect(bindings()[1]).toEqual({ target: "visual:rod", property: "deformation", family: "torsion", basis: "linear", beam: { axis: "+z" }, signal: ["B/eta_t[1]"] });
  });

  it("edits family, mapping, modes and strain of a row, and shows its problems", { timeout: 20_000 }, async () => {
    openModel([{ ...TORSION, family: "bending-y", signal: ["B/eta_y[1]"] }, { ...TORSION, target: "visual:ball" }]);
    await mount();
    fireEvent.click(screen.getByTestId("bindings-toggle"));
    // the ball is no beam (E301)
    expect(screen.getByTestId("binding-row-1").dataset["invalid"]).toBe("true");
    expect(screen.getByTestId("binding-problem-1").textContent).toMatch(/E301.*sphere is not a beam/);
    expect(screen.getByTestId("binding-row-0").dataset["invalid"]).toBeUndefined();

    select("binding-family-0", "bending-z");
    expect((bindings()[0] as DeformationBinding).family).toBe("bending-z");
    select("binding-beam-y-0", "-z");
    expect((bindings()[0] as DeformationBinding).beam).toEqual({ axis: "+x", y: "-z" });
    // the axis moves the y along when they would coincide
    select("binding-axis-0", "+z");
    expect((bindings()[0] as DeformationBinding).beam).toEqual({ axis: "+z" });
    const length = screen.getByTestId("binding-length-0");
    fireEvent.change(length, { target: { value: "0.9" } });
    fireEvent.blur(length);
    expect((bindings()[0] as DeformationBinding).beam.length).toBe(0.9);
    fireEvent.change(length, { target: { value: "" } });
    fireEvent.blur(length);
    expect((bindings()[0] as DeformationBinding).beam.length).toBeUndefined();

    fireEvent.click(screen.getByTestId("binding-signal-0-add-mode"));
    expect((bindings()[0] as DeformationBinding).signal).toEqual(["B/eta_y[1]", ""]);
    fireEvent.click(screen.getByTestId("binding-signal-0-remove-mode"));
    expect((bindings()[0] as DeformationBinding).signal).toEqual(["B/eta_y[1]"]);

    act(() => {
      fireEvent.click(screen.getByTestId("binding-strain-0"));
    });
    expect((bindings()[0] as DeformationBinding).strain).toEqual({ colormap: "heat", range: [0, 0.001] });
    fireEvent.click(screen.getByTestId("binding-strain-0"));
    expect((bindings()[0] as DeformationBinding).strain).toBeUndefined();
    // a deformation has no offset
    expect(screen.queryByTestId("binding-offset-0")).toBeNull();
  });
});
