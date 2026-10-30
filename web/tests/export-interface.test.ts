/**
 * The Export dialog's interface preview and wording (W-EX1): the same naming rules as
 * BGSim.Export.scope_document and the marker scan of export_model.
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { Model } from "../src/contracts/model";
import {
  buildLines,
  defaultStep,
  formatBytes,
  formatStep,
  methodLabel,
  parseOptionalPositive,
  progressLabel,
  timingParts,
} from "../src/export/exportFormat";
import {
  defaultPowerInputs,
  findSubsystem,
  isEmptyInterface,
  listSubsystems,
  previewInterface,
} from "../src/export/exportInterface";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

function readJson<T>(...parts: string[]): T {
  return JSON.parse(readFileSync(path.join(repoRoot, ...parts), "utf8")) as T;
}

const scoped = readJson<{ model: Model }>(
  "contracts", "fixtures", "export-request", "valid", "export-request.scope.json",
).model;
const hydraulic = readJson<Model>("examples", "hydraulic-servo", "models", "hydraulic-servo.bgmodel.json");
const panda = readJson<Model>("examples", "panda-3d", "models", "panda.bgmodel.json");

function withMarkers(model: Model): Model {
  const copy = structuredClone(model);
  copy.diagram.nodes.push(
    { id: "m1", name: "setpoint", block: { ref: "stdlib:converters/ExportInput" }, position: { x: 0, y: 0 } },
    { id: "m2", name: "speed", block: { ref: "stdlib:converters/ExportOutput" }, position: { x: 0, y: 0 } },
    { id: "m3", name: "gain", block: { ref: "stdlib:converters/ExportParameter" }, position: { x: 0, y: 0 } },
  );
  return copy;
}

describe("listSubsystems / findSubsystem", () => {
  it("lists every subsystem by instance path", () => {
    expect(listSubsystems(scoped)).toEqual([{ path: "Plant", name: "Plant" }]);
    expect(listSubsystems(hydraulic).map((s) => s.path)).toEqual(["Valve"]);
    expect(listSubsystems(panda).map((s) => s.path)).toEqual(["Robot"]);
    expect(findSubsystem(scoped, "Plant")?.name).toBe("Plant");
    expect(findSubsystem(scoped, "Drive")).toBeNull();
    expect(findSubsystem(scoped, "Nope")).toBeNull();
  });
});

describe("previewInterface", () => {
  it("publishes the markers of the whole model, and nothing without them (W209)", () => {
    const empty = previewInterface(scoped, null, {});
    expect(isEmptyInterface(empty)).toBe(true);
    const marked = previewInterface(withMarkers(scoped), null, {});
    expect(marked.inputs.map((e) => e.name)).toEqual(["setpoint"]);
    expect(marked.outputs.map((e) => e.name)).toEqual(["speed"]);
    expect(marked.parameters.map((e) => e.name)).toEqual(["gain"]);
    expect(isEmptyInterface(marked)).toBe(false);
  });

  it("publishes a subsystem's ports, a power port by the chosen variable", () => {
    expect(defaultPowerInputs(scoped, "Plant")).toEqual({ p: "effort" });
    const effort = previewInterface(scoped, "Plant", { p: "effort" });
    expect(effort.inputs.map((e) => e.name)).toEqual(["u", "p_e"]);
    expect(effort.outputs.map((e) => e.name)).toEqual(["y", "p_f"]);
    expect(effort.powerPorts).toEqual([{ name: "p", domain: "Generic", choice: "effort" }]);
    const flow = previewInterface(scoped, "Plant", { p: "flow" });
    expect(flow.inputs.map((e) => e.name)).toEqual(["u", "p_f"]);
    expect(flow.outputs.map((e) => e.name)).toEqual(["y", "p_e"]);
  });

  it("previews the example subsystems", () => {
    const valve = previewInterface(hydraulic, "Valve", defaultPowerInputs(hydraulic, "Valve"));
    expect(valve.powerPorts.map((p) => p.name)).toEqual(["P", "T", "A", "B"]);
    expect(valve.inputs.map((e) => e.name)).toEqual(["u", "P_e", "T_e", "A_e", "B_e"]);
    const robot = previewInterface(panda, "Robot", {});
    expect(robot.inputs).toHaveLength(7);
    expect(robot.outputs).toHaveLength(21);
    expect(robot.powerPorts).toEqual([]);
  });

  it("flags a missing scope and ports a scope cannot take", () => {
    expect(previewInterface(scoped, "Nope", {}).missingScope).toBe(true);
    const vector = structuredClone(scoped);
    const plant = vector.diagram.nodes[1];
    if (plant === undefined || !("subsystem" in plant.block)) {
      throw new Error("fixture changed");
    }
    const port = plant.block.subsystem.ports[0];
    if (port?.kind === "signal") {
      port.size = [3];
    }
    const preview = previewInterface(vector, "Plant", { p: "effort" });
    expect(preview.problems).toEqual([
      "The vector signal port u cannot be an export interface yet (E112).",
    ]);
  });
});

describe("export wording", () => {
  it("formats steps, sizes and labels", () => {
    expect(formatStep(1e-3)).toBe("1 ms");
    expect(formatStep(6.25e-5)).toBe("62.5 µs");
    expect(formatStep(4e-8)).toBe("40 ns");
    expect(formatStep(0.5)).toBe("500 ms");
    // the same rule as BGSim.Export.default_step
    expect(defaultStep(1)).toBe(1e-3);
    expect(defaultStep(0.3)).toBe(5e-4);
    expect(defaultStep(0.1)).toBe(2e-4);
    expect(defaultStep(5.15)).toBe(1e-3);
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(91234)).toBe("89.1 KB");
    expect(methodLabel("rodas4p")).toBe("Rodas4P");
    expect(progressLabel("queued", null)).toBe("Waiting for another export to finish");
    expect(progressLabel("running", "reference")).toBe("Running the reference simulation");
    expect(parseOptionalPositive("")).toBeNull();
    expect(parseOptionalPositive(" 1e-4 ")).toBe(1e-4);
    expect(parseOptionalPositive("-1")).toBeNaN();
    expect(parseOptionalPositive("abc")).toBeNaN();
    expect(timingParts({ juliaS: 14.2, flattenS: 1.1, buildS: 3.25 })).toEqual([
      "Julia start 14.2 s",
      "flatten 1.1 s",
      "build 3.25 s",
    ]);
  });

  it("states the build results, or why the FMU is source-only", () => {
    expect(
      buildLines({ compilerFound: false, sourceOnly: true, ok: true, note: "no C compiler was found" }),
    ).toEqual(["Source-only FMU: no C compiler was found."]);
    const lines = buildLines({
      compilerFound: true,
      compiler: "C:\\msys64\\mingw64\\bin\\gcc.exe",
      sourceOnly: false,
      platform: "win64",
      ok: true,
      symbolCheck: true,
      cxxOk: true,
      harnessDoSteps: 20000,
      allocationsAfterInstantiate: 0,
      doStepMeanUs: 0.41,
      doStepMaxUs: 12.3,
    });
    expect(lines).toEqual([
      "Built with gcc.exe for win64.",
      "Symbol check passed: the hot path imports no allocator, stdio or exit.",
      "The sources also compile as C++17.",
      "0 allocations after instantiate over 20000 doStep calls.",
      "doStep on this machine: mean 0.41 µs, max 12.3 µs.",
    ]);
  });
});
