/**
 * W2.1 autocomplete (plan 7.7): the whitelist functions, the names declared in
 * the block, the power-port fields and unit strings. The mirror lists are
 * checked against the Julia source, because the parser is the authority.
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { CompletionContext } from "@codemirror/autocomplete";
import { EditorState } from "@codemirror/state";
import { describe, expect, it } from "vitest";

import {
  UNITS,
  WHITELIST_FUNCTIONS,
  blockCompletionSource,
  outlineNames,
  parseBlockOutline,
  unitSpanAt,
} from "../src/code/completion";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..", "..");

function juliaSource(relative: string): string {
  return readFileSync(path.join(repoRoot, relative), "utf8");
}

const SOURCE = `@block Controller begin
    @constants N = 3
    @parameters kp::Real = 2.0, [description = "gain"]
    @inputs u::Real, w::Real
    @outputs y::Real
    @ports p::Generic, q::Generic
    @variables x::Real, e::Real
    @equations y ~ kp * u + x
end
`;

function complete(text: string, explicit = false) {
  const state = EditorState.create({ doc: text });
  const context = new CompletionContext(state, text.length, explicit);
  return blockCompletionSource(context);
}

function labels(result: Awaited<ReturnType<typeof blockCompletionSource>>): string[] {
  if (result === null) {
    return [];
  }
  return result.options.map((option) => (typeof option === "string" ? option : option.label));
}

describe("block outline", () => {
  it("reads the block name, declarations and power ports", () => {
    const outline = parseBlockOutline(SOURCE);
    expect(outline.name).toBe("Controller");
    expect(outline.declarations["@constants"]).toEqual(["N"]);
    expect(outline.declarations["@parameters"]).toEqual(["kp"]);
    expect(outline.declarations["@inputs"]).toEqual(["u", "w"]);
    expect(outline.declarations["@outputs"]).toEqual(["y"]);
    expect(outline.declarations["@variables"]).toEqual(["x", "e"]);
    expect(outline.ports).toEqual(["p", "q"]);
  });

  it("lists every declared name once, in scope order", () => {
    expect(outlineNames(parseBlockOutline(SOURCE))).toEqual([
      "N",
      "kp",
      "u",
      "w",
      "y",
      "p",
      "q",
      "x",
      "e",
    ]);
  });

  it("ignores comments and attribute segments", () => {
    const outline = parseBlockOutline(`@block B begin
    @parameters k::Real = 1.0, [description = "a, b"] # k is the gain
    # @inputs ignored::Real
    @inputs value::Real
end
`);
    expect(outline.declarations["@parameters"]).toEqual(["k"]);
    expect(outline.declarations["@inputs"]).toEqual(["value"]);
  });
});

describe("unit completion", () => {
  it("detects the string after unit = and replaces the prefix", () => {
    const text = '    @parameters c::Real = 1.0, [unit = "m/s';
    expect(unitSpanAt(text, text.length)).toEqual({
      from: text.length - "m/s".length,
      to: text.length,
    });
  });

  it("offers unit names inside the string only", () => {
    const inside = 'k::Real = 1.0, [unit = "';
    const result = complete(inside);
    expect(labels(result)).toEqual(expect.arrayContaining(["V", "N", "m"]));
    expect(labels(result)).not.toContain("sin");

    const outside = "y ~ u";
    expect(labels(complete(outside))).not.toContain("V");
  });
});

describe("name and function completion", () => {
  it("offers whitelist functions and declared names", () => {
    const result = complete(SOURCE, true);
    const names = labels(result);
    expect(names).toEqual(expect.arrayContaining(["kp"]));
    expect(names).toEqual(expect.arrayContaining(["sin", "sqrt", "interp1"]));
    expect(names).toEqual(expect.arrayContaining(["u", "w", "y", "x", "e", "t", "Ts"]));
  });

  it("filters function and name completions by the typed prefix", () => {
    const result = complete(`${SOURCE}    sq`);
    const names = labels(result);
    expect(names).toEqual(["sqrt"]);
  });

  it("offers the fields of each declared power port", () => {
    const result = complete(`${SOURCE}    p.`);
    const names = labels(result);
    expect(names).toEqual(["e", "f"]);
  });

  it("returns nothing for ordinary code without a word or an explicit request", () => {
    expect(complete("y ~ kp * u + 1 ")).toBeNull();
  });

  it("explains that the function whitelist mirrors the Julia table", () => {
    const source = juliaSource("julia/BGSim/src/syntax/whitelist.jl");
    const julia = new Set<string>();
    for (const match of source.matchAll(/FunctionRule\(\s*\[([^\]]*)\]/g)) {
      for (const name of (match[1] ?? "").split(",")) {
        const symbol = name.trim().replace(/^:/, "");
        if (symbol.length > 0) {
          julia.add(symbol);
        }
      }
    }
    const ours = new Set(WHITELIST_FUNCTIONS.filter((name) => name !== "ifelse"));
    expect([...ours].sort()).toEqual([...julia].sort());
  });

  it("explains that the unit list mirrors UNIT_TABLE", () => {
    const source = juliaSource("julia/BGSim/src/units/dims.jl");
    const start = source.indexOf("const UNIT_TABLE");
    const end = source.indexOf("const DISPLAY_UNITS", start);
    expect(start).toBeGreaterThan(0);
    expect(end).toBeGreaterThan(start);
    const table = source.slice(start, end);
    const julia = new Set<string>();
    for (const match of table.matchAll(/^\s*"([^"]+)"\s*=>/gm)) {
      if (match[1] !== undefined) {
        julia.add(match[1]);
      }
    }
    expect([...new Set(UNITS)].sort()).toEqual([...julia].sort());
  });
});
