/**
 * Field validation for the inspector.
 *
 * The catalog gives each parameter a unit, optional min/max, a type and (D11)
 * optional labels for an Int enumeration. These checks are deliberately local
 * and cheap: syntax and literal bounds. Resolving names, dimensions and
 * domain-dependent units is the worker's job, and its diagnostics are shown
 * next to the fields when they arrive (the `diagnostics` prop of Inspector).
 */

import type { ConstantDecl, ParameterDecl } from "../contracts/catalog";
import type { ModelConstantValue } from "../contracts/model";
import { evaluateLiteral, parseExpression } from "./expression";

export function textValue(value: ModelConstantValue): string {
  if (Array.isArray(value)) {
    return JSON.stringify(value);
  }
  return String(value);
}

function unitSuffix(unit: string | null): string {
  return unit === null || unit.length === 0 ? "" : ` ${unit}`;
}

function rangeIssue(value: number, decl: ParameterDecl): string | null {
  if (decl.min !== null && decl.max !== null && decl.min === decl.max) {
    if (value !== decl.min) {
      return `Must be ${decl.min}${unitSuffix(decl.unit)}.`;
    }
    return null;
  }
  if (decl.min !== null && value < decl.min) {
    return `Must be at least ${decl.min}${unitSuffix(decl.unit)}.`;
  }
  if (decl.max !== null && value > decl.max) {
    return `Must be at most ${decl.max}${unitSuffix(decl.unit)}.`;
  }
  return null;
}

/** The first problem with a parameter expression, or null when it looks valid. */
export function parameterIssue(value: string, decl: ParameterDecl): string | null {
  const text = value.trim();
  if (text.length === 0) {
    return "Enter a value.";
  }
  if (decl.type === "Bool") {
    return text === "true" || text === "false" ? null : "Use true or false.";
  }
  const parsed = parseExpression(text);
  if (!parsed.ok) {
    return parsed.message;
  }
  const number = evaluateLiteral(parsed.ast);
  if (number === null) {
    // A named expression: names and units are checked by the worker.
    return null;
  }
  if (!Number.isFinite(number)) {
    return "The value must be a finite number.";
  }
  if (decl.type === "Int" && !Number.isInteger(number)) {
    return "The value must be a whole number.";
  }
  if (decl.options !== null) {
    if (!Number.isInteger(number) || number < 1 || number > decl.options.length) {
      return `Choose a number from 1 to ${decl.options.length}.`;
    }
    return null;
  }
  return rangeIssue(number, decl);
}

/** Start-value overrides may be left empty, which removes the override. */
export function startIssue(value: string): string | null {
  const text = value.trim();
  if (text.length === 0) {
    return null;
  }
  const parsed = parseExpression(text);
  return parsed.ok ? null : parsed.message;
}

/** A constant's default rendered into its input. */
export function constantDefaultText(decl: ConstantDecl): string {
  return textValue(decl.default);
}

/** The first problem with a constant input, or null. Empty means "use default". */
export function constantIssue(value: string, decl: ConstantDecl): string | null {
  const text = value.trim();
  if (text.length === 0) {
    return null;
  }
  if (Array.isArray(decl.default)) {
    return arrayConstantIssue(text);
  }
  if (decl.type === "Bool") {
    return text === "true" || text === "false" ? null : "Use true or false.";
  }
  const parsed = parseExpression(text);
  if (!parsed.ok) {
    return parsed.message;
  }
  const number = evaluateLiteral(parsed.ast);
  if (number === null) {
    // A named constant expression; the worker resolves it.
    return null;
  }
  if (!Number.isFinite(number)) {
    return "The value must be a finite number.";
  }
  if (decl.type === "Int" && !Number.isInteger(number)) {
    return "The value must be a whole number.";
  }
  return null;
}

/** Vector and matrix constants are stored as JSON arrays (plan 3.3). */
export function arrayConstantIssue(value: string): string | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    return "Use a JSON array of numbers, for example [1, 2, 3].";
  }
  if (!Array.isArray(parsed)) {
    return "Use a JSON array of numbers, for example [1, 2, 3].";
  }
  if (!parsed.every((entry) => isNumber(entry) || (Array.isArray(entry) && entry.every(isNumber)))) {
    return "Every entry must be a number (or a row of numbers for a matrix).";
  }
  return null;
}

function isNumber(value: unknown): boolean {
  return typeof value === "number" && Number.isFinite(value);
}

/**
 * Turn the text of a constant input into the document value. An expression
 * that has a literal value is stored as a number; anything else stays a string
 * for the constant-folding pass (plan 5.2.4). Null removes the override.
 */
export function parseConstantInput(
  text: string,
  decl: ConstantDecl,
): { ok: true; value: ModelConstantValue | null } | { ok: false; message: string } {
  const trimmed = text.trim();
  if (trimmed.length === 0) {
    return { ok: true, value: null };
  }
  const issue = constantIssue(trimmed, decl);
  if (issue !== null) {
    return { ok: false, message: issue };
  }
  if (Array.isArray(decl.default)) {
    return { ok: true, value: JSON.parse(trimmed) as ModelConstantValue };
  }
  if (decl.type === "Bool") {
    return { ok: true, value: trimmed === "true" };
  }
  const parsed = parseExpression(trimmed);
  const literal = parsed.ok ? evaluateLiteral(parsed.ast) : null;
  if (literal !== null && Number.isFinite(literal)) {
    return { ok: true, value: literal };
  }
  return { ok: true, value: trimmed };
}
