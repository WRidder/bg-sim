/**
 * Autocomplete for the block source (plan 7.7):
 *
 * * the whitelisted functions (`julia/BGSim/src/syntax/whitelist.jl` is the
 *   source of truth; this list mirrors it and is checked by a test);
 * * the names declared in the current block (`@block`, `@constants`,
 *   `@parameters`, `@variables`, `@inputs`, `@outputs`, `@ports`);
 * * the field names of each declared power port (`p.e`, `p.f`);
 * * unit strings inside `unit = "..."` (`UNIT_TABLE` in
 *   `julia/BGSim/src/units/dims.jl`).
 *
 * The outline parser is deliberately line-based: a block is a flat sequence
 * of scope macros, and completion must stay cheap enough to run on every
 * keystroke without waiting for a syntax tree.
 */

import type { Completion, CompletionContext, CompletionResult } from "@codemirror/autocomplete";

/** The scope macros of the language (spec section 2). */
export const SCOPE_MACROS = [
  "@block",
  "@constants",
  "@parameters",
  "@inputs",
  "@outputs",
  "@ports",
  "@variables",
  "@initial",
  "@equations",
  "@discrete",
  "@events",
  "@components",
  "@connections",
  "@causality",
] as const;

export type ScopeMacro = (typeof SCOPE_MACROS)[number];

/** The built-in function names of the whitelist table. */
export const WHITELIST_FUNCTIONS = [
  "sin",
  "cos",
  "tan",
  "asin",
  "acos",
  "atan",
  "sinh",
  "cosh",
  "tanh",
  "exp",
  "log",
  "log10",
  "sqrt",
  "abs",
  "sign",
  "min",
  "max",
  "clamp",
  "floor",
  "ceil",
  "round",
  "mod",
  "rem",
  "hypot",
  "dot",
  "norm",
  "cross",
  "transpose",
  "ddt",
  "int",
  "deadzone",
  "saturate",
  "delay",
  "previous",
  "hold",
  "interp1",
  "interp2",
  "noise_normal",
  "reinit",
  "ifelse",
] as const;

/** The accepted unit spellings of the dimension table (`UNIT_TABLE`). */
export const UNITS = [
  "1",
  "m",
  "kg",
  "s",
  "A",
  "K",
  "mol",
  "cd",
  "g",
  "mm",
  "cm",
  "min",
  "h",
  "N",
  "J",
  "W",
  "V",
  "Ohm",
  "Ω",
  "F",
  "H",
  "Pa",
  "bar",
  "Hz",
  "rpm",
  "rad",
  "deg",
  "°",
  "L",
  "effort",
  "flow",
] as const;

/** The declaration scopes whose names are usable as identifiers. */
const DECLARATION_SCOPES: readonly ScopeMacro[] = [
  "@constants",
  "@parameters",
  "@inputs",
  "@outputs",
  "@ports",
  "@variables",
];

export interface BlockOutline {
  name: string | null;
  /** Declared names per scope, in source order and without duplicates. */
  declarations: Partial<Record<ScopeMacro, string[]>>;
  /** Power ports, whose `e`/`f` fields are offered. */
  ports: string[];
}

const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/;

function stripComment(text: string): string {
  let inString = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === '"') {
      inString = !inString;
    } else if (char === "#" && !inString) {
      return text.slice(0, index);
    }
  }
  return text;
}

function topLevelSegments(text: string): string[] {
  const segments: string[] = [];
  let current = "";
  let depth = 0;
  let inString = false;
  for (const char of text) {
    if (char === '"') {
      inString = !inString;
    }
    if (!inString) {
      if (char === "[" || char === "(" || char === "{") {
        depth += 1;
      } else if (char === "]" || char === ")" || char === "}") {
        depth = Math.max(0, depth - 1);
      } else if (char === "," && depth === 0) {
        segments.push(current);
        current = "";
        continue;
      }
    }
    current += char;
  }
  if (current.trim().length > 0) {
    segments.push(current);
  }
  return segments;
}

function declaredNames(payload: string): string[] {
  const names: string[] = [];
  for (const segment of topLevelSegments(payload)) {
    const match = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:::|=|$)/.exec(segment);
    if (match?.[1] !== undefined) {
      names.push(match[1]);
    }
  }
  return names;
}

