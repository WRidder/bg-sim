/**
 * The Dashboard tab's pure logic (plan/DASHBOARD_PLAN.md): card kinds and sizes, parameter
 * lookup by instance path, binding and schedule validation, the run inputs a dashboard gives
 * (`parameterOverrides` / `parameterSchedule` of the run request) and the value of a recorded
 * signal at the inspect time.
 *
 * Nothing here touches a store; the components and `runInputs.ts` call these functions.
 */

import type { ParameterDecl } from "../contracts/catalog";
import type {
  DashboardCardKind,
  DashboardCardSize,
  Model,
  ModelDashboard,
  ModelDashboardCard,
  ModelDashboardSchedule,
  ModelDiagram,
  ModelNode,
} from "../contracts/model";
import type { ParameterOverride, ParameterStep } from "../contracts/run-manifest";
import { evaluateGlobals, globalsOf, type GlobalEvaluation } from "../globals/globals";
import {
  evaluateExpression,
  evaluateLiteral,
  expressionNames,
  parseExpression,
} from "../inspector/expression";
import type { CatalogIndex } from "../library/catalogIndex";

// ------------------------------------------------------------------ card kinds

export type CardRole = "display" | "input" | "schedule";

export interface CardKindInfo {
  kind: DashboardCardKind;
  label: string;
  role: CardRole;
  description: string;
  size: DashboardCardSize;
}

export const CARD_KINDS: readonly CardKindInfo[] = [
  { kind: "plot", label: "Plot", role: "display", size: "4x2", description: "Signals over time, with the shared cursor." },
  { kind: "value", label: "Value", role: "display", size: "1x1", description: "A big number with its unit and an optional sparkline." },
  { kind: "gauge", label: "Gauge", role: "display", size: "2x2", description: "A dial between min and max with colour zones." },
  { kind: "bar", label: "Bar", role: "display", size: "1x2", description: "A linear scale, e.g. a tank level." },
  { kind: "indicator", label: "Indicator", role: "display", size: "1x1", description: "A light that switches at a threshold." },
  { kind: "text", label: "Text", role: "display", size: "2x1", description: "A note, plain text or Markdown." },
  { kind: "number", label: "Number", role: "input", size: "1x1", description: "Type a parameter value for the next run." },
  { kind: "slider", label: "Slider", role: "input", size: "2x1", description: "Slide a parameter between min and max." },
  { kind: "knob", label: "Knob", role: "input", size: "1x1", description: "Turn a parameter (drag, wheel or arrow keys)." },
  { kind: "toggle", label: "Toggle", role: "input", size: "1x1", description: "Switch a Bool parameter." },
  { kind: "select", label: "Select", role: "input", size: "2x1", description: "Pick an option of an enumeration parameter." },
  { kind: "schedule", label: "Schedule", role: "schedule", size: "4x2", description: "Set parameters from time t on (a table)." },
];

export const CARD_SIZES: readonly DashboardCardSize[] = ["1x1", "2x1", "1x2", "2x2", "4x2"];

export function kindInfo(kind: DashboardCardKind): CardKindInfo {
  return CARD_KINDS.find((entry) => entry.kind === kind) ?? CARD_KINDS[0]!;
}

export const isInputKind = (kind: DashboardCardKind): boolean => kindInfo(kind).role === "input";
export const isDisplayKind = (kind: DashboardCardKind): boolean =>
  kindInfo(kind).role === "display";

/** Grid span of a size preset. */
export function sizeSpan(size: DashboardCardSize): { columns: number; rows: number } {
  const [columns, rows] = size.split("x").map((part) => Number(part));
  return { columns: columns ?? 1, rows: rows ?? 1 };
}

/** A fresh card id that is not used by the dashboard yet. */
export function nextCardId(dashboard: ModelDashboard | undefined): string {
  const used = new Set((dashboard?.cards ?? []).map((card) => card.id));
  let n = used.size + 1;
  while (used.has(`card-${n}`)) {
    n += 1;
  }
  return `card-${n}`;
}

export function newCard(kind: DashboardCardKind, id: string): ModelDashboardCard {
  const card: ModelDashboardCard = { id, kind, size: kindInfo(kind).size };
  if (kind === "schedule") {
    card.schedule = { parameters: [], rows: [] };
  }
  if (kind === "text") {
    card.options = { text: "", markdown: true };
  }
  return card;
}

