/**
 * "Save to project library" of a subsystem: the drawn subsystem becomes a
 * reusable project block, a textual composite (`@components` /
 * `@connections`, spec "Textual subsystems"), and the node on the diagram
 * becomes an instance of it.
 *
 * The compiler lowers a textual composite to the same diagram a model-JSON
 * subsystem has, so the translation is one to one:
 *
 *   node                      ->  `name = Block(param = value, ...)`
 *   junction node             ->  `name = Junction(0 | 1)`
 *   bond                      ->  `bond(a.p, b.q)` (directed, any domain)
 *   wire, signal              ->  `connect(a.p, b.q)`
 *   exposed port              ->  a `@ports` / `@inputs` / `@outputs` entry
 *                                 and `connect(port, a.p)`
 *
 * A component names its block, so everything inside must be a library block:
 * a nested subsystem becomes a project block of its own (`<Name>_<Inner>`)
 * and an inline code block is saved like "Save to project library" does.
 *
 * Values. A block cannot see the model's global parameters, so a value that
 * uses one is exposed as a parameter of the new block and the expression
 * moves to the instance. Any other parameter may be exposed on request, so
 * that each instance can set it. Start values are per instance: they move to
 * the instance as `<component>/<variable>`.
 *
 * Signal names. A component keeps its node's name, so every signal keeps its
 * id (`Arm/Motor/w`). Two things move, and references in plots and on the
 * dashboard follow them: an exposed parameter (`Arm/Motor/R` is now `Arm/R`)
 * and the effort and flow of a bond between two junctions, which the compiler
 * names after the connection (`Arm/c12.e` is now `Arm/<Block>/c3.e`).
 *
 * Everything here is pure. `planSubsystemBlock` reports what cannot be
 * translated in `problems` (then nothing is written) and what is not carried
 * over in `notes`.
 */

import { activeDiagram } from "../editor/subsystemPath";
import { blockNameOf } from "../code/templates";
import type { CatalogBlock, ParameterDecl } from "../contracts/catalog";
import type {
  Model,
  ModelBlockSubsystem,
  ModelConstantValue,
  ModelDiagram,
  ModelNode,
  ModelSubsystemPort,
} from "../contracts/model";
import { JUNCTION_PORT } from "../editor/subsystemPorts";
import { identifierSpans, isPlainLiteral, stripEquationPrefix } from "../inspector/expression";
import type { CatalogIndex } from "./catalogIndex";
import { blockNameProblem, freeBlockName, renameBlockDeclaration } from "./projectBlocks";

type Subsystem = ModelBlockSubsystem["subsystem"];

/** One parameter of a block inside the subsystem, as the dialog lists it. */
export interface SubsystemParameter {
  /** `<component path>/<parameter>` inside the subsystem, e.g. `Motor/R`. */
  key: string;
  /** Component path inside the subsystem (`Motor`, `Drive/Motor`). */
  component: string;
  parameter: string;
  /** The value set on the node, or null when it uses the block's default. */
  value: string | null;
  /** The block's own default. */
  default: string;
  unit: string | null;
  description: string;
  /** The value uses a global parameter, so it must be exposed. */
  forced: boolean;
  /** Why it cannot be exposed, or null. */
  blocked: string | null;
}

/** One library file the save writes, dependencies first. */
export interface PlannedBlock {
  name: string;
  source: string;
  origin: "subsystem" | "inline";
  /** Where it comes from, for the dialog: the instance path inside the model. */
  path: string;
}

/** A parameter of the new block. */
export interface ExposedParameter {
  /** Name in the new block. */
  name: string;
  /** The internal parameter it stands for (`SubsystemParameter.key`). */
  key: string;
}

export interface SubsystemBlockPlan {
  /** Why the subsystem cannot be saved; empty when it can. */
  problems: string[];
  /** What the library block does not carry over. */
  notes: string[];
  /** The files to write, dependencies first; the last one is the block itself. */
  blocks: PlannedBlock[];
  /** The values of the instance that replaces the subsystem node. */
  instance: {
    params: Record<string, string>;
    constants: Record<string, ModelConstantValue>;
    starts: Record<string, string>;
  };
  exposed: ExposedParameter[];
  /**
   * The bonds inside. The compiler names the effort and flow of a bond between
   * two junctions after the connection, so a signal `<path>/<from>.e` is
   * `<path>/<to>.e` in the instance. Bonds without such signals are listed too.
   */
  bondRenames: { from: string; to: string }[];
}

