/**
 * The tunables editor of the Export dialog (plan/EXPORT_PLAN.md W-EX1, J-EX8;
 * plan/GLOBAL_PARAMETERS.md "Expose global parameters as FMU parameters").
 *
 * By default the export folds every parameter into a literal (D-EX10), which is the fastest
 * code. A tunable stays an FMU parameter the host sets before initialization
 * (`causality="parameter"`, `variability="fixed"`): a block parameter (`Motor1/R`) or a global
 * parameter (`global:m`). Exposing a global turns every block parameter and start computed
 * from it into a calculated value that the FMU recomputes once in
 * `fmi2ExitInitializationMode`. Each tunable carries a range (D-EX16): the export proves the
 * step stable over it and the FMU refuses values outside it; a block parameter starts from
 * its catalog `min`/`max`.
 *
 * The rules are the exporter's (`BGSim.Export.plan_tunables`); this module only lists the
 * candidates the browser can see and builds the request. The report is the authority (W215
 * says what it did not honour).
 */

import type { ParameterDecl } from "../contracts/catalog";
import type { ExportTunable } from "../contracts/export-request";
import type { Model, ModelDiagram, ModelNode } from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import {
  evaluateField,
  evaluateGlobals,
  globalsOf,
  namesIn,
  type GlobalEvaluation,
} from "../globals/globals";
import { findSubsystem, MARKER_INPUT, MARKER_OUTPUT, MARKER_PARAMETER } from "./exportInterface";

/** The request id prefix of a global parameter (Julia `IR.GLOBAL_OVERRIDE_PREFIX`). */
export const GLOBAL_PREFIX = "global:";

export interface TunableCandidate {
  /** The request id: `Inst/param` or `global:<name>`. */
  id: string;
  kind: "parameter" | "global";
  /** The value the export would fold (null when the browser cannot evaluate it). */
  value: number | null;
  unit: string | null;
  /** The catalog range of a block parameter (null: open). */
  min: number | null;
  max: number | null;
  description: string;
  /**
   * Why it cannot be picked, or null: a driven global (an equation over other globals), a
   * parameter whose value is an expression over globals (expose the global instead), or a
   * parameter that is already tunable at runtime.
   */
  blocked: string | null;
}

/** One picked tunable as the dialog edits it (texts, so a half-typed number is kept). */
export interface TunableRow {
  id: string;
  minText: string;
  maxText: string;
}

const MARKERS = new Set([MARKER_INPUT, MARKER_OUTPUT, MARKER_PARAMETER]);

function* walk(diagram: ModelDiagram, prefix: string): Generator<[string, ModelNode]> {
  for (const node of diagram.nodes) {
    const path = `${prefix}${node.name}`;
    yield [path, node];
    if ("subsystem" in node.block) {
      yield* walk(node.block.subsystem.diagram, `${path}/`);
    }
  }
}

function parameterCandidate(
  path: string,
  node: ModelNode,
  decl: ParameterDecl,
  evaluation: GlobalEvaluation,
): TunableCandidate | null {
  if (decl.type !== "Real") {
    return null;
  }
  const text = node.params?.[decl.name] ?? decl.default;
  const field = evaluateField(String(text), evaluation);
  if (typeof field.value !== "number" || !Number.isFinite(field.value)) {
    return null;
  }
  const usesGlobal = field.driven && namesIn(String(text)).some((name) => evaluation.byName.has(name));
  return {
    id: `${path}/${decl.name}`,
    kind: "parameter",
    value: field.value,
    unit: decl.unit,
    min: decl.min,
    max: decl.max,
    description: decl.description,
    blocked: decl.tunable
      ? "already tunable at runtime"
      : usesGlobal
        ? "computed from a global parameter; expose the global instead"
        : null,
  };
}

/**
 * Everything the tunables editor offers for an export of `scope` (null: the whole model):
 * the global parameters first, then the scalar Real parameters of every catalog block, by
 * instance path as the scoped model names them.
 */