/** The title a card shows: its own title, else its binding, else the kind. */
export function cardTitle(card: ModelDashboardCard): string {
  const title = card.title?.trim() ?? "";
  if (title.length > 0) {
    return title;
  }
  if (card.parameter !== undefined) {
    return card.parameter;
  }
  const first = card.signals?.[0];
  if (first !== undefined) {
    return card.signals!.length > 1 ? `${first} +${card.signals!.length - 1}` : first;
  }
  return kindInfo(card.kind).label;
}

/** Move the card `id` to `index` (clamped); returns a new array. */
export function moveCard(
  cards: readonly ModelDashboardCard[],
  id: string,
  index: number,
): ModelDashboardCard[] {
  const from = cards.findIndex((card) => card.id === id);
  if (from < 0) {
    return [...cards];
  }
  const next = [...cards];
  const [card] = next.splice(from, 1);
  const to = Math.max(0, Math.min(next.length, index));
  next.splice(to, 0, card!);
  return next;
}

// ------------------------------------------------------------- parameters

/** The target prefix of a model-level global parameter (`global:m`, the Julia override key). */
export const GLOBAL_TARGET_PREFIX = "global:";

export function isGlobalTarget(target: string): boolean {
  return target.startsWith(GLOBAL_TARGET_PREFIX);
}

/**
 * A parameter an input card can bind: a block parameter found by instance path, or a global
 * parameter (`global:<name>`, kind "global": folded at compile time, so it can be overridden
 * for a run but not scheduled).
 */
export interface ParameterInfo {
  /** `<instance path>/<param>`, or `global:<name>`. */
  target: string;
  kind: "block" | "global";
  /** Instance path of the node (`Sub/Motor1`); empty for a global. */
  path: string;
  /** The node; null for a global. */
  node: ModelNode | null;
  decl: ParameterDecl;
  /** The node's own expression, or the declared default. */
  modelText: string;
  /**
   * The model value as a number (Bool as 0/1): the literal, or the expression evaluated with
   * the global parameters in scope (`h_step`, `2*m`); null when it cannot be evaluated.
   */
  modelValue: number | null;
  /** The global parameters the model expression reads (empty for a literal). */
  drivenBy: string[];
}

function literalValue(text: string, type: ParameterDecl["type"]): number | null {
  const trimmed = text.trim();
  if (type === "Bool" || trimmed === "true" || trimmed === "false") {
    if (trimmed === "true") return 1;
    if (trimmed === "false") return 0;
  }
  const parsed = parseExpression(trimmed);
  if (!parsed.ok) {
    return null;
  }
  const value = evaluateLiteral(parsed.ast);
  return value !== null && Number.isFinite(value) ? value : null;
}

/** The parameter declarations of a node: the catalog block's, or the node's own params. */
function nodeDecls(node: ModelNode, index: CatalogIndex | null): ParameterDecl[] {
  if ("ref" in node.block) {
    const block = index?.blocksByRef.get(node.block.ref);
    if (block !== undefined) {
      return block.parameters;
    }
  }
  if ("junction" in node.block || "subsystem" in node.block) {
    return [];
  }
  // An inline block (or a block the catalog does not know yet): what the node sets.
  return Object.keys(node.params ?? {}).map((name) => ({
    name,
    type: "Real",
    default: node.params?.[name] ?? "0",
    unit: null,
    min: null,
    max: null,
    tunable: true,
    description: "",
    options: null,
  }));
}

/**
 * The value of a block parameter's expression with the globals in scope, and the globals it
 * reads. A literal needs no globals; an expression such as `h_step` is what the compiler folds
 * from the global table, so the card shows that value instead of nothing.
 */
function expressionValue(
  text: string,
  type: ParameterDecl["type"],
  evaluation: GlobalEvaluation | null,
): { value: number | null; drivenBy: string[] } {
  const literal = literalValue(text, type);
  if (literal !== null || evaluation === null) {
    return { value: literal, drivenBy: [] };
  }
  const parsed = parseExpression(text.trim());
  if (!parsed.ok) {
    return { value: null, drivenBy: [] };
  }
  const drivenBy = expressionNames(parsed.ast).filter((name) => evaluation.byName.has(name));
  const result = evaluateExpression(parsed.ast, evaluation.values);
  if (!result.ok) {
    return { value: null, drivenBy };
  }
  const value = typeof result.value === "boolean" ? (result.value ? 1 : 0) : result.value;
  return { value: Number.isFinite(value) ? value : null, drivenBy };
}