export interface SubsystemBlockInput {
  doc: Model;
  /** The subsystem node. */
  node: ModelNode;
  /** Instance path of the node in the model, e.g. `Arm/Joint1`. */
  path: string;
  /** The new block's name. */
  name: string;
  index: CatalogIndex;
  /** Block names already in the project library. */
  taken: readonly string[];
  /** `SubsystemParameter.key`s to expose besides the forced ones. */
  expose?: ReadonlySet<string>;
}

const KEYWORDS = new Set([
  "baremodule", "begin", "break", "catch", "const", "continue", "do", "else", "elseif", "end",
  "export", "false", "finally", "for", "function", "global", "if", "import", "let", "local",
  "macro", "module", "quote", "return", "struct", "true", "try", "using", "while",
  "abstract", "in", "isa", "mutable", "outer", "primitive", "type", "where",
  // Reserved by the block language inside a composite.
  "Junction", "connect", "bond",
  // Predefined in block source: time, the sample time and the built-in names.
  "t", "Ts", "ifelse", "pi", "Inf", "NaN",
]);

const NUMBER = String.raw`[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?`;
const VECTOR_LITERAL = new RegExp(String.raw`^\[\s*${NUMBER}(?:\s*,\s*${NUMBER})*\s*\]$`);

function globalNames(doc: Model): Set<string> {
  return new Set((doc.parameters ?? []).map((entry) => entry.name));
}

/** The global parameters an expression string uses. */
function globalsUsed(text: string, globals: ReadonlySet<string>): string[] {
  if (globals.size === 0) {
    return [];
  }
  const used = new Set<string>();
  for (const span of identifierSpans(text)) {
    if (!span.call && globals.has(span.name)) {
      used.add(span.name);
    }
  }
  return [...used];
}

/** `scalar`, the length of a literal vector, or null when the text is neither. */
function literalShape(text: string): "scalar" | number | null {
  const trimmed = text.trim();
  if (isPlainLiteral(trimmed)) {
    return "scalar";
  }
  if (VECTOR_LITERAL.test(trimmed)) {
    return trimmed.split(",").length;
  }
  return null;
}

function quoted(text: string): string {
  return `"${text.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\$/g, "\\$").replace(/\r?\n/g, " ")}"`;
}

/** The value of a node parameter as it is compiled: no `=` prefix, trimmed. */
function valueText(value: string): string {
  return stripEquationPrefix(value).trim();
}

