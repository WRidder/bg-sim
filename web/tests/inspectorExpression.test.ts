/**
 * The inspector's constant-expression checks: syntax errors point at the
 * offending token, literal expressions are evaluated for catalog min/max, and
 * named expressions are accepted for the worker to resolve (plan 5.2.4).
 */

import { describe, expect, it } from "vitest";

import type { ConstantDecl, ParameterDecl } from "../src/contracts/catalog";
import {
  evaluateLiteral,
  literalValue,
  parseExpression,
  type ExpressionNode,
} from "../src/inspector/expression";
import {
  arrayConstantIssue,
  constantIssue,
  parameterIssue,
  parseConstantInput,
  startIssue,
} from "../src/inspector/validation";

function ast(source: string): ExpressionNode {
  const parsed = parseExpression(source);
  if (!parsed.ok) {
    throw new Error(`expected "${source}" to parse, got: ${parsed.message}`);
  }
  return parsed.ast;
}

function realDecl(overrides: Partial<ParameterDecl> = {}): ParameterDecl {
  return {
    name: "R",
    type: "Real",
    default: "2.0",
    unit: "Ohm",
    min: 0,
    max: null,
    tunable: false,
    description: "Winding resistance",
    options: null,
    ...overrides,
  };
}

function constantDecl(overrides: Partial<ConstantDecl> = {}): ConstantDecl {
  return {
    name: "N",
    type: "Int",
    default: 2,
    structural: true,
    ...overrides,
  };
}

describe("expression syntax", () => {
  it("parses numbers, names, arithmetic, calls and comparisons", () => {
    expect(parseExpression("2.0").ok).toBe(true);
    expect(parseExpression("5e-4").ok).toBe(true);
    expect(parseExpression("1 + 2 * (3 - 4) / 5").ok).toBe(true);
    expect(parseExpression("2^3^2").ok).toBe(true);
    expect(parseExpression("2^-3").ok).toBe(true);
    expect(parseExpression("ifelse(t >= 1.0, final, initial)").ok).toBe(true);
    expect(parseExpression("2*R && N > 1").ok).toBe(true);
    expect(parseExpression("pi").ok).toBe(true);
  });

  it("evaluates only pure literals", () => {
    expect(literalValue("1 + 2 * 3")).toBe(7);
    expect(literalValue("(1 + 2) / 3")).toBe(1);
    expect(literalValue("-2^2")).toBe(-4);
    expect(literalValue("2^3^2")).toBe(512);
    expect(literalValue("2^-2")).toBe(0.25);
    expect(literalValue("pi")).toBeCloseTo(Math.PI, 12);
    expect(literalValue("2 * R")).toBeNull();
    expect(literalValue("ifelse(1 < 2, 3, 4)")).toBeNull();
    expect(evaluateLiteral(ast("4 / 2"))).toBe(2);
  });

  it("reports equations and malformed expressions with an actionable message", () => {
    const equation = parseExpression("R = 2");
    expect(equation.ok).toBe(false);
    if (!equation.ok) {
      expect(equation.message).toContain("not an equation");
    }

    const tilde = parseExpression("p.e ~ R");
    expect(tilde.ok).toBe(false);
    if (!tilde.ok) {
      expect(tilde.message).toContain("not an equation");
    }

    const incomplete = parseExpression("2 +");
    expect(incomplete.ok).toBe(false);
    if (!incomplete.ok) {
      expect(incomplete.message).toBe("The expression is incomplete.");
    }

    const doubleStar = parseExpression("2 ** 3");
    expect(doubleStar.ok).toBe(false);
    if (!doubleStar.ok) {
      expect(doubleStar.message).toContain("Expected a number");
    }

    const call = parseExpression("ifelse(1, 2");
    expect(call.ok).toBe(false);
    if (!call.ok) {
      expect(call.message).toContain("missing its closing");
    }

    const character = parseExpression("2 @ 3");
    expect(character.ok).toBe(false);
    if (!character.ok) {
      expect(character.message).toContain('Unexpected character "@"');
    }

    const empty = parseExpression("   ");
    expect(empty.ok).toBe(false);
    if (!empty.ok) {
      expect(empty.message).toBe("Enter a value.");
    }
  });
});