function infoFor(
  path: string,
  node: ModelNode,
  decl: ParameterDecl,
  evaluation: GlobalEvaluation | null,
): ParameterInfo {
  const modelText = node.params?.[decl.name] ?? decl.default;
  const { value, drivenBy } = expressionValue(modelText, decl.type, evaluation);
  return {
    target: `${path}/${decl.name}`,
    kind: "block",
    path,
    node,
    decl,
    modelText,
    modelValue: value,
    drivenBy,
  };
}

/** The folded global table of a model, or null when it has no globals. */
function globalEvaluation(doc: Model): GlobalEvaluation | null {
  const globals = globalsOf(doc);
  return globals.length === 0 ? null : evaluateGlobals(globals);
}

function walk(
  diagram: ModelDiagram,
  prefix: string,
  visit: (path: string, node: ModelNode) => void,
): void {
  for (const node of diagram.nodes) {
    const path = prefix.length === 0 ? node.name : `${prefix}/${node.name}`;
    visit(path, node);
    if ("subsystem" in node.block) {
      walk(node.block.subsystem.diagram, path, visit);
    }
  }
}

/** The model's global parameters as Real parameters, valued by the compiler's folding rules. */
function globalInfos(doc: Model): ParameterInfo[] {
  const globals = globalsOf(doc);
  if (globals.length === 0) {
    return [];
  }
  const evaluation = evaluateGlobals(globals);
  return globals.map((entry) => ({
    target: `${GLOBAL_TARGET_PREFIX}${entry.name}`,
    kind: "global",
    path: "",
    node: null,
    decl: {
      name: entry.name,
      type: "Real",
      default: entry.value,
      unit: entry.unit ?? null,
      min: null,
      max: null,
      tunable: false,
      description: entry.description ?? "Global parameter",
      options: null,
    },
    modelText: entry.value,
    modelValue: evaluation.byName.get(entry.name)?.value ?? null,
    drivenBy: [...(evaluation.byName.get(entry.name)?.deps ?? [])],
  }));
}

/** Every scalar block parameter of the model in diagram order, then the global parameters. */
export function listParameters(doc: Model, index: CatalogIndex | null): ParameterInfo[] {
  const out: ParameterInfo[] = [];
  const evaluation = globalEvaluation(doc);
  walk(doc.diagram, "", (path, node) => {
    for (const decl of nodeDecls(node, index)) {
      out.push(infoFor(path, node, decl, evaluation));
    }
  });
  out.push(...globalInfos(doc));
  return out;
}

/**
 * The parameter `target` (`<instance path>/<param>` or `global:<name>`), or null when the
 * model has none.
 */
export function findParameter(
  doc: Model,
  index: CatalogIndex | null,
  target: string,
): ParameterInfo | null {
  if (isGlobalTarget(target)) {
    return globalInfos(doc).find((info) => info.target === target) ?? null;
  }
  const parts = target.split("/");
  const name = parts.pop();
  if (name === undefined || parts.length === 0) {
    return null;
  }
  let diagram: ModelDiagram | null = doc.diagram;
  let node: ModelNode | undefined;
  for (const [position, segment] of parts.entries()) {
    if (diagram === null) {
      return null;
    }
    node = diagram.nodes.find((entry) => entry.name === segment);
    if (node === undefined) {
      return null;
    }
    diagram =
      position < parts.length - 1 && "subsystem" in node.block
        ? node.block.subsystem.diagram
        : null;
  }
  if (node === undefined) {
    return null;
  }
  const decl = nodeDecls(node, index).find((entry) => entry.name === name);
  return decl === undefined ? null : infoFor(parts.join("/"), node, decl, globalEvaluation(doc));
}

/** Which input kinds suit a parameter declaration. */
export function inputKindsFor(decl: ParameterDecl): DashboardCardKind[] {
  if (decl.type === "Bool") {
    return ["toggle", "number"];
  }
  if (decl.options !== null && decl.options.length > 0) {
    return ["select", "number"];
  }
  return ["slider", "knob", "number"];
}

// ------------------------------------------------------------- input values

export interface InputRange {
  min: number;
  max: number;
  step: number;
}

