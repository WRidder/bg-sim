/**
 * Global (model-level) parameters, SolidWorks "Global Variables / Equations"
 * style (spec "Global parameters", plan/GLOBAL_PARAMETERS.md).
 *
 * A model's top-level `parameters` are named constant expressions over
 * literals, other globals and the pure built-in functions. The compiler folds
 * them statically (Julia `src/compile/globals.jl`); this module is the
 * browser's mirror of the same rules, so the editor can show values, cycles
 * and errors while the user types:
 *
 * * names are identifiers, unique, not reserved and not a built-in function;
 * * evaluation follows the dependency order; a cycle is an error on every
 *   member, with the cycle path; a global that uses a broken one is broken;
 * * results must be finite numbers.
 *
 * It also finds every instance expression (params, starts, string constants)
 * at every diagram level, which is what "used by", the rename refactor and the
 * Equations view need.
 */

import type { Model, ModelDiagram, ModelGlobalParameter, ModelNode } from "../contracts/model";
import { WHITELIST_FUNCTIONS } from "../code/completion";
import {
  BUILTIN_CONSTANTS,
  evaluateExpression,
  expressionNames,
  isPlainLiteral,
  parseExpression,
  renameIdentifier,
} from "../inspector/expression";

export const GLOBAL_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** The compiler's `RESERVED_GLOBAL_NAMES` (Julia `globals.jl`); keep the two in step. */
export const RESERVED_GLOBAL_NAMES: ReadonlySet<string> = new Set([
  ...BUILTIN_CONSTANTS.keys(),
  "t", "Ts", "ifelse", "true", "false", "begin", "end", "if", "else", "elseif", "for",
  "while", "function", "return", "let", "local", "global", "const", "struct", "module",
  "using", "import", "do", "try", "catch", "finally", "quote", "macro", "abstract",
  "primitive", "mutable", "baremodule", "export", "in", "isa", "where", "break", "continue",
  "type",
]);

const FUNCTION_NAMES: ReadonlySet<string> = new Set(WHITELIST_FUNCTIONS);

/** The model's global parameters (an absent array is none). */
export function globalsOf(doc: Pick<Model, "parameters"> | null): readonly ModelGlobalParameter[] {
  return doc?.parameters ?? [];
}

/** Why `name` cannot name a global (other than `self`), or null. */
export function globalNameIssue(
  globals: readonly ModelGlobalParameter[],
  name: string,
  self: string | null = null,
): string | null {
  if (name.length === 0) {
    return "Enter a name.";
  }
  if (!GLOBAL_NAME_PATTERN.test(name)) {
    return "Names start with a letter or underscore and use only letters, digits and underscores.";
  }
  if (RESERVED_GLOBAL_NAMES.has(name)) {
    return `"${name}" is reserved.`;
  }
  if (FUNCTION_NAMES.has(name)) {
    return `"${name}" is a built-in function.`;
  }
  if (globals.some((entry) => entry.name === name && entry.name !== self)) {
    return `A global parameter named "${name}" already exists.`;
  }
  return null;
}

export interface GlobalStatus {
  name: string;
  /** The folded value, when the global evaluates. */
  value: number | null;
  /** Why it does not evaluate, ready to show. */
  error: string | null;
  /** The other globals its expression reads. */
  deps: string[];
}

export interface GlobalEvaluation {
  /** One status per row of the table, in document order (a duplicate name has its own row). */
  rows: readonly GlobalStatus[];
  /** The first global of each name. */
  byName: ReadonlyMap<string, GlobalStatus>;
  /** The folded values of the globals that evaluate: the scope of instance expressions. */
  values: ReadonlyMap<string, number>;
  /** Evaluation (dependency) order; cycle members come last. */
  order: readonly string[];
}