describe("parameter validation", () => {
  it("refuses values below the minimum and above the maximum", () => {
    expect(parameterIssue("-1", realDecl())).toBe("Must be at least 0 Ohm.");
    expect(parameterIssue("0", realDecl())).toBeNull();
    expect(parameterIssue("4", realDecl({ max: 3 }))).toBe("Must be at most 3 Ohm.");
    expect(parameterIssue("3", realDecl({ max: 3 }))).toBeNull();
    expect(parameterIssue("5", realDecl({ min: 5, max: 5 }))).toBeNull();
    expect(parameterIssue("4", realDecl({ min: 5, max: 5 }))).toBe("Must be 5 Ohm.");
    expect(parameterIssue("-5", realDecl({ min: null }))).toBeNull();
  });

  it("skips literal bounds for named expressions but still checks syntax", () => {
    expect(parameterIssue("2*R", realDecl())).toBeNull();
    expect(parameterIssue("2*R +", realDecl())).toBe("The expression is incomplete.");
  });

  it("checks integers, booleans, finite numbers and enumerations", () => {
    expect(parameterIssue("2.5", realDecl({ type: "Int", unit: null }))).toBe(
      "The value must be a whole number.",
    );
    expect(parameterIssue("2", realDecl({ type: "Int", unit: null }))).toBeNull();
    expect(parameterIssue("true", realDecl({ type: "Bool", unit: null }))).toBeNull();
    expect(parameterIssue("yes", realDecl({ type: "Bool", unit: null }))).toBe(
      "Use true or false.",
    );
    expect(parameterIssue("1/0", realDecl())).toBe("The value must be a finite number.");
    expect(
      parameterIssue("2", realDecl({ type: "Int", unit: null, options: ["hold", "linear"] })),
    ).toBeNull();
    expect(
      parameterIssue("3", realDecl({ type: "Int", unit: null, options: ["hold", "linear"] })),
    ).toBe("Choose a number from 1 to 2.");
    expect(parameterIssue("", realDecl())).toBe("Enter a value.");
  });

  it("treats empty start values as 'use the declared start'", () => {
    expect(startIssue("")).toBeNull();
    expect(startIssue("0.0")).toBeNull();
    expect(startIssue("2*pi")).toBeNull();
    expect(startIssue("1 +")).toBe("The expression is incomplete.");
  });
});

describe("constant validation", () => {
  it("validates whole numbers and named constant expressions", () => {
    expect(constantIssue("", constantDecl())).toBeNull();
    expect(constantIssue("3", constantDecl())).toBeNull();
    expect(constantIssue("2.5", constantDecl())).toBe("The value must be a whole number.");
    expect(constantIssue("N + 1", constantDecl())).toBeNull();
    expect(constantIssue("true", constantDecl({ type: "Bool", default: false }))).toBeNull();
    expect(constantIssue("yes", constantDecl({ type: "Bool", default: false }))).toBe(
      "Use true or false.",
    );
  });

  it("validates vector and matrix constants as JSON arrays", () => {
    expect(arrayConstantIssue("[1, 2, 3]")).toBeNull();
    expect(arrayConstantIssue("[[1, 2], [3, 4]]")).toBeNull();
    expect(arrayConstantIssue("[]")).toBeNull();
    expect(arrayConstantIssue("[1, 2")).toContain("JSON array");
    expect(arrayConstantIssue('["a"]')).toContain("Every entry must be a number");
    expect(arrayConstantIssue("3")).toContain("JSON array");
  });

  it("turns an input into the document's constant value", () => {
    expect(parseConstantInput("", constantDecl())).toEqual({ ok: true, value: null });
    expect(parseConstantInput("3", constantDecl())).toEqual({ ok: true, value: 3 });
    expect(parseConstantInput("2*N", constantDecl())).toEqual({ ok: true, value: "2*N" });
    expect(parseConstantInput("2.5", constantDecl())).toMatchObject({ ok: false });
    expect(
      parseConstantInput("[1, 2]", constantDecl({ default: [1, 2] })),
    ).toEqual({ ok: true, value: [1, 2] });
    expect(
      parseConstantInput("true", constantDecl({ type: "Bool", default: false })),
    ).toEqual({ ok: true, value: true });
    expect(
      parseConstantInput("1e-3", constantDecl({ type: "Real", default: 1, structural: false })),
    ).toEqual({ ok: true, value: 0.001 });
  });
});