/** Parse the declarations of one block source (see the module comment). */
export function parseBlockOutline(source: string): BlockOutline {
  const outline: BlockOutline = { name: null, declarations: {}, ports: [] };
  let scope: ScopeMacro | null = null;
  const lines = source.split(/\r?\n/);

  const add = (current: ScopeMacro, entries: string[]): void => {
    if (entries.length === 0) {
      return;
    }
    const list = outline.declarations[current] ?? [];
    for (const entry of entries) {
      if (!list.includes(entry)) {
        list.push(entry);
      }
    }
    outline.declarations[current] = list;
    if (current === "@ports") {
      for (const entry of entries) {
        if (!outline.ports.includes(entry)) {
          outline.ports.push(entry);
        }
      }
    }
  };

  for (const rawLine of lines) {
    const line = stripComment(rawLine);
    const trimmed = line.trim();
    if (trimmed.length === 0) {
      continue;
    }
    if (trimmed === "end" || trimmed.startsWith("end ")) {
      scope = null;
      continue;
    }
    if (trimmed.startsWith("@")) {
      const match = /^(@[A-Za-z_][A-Za-z0-9_]*)\b(.*)$/.exec(trimmed) ?? [
        "",
        trimmed,
        "",
      ];
      const macro = match[1] ?? "";
      if (macro === "@block") {
        const blockName = /^@block\s+([A-Za-z_][A-Za-z0-9_]*)/.exec(trimmed);
        outline.name = blockName?.[1] ?? null;
        scope = null;
        continue;
      }
      if (
        (SCOPE_MACROS as readonly string[]).includes(macro) &&
        (DECLARATION_SCOPES as readonly string[]).includes(macro)
      ) {
        const declarationScope = macro as ScopeMacro;
        scope = declarationScope;
        add(declarationScope, declaredNames(match[2] ?? ""));
        continue;
      }
      // Any other scope macro has no declarations to collect; its body is
      // statements or equations, not names.
      scope = null;
      continue;
    }
    if (scope !== null) {
      add(scope, declaredNames(trimmed));
    }
  }
  return outline;
}

/** Every declared identifier of an outline, de-duplicated in scope order. */
export function outlineNames(outline: BlockOutline): string[] {
  const names: string[] = [];
  for (const scope of DECLARATION_SCOPES) {
    for (const name of outline.declarations[scope] ?? []) {
      if (!names.includes(name)) {
        names.push(name);
      }
    }
  }
  return names;
}

const FUNCTION_OPTIONS: Completion[] = WHITELIST_FUNCTIONS.map((name) => ({
  label: name,
  type: "function",
  detail: "built-in",
}));

const UNIT_OPTIONS: Completion[] = UNITS.map((name) => ({
  label: name,
  type: "constant",
  detail: "unit",
}));

/** True when the cursor is inside the string of a `unit = "..."` attribute. */
export function unitSpanAt(source: string, offset: number): { from: number; to: number } | null {
  const lineStart = source.lastIndexOf("\n", Math.max(0, offset - 1)) + 1;
  const before = source.slice(lineStart, offset);
  const match = /unit\s*=\s*"([^"]*)$/i.exec(before);
  if (match === null) {
    return null;
  }
  const partial = match[1] ?? "";
  return { from: offset - partial.length, to: offset };
}

/**
 * The completion source of the block editor. It reads the text from the
 * editor state, so the same source works while the user types and after undo.
 */
export function blockCompletionSource(context: CompletionContext): CompletionResult | null {
  const source = context.state.doc.toString();
  const offset = context.pos;

  const unitSpan = unitSpanAt(source, offset);
  if (unitSpan !== null) {
    if (!context.explicit && !context.matchBefore(/[A-Za-z0-9_/*^.-]*$/)) {
      return null;
    }
    return {
      from: unitSpan.from,
      to: unitSpan.to,
      options: UNIT_OPTIONS,
      validFor: /^[A-Za-z0-9_/*^.-]*$/,
    };
  }

  const outline = parseBlockOutline(source);
  const word = context.matchBefore(/[A-Za-z_][A-Za-z0-9_]*$/);
  if (word === null && !context.explicit) {
    const dot = /([A-Za-z_][A-Za-z0-9_]*)\.$/.exec(source.slice(0, offset));
    if (dot !== null && outline.ports.includes(dot[1] ?? "")) {
      return {
        from: offset,
        to: offset,
        options: [
          { label: "e", type: "property", detail: "effort" },
          { label: "f", type: "property", detail: "flow" },
        ],
        validFor: /^[A-Za-z_][A-Za-z0-9_]*/,
      };
    }
    return null;
  }

  const options: Completion[] = [...FUNCTION_OPTIONS];

  for (const name of outlineNames(outline)) {
    options.push({ label: name, type: "variable", detail: "declared" });
  }
  for (const port of outline.ports) {
    options.push({ label: `${port}.e`, type: "property", detail: "effort" });
    options.push({ label: `${port}.f`, type: "property", detail: "flow" });
  }
  for (const name of ["t", "Ts"]) {
    options.push({ label: name, type: "variable", detail: "predefined" });
  }
  for (const macro of SCOPE_MACROS) {
    options.push({ label: macro, type: "keyword", detail: "scope" });
  }

  const typed = word?.text ?? "";
  const filtered = options.filter((option) => {
    const label = typeof option === "string" ? option : option.label;
    return typed.length === 0 || label.toLowerCase().startsWith(typed.toLowerCase());
  });

  return {
    from: word?.from ?? offset,
    to: offset,
    options: filtered,
    validFor: IDENTIFIER,
  };
}