/** Evaluate the global table with the compiler's rules. */
export function evaluateGlobals(globals: readonly ModelGlobalParameter[]): GlobalEvaluation {
  const byName = new Map<string, GlobalStatus>();
  const rows: GlobalStatus[] = [];
  const asts = new Map<string, ReturnType<typeof parseExpression>>();
  for (const entry of globals) {
    const status: GlobalStatus = { name: entry.name, value: null, error: null, deps: [] };
    rows.push(status);
    if (byName.has(entry.name)) {
      status.error = "Declared twice.";
      continue;
    }
    byName.set(entry.name, status);
    const nameIssue = globalNameIssue([], entry.name);
    if (nameIssue !== null) {
      status.error = nameIssue;
      continue;
    }
    const parsed = parseExpression(entry.value);
    asts.set(entry.name, parsed);
    if (!parsed.ok) {
      status.error = parsed.message;
      continue;
    }
    const names = expressionNames(parsed.ast).filter((name) => !BUILTIN_CONSTANTS.has(name));
    const unknown = names.filter((name) => !globals.some((other) => other.name === name));
    status.deps = names.filter((name) => !unknown.includes(name));
    if (unknown.length > 0) {
      status.error = `${unknown.map((name) => `"${name}"`).join(", ")} ${
        unknown.length === 1 ? "is" : "are"
      } not a global parameter.`;
    }
  }

  // Kahn's algorithm over the globals that parsed; what is left is on or behind a cycle.
  const pending = new Set(
    [...byName.values()].filter((s) => asts.get(s.name)?.ok === true && byName.get(s.name) === s).map((s) => s.name),
  );
  const order: string[] = [];
  let progressed = true;
  while (progressed) {
    progressed = false;
    for (const entry of globals) {
      const status = byName.get(entry.name);
      if (status === undefined || !pending.has(entry.name)) {
        continue;
      }
      if (status.deps.every((dep) => !pending.has(dep))) {
        pending.delete(entry.name);
        order.push(entry.name);
        progressed = true;
      }
    }
  }
  for (const name of pending) {
    const cycle = findCycle(byName, name, pending);
    const status = byName.get(name);
    if (status !== undefined && status.error === null) {
      status.error =
        cycle === null
          ? "Depends on a cycle."
          : `Cycle: ${[...cycle, cycle[0]].join(" → ")}.`;
    }
    order.push(name);
  }

  const values = new Map<string, number>();
  for (const name of order) {
    const status = byName.get(name);
    const parsed = asts.get(name);
    if (status === undefined || parsed === undefined || !parsed.ok || status.error !== null) {
      continue;
    }
    const broken = status.deps.find((dep) => !values.has(dep));
    if (broken !== undefined) {
      status.error = `Uses "${broken}", which has an error.`;
      continue;
    }
    const result = evaluateExpression(parsed.ast, values);
    if (!result.ok) {
      status.error = result.message;
    } else if (typeof result.value !== "number") {
      status.error = "The value must be a number, not a Bool.";
    } else if (!Number.isFinite(result.value)) {
      status.error = `Evaluates to ${result.value}, which is not finite.`;
    } else {
      status.value = result.value;
      values.set(name, result.value);
    }
  }
  return { rows, byName, values, order };
}

function findCycle(
  byName: ReadonlyMap<string, GlobalStatus>,
  start: string,
  among: ReadonlySet<string>,
): string[] | null {
  const path = [start];
  const seen = new Set<string>();
  const walk = (name: string): boolean => {
    for (const dep of byName.get(name)?.deps ?? []) {
      if (!among.has(dep)) {
        continue;
      }
      if (dep === start) {
        return true;
      }
      if (path.includes(dep) || seen.has(dep)) {
        continue;
      }
      path.push(dep);
      if (walk(dep)) {
        return true;
      }
      path.pop();
      seen.add(dep);
    }
    return false;
  };
  return walk(start) ? path : null;
}

// ---------------------------------------------------------------------------
// Instance expressions
// ---------------------------------------------------------------------------

export type FieldKind = "param" | "start" | "constant";

/** One expression string of one node, anywhere in the model. */
export interface ExpressionField {
  /** Subsystem node ids from the root to the node's diagram (the store's `activePath`). */
  diagramPath: string[];
  /** Instance names from the root to the node, e.g. `["Plant", "Spring1"]`. */
  instancePath: string[];
  nodeId: string;
  kind: FieldKind;
  key: string;
  text: string;
}

function stringFields(node: ModelNode): { kind: FieldKind; key: string; text: string }[] {
  const out: { kind: FieldKind; key: string; text: string }[] = [];
  for (const [key, text] of Object.entries(node.params ?? {})) {
    out.push({ kind: "param", key, text });
  }
  for (const [key, text] of Object.entries(node.starts ?? {})) {
    out.push({ kind: "start", key, text });
  }
  for (const [key, value] of Object.entries(node.constants ?? {})) {
    if (typeof value === "string") {
      out.push({ kind: "constant", key, text: value });
    }
  }
  return out;
}

