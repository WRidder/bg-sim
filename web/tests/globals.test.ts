/**
 * Global parameters (spec "Global parameters"): the browser mirror of the
 * compiler's static evaluation, whole-identifier renaming, the "used by" and
 * Equations queries, and the document-store commands with undo.
 */

import { beforeEach, describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import fixtureJson from "../../contracts/fixtures/model/valid/model.global-parameters.json";
import type { Catalog, CatalogBlock } from "../src/contracts/catalog";
import type { Model, ModelGlobalParameter, ModelNode } from "../src/contracts/model";
import {
  drivenFields,
  evaluateField,
  evaluateGlobals,
  formatValue,
  globalNameIssue,
  globalUsages,
} from "../src/globals/globals";
import {
  evaluateExpression,
  identifierSpans,
  isPlainLiteral,
  parseExpression,
  renameIdentifier,
  stripEquationPrefix,
} from "../src/inspector/expression";
import { parameterIssue, startIssue } from "../src/inspector/validation";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel, createNodeFromBlock } from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;

function block(name: string): CatalogBlock {
  const entry = catalog.blocks.find((candidate) => candidate.name === name);
  if (entry === undefined) {
    throw new Error(`no block ${name}`);
  }
  return entry;
}

function g(name: string, value: string): ModelGlobalParameter {
  return { name, value };
}

function values(globals: ModelGlobalParameter[]): Record<string, number | null> {
  const evaluation = evaluateGlobals(globals);
  return Object.fromEntries(evaluation.rows.map((row) => [row.name, row.value]));
}

describe("expression helpers", () => {
  it("evaluates with named values, functions, comparisons and ifelse", () => {
    const env = new Map([
      ["m", 2],
      ["k", 8],
    ]);
    const run = (text: string) => {
      const parsed = parseExpression(text);
      if (!parsed.ok) {
        throw new Error(parsed.message);
      }
      return evaluateExpression(parsed.ast, env);
    };
    expect(run("sqrt(k/m)")).toEqual({ ok: true, value: 2 });
    expect(run("ifelse(m > 1, 10, 20)")).toEqual({ ok: true, value: 10 });
    expect(run("max(m, 3) ^ 2")).toEqual({ ok: true, value: 9 });
    expect(run("2*pi")).toEqual({ ok: true, value: 2 * Math.PI });
    expect(run("mass + 1")).toMatchObject({ ok: false, name: "mass" });
    expect(run("1/0")).toMatchObject({ ok: false });
    expect(run("sqrt(-1)")).toMatchObject({ ok: false });
    expect(run("ddt(m)")).toMatchObject({ ok: false });
  });

  it("finds identifiers with positions and renames whole identifiers only", () => {
    expect(identifierSpans("1e-3*k + k2 - sqrt(k) + a.k").map((span) => span.name)).toEqual([
      "k",
      "k2",
      "sqrt",
      "k",
    ]);
    expect(renameIdentifier("k + k2 + 2*k + sqrt(k) - 1e-3", "k", "stiffness")).toBe(
      "stiffness + k2 + 2*stiffness + sqrt(stiffness) - 1e-3",
    );
    // `e` inside a number is not the global `e`; a function name is not a value.
    expect(renameIdentifier("2e3 + e", "e", "eps")).toBe("2e3 + eps");
    expect(renameIdentifier("sin(1) + sin", "sin", "s")).toBe("sin(1) + s");
  });

  it("tells plain values from equations and strips the = prefix", () => {
    expect(isPlainLiteral("2.5")).toBe(true);
    expect(isPlainLiteral(" -1e-3 ")).toBe(true);
    expect(isPlainLiteral("true")).toBe(true);
    expect(isPlainLiteral("2*3")).toBe(false);
    expect(isPlainLiteral("k")).toBe(false);
    expect(stripEquationPrefix("= 4*m")).toBe("4*m");
    expect(stripEquationPrefix("==")).toBe("==");
    expect(stripEquationPrefix(" 3 ")).toBe("3");
  });
});