/** Slider/knob range: the card options, else the declaration, else around the model value. */
export function inputRange(card: ModelDashboardCard, info: ParameterInfo | null): InputRange {
  const decl = info?.decl;
  const base = info?.modelValue ?? 1;
  let min = card.options?.min ?? decl?.min ?? null;
  let max = card.options?.max ?? decl?.max ?? null;
  if (min === null && max === null) {
    const span = Math.abs(base) > 0 ? Math.abs(base) * 2 : 1;
    min = base >= 0 ? 0 : base - span;
    max = base >= 0 ? base + span : base + span;
  } else if (min === null) {
    min = max! > 0 ? 0 : max! - Math.max(1, Math.abs(max!));
  } else if (max === null) {
    max = min + Math.max(1, Math.abs(min) * 2, Math.abs(base) * 2);
  }
  if (!(max! > min)) {
    max = min + 1;
  }
  const step = card.options?.step ?? niceStep((max! - min) / 200);
  return { min, max: max!, step };
}

/** A 1/2/5 step not larger than `raw`. */
export function niceStep(raw: number): number {
  if (!(raw > 0) || !Number.isFinite(raw)) {
    return 1;
  }
  const power = 10 ** Math.floor(Math.log10(raw));
  const unit = raw / power;
  const nice = unit >= 5 ? 5 : unit >= 2 ? 2 : 1;
  return nice * power;
}

export function clampToRange(value: number, range: InputRange): number {
  return Math.min(range.max, Math.max(range.min, value));
}

/** Snap to the range's step grid (from min), avoiding float dust. */
export function snapToStep(value: number, range: InputRange): number {
  const steps = Math.round((value - range.min) / range.step);
  const snapped = range.min + steps * range.step;
  const decimals = Math.max(0, -Math.floor(Math.log10(range.step)) + 1);
  return clampToRange(Number(snapped.toFixed(Math.min(12, decimals))), range);
}

/** The value an input card shows: its override, else the model's value. */
export function effectiveInputValue(
  card: ModelDashboardCard,
  info: ParameterInfo | null,
): number | boolean | null {
  if (card.value !== undefined) {
    return card.value;
  }
  if (info === null || info.modelValue === null) {
    return null;
  }
  return info.decl.type === "Bool" ? info.modelValue !== 0 : info.modelValue;
}

// ---------------------------------------------------------------- validation

export interface DashboardIssue {
  cardId: string;
  message: string;
}

/** Every parameter a card binds: an input card's parameter, a schedule's columns. */
export function boundParameters(card: ModelDashboardCard): string[] {
  if (isInputKind(card.kind)) {
    return card.parameter === undefined ? [] : [card.parameter];
  }
  if (card.kind === "schedule") {
    return [...(card.schedule?.parameters ?? [])];
  }
  return [];
}

/** A parameter bound by more than one input card or schedule column. */
export function bindingConflicts(dashboard: ModelDashboard | undefined): DashboardIssue[] {
  const owners = new Map<string, string[]>();
  for (const card of dashboard?.cards ?? []) {
    const seen = new Set<string>();
    for (const target of boundParameters(card)) {
      if (seen.has(target)) {
        continue;
      }
      seen.add(target);
      owners.set(target, [...(owners.get(target) ?? []), card.id]);
    }
  }
  const issues: DashboardIssue[] = [];
  const titles = new Map((dashboard?.cards ?? []).map((card) => [card.id, cardTitle(card)]));
  for (const [target, cards] of owners) {
    if (cards.length < 2) {
      continue;
    }
    const names = cards.map((id) => `"${titles.get(id) ?? id}"`).join(" and ");
    for (const id of cards) {
      issues.push({
        cardId: id,
        message: `${target} is bound by ${names}; a parameter can have one input card or schedule column.`,
      });
    }
  }
  return issues;
}

export interface ScheduleCellIssue {
  row: number;
  /** -1 for the t column. */
  column: number;
  message: string;
}