function walk(
  diagram: ModelDiagram,
  diagramPath: string[],
  instancePath: string[],
  out: ExpressionField[],
): void {
  for (const node of diagram.nodes) {
    const here = [...instancePath, node.name];
    for (const field of stringFields(node)) {
      out.push({ diagramPath, instancePath: here, nodeId: node.id, ...field });
    }
    if ("subsystem" in node.block) {
      walk(node.block.subsystem.diagram, [...diagramPath, node.id], here, out);
    }
  }
}

/** Every params/starts/string-constants entry of the model, root first, depth first. */
export function expressionFields(doc: Pick<Model, "diagram">): ExpressionField[] {
  const out: ExpressionField[] = [];
  walk(doc.diagram, [], [], out);
  return out;
}

/** The fields that are equations (not a plain literal): the Equations view. */
export function drivenFields(doc: Pick<Model, "diagram">): ExpressionField[] {
  return expressionFields(doc).filter((field) => !isPlainLiteral(field.text));
}

/** The names an expression string reads, or [] when it does not parse. */
export function namesIn(text: string): string[] {
  const parsed = parseExpression(text);
  return parsed.ok ? expressionNames(parsed.ast) : [];
}

/** The instance fields that read global `name`. */
export function globalUsages(doc: Pick<Model, "diagram">, name: string): ExpressionField[] {
  return expressionFields(doc).filter((field) => namesIn(field.text).includes(name));
}

/** The globals whose expression reads global `name`. */
export function globalDependents(
  globals: readonly ModelGlobalParameter[],
  name: string,
): string[] {
  return globals.filter((entry) => namesIn(entry.value).includes(name)).map((entry) => entry.name);
}

/** Rewrite every whole-identifier use of `from` in a diagram (in place, on an immer draft). */
export function renameInDiagram(diagram: ModelDiagram, from: string, to: string): void {
  for (const node of diagram.nodes) {
    for (const map of [node.params, node.starts] as (Record<string, string> | undefined)[]) {
      if (map === undefined) {
        continue;
      }
      for (const [key, text] of Object.entries(map)) {
        const next = renameIdentifier(text, from, to);
        if (next !== text) {
          map[key] = next;
        }
      }
    }
    if (node.constants !== undefined) {
      for (const [key, value] of Object.entries(node.constants)) {
        if (typeof value === "string") {
          const next = renameIdentifier(value, from, to);
          if (next !== value) {
            node.constants[key] = next;
          }
        }
      }
    }
    if ("subsystem" in node.block) {
      renameInDiagram(node.block.subsystem.diagram, from, to);
    }
  }
}

export interface FieldEvaluation {
  /** The expression is an equation (not a plain literal): the Σ marker. */
  driven: boolean;
  /** The value, when the browser can compute it. */
  value: number | boolean | null;
  /** Why it cannot (an unknown name, a broken global, a domain error), or null. */
  error: string | null;
}

/**
 * Evaluate one instance expression with the globals in scope. `value` is null
 * (and `error` null) when the text does not parse: the syntax check of the
 * field reports that.
 */
export function evaluateField(text: string, evaluation: GlobalEvaluation): FieldEvaluation {
  const driven = !isPlainLiteral(text);
  const parsed = parseExpression(text);
  if (!parsed.ok) {
    return { driven, value: null, error: null };
  }
  const result = evaluateExpression(parsed.ast, evaluation.values);
  if (result.ok) {
    return { driven, value: result.value, error: null };
  }
  if (result.name !== undefined) {
    const status = evaluation.byName.get(result.name);
    if (status !== undefined) {
      return { driven, value: null, error: `Global "${result.name}" has an error: ${status.error ?? ""}`.trim() };
    }
    return {
      driven,
      value: null,
      error: `Unknown name "${result.name}": declare it as a global parameter (Model inspector).`,
    };
  }
  return { driven, value: null, error: result.message };
}

/** A compact number for the "= value" readouts: 6 significant digits, no trailing zeros. */
export function formatValue(value: number | boolean): string {
  if (typeof value === "boolean") {
    return String(value);
  }
  if (Number.isInteger(value) && Math.abs(value) < 1e15) {
    return String(value);
  }
  const abs = Math.abs(value);
  if (abs !== 0 && (abs < 1e-4 || abs >= 1e6)) {
    return value.toExponential(4).replace(/\.?0+e/, "e");
  }
  return String(Number(value.toPrecision(6)));
}

/** A unique default name for a new global: `p1`, `p2`, ... */
export function nextGlobalName(globals: readonly ModelGlobalParameter[]): string {
  for (let index = 1; ; index += 1) {
    const name = `p${index}`;
    if (!globals.some((entry) => entry.name === name)) {
      return name;
    }
  }
}