describe("evaluateGlobals", () => {
  it("folds chains in dependency order regardless of the table order", () => {
    const evaluation = evaluateGlobals([g("k", "4*m"), g("w", "sqrt(k/m)"), g("m", "2")]);
    expect(evaluation.order).toEqual(["m", "k", "w"]);
    expect(values([g("k", "4*m"), g("w", "sqrt(k/m)"), g("m", "2")])).toEqual({
      k: 8,
      w: 2,
      m: 2,
    });
  });

  it("reports a cycle on every member with its path, and dependents of broken globals", () => {
    const evaluation = evaluateGlobals([
      g("a", "b + 1"),
      g("b", "2*a"),
      g("c", "a + 1"),
      g("d", "5"),
    ]);
    expect(evaluation.byName.get("a")?.error).toBe("Cycle: a → b → a.");
    expect(evaluation.byName.get("b")?.error).toBe("Cycle: b → a → b.");
    expect(evaluation.byName.get("c")?.error).toBe("Depends on a cycle.");
    expect(evaluation.byName.get("d")?.value).toBe(5);
    expect(evaluateGlobals([g("x", "x + 1")]).byName.get("x")?.error).toBe("Cycle: x → x.");
  });

  it("reports undeclared names, syntax, duplicates, reserved names and non-finite values", () => {
    const evaluation = evaluateGlobals([
      g("k", "4*mass"),
      g("s", "2 +"),
      g("m", "1"),
      g("m", "2"),
      g("t", "1"),
      g("sin", "1"),
      g("z", "1e308*10"),
      g("u", "k + 1"),
    ]);
    expect(evaluation.rows[0]?.error).toBe('"mass" is not a global parameter.');
    expect(evaluation.rows[1]?.error).toBe("The expression is incomplete.");
    expect(evaluation.rows[2]?.value).toBe(1);
    expect(evaluation.rows[3]?.error).toBe("Declared twice.");
    expect(evaluation.rows[4]?.error).toBe('"t" is reserved.');
    expect(evaluation.rows[5]?.error).toBe('"sin" is a built-in function.');
    expect(evaluation.rows[6]?.error).toContain("not finite");
    expect(evaluation.rows[7]?.error).toBe('Uses "k", which has an error.');
    expect(evaluation.values.has("k")).toBe(false);
  });

  it("checks new names", () => {
    const globals = [g("m", "1")];
    expect(globalNameIssue(globals, "m")).toContain("already exists");
    expect(globalNameIssue(globals, "m", "m")).toBeNull();
    expect(globalNameIssue(globals, "2k")).toContain("letter or underscore");
    expect(globalNameIssue(globals, "end")).toContain("reserved");
    expect(globalNameIssue(globals, "stiffness")).toBeNull();
  });

  it("formats values compactly", () => {
    expect(formatValue(8)).toBe("8");
    expect(formatValue(Math.SQRT2 + 0.5)).toBe("1.91421");
    expect(formatValue(1.5e-6)).toBe("1.5e-6");
    expect(formatValue(true)).toBe("true");
  });
});

describe("instance expressions", () => {
  const doc = fixtureJson as unknown as Model;
  const evaluation = evaluateGlobals(doc.parameters ?? []);

  it("finds driven fields at every level and who uses a global", () => {
    const driven = drivenFields(doc).map((field) => `${field.instancePath.join("/")}.${field.key}`);
    expect(driven).toEqual(["Source/Rate.value", "Int1.x"]);
    const users = globalUsages(doc, "rate");
    expect(users).toHaveLength(1);
    expect(users[0]).toMatchObject({ diagramPath: ["n1"], nodeId: "s1", kind: "param", key: "value" });
    expect(globalUsages(doc, "m")).toHaveLength(0);
  });

  it("evaluates a field with the globals and validates bounds on the evaluated value", () => {
    expect(evaluateField("rate / 2", evaluation)).toEqual({ driven: true, value: 4, error: null });
    expect(evaluateField("3", evaluation)).toEqual({ driven: false, value: 3, error: null });
    expect(evaluateField("nope", evaluation).error).toContain("declare it as a global parameter");
    const spring = block("Spring").parameters.find((p) => p.name === "k");
    if (spring === undefined) {
      throw new Error("Spring has no k");
    }
    expect(parameterIssue("rate", spring, evaluation)).toBeNull();
    expect(parameterIssue("-rate", spring, evaluation)).toBe("Must be at least 0 N/m.");
    expect(parameterIssue("= rate", spring, evaluation)).toBeNull();
    expect(parameterIssue("stiff", spring, evaluation)).toContain("Unknown name");
    // Without the globals the old behaviour holds: a name is left to the worker.
    expect(parameterIssue("stiff", spring)).toBeNull();
    expect(startIssue("x0 + 1", evaluation)).toBeNull();
    expect(startIssue("y0", evaluation)).toContain("Unknown name");
  });
});