/** Problems of a schedule table: t range, duplicate t, empty cells, duplicate columns. */
export function scheduleIssues(
  schedule: ModelDashboardSchedule,
  range: { t_start: number; t_end: number },
): ScheduleCellIssue[] {
  const issues: ScheduleCellIssue[] = [];
  const seen = new Map<number, number>();
  const columns = new Set<string>();
  schedule.parameters.forEach((target, column) => {
    if (columns.has(target)) {
      issues.push({ row: -1, column, message: `${target} is already a column.` });
    }
    if (isGlobalTarget(target)) {
      issues.push({
        row: -1,
        column,
        message: `${target} is a global parameter: globals are fixed for a run and cannot be scheduled.`,
      });
    }
    columns.add(target);
  });
  schedule.rows.forEach((row, index) => {
    if (!Number.isFinite(row.t)) {
      issues.push({ row: index, column: -1, message: "t must be a number." });
    } else if (row.t < range.t_start || row.t > range.t_end) {
      issues.push({
        row: index,
        column: -1,
        message: `t = ${row.t} s is outside the run [${range.t_start}, ${range.t_end}] s.`,
      });
    } else if (seen.has(row.t)) {
      issues.push({
        row: index,
        column: -1,
        message: `t = ${row.t} s is already row ${seen.get(row.t)! + 1}.`,
      });
    } else {
      seen.set(row.t, index);
    }
    schedule.parameters.forEach((target, column) => {
      const value = row.values[column];
      if (value === null || value === undefined || !Number.isFinite(value)) {
        issues.push({ row: index, column, message: `Enter a value for ${target}.` });
      }
    });
  });
  return issues;
}

/** Rows sorted by t (a stable sort keeps equal times in order). */
export function sortScheduleRows(schedule: ModelDashboardSchedule): ModelDashboardSchedule {
  const rows = [...schedule.rows].sort((a, b) => a.t - b.t);
  return { ...schedule, rows };
}

// ---------------------------------------------------------------- run inputs

export interface DashboardRunInputs {
  parameterOverrides: ParameterOverride[];
  parameterSchedule: ParameterStep[];
  /** Problems that make the inputs unusable; a run is refused while there are any. */
  issues: DashboardIssue[];
}

/**
 * What the dashboard asks of the next run: each input card with a value is an override of its
 * parameter; each schedule row gives one step per column. Problems (a parameter bound twice,
 * an unknown parameter, a bad schedule cell) are returned instead of being dropped silently.
 */
export function dashboardRunInputs(
  doc: Model,
  index: CatalogIndex | null,
): DashboardRunInputs {
  const dashboard = doc.dashboard;
  const parameterOverrides: ParameterOverride[] = [];
  const parameterSchedule: ParameterStep[] = [];
  const issues: DashboardIssue[] = [...bindingConflicts(dashboard)];
  // Globals need no catalog; block parameters are checked once the catalog is loaded.
  const known = (target: string): boolean =>
    isGlobalTarget(target)
      ? findParameter(doc, index, target) !== null
      : index === null || findParameter(doc, index, target) !== null;
  for (const card of dashboard?.cards ?? []) {
    const title = cardTitle(card);
    if (isInputKind(card.kind)) {
      if (card.parameter === undefined || card.value === undefined) {
        continue;
      }
      const global = isGlobalTarget(card.parameter);
      if (!known(card.parameter)) {
        const what = global
          ? `global parameter ${card.parameter.slice(GLOBAL_TARGET_PREFIX.length)}`
          : `block parameter ${card.parameter}`;
        issues.push({
          cardId: card.id,
          message: `"${title}": the model has no ${what}. Rebind or remove the card.`,
        });
        continue;
      }
      const info = global || index !== null ? findParameter(doc, index, card.parameter) : null;
      const value = typedValue(card.value, info);
      if (global) {
        // A global is a Real folded at compile time: a number, applied before static evaluation.
        parameterOverrides.push({
          target: card.parameter,
          kind: "global",
          value: typeof value === "boolean" ? (value ? 1 : 0) : value,
        });
      } else {
        parameterOverrides.push({ target: card.parameter, value });
      }
    } else if (card.kind === "schedule" && card.schedule !== undefined) {
      const schedule = card.schedule;
      if (schedule.parameters.length === 0 || schedule.rows.length === 0) {
        continue;
      }
      const cellIssues = scheduleIssues(schedule, doc.settings);
      if (cellIssues.length > 0) {
        issues.push({ cardId: card.id, message: `"${title}": ${cellIssues[0]!.message}` });
        continue;
      }
      const unknown = schedule.parameters.filter((target) => !known(target));
      if (unknown.length > 0) {
        issues.push({
          cardId: card.id,
          message: `"${title}": the model has no block parameter ${unknown.join(", ")}.`,
        });
        continue;
      }
      for (const row of sortScheduleRows(schedule).rows) {
        schedule.parameters.forEach((target, column) => {
          parameterSchedule.push({ t: row.t, target, value: row.values[column] as number });
        });
      }
    }
  }
  return { parameterOverrides, parameterSchedule, issues };
}