export function listTunableCandidates(
  doc: Pick<Model, "diagram" | "parameters">,
  scope: string | null,
  index: CatalogIndex | null,
): TunableCandidate[] {
  const globals = globalsOf(doc as Pick<Model, "parameters">);
  const evaluation = evaluateGlobals(globals);
  const out: TunableCandidate[] = [];
  for (const row of evaluation.rows) {
    const entry = globals.find((g) => g.name === row.name);
    out.push({
      id: `${GLOBAL_PREFIX}${row.name}`,
      kind: "global",
      value: row.value,
      unit: entry?.unit ?? null,
      min: null,
      max: null,
      description: entry?.description ?? "",
      blocked: row.error !== null
        ? row.error
        : row.deps.length > 0
          ? `an equation over ${row.deps.join(", ")}; recomputed from them`
          : null,
    });
  }
  if (index === null) {
    return out;
  }
  let diagram = doc.diagram;
  let prefix = "";
  if (scope !== null) {
    const node = findSubsystem(doc, scope);
    if (node === null || !("subsystem" in node.block)) {
      return out;
    }
    // The scoped model has the subsystem at its root (Export.scope_document).
    diagram = node.block.subsystem.diagram;
    prefix = `${node.name}/`;
  }
  for (const [path, node] of walk(diagram, prefix)) {
    if (!("ref" in node.block) || MARKERS.has(node.block.ref)) {
      continue;
    }
    const block = index.blocksByRef.get(node.block.ref);
    for (const decl of block?.parameters ?? []) {
      const candidate = parameterCandidate(path, node, decl, evaluation);
      if (candidate !== null) {
        out.push(candidate);
      }
    }
  }
  return out;
}

/** A row for a newly picked candidate: its catalog range, empty texts for an open end. */
export function newTunableRow(candidate: TunableCandidate): TunableRow {
  return {
    id: candidate.id,
    minText: candidate.min === null ? "" : String(candidate.min),
    maxText: candidate.max === null ? "" : String(candidate.max),
  };
}

/** Rows for every independent global not yet picked (the one-click "Expose all globals"). */
export function exposeAllGlobals(
  rows: readonly TunableRow[],
  candidates: readonly TunableCandidate[],
): TunableRow[] {
  const have = new Set(rows.map((row) => row.id));
  const added = candidates
    .filter((c) => c.kind === "global" && c.blocked === null && !have.has(c.id))
    .map(newTunableRow);
  return [...rows, ...added];
}

function parseEnd(text: string): number | null {
  const trimmed = text.trim();
  if (trimmed === "") {
    return null;
  }
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : Number.NaN;
}

/** Why the row's range is not usable, or null. An open end is allowed (W210 in the report). */
export function rowProblem(row: TunableRow, candidate: TunableCandidate | undefined): string | null {
  const min = parseEnd(row.minText);
  const max = parseEnd(row.maxText);
  if (Number.isNaN(min) || Number.isNaN(max)) {
    return "min and max must be numbers (empty: open)";
  }
  if (min !== null && max !== null && min > max) {
    return "min is above max";
  }
  const value = candidate?.value ?? null;
  if (value !== null && ((min !== null && value < min) || (max !== null && value > max))) {
    return `the range must contain the model's value ${value}`;
  }
  return null;
}

/** True when a row leaves an end of its range open (the step is then proven only at the value). */
export function rowOpen(row: TunableRow): boolean {
  return row.minText.trim() === "" || row.maxText.trim() === "";
}

/** The request's `settings.tunables`. */
export function tunablesRequest(rows: readonly TunableRow[]): ExportTunable[] {
  return rows.map((row) => {
    const entry: ExportTunable = { id: row.id };
    const min = parseEnd(row.minText);
    const max = parseEnd(row.maxText);
    if (min !== null && !Number.isNaN(min)) {
      entry.min = min;
    }
    if (max !== null && !Number.isNaN(max)) {
      entry.max = max;
    }
    return entry;
  });
}

/** The cost line of the report: right-hand-side operations with the tunables and folded. */
export function tunableCostText(rhsOps: number | undefined, folded: number | null | undefined): string | null {
  if (typeof rhsOps !== "number" || typeof folded !== "number") {
    return null;
  }
  const delta = rhsOps - folded;
  const pct = folded > 0 ? ` (${delta >= 0 ? "+" : ""}${((100 * delta) / folded).toFixed(1)} %)` : "";
  return `${rhsOps} operations per right-hand side with the tunables, ${folded} with everything folded${pct}`;
}
