/** Wording and number formats of the Export dialog (pure, unit-tested). */

import type { ExportJobPhase, ExportJobStatus, ExportTimings } from "../contracts/export-job";
import type { ExportBuild } from "../contracts/export-report";
import type { ExportMethod } from "../contracts/export-request";
import { formatDuration, formatNumber, trimZeros } from "../plot/format";

export const METHOD_LABELS: Record<ExportMethod, string> = {
  auto: "Auto",
  euler: "Euler",
  rk4: "RK4",
  ros2: "ROS2",
  ros34pw2: "ROS34PW2",
  rodas4p: "Rodas4P",
};

export function methodLabel(method: string): string {
  return METHOD_LABELS[method as ExportMethod] ?? method;
}

const PHASES: Record<NonNullable<ExportJobPhase>, string> = {
  starting: "Starting Julia and loading BGSim",
  scope: "Building the scoped model",
  flatten: "Flattening the model",
  reference: "Running the reference simulation",
  export: "Analysing the spectrum and generating C",
  build: "Compiling and checking the FMU",
};

/** What a queued or running job is doing, for the progress line. */
export function progressLabel(status: ExportJobStatus, phase: ExportJobPhase | undefined): string {
  if (status === "queued") {
    return "Waiting for another export to finish";
  }
  return phase ? PHASES[phase] : "Exporting";
}

/** A step size in seconds as `1 ms`, `62.5 µs`, `40 ns`. */
export function formatStep(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return "—";
  }
  const units: [number, string][] = [
    [1, "s"],
    [1e-3, "ms"],
    [1e-6, "µs"],
    [1e-9, "ns"],
  ];
  for (const [scale, unit] of units) {
    if (Math.abs(seconds) >= scale || scale === 1e-9) {
      return `${trimZeros((seconds / scale).toPrecision(4))} ${unit}`;
    }
  }
  return `${seconds} s`;
}

/** An estimated flop count as `1240`, `4.2e6`. */
export function formatCost(cost: number | null | undefined): string {
  return cost === null || cost === undefined ? "—" : formatNumber(Math.round(cost));
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${trimZeros((bytes / 1024).toFixed(1))} KB`;
  }
  return `${trimZeros((bytes / 1024 / 1024).toFixed(1))} MB`;
}

const TIMING_PARTS: [keyof ExportTimings, string][] = [
  ["juliaS", "Julia start"],
  ["scopeS", "scope"],
  ["flattenS", "flatten"],
  ["referenceS", "reference run"],
  ["exportS", "analysis and C"],
  ["buildS", "build"],
];

/** `Julia start 14 s · flatten 1.1 s · … ` without the total. */
export function timingParts(timings: ExportTimings | undefined): string[] {
  if (timings === undefined) {
    return [];
  }
  return TIMING_PARTS.filter(([key]) => typeof timings[key] === "number").map(
    ([key, label]) => `${label} ${formatDuration(timings[key] as number)}`,
  );
}

/** One sentence per build result (D-EX15: a source-only FMU says why). */
export function buildLines(build: ExportBuild | undefined): string[] {
  if (build === undefined) {
    return [];
  }
  if (build.sourceOnly) {
    return [`Source-only FMU: ${build.note ?? "no binary was built"}.`];
  }
  const lines: string[] = [];
  const compiler = build.compiler?.split(/[\\/]/).pop() ?? "a C compiler";
  lines.push(`Built with ${compiler}${build.platform ? ` for ${build.platform}` : ""}.`);
  if (build.symbolCheck === true) {
    lines.push("Symbol check passed: the hot path imports no allocator, stdio or exit.");
  } else if (build.symbolCheck === false) {
    lines.push(`Symbol check failed: ${(build.forbiddenSymbols ?? []).join(", ")}.`);
  }
  if (build.cxxOk === true) {
    lines.push("The sources also compile as C++17.");
  } else if (build.cxxOk === false) {
    lines.push("The sources do not compile as C++17.");
  }
  if (build.allocationsAfterInstantiate !== null && build.allocationsAfterInstantiate !== undefined) {
    lines.push(
      `${build.allocationsAfterInstantiate} allocation${build.allocationsAfterInstantiate === 1 ? "" : "s"} after instantiate over ${build.harnessDoSteps ?? "?"} doStep calls.`,
    );
  }
  if (typeof build.doStepMeanUs === "number") {
    lines.push(
      `doStep on this machine: mean ${formatNumber(build.doStepMeanUs)} µs, max ${formatNumber(build.doStepMaxUs ?? Number.NaN)} µs.`,
    );
  }
  if (build.error) {
    lines.push(`Build problem: ${build.error.split("\n")[0]}`);
  }
  return lines;
}

/** Parse an optional positive number field: "" is null (automatic), NaN is invalid. */
export function parseOptionalPositive(text: string): number | null {
  const trimmed = text.trim();
  if (trimmed.length === 0) {
    return null;
  }
  const value = Number(trimmed);
  return Number.isFinite(value) && value > 0 ? value : Number.NaN;
}