/** An input value in the parameter's own type: Bool as a boolean, Int rounded. */
export function typedValue(value: number | boolean, info: ParameterInfo | null): number | boolean {
  const type = info?.decl.type;
  if (type === "Bool") {
    return typeof value === "boolean" ? value : value !== 0;
  }
  const number = typeof value === "boolean" ? (value ? 1 : 0) : value;
  return type === "Int" ? Math.round(number) : number;
}

/** The override (or schedule) a dashboard puts on one parameter, for the inspector badge. */
export function dashboardOverrideOf(
  dashboard: ModelDashboard | undefined,
  target: string,
): { kind: "value"; value: number | boolean } | { kind: "schedule"; rows: number } | null {
  for (const card of dashboard?.cards ?? []) {
    if (isInputKind(card.kind) && card.parameter === target && card.value !== undefined) {
      return { kind: "value", value: card.value };
    }
    if (card.kind === "schedule" && card.schedule?.parameters.includes(target) === true) {
      return { kind: "schedule", rows: card.schedule.rows.length };
    }
  }
  return null;
}

/** Display signals of every card, for the run store's data subscription. */
export function dashboardSignalIds(dashboard: ModelDashboard | undefined): string[] {
  const out: string[] = [];
  for (const card of dashboard?.cards ?? []) {
    if (isDisplayKind(card.kind)) {
      out.push(...(card.signals ?? []));
    }
  }
  return [...new Set(out)];
}

// ----------------------------------------------------------- value at a time

/**
 * The value of a recorded series at `t`: linear between samples (sample-and-hold for Bool/Int
 * signals), the right limit at an event instant (two rows with the same t), the last value when
 * `t` is null (live: the latest row) or past the end, and null before the first sample.
 */
export function valueAt(
  time: ArrayLike<number>,
  values: ArrayLike<number> | undefined,
  t: number | null,
  hold = false,
): number | null {
  const n = Math.min(time.length, values?.length ?? 0);
  if (values === undefined || n === 0) {
    return null;
  }
  if (t === null || t >= (time[n - 1] ?? Infinity)) {
    for (let k = n - 1; k >= 0; k -= 1) {
      const v = values[k]!;
      if (Number.isFinite(v)) return v;
    }
    return null;
  }
  if (t < time[0]!) {
    return null;
  }
  // The last index with time <= t.
  let lo = 0;
  let hi = n - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (time[mid]! <= t) lo = mid;
    else hi = mid - 1;
  }
  const v0 = values[lo]!;
  const t0 = time[lo]!;
  if (hold || t0 === t || lo + 1 >= n) {
    return Number.isFinite(v0) ? v0 : null;
  }
  const t1 = time[lo + 1]!;
  const v1 = values[lo + 1]!;
  if (!(t1 > t0) || !Number.isFinite(v1) || !Number.isFinite(v0)) {
    return Number.isFinite(v0) ? v0 : null;
  }
  return v0 + ((v1 - v0) * (t - t0)) / (t1 - t0);
}

/** Format a card value with fixed decimals, or the plot's compact rule when unset. */
export function formatCardValue(
  value: number | null,
  decimals: number | undefined,
  fallback: (v: number) => string,
): string {
  if (value === null || !Number.isFinite(value)) {
    return "—";
  }
  return decimals === undefined ? fallback(value) : value.toFixed(decimals);
}

/** The zone a value falls in (the last matching zone wins). */
export function zoneOf(
  value: number | null,
  zones: ReadonlyArray<{ from: number; to: number; tone: string }> | undefined,
): string | null {
  if (value === null || zones === undefined) {
    return null;
  }
  let tone: string | null = null;
  for (const zone of zones) {
    const lo = Math.min(zone.from, zone.to);
    const hi = Math.max(zone.from, zone.to);
    if (value >= lo && value <= hi) {
      tone = zone.tone;
    }
  }
  return tone;
}

/** Fraction of `value` within [min, max], clamped to [0, 1]. */
export function fractionOf(value: number | null, min: number, max: number): number {
  if (value === null || !Number.isFinite(value) || !(max > min)) {
    return 0;
  }
  return Math.min(1, Math.max(0, (value - min) / (max - min)));
}