/** How an exposed parameter is declared in the new block. */
interface ParameterShape {
  /** `Real`, `Int`, `Bool` or `Vec{n}`. */
  type: string;
  /** The default written into the block: a plain number or a literal vector. */
  default: string;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The declared type of `name` in a block source (`Vec{N}`, `Mat{2,N}`, `Real`), or null. */
function declaredType(source: string, name: string): string | null {
  const pattern = new RegExp(`(?:^|[\\s(;])${escapeRegExp(name)}\\s*::\\s*([A-Za-z]+(?:\\{[^}]*\\})?)`, "m");
  return pattern.exec(source)?.[1] ?? null;
}

/** The value of a structural constant on this node: its override, else the block's default. */
function constantNumber(block: CatalogBlock, node: ModelNode, name: string): number | null {
  const own = node.constants?.[name];
  const value = own !== undefined ? own : block.constants.find((entry) => entry.name === name)?.default;
  if (typeof value === "number") {
    return value;
  }
  if (typeof value === "string" && /^\s*\d+\s*$/.test(value)) {
    return Number(value);
  }
  return null;
}

/**
 * How parameter `decl` of `block`, as used by `node`, is declared in another
 * block, or why it cannot be. The catalog does not carry a parameter's size,
 * so the type is read from the block's own source; a vector's length may come
 * from a structural constant of the node. The default is the node's own number
 * when it has one (a new instance then starts out like this one), else the
 * block's default.
 */
function parameterShape(
  block: CatalogBlock,
  decl: ParameterDecl,
  node: ModelNode,
): ParameterShape | { blocked: string } {
  const raw = node.params?.[decl.name];
  const value = raw === undefined ? null : valueText(raw);
  const type =
    declaredType(block.source, decl.name) ?? (literalShape(decl.default) === "scalar" ? decl.type : null);
  if (type === null) {
    return { blocked: "its declaration is not found in the block source" };
  }
  let size: "scalar" | number;
  if (type === "Real" || type === "Int" || type === "Bool") {
    size = "scalar";
  } else {
    const vector = /^Vec\{\s*([A-Za-z_][A-Za-z0-9_]*|\d+)\s*\}$/.exec(type);
    if (vector === null || vector[1] === undefined) {
      return { blocked: `it is a ${type}, and only numbers and vectors can be exposed` };
    }
    const length = /^\d+$/.test(vector[1]) ? Number(vector[1]) : constantNumber(block, node, vector[1]);
    if (length === null) {
      return { blocked: `its size (${vector[1]}) is not a plain number` };
    }
    size = length;
  }
  const fits = (text: string | null): text is string => text !== null && literalShape(text) === size;
  const fallback = decl.default.trim();
  const chosen = fits(value) ? value : fits(fallback) ? fallback : null;
  if (chosen === null) {
    return {
      blocked:
        fallback.length === 0
          ? "it has no default value"
          : `its default (${fallback}) is not a plain ${size === "scalar" ? "number" : "vector"} of its size`,
    };
  }
  return { type: size === "scalar" ? type : `Vec{${size}}`, default: chosen };
}

/** The `@parameters` entry of an exposed parameter. */
function parameterDeclaration(name: string, decl: ParameterDecl, shape: ParameterShape): string {
  const attrs: string[] = [];
  if (decl.unit !== null && decl.unit.length > 0) {
    attrs.push(`unit = ${quoted(decl.unit)}`);
  }
  if (decl.min !== null) {
    attrs.push(`min = ${decl.min}`);
  }
  if (decl.max !== null) {
    attrs.push(`max = ${decl.max}`);
  }
  if (decl.tunable) {
    attrs.push("tunable = true");
  }
  if (decl.options !== null && decl.options.length > 0) {
    attrs.push(`options = [${decl.options.map(quoted).join(", ")}]`);
  }
  if (decl.description.length > 0) {
    attrs.push(`description = ${quoted(decl.description)}`);
  }
  const tail = attrs.length === 0 ? "" : `, [${attrs.join(", ")}]`;
  return `${name}::${shape.type} = ${shape.default}${tail}`;
}

/** A constant override as block source, or the reason it cannot be written. */
function constantText(value: ModelConstantValue): { text: string } | { problem: string } {
  if (typeof value === "number" || typeof value === "boolean") {
    return { text: String(value) };
  }
  if (typeof value === "string") {
    const text = valueText(value);
    return text.length === 0 ? { problem: "is empty" } : { text };
  }
  if (value.every((entry) => typeof entry === "number")) {
    return { text: `[${value.join(", ")}]` };
  }
  const rows = value.map((entry) => (Array.isArray(entry) ? entry : [entry]));
  const width = rows[0]?.length ?? 0;
  if (width < 2 || rows.some((row) => row.length !== width)) {
    // `[1; 2]` is a vector in the block language, so a one-column matrix has no literal.
    return { problem: "is a one-column or ragged matrix, which has no literal in block source" };
  }
  return { text: `[${rows.map((row) => row.join(" ")).join("; ")}]` };
}

function walkParameters(
  sub: Subsystem,
  prefix: string,
  index: CatalogIndex,
  globals: ReadonlySet<string>,
  out: SubsystemParameter[],
): void {
  for (const node of sub.diagram.nodes) {
    const component = `${prefix}${node.name}`;
    if ("subsystem" in node.block) {
      walkParameters(node.block.subsystem, `${component}/`, index, globals, out);
      continue;
    }
    if (!("ref" in node.block)) {
      continue;
    }
    const block = index.blocksByRef.get(node.block.ref);
    if (block === undefined) {
      continue;
    }
    for (const decl of block.parameters) {
      const raw = node.params?.[decl.name];
      const value = raw === undefined ? null : valueText(raw);
      const shape = parameterShape(block, decl, node);
      out.push({
        key: `${component}/${decl.name}`,
        component,
        parameter: decl.name,
        value,
        default: decl.default,
        unit: decl.unit,
        description: decl.description,
        forced: value !== null && globalsUsed(value, globals).length > 0,
        blocked: "blocked" in shape ? shape.blocked : null,
      });
    }
  }
}

/** Every parameter of the library blocks inside the subsystem, nested subsystems included. */
export function subsystemParameters(doc: Model, node: ModelNode, index: CatalogIndex): SubsystemParameter[] {
  const out: SubsystemParameter[] = [];
  if ("subsystem" in node.block) {
    walkParameters(node.block.subsystem, "", index, globalNames(doc), out);
  }
  return out;
}

interface Exposure {
  /** Name in the block that declares it. */
  name: string;
  key: string;
  decl: ParameterDecl;
  shape: ParameterShape;
  /** The node's value (an expression string), or null. */
  value: string | null;
}

interface Context {
  index: CatalogIndex;
  globals: ReadonlySet<string>;
  expose: ReadonlySet<string>;
  /** Names that a new block cannot take: the project library, the stdlib, and the plan so far. */
  reserved: string[];
  stdlibNames: Map<string, number>;
  projectNames: Set<string>;
  /** Inline source -> the project block planned for it. */
  inline: Map<string, string>;
  blocks: PlannedBlock[];
  problems: string[];
  starts: Record<string, string>;
  bondRenames: { from: string; to: string }[];
  dropped: { notes: number; shapes: number; probes: number };
}

function freeName(taken: ReadonlySet<string>, ...candidates: string[]): string {
  for (const candidate of candidates) {
    if (!taken.has(candidate) && !KEYWORDS.has(candidate)) {
      return candidate;
    }
  }
  const base = candidates[candidates.length - 1] ?? "p";
  let n = 2;
  while (taken.has(`${base}${n}`)) {
    n += 1;
  }
  return `${base}${n}`;
}

/** The name a component uses for a library block, or null (with a problem) when it has none. */
function componentBlockName(ctx: Context, block: CatalogBlock, where: string): string | null {
  if (block.ref.startsWith("project:")) {
    return block.name;
  }
  if ((ctx.stdlibNames.get(block.name) ?? 0) > 1) {
    ctx.problems.push(
      `${where} uses ${block.ref}, but the standard library has more than one block called ${block.name}; a library block names its components by block name. Copy the block to the project library under its own name first.`,
    );
    return null;
  }
  if (ctx.projectNames.has(block.name)) {
    ctx.problems.push(
      `${where} uses ${block.ref}, but the project library has its own ${block.name}, which a library block would use instead. Rename the project block first.`,
    );
    return null;
  }
  return block.name;
}

function portDeclaration(port: ModelSubsystemPort, ctx: Context, where: string): string | null {
  if (port.kind === "power") {
    const frame = port.frame === undefined || port.frame === null ? "" : `, [frame = ${quoted(port.frame)}]`;
    return `${port.name}::Power{${port.domain}}${frame}`;
  }
  let type: string;
  if (port.size.length === 0) {
    type = port.type;
  } else if (port.type !== "Real") {
    ctx.problems.push(`Port ${port.name} of ${where} is an array of ${port.type}; block source has Real arrays only.`);
    return null;
  } else if (port.size.length === 1) {
    type = `Vec{${port.size[0]}}`;
  } else if (port.size.length === 2) {
    type = `Mat{${port.size[0]},${port.size[1]}}`;
  } else {
    ctx.problems.push(`Port ${port.name} of ${where} has more than two dimensions.`);
    return null;
  }
  const unit = port.unit === null || port.unit.length === 0 ? "" : `, [unit = ${quoted(port.unit)}]`;
  return `${port.name}::${type}${unit}`;
}

function scope(name: string, lines: readonly string[]): string[] {
  if (lines.length === 0) {
    return [];
  }
  return [`    ${name} begin`, ...lines.map((line) => `        ${line}`), "    end"];
}

/**
 * Plan the block of one subsystem (and, first, of everything inside it that is
 * not a library block yet). `prefix` is the component path inside the top
 * subsystem (`""`, `Drive/`); `where` the instance path for messages.
 */
function convert(
  ctx: Context,
  sub: Subsystem,
  blockName: string,
  prefix: string,
  where: string,
): Exposure[] {
  const diagram: ModelDiagram = sub.diagram;
  const nodes = new Map(diagram.nodes.map((node) => [node.id, node]));
  const faceNames = new Set(sub.ports.map((port) => port.name));
  const names = new Set<string>([...faceNames, ...diagram.nodes.map((node) => node.name)]);
  const exposures: Exposure[] = [];
  const components: string[] = [];

  ctx.dropped.notes += diagram.annotations?.length ?? 0;
  ctx.dropped.shapes += diagram.shapes?.length ?? 0;
  ctx.dropped.probes += diagram.probes?.length ?? 0;

  if (diagram.nodes.length === 0) {
    ctx.problems.push(`${where} is empty; a library block needs at least one block inside.`);
  }

  const exposeAs = (
    component: string,
    decl: ParameterDecl,
    shape: ParameterShape,
    key: string,
    value: string | null,
  ): string => {
    const name = freeName(names, decl.name, `${component}_${decl.name}`);
    names.add(name);
    exposures.push({ name, key, decl, shape, value });
    return name;
  };

  for (const node of diagram.nodes) {
    const at = `${where}/${node.name}`;
    if (KEYWORDS.has(node.name)) {
      ctx.problems.push(`${at}: “${node.name}” is a reserved word in block source. Rename the block first.`);
    }
    if (faceNames.has(node.name)) {
      ctx.problems.push(
        `${where} has both a port and a block called ${node.name}; in a library block they share one namespace. Rename one of them first.`,
      );
    }
    for (const [key, value] of Object.entries(node.starts ?? {})) {
      ctx.starts[`${prefix}${node.name}/${key}`] = value;
    }

    if ("junction" in node.block) {
      components.push(`${node.name} = Junction(${node.block.junction})`);
      continue;
    }

    if ("subsystem" in node.block) {
      const childName = freeBlockName(`${blockName}_${node.name}`, ctx.reserved);
      ctx.reserved.push(childName);
      const inner = convert(ctx, node.block.subsystem, childName, `${prefix}${node.name}/`, at);
      const kwargs = inner.map((entry) => {
        const own = exposeAs(node.name, entry.decl, entry.shape, entry.key, entry.value);
        return `${entry.name} = ${own}`;
      });
      components.push(`${node.name} = ${childName}(${kwargs.join(", ")})`);
      continue;
    }

    const kwargs: string[] = [];
    let blockRefName: string | null;
    let block: CatalogBlock | undefined;
    if ("inline" in node.block) {
      const source = node.block.inline.source;
      const declared = blockNameOf(source);
      if (declared === null) {
        ctx.problems.push(`${at} is an inline block without a @block <Name> declaration.`);
        continue;
      }
      let planned = ctx.inline.get(source);
      if (planned === undefined) {
        planned = freeBlockName(declared, ctx.reserved);
        ctx.reserved.push(planned);
        ctx.inline.set(source, planned);
        ctx.blocks.push({
          name: planned,
          source: renameBlockDeclaration(source, planned),
          origin: "inline",
          path: at,
        });
      }
      blockRefName = planned;
    } else {
      block = ctx.index.blocksByRef.get(node.block.ref);
      if (block === undefined) {
        ctx.problems.push(`${at} uses ${node.block.ref}, which is not in the catalog.`);
        continue;
      }
      blockRefName = componentBlockName(ctx, block, at);
    }
    if (blockRefName === null) {
      continue;
    }

    const declared = new Map((block?.parameters ?? []).map((decl) => [decl.name, decl]));
    const constantNames = new Set((block?.constants ?? []).map((decl) => decl.name));
    for (const [key, value] of Object.entries(node.constants ?? {})) {
      if (block !== undefined && !constantNames.has(key)) {
        ctx.problems.push(
          `${at} keeps the setting “${key}” (a data file reference), which a library block cannot carry.`,
        );
        continue;
      }
      const used = typeof value === "string" ? globalsUsed(value, ctx.globals) : [];
      if (used.length > 0) {
        ctx.problems.push(
          `Constant ${key} of ${at} uses the global parameter ${used.join(", ")}; a library block cannot see globals. Enter a number first.`,
        );
        continue;
      }
      const text = constantText(value);
      if ("problem" in text) {
        ctx.problems.push(`Constant ${key} of ${at} ${text.problem}.`);
        continue;
      }
      kwargs.push(`${key} = ${text.text}`);
    }

    const paramKeys = new Set([...declared.keys(), ...Object.keys(node.params ?? {})]);
    for (const key of paramKeys) {
      const raw = node.params?.[key];
      const value = raw === undefined ? null : valueText(raw);
      const decl = declared.get(key);
      const fullKey = `${prefix}${node.name}/${key}`;
      const used = value === null ? [] : globalsUsed(value, ctx.globals);
      const wanted = used.length > 0 || ctx.expose.has(fullKey);
      if (wanted) {
        const shape: ParameterShape | { blocked: string } =
          decl === undefined || block === undefined
            ? { blocked: "its block is not a library block yet" }
            : parameterShape(block, decl, node);
        if (decl === undefined || "blocked" in shape) {
          const blocker = "blocked" in shape ? shape.blocked : "it is not declared";
          ctx.problems.push(
            used.length > 0
              ? `Parameter ${key} of ${at} uses the global parameter ${used.join(", ")}, so it has to become a parameter of the library block, but ${blocker}. Enter a number first.`
              : `Parameter ${key} of ${at} cannot be exposed: ${blocker}.`,
          );
          continue;
        }
        kwargs.push(`${key} = ${exposeAs(node.name, decl, shape, fullKey, value)}`);
      } else if (value !== null) {
        if (value.length === 0) {
          ctx.problems.push(`Parameter ${key} of ${at} is empty.`);
          continue;
        }
        kwargs.push(`${key} = ${value}`);
      }
    }
    components.push(`${node.name} = ${blockRefName}(${kwargs.join(", ")})`);
  }

  // The interface and its faces.
  const ports: string[] = [];
  const inputs: string[] = [];
  const outputs: string[] = [];
  const connections: string[] = [];
  const endpoint = (nodeId: string, port: string | undefined, what: string): string | null => {
    const node = nodes.get(nodeId);
    if (node === undefined) {
      ctx.problems.push(`${what} of ${where} refers to a block that is no longer there.`);
      return null;
    }
    if ("junction" in node.block) {
      return node.name;
    }
    if (port === undefined || port.length === 0) {
      ctx.problems.push(`${what} of ${where} names no port of ${node.name}.`);
      return null;
    }
    return `${node.name}.${port}`;
  };

  const seenFaces = new Set<string>();
  for (const port of sub.ports) {
    if (seenFaces.has(port.name)) {
      ctx.problems.push(`${where} has two ports called ${port.name}.`);
      continue;
    }
    seenFaces.add(port.name);
    if (KEYWORDS.has(port.name)) {
      ctx.problems.push(`Port ${port.name} of ${where} is a reserved word in block source. Rename the port first.`);
    }
    const declaration = portDeclaration(port, ctx, where);
    const target = endpoint(port.node, port.port === JUNCTION_PORT ? undefined : port.port, `Port ${port.name}`);
    if (declaration === null || target === null) {
      continue;
    }
    (port.kind === "power" ? ports : port.direction === "input" ? inputs : outputs).push(declaration);
    connections.push(`connect(${port.name}, ${target})`);
  }

  for (const connection of diagram.connections) {
    const from = endpoint(connection.from.node, connection.from.port, "A connection");
    const to = endpoint(connection.to.node, connection.to.port, "A connection");
    if (from === null || to === null) {
      continue;
    }
    // A drawn bond is directed whatever the domains; `connect` would make two concrete-domain
    // power ports a wire.
    connections.push(`${connection.kind === "bond" ? "bond" : "connect"}(${from}, ${to})`);
    if (connection.kind === "bond" && !names.has(connection.id)) {
      // A bond that joins two junctions has an effort and a flow of its own, named after the
      // connection. Which bonds do is the compiler's knowledge (a port of a body is a junction
      // too), so every bond is listed; the name only matters where such a signal exists. The
      // compiler numbers a composite's connections in source order, faces included.
      ctx.bondRenames.push({
        from: `${prefix}${connection.id}`,
        to: `${prefix}${blockName}/c${connections.length}`,
      });
    }
  }

  const parameters = exposures.map((entry) => parameterDeclaration(entry.name, entry.decl, entry.shape));
  const source = [
    `@block ${blockName} begin`,
    `    # Saved from the subsystem ${where}.`,
    ...scope("@ports", ports),
    ...scope("@inputs", inputs),
    ...scope("@outputs", outputs),
    ...scope("@parameters", parameters),
    ...scope("@components", components),
    ...scope("@connections", connections),
    "end",
    "",
  ].join("\n");
  ctx.blocks.push({ name: blockName, source, origin: "subsystem", path: where });
  return exposures;
}

/** Why `name` cannot be the new block, or null: a free project name that no stdlib block has. */
export function subsystemBlockNameProblem(
  name: string,
  taken: Iterable<string>,
  index: CatalogIndex,
): string | null {
  const problem = blockNameProblem(name, taken);
  if (problem !== null) {
    return problem;
  }
  const trimmed = name.trim();
  const clash = index.blocks.find(
    (block) => block.ref.startsWith("stdlib:") && block.name.toLowerCase() === trimmed.toLowerCase(),
  );
  return clash === undefined
    ? null
    : `The standard library already has ${clash.name} (${clash.ref}); a project block of that name would replace it inside other library blocks.`;
}

/** A free name for the new block, proposed from the subsystem's instance name. */
export function suggestedSubsystemBlockName(
  node: ModelNode,
  taken: Iterable<string>,
  index: CatalogIndex,
): string {
  const stem = node.name.replace(/\d+$/, "");
  const base = stem.length > 0 && !KEYWORDS.has(stem) ? stem : "Subsystem";
  const reserved = [...taken, ...index.blocks.map((block) => block.name)];
  return freeBlockName(base.charAt(0).toUpperCase() + base.slice(1), reserved);
}

export function planSubsystemBlock(input: SubsystemBlockInput): SubsystemBlockPlan {
  const plan: SubsystemBlockPlan = {
    problems: [],
    notes: [],
    blocks: [],
    instance: { params: {}, constants: {}, starts: {} },
    exposed: [],
    bondRenames: [],
  };
  if (!("subsystem" in input.node.block)) {
    plan.problems.push("Only a subsystem can be saved as a library block this way.");
    return plan;
  }
  const stdlibNames = new Map<string, number>();
  const projectNames = new Set<string>();
  for (const block of input.index.blocks) {
    if (block.ref.startsWith("stdlib:")) {
      stdlibNames.set(block.name, (stdlibNames.get(block.name) ?? 0) + 1);
    } else if (block.ref.startsWith("project:")) {
      projectNames.add(block.name);
    }
  }
  const ctx: Context = {
    index: input.index,
    globals: globalNames(input.doc),
    expose: input.expose ?? new Set<string>(),
    reserved: [...input.taken, ...projectNames, ...stdlibNames.keys(), input.name],
    stdlibNames,
    projectNames,
    inline: new Map(),
    blocks: plan.blocks,
    problems: plan.problems,
    starts: plan.instance.starts,
    bondRenames: plan.bondRenames,
    dropped: { notes: 0, shapes: 0, probes: 0 },
  };
  const exposures = convert(ctx, input.node.block.subsystem, input.name, "", input.path);

  for (const entry of exposures) {
    plan.exposed.push({ name: entry.name, key: entry.key });
    if (entry.value !== null && entry.value !== entry.shape.default) {
      plan.instance.params[entry.name] = entry.value;
    }
  }

  plan.notes.push(
    "The drawing inside the subsystem (positions, routes) is not kept: the library block is edited as code in the Code tab. Undo brings the subsystem back.",
  );
  const { notes, shapes, probes } = ctx.dropped;
  const lost = [
    notes > 0 ? `${notes} note${notes === 1 ? "" : "s"}` : null,
    shapes > 0 ? `${shapes} shape${shapes === 1 ? "" : "s"}` : null,
    probes > 0 ? `${probes} probe${probes === 1 ? "" : "s"}` : null,
  ].filter((entry): entry is string => entry !== null);
  if (lost.length > 0) {
    plan.notes.push(`Not carried over: ${lost.join(", ")} inside the subsystem.`);
  }
  const startCount = Object.keys(plan.instance.starts).length;
  if (startCount > 0) {
    plan.notes.push(
      `${startCount} start value${startCount === 1 ? "" : "s"} stay${startCount === 1 ? "s" : ""} with this instance (as component/variable). A new instance from the library starts at the block defaults; copy this instance to keep them.`,
    );
  }
  return plan;
}

/** The parameter ids that moved: `<path>/<component>/<param>` is now `<path>/<name>`. */
export function parameterRetargets(path: string, plan: SubsystemBlockPlan): Map<string, string> {
  return new Map(plan.exposed.map((entry) => [`${path}/${entry.key}`, `${path}/${entry.name}`]));
}

/** The bonds between junctions that moved: `<path>/<connection>` is now `<path>/<Block>/c<k>`. */
export function signalRetargets(path: string, plan: SubsystemBlockPlan): Map<string, string> {
  return new Map(plan.bondRenames.map((entry) => [`${path}/${entry.from}`, `${path}/${entry.to}`]));
}

/**
 * Replace the subsystem node `nodeId` of `doc` (anywhere in the model) by an
 * instance of `ref` with the plan's values, in place. Dashboard inputs that
 * named an exposed parameter follow it, and so do plots and dashboard displays
 * of a bond between two junctions. Returns false when the node is not a
 * subsystem of the model.
 */
export function applySubsystemReplacement(
  doc: Model,
  nodeId: string,
  ref: string,
  path: string,
  plan: SubsystemBlockPlan,
  within: readonly string[] | null = null,
): boolean {
  const find = (diagram: ModelDiagram): ModelNode | null => {
    for (const node of diagram.nodes) {
      if (node.id === nodeId) {
        return node;
      }
      if ("subsystem" in node.block) {
        const inner = find(node.block.subsystem.diagram);
        if (inner !== null) {
          return inner;
        }
      }
    }
    return null;
  };
  // A node id is unique in its own diagram only (many models repeat ids across
  // subsystems, and the instances of a library subsystem share theirs), so with `within`
  // the node is looked up in that diagram and nowhere else.
  const node =
    within === null
      ? find(doc.diagram)
      : (activeDiagram(doc, within)?.nodes.find((entry) => entry.id === nodeId) ?? null);
  if (node === null || !("subsystem" in node.block)) {
    return false;
  }
  node.block = { ref };
  node.params = { ...plan.instance.params };
  node.constants = { ...plan.instance.constants };
  node.starts = { ...plan.instance.starts };

  const moved = parameterRetargets(path, plan);
  if (moved.size > 0) {
    const retarget = (id: string): string => {
      const direct = moved.get(id);
      if (direct !== undefined) {
        return direct;
      }
      // An element of a vector parameter: `Arm/Motor/k[2]`.
      const bracket = id.indexOf("[");
      const base = bracket < 0 ? undefined : moved.get(id.slice(0, bracket));
      return base === undefined ? id : `${base}${id.slice(bracket)}`;
    };
    for (const card of doc.dashboard?.cards ?? []) {
      if (card.parameter !== undefined) {
        card.parameter = retarget(card.parameter);
      }
      if (card.schedule !== undefined) {
        card.schedule.parameters = card.schedule.parameters.map(retarget);
      }
    }
  }

  const bonds = signalRetargets(path, plan);
  if (bonds.size > 0) {
    // `Arm/c12.e`, `Arm/c12.f[2]`: the bond's id up to the field.
    const rename = (id: string): string => {
      const field = /\.[ef](?:\[\d+\])?$/.exec(id);
      const base = field === null ? undefined : bonds.get(id.slice(0, field.index));
      return base === undefined || field === null ? id : `${base}${field[0]}`;
    };
    for (const plot of doc.plots ?? []) {
      plot.signals = plot.signals.map(rename);
      if (typeof plot.x === "string") {
        plot.x = rename(plot.x);
      }
    }
    for (const card of doc.dashboard?.cards ?? []) {
      if (card.signals !== undefined) {
        card.signals = card.signals.map(rename);
      }
      if (card.x !== undefined) {
        card.x = rename(card.x);
      }
    }
  }
  return true;
}