describe("document store commands", () => {
  function openModel(): void {
    const doc = createEmptyModel("Globals");
    const spring: ModelNode = createNodeFromBlock(block("Spring"), { x: 0, y: 0 }, "n1", "Spring1");
    spring.params = { ...(spring.params ?? {}), k: "k" };
    const mass: ModelNode = createNodeFromBlock(block("Mass"), { x: 100, y: 0 }, "n2", "Mass1");
    mass.params = { ...(mass.params ?? {}), m: "m" };
    mass.starts = { x: "k/1000 + k2" };
    doc.diagram.nodes = [spring, mass];
    doc.parameters = [g("m", "2"), g("k", "4*m"), g("k2", "k + 1")];
    useDocumentStore.getState().openDocument("demo", "Globals", doc);
  }

  beforeEach(() => {
    resetDocumentStore();
    openModel();
  });

  const state = () => useDocumentStore.getState();
  const node = (id: string) => state().doc?.diagram.nodes.find((entry) => entry.id === id);

  it("adds, updates (with the = prefix) and reorders globals, each one undo step", () => {
    const added = state().addGlobalParameter();
    expect(added).toEqual({ ok: true, name: "p1" });
    expect(state().doc?.parameters?.map((entry) => entry.name)).toEqual(["m", "k", "k2", "p1"]);
    expect(state().updateGlobalParameter("p1", { value: "= m / 4", unit: "kg", description: "quarter" })).toEqual({ ok: true });
    expect(state().doc?.parameters?.[3]).toEqual({ name: "p1", value: "m / 4", unit: "kg", description: "quarter" });
    expect(state().updateGlobalParameter("p1", { value: "2 +" }).ok).toBe(false);
    expect(state().moveGlobalParameter("p1", 0)).toEqual({ ok: true });
    expect(state().doc?.parameters?.map((entry) => entry.name)).toEqual(["p1", "m", "k", "k2"]);
    state().undo();
    expect(state().doc?.parameters?.map((entry) => entry.name)).toEqual(["m", "k", "k2", "p1"]);
    state().undo();
    state().undo();
    expect(state().doc?.parameters?.map((entry) => entry.name)).toEqual(["m", "k", "k2"]);
  });

  it("renames a global and rewrites every reference as one undo step", () => {
    expect(state().renameGlobalParameter("k", "stiffness")).toMatchObject({ ok: true });
    expect(state().doc?.parameters?.map((entry) => `${entry.name}=${entry.value}`)).toEqual([
      "m=2",
      "stiffness=4*m",
      "k2=stiffness + 1",
    ]);
    expect(node("n1")?.params?.k).toBe("stiffness");
    // `k2` is a different identifier and stays.
    expect(node("n2")?.starts?.x).toBe("stiffness/1000 + k2");
    expect(state().renameGlobalParameter("stiffness", "m").ok).toBe(false);
    expect(state().renameGlobalParameter("stiffness", "sin").ok).toBe(false);
    state().undo();
    expect(state().doc?.parameters?.[1]?.name).toBe("k");
    expect(node("n1")?.params?.k).toBe("k");
    expect(node("n2")?.starts?.x).toBe("k/1000 + k2");
    state().redo();
    expect(node("n1")?.params?.k).toBe("stiffness");
  });

  it("renames references inside subsystems", () => {
    const doc = fixtureJson as unknown as Model;
    useDocumentStore.getState().openDocument("demo", "GlobalParameters", doc);
    expect(state().renameGlobalParameter("rate", "speed")).toMatchObject({ ok: true });
    const source = state().doc?.diagram.nodes[0];
    const inner =
      source !== undefined && "subsystem" in source.block
        ? source.block.subsystem.diagram.nodes[0]
        : undefined;
    expect(inner?.params?.value).toBe("speed");
  });

  it("refuses to delete a used global and lists its users; deletes an unused one", () => {
    const refused = state().deleteGlobalParameter("k");
    expect(refused.ok).toBe(false);
    expect(refused.error).toContain("Spring1.k");
    expect(refused.error).toContain("Mass1.x");
    expect(refused.error).toContain("global k2");
    state().setNodeParam("n1", "k", "1000");
    state().setNodeStart("n2", "x", null);
    expect(state().deleteGlobalParameter("k2")).toEqual({ ok: true });
    expect(state().deleteGlobalParameter("k")).toEqual({ ok: true });
    expect(state().doc?.parameters?.map((entry) => entry.name)).toEqual(["m"]);
    state().undo();
    expect(state().doc?.parameters?.map((entry) => entry.name)).toEqual(["m", "k"]);
  });

  it("edits any field by reference (the Equations view)", () => {
    expect(
      state().setFieldExpression({ diagramPath: [], nodeId: "n2", kind: "param", key: "m" }, "=2*m"),
    ).toEqual({ ok: true });
    expect(node("n2")?.params?.m).toBe("2*m");
    expect(
      state().setFieldExpression({ diagramPath: [], nodeId: "n2", kind: "start", key: "x" }, ""),
    ).toEqual({ ok: true });
    expect(node("n2")?.starts?.x).toBeUndefined();
    expect(
      state().setFieldExpression({ diagramPath: [], nodeId: "nX", kind: "param", key: "m" }, "1").ok,
    ).toBe(false);
  });
});
