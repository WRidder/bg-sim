/**
 * Linked subsystems: a drawn subsystem of the project library and its instances.
 *
 * On disk a definition is `library/<Name>.bgsub.json` (contract
 * `subsystemDefinition`) and an instance is a node with `block.ref`
 * `project:<Name>`, with its own values for the pinned parameters and start
 * values in `params` and `starts` (keyed by the path inside the definition,
 * `rotor/J`).
 *
 * While a model is open the editor holds every instance as a *working copy*: a
 * subsystem node whose `block.subsystem.definition` names the definition, with
 * the definition's diagram and the instance's pinned values in place. So the
 * canvas, the inspectors, the signal pickers and the compiler all see an
 * ordinary subsystem, at the instance's own path. `syncLinked` keeps the copies
 * equal after every edit: an edit inside one instance becomes the definition and
 * reaches every other instance, except for a pinned value, which stays with the
 * instance it was typed in.
 *
 * Everything here is pure, with structural sharing: an object that does not
 * change keeps its identity.
 */

import type {
  Model,
  ModelBlockSubsystem,
  ModelConnection,
  ModelDiagram,
  ModelNode,
  ModelSubsystemPort,
  SubsystemDefinition,
} from "../contracts/model";

export type Definitions = Record<string, SubsystemDefinition>;
export type PinKind = "params" | "starts";
export const PIN_KINDS: readonly PinKind[] = ["params", "starts"];

type Subsystem = ModelBlockSubsystem["subsystem"];
type SubsystemNode = ModelNode & { block: ModelBlockSubsystem };

const PROJECT_PREFIX = "project:";

/** A block or a subsystem definition name: a Julia identifier. */
export const DEFINITION_NAME_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

function isSubsystemNode(node: ModelNode): node is SubsystemNode {
  return "subsystem" in node.block;
}

/** The definition a node is an instance of, or null for any other node. */
export function linkedDefinition(node: ModelNode): string | null {
  return isSubsystemNode(node) ? (node.block.subsystem.definition ?? null) : null;
}

function withSubsystem(node: SubsystemNode, subsystem: Subsystem): SubsystemNode {
  return { ...node, block: { ...node.block, subsystem } };
}

// ---------------------------------------------------------------------------
// Pinned values
// ---------------------------------------------------------------------------

/**
 * The node a pinned path names and what that node calls the value. Node names
 * are followed through nested subsystems as far as they go; the rest is the key
 * on the node reached (`rotor/J`, `Inner/gear/n`, `drive/inertia/P`). The
 * compiler resolves a path the same way (`_pin_target`).
 */
function pinSteps(diagram: ModelDiagram, path: string): { nodes: ModelNode[]; key: string } | null {
  const parts = path.split("/");
  const nodes: ModelNode[] = [];
  let current = diagram;
  for (let k = 0; k < parts.length - 1; k += 1) {
    const node = current.nodes.find((entry) => entry.name === parts[k]);
    if (node === undefined) {
      return null;
    }
    nodes.push(node);
    if (isSubsystemNode(node) && k < parts.length - 2) {
      current = node.block.subsystem.diagram;
      continue;
    }
    if (!("ref" in node.block) && !("inline" in node.block)) {
      return null;
    }
    return { nodes, key: parts.slice(k + 1).join("/") };
  }
  return null;
}

/**
 * The path that names, in `diagram`, the blocks `path` names in `from`: the same
 * node ids, whatever they are called now. Null when one of them is gone, and
 * `path` itself when it names nothing in `from` either. This is what lets a pin
 * follow a block that is renamed.
 */
function pinPathIn(from: ModelDiagram, path: string, diagram: ModelDiagram): string | null {
  const steps = pinSteps(from, path);
  if (steps === null) {
    return path;
  }
  const names: string[] = [];
  let current = diagram;
  for (let k = 0; k < steps.nodes.length; k += 1) {
    const node = current.nodes.find((entry) => entry.id === steps.nodes[k]?.id);
    if (node === undefined) {
      return null;
    }
    names.push(node.name);
    if (k < steps.nodes.length - 1) {
      if (!isSubsystemNode(node)) {
        return null;
      }
      current = node.block.subsystem.diagram;
    } else if (!("ref" in node.block) && !("inline" in node.block)) {
      return null;
    }
  }
  return [...names, steps.key].join("/");
}

/** Whether `path` names something in `diagram` that can carry a value. */
export function pinResolves(diagram: ModelDiagram, path: string): boolean {
  return pinSteps(diagram, path) !== null;
}

/** The value at a pinned path: undefined when unset or when the path names nothing. */
export function readPin(diagram: ModelDiagram, kind: PinKind, path: string): string | undefined {
  const steps = pinSteps(diagram, path);
  const node = steps?.nodes[steps.nodes.length - 1];
  return node?.[kind]?.[steps?.key ?? ""];
}

/** `diagram` with the value at `path` set (or removed with undefined). */
export function writePin(
  diagram: ModelDiagram,
  kind: PinKind,
  path: string,
  value: string | undefined,
): ModelDiagram {
  const steps = pinSteps(diagram, path);
  if (steps === null) {
    return diagram;
  }
  const last = steps.nodes[steps.nodes.length - 1];
  if (last === undefined || last[kind]?.[steps.key] === value) {
    return diagram;
  }
  const values = { ...(last[kind] ?? {}) };
  if (value === undefined) {
    delete values[steps.key];
  } else {
    values[steps.key] = value;
  }
  let replacement: ModelNode = { ...last, [kind]: values };
  if (Object.keys(values).length === 0) {
    delete replacement[kind];
  }
  // Rebuild the chain of diagrams from the innermost node outwards.
  for (let k = steps.nodes.length - 2; k >= 0; k -= 1) {
    const parent = steps.nodes[k] as SubsystemNode;
    const inner = parent.block.subsystem;
    const child = replacement;
    replacement = withSubsystem(parent, {
      ...inner,
      diagram: {
        ...inner.diagram,
        nodes: inner.diagram.nodes.map((entry) => (entry.id === child.id ? child : entry)),
      },
    });
  }
  const top = replacement;
  return { ...diagram, nodes: diagram.nodes.map((entry) => (entry.id === top.id ? top : entry)) };
}

export function pinsOf(definition: SubsystemDefinition, kind: PinKind): readonly string[] {
  return definition.pins?.[kind] ?? [];
}

export interface InstanceValue {
  kind: PinKind;
  /** The path inside the definition: `rotor/J`. */
  path: string;
  /** What this instance has; undefined when unset (the block's own default). */
  value: string | undefined;
  /** What the definition has, and so every instance that does not set its own. */
  default: string | undefined;
  changed: boolean;
  /** False when the path names nothing in the definition any more. */
  resolves: boolean;
}

/** Every pinned value of an instance next to the definition's value. */
export function instanceValues(
  subsystem: Subsystem,
  definition: SubsystemDefinition,
): InstanceValue[] {
  const values: InstanceValue[] = [];
  for (const kind of PIN_KINDS) {
    for (const path of pinsOf(definition, kind)) {
      const value = readPin(subsystem.diagram, kind, path);
      const base = readPin(definition.diagram, kind, path);
      values.push({
        kind,
        path,
        value,
        default: base,
        changed: value !== base,
        resolves: pinResolves(definition.diagram, path),
      });
    }
  }
  return values;
}

/** How many pinned values of an instance differ from the definition. */
export function changedValueCount(node: ModelNode, definitions: Definitions | undefined): number {
  const name = linkedDefinition(node);
  const definition = name === null ? undefined : definitions?.[name];
  if (definition === undefined || !isSubsystemNode(node)) {
    return 0;
  }
  return instanceValues(node.block.subsystem, definition).filter((entry) => entry.changed).length;
}

/** The working copy of `definition` for an instance with these pinned values. */
function instanceSubsystem(
  definition: SubsystemDefinition,
  values: (kind: PinKind, path: string) => string | undefined,
): Subsystem {
  let diagram = definition.diagram;
  for (const kind of PIN_KINDS) {
    for (const path of pinsOf(definition, kind)) {
      const value = values(kind, path);
      if (value !== undefined) {
        diagram = writePin(diagram, kind, path, value);
      }
    }
  }
  return { ports: definition.ports, diagram, definition: definition.name };
}

/** A fresh working copy with the definition's own values: what a new instance starts as. */
export function newInstanceSubsystem(definition: SubsystemDefinition): Subsystem {
  return instanceSubsystem(definition, () => undefined);
}

// ---------------------------------------------------------------------------
// Walking
// ---------------------------------------------------------------------------

/** The names of the definitions instanced anywhere in `diagram`, at any depth. */
export function linkedNamesIn(diagram: ModelDiagram, into: Set<string> = new Set()): Set<string> {
  for (const node of diagram.nodes) {
    if (!isSubsystemNode(node)) {
      continue;
    }
    const name = node.block.subsystem.definition;
    if (name !== undefined) {
      into.add(name);
    }
    linkedNamesIn(node.block.subsystem.diagram, into);
  }
  return into;
}

/** How many instances of `name` the model itself has (instances inside other definitions count once per copy). */
export function instanceCount(doc: Pick<Model, "diagram">, name: string): number {
  let count = 0;
  const walk = (diagram: ModelDiagram): void => {
    for (const node of diagram.nodes) {
      if (isSubsystemNode(node)) {
        if (node.block.subsystem.definition === name) {
          count += 1;
        }
        walk(node.block.subsystem.diagram);
      }
    }
  };
  walk(doc.diagram);
  return count;
}

/** The definitions whose own diagram holds an instance of `name`. */
export function definitionsUsing(definitions: Definitions | undefined, name: string): string[] {
  return Object.values(definitions ?? {})
    .filter((entry) => entry.name !== name && linkedNamesIn(entry.diagram).has(name))
    .map((entry) => entry.name)
    .sort();
}

/**
 * The innermost instance on the way to the diagram at `path` (node ids from the
 * root), with the path of that instance: the definition an edit there changes.
 */
export function enclosingInstance(
  doc: Pick<Model, "diagram">,
  path: readonly string[],
): { name: string; node: ModelNode; path: string[]; inner: string[] } | null {
  let found: { name: string; node: ModelNode; path: string[]; inner: string[] } | null = null;
  let diagram = doc.diagram;
  for (let k = 0; k < path.length; k += 1) {
    const node = diagram.nodes.find((entry) => entry.id === path[k]);
    if (node === undefined || !isSubsystemNode(node)) {
      break;
    }
    const name = node.block.subsystem.definition;
    if (name !== undefined) {
      found = { name, node, path: path.slice(0, k + 1), inner: [] };
    }
    diagram = node.block.subsystem.diagram;
  }
  if (found === null) {
    return null;
  }
  // The names from the instance down to the open diagram: the prefix of a pinned path.
  const names: string[] = [];
  let inside = (found.node as SubsystemNode).block.subsystem.diagram;
  for (const id of path.slice(found.path.length)) {
    const node = inside.nodes.find((entry) => entry.id === id);
    if (node === undefined || !isSubsystemNode(node)) {
      break;
    }
    names.push(node.name);
    inside = node.block.subsystem.diagram;
  }
  return { ...found, inner: names };
}

// ---------------------------------------------------------------------------
// Loading and saving
// ---------------------------------------------------------------------------

function refName(node: ModelNode): string | null {
  if (!("ref" in node.block) || !node.block.ref.startsWith(PROJECT_PREFIX)) {
    return null;
  }
  return node.block.ref.slice(PROJECT_PREFIX.length);
}

/**
 * The model as the editor holds it: every instance (`ref: project:<Name>` of a
 * definition) as a working copy, and the definitions themselves, hydrated the
 * same way, in `definitions`. A definition that contains itself is left as a
 * reference, which the compiler reports.
 */
export function hydrateModel(model: Model, files: Definitions): Model {
  const names = Object.keys(files);
  if (names.length === 0) {
    return model;
  }
  const hydrated = new Map<string, SubsystemDefinition>();
  const building = new Set<string>();
  const definitionOf = (name: string): SubsystemDefinition | undefined => {
    const done = hydrated.get(name);
    if (done !== undefined) {
      return done;
    }
    const file = files[name];
    if (file === undefined || building.has(name)) {
      return undefined;
    }
    building.add(name);
    const result: SubsystemDefinition = { ...file, name, diagram: hydrateDiagram(file.diagram) };
    building.delete(name);
    hydrated.set(name, result);
    return result;
  };
  const hydrateDiagram = (diagram: ModelDiagram): ModelDiagram => {
    let changed = false;
    const nodes = diagram.nodes.map((node) => {
      if (isSubsystemNode(node)) {
        const inner = hydrateDiagram(node.block.subsystem.diagram);
        if (inner === node.block.subsystem.diagram) {
          return node;
        }
        changed = true;
        return withSubsystem(node, { ...node.block.subsystem, diagram: inner });
      }
      const name = refName(node);
      const definition = name === null ? undefined : definitionOf(name);
      if (definition === undefined) {
        return node;
      }
      changed = true;
      const { params, starts, ...rest } = node;
      const own = { params, starts };
      return {
        ...rest,
        block: { subsystem: instanceSubsystem(definition, (kind, path) => own[kind]?.[path]) },
      } as ModelNode;
    });
    return changed ? { ...diagram, nodes } : diagram;
  };
  const diagram = hydrateDiagram(model.diagram);
  const definitions: Definitions = {};
  for (const name of names.sort()) {
    const definition = definitionOf(name);
    if (definition !== undefined) {
      definitions[name] = definition;
    }
  }
  return { ...model, diagram, definitions };
}

function dehydrateDiagram(diagram: ModelDiagram, definitions: Definitions): ModelDiagram {
  let changed = false;
  const nodes = diagram.nodes.map((node) => {
    if (!isSubsystemNode(node)) {
      return node;
    }
    const subsystem = node.block.subsystem;
    const definition = subsystem.definition === undefined ? undefined : definitions[subsystem.definition];
    if (definition === undefined) {
      const inner = dehydrateDiagram(subsystem.diagram, definitions);
      if (inner === subsystem.diagram && subsystem.definition === undefined) {
        return node;
      }
      changed = true;
      // A copy of a definition this project does not have is an ordinary subsystem.
      return withSubsystem(node, { ports: subsystem.ports, diagram: inner });
    }
    changed = true;
    const own: Record<PinKind, Record<string, string>> = { params: {}, starts: {} };
    for (const entry of instanceValues(subsystem, definition)) {
      if (entry.changed && entry.value !== undefined) {
        own[entry.kind][entry.path] = entry.value;
      }
    }
    const { params: _params, starts: _starts, constants: _constants, ...rest } = node;
    const instance: ModelNode = {
      ...rest,
      block: { ref: `${PROJECT_PREFIX}${definition.name}` },
    };
    if (Object.keys(own.params).length > 0) {
      instance.params = own.params;
    }
    if (Object.keys(own.starts).length > 0) {
      instance.starts = own.starts;
    }
    return instance;
  });
  return changed ? { ...diagram, nodes } : diagram;
}

/** A definition as its library file holds it: instances inside it as references. */
export function definitionFile(
  definition: SubsystemDefinition,
  definitions: Definitions,
): SubsystemDefinition {
  return { ...definition, diagram: dehydrateDiagram(definition.diagram, definitions) };
}

/**
 * What saving writes: the model with its instances as references and without
 * `definitions`, and every definition as its library file.
 */
export function dehydrateModel(doc: Model): { model: Model; files: Definitions } {
  if (doc.definitions === undefined) {
    return { model: doc, files: {} };
  }
  const definitions = doc.definitions;
  const { definitions: _dropped, ...rest } = doc;
  const model: Model = { ...rest, diagram: dehydrateDiagram(doc.diagram, definitions) };
  const files: Definitions = {};
  for (const [name, definition] of Object.entries(definitions)) {
    files[name] = definitionFile(definition, definitions);
  }
  return { model, files };
}

// ---------------------------------------------------------------------------
// Keeping the copies equal
// ---------------------------------------------------------------------------

interface Located {
  name: string;
  subsystem: Subsystem;
}

/** Every instance in a model by where it is: the container and the node ids down to it. */
function locate(doc: Pick<Model, "diagram" | "definitions">): Map<string, Located> {
  const found = new Map<string, Located>();
  const walk = (diagram: ModelDiagram, key: string): void => {
    for (const node of diagram.nodes) {
      if (!isSubsystemNode(node)) {
        continue;
      }
      const here = `${key}/${node.id}`;
      const name = node.block.subsystem.definition;
      if (name !== undefined) {
        found.set(here, { name, subsystem: node.block.subsystem });
      }
      walk(node.block.subsystem.diagram, here);
    }
  };
  walk(doc.diagram, "model");
  for (const [name, definition] of Object.entries(doc.definitions ?? {})) {
    walk(definition.diagram, `definition:${name}`);
  }
  return found;
}

/** A port's identity through a rename: the inner node and port it exposes. */
function portKey(port: ModelSubsystemPort): string {
  return `${port.node}\u0000${port.port}`;
}

/**
 * How the ports of an instance changed: `renamed` maps an old name to its new
 * one (same inner port), `removed` lists the names that are gone.
 */
function portChanges(
  before: readonly ModelSubsystemPort[],
  after: readonly ModelSubsystemPort[],
): { renamed: Map<string, string>; removed: Set<string> } {
  const renamed = new Map<string, string>();
  const removed = new Set<string>();
  const names = new Set(after.map((port) => port.name));
  const byKey = new Map(after.map((port) => [portKey(port), port.name]));
  for (const port of before) {
    if (names.has(port.name)) {
      continue;
    }
    const next = byKey.get(portKey(port));
    if (next === undefined) {
      removed.add(port.name);
    } else {
      renamed.set(port.name, next);
    }
  }
  return { renamed, removed };
}

const NO_PORTS: ModelSubsystemPort[] = [];

/**
 * `diagram` with every instance replaced by `replace(node)` (null keeps it), at
 * any depth, and with everything around a replaced instance following its ports:
 * a renamed port keeps its connections, a removed one loses them (and the probe
 * links on them). `ports` are the ports of the subsystem that owns `diagram`:
 * one that exposes a port of a replaced instance is renamed or removed with it,
 * and that change is carried on to the owner's own surroundings, level by level.
 */
function replaceInstances(
  diagram: ModelDiagram,
  replace: (node: SubsystemNode) => Subsystem | null,
  ports: ModelSubsystemPort[],
): { diagram: ModelDiagram; ports: ModelSubsystemPort[] } {
  const result = replaceInside(diagram, replace, ports);
  return { diagram: result.diagram, ports: result.ports };
}

function replaceInside(
  diagram: ModelDiagram,
  replace: (node: SubsystemNode) => Subsystem | null,
  ports: ModelSubsystemPort[],
): { diagram: ModelDiagram; ports: ModelSubsystemPort[] } {
  let changed = false;
  const renames = new Map<string, Map<string, string>>();
  const removals = new Map<string, Set<string>>();
  const nodes = diagram.nodes.map((node) => {
    if (!isSubsystemNode(node)) {
      return node;
    }
    const replacement = node.block.subsystem.definition === undefined ? null : replace(node);
    if (replacement !== null) {
      if (replacement === node.block.subsystem) {
        return node;
      }
      changed = true;
      const { renamed, removed } = portChanges(node.block.subsystem.ports, replacement.ports);
      if (renamed.size > 0) {
        renames.set(node.id, renamed);
      }
      if (removed.size > 0) {
        removals.set(node.id, removed);
      }
      return withSubsystem(node, replacement);
    }
    const own = node.block.subsystem;
    const inner = replaceInside(own.diagram, replace, own.ports);
    if (inner.diagram === own.diagram && inner.ports === own.ports) {
      return node;
    }
    changed = true;
    if (inner.ports !== own.ports) {
      // This subsystem exposed a port of an instance inside it: its own port changed too.
      const { renamed, removed } = portChanges(own.ports, inner.ports);
      if (renamed.size > 0) {
        renames.set(node.id, renamed);
      }
      if (removed.size > 0) {
        removals.set(node.id, removed);
      }
    }
    return withSubsystem(node, {
      ...own,
      diagram: inner.diagram,
      ports: inner.ports,
    });
  });
  if (!changed) {
    return { diagram, ports };
  }
  if (renames.size === 0 && removals.size === 0) {
    return { diagram: { ...diagram, nodes }, ports };
  }
  // The owner's ports that expose a changed port of a node of this diagram.
  let ownerPorts = ports;
  if (ports.some((port) => renames.get(port.node)?.has(port.port) === true || removals.get(port.node)?.has(port.port) === true)) {
    ownerPorts = ports
      .filter((port) => removals.get(port.node)?.has(port.port) !== true)
      .map((port) => {
        const renamed = renames.get(port.node)?.get(port.port);
        return renamed === undefined ? port : { ...port, port: renamed };
      });
  }
  const dropped = new Set<string>();
  const connections: ModelConnection[] = [];
  for (const connection of diagram.connections) {
    let next = connection;
    let gone = false;
    for (const side of ["from", "to"] as const) {
      const end = next[side];
      if (end.port === undefined) {
        continue;
      }
      if (removals.get(end.node)?.has(end.port) === true) {
        gone = true;
      }
      const renamed = renames.get(end.node)?.get(end.port);
      if (renamed !== undefined) {
        next = { ...next, [side]: { ...end, port: renamed } };
      }
    }
    if (gone) {
      dropped.add(connection.id);
    } else {
      connections.push(next);
    }
  }
  const result: ModelDiagram = { ...diagram, nodes, connections };
  if (dropped.size > 0 && diagram.probes !== undefined) {
    result.probes = diagram.probes.map((probe) => ({
      ...probe,
      links: probe.links.filter((link) => !dropped.has(link.connection)),
    }));
  }
  return { diagram: result, ports: ownerPorts };
}

function sameContent(a: unknown, b: unknown): boolean {
  return a === b || JSON.stringify(a) === JSON.stringify(b);
}

export type SyncResult = { ok: true; model: Model } | { ok: false; error: string };

/**
 * Make every instance equal to its definition again after an edit took `before`
 * to `now`.
 *
 * - An instance that changed is the new definition: its diagram and ports, with
 *   the definition's own value kept at every pinned path.
 * - Every other instance gets the definition's diagram and ports with its own
 *   pinned values, wherever it is: in the model, inside another instance, inside
 *   another definition.
 * - A definition that changed by itself (a pin, a description) reaches its
 *   instances the same way. Unpinning a value returns every instance to the
 *   definition's value.
 * - A new instance (pasted, dropped from the library) never changes the
 *   definition: it takes the definition's diagram, with its own pinned values.
 * - A copy of a definition the model does not know becomes an ordinary subsystem.
 *
 * `now` is returned as it is when nothing has to change. A definition that would
 * contain itself is refused.
 */
export function syncLinked(
  now: Model,
  before: Model | null,
  preferred: ReadonlySet<string> = new Set(),
): SyncResult {
  const definitions = now.definitions ?? {};
  const present = locate(now);
  if (present.size === 0 && now.definitions === before?.definitions) {
    return { ok: true, model: now };
  }
  const earlier = before === null ? new Map<string, Located>() : locate(before);

  // What to bring in line: the definitions with an edited instance, a changed or new
  // definition, or a new instance.
  const sources = new Map<string, string>();
  const stale = new Set<string>();
  let orphans = false;
  for (const [key, entry] of present) {
    if (definitions[entry.name] === undefined) {
      orphans = true;
      continue;
    }
    const old = earlier.get(key);
    if (old === undefined || old.name !== entry.name) {
      stale.add(entry.name);
    } else if (old.subsystem !== entry.subsystem) {
      stale.add(entry.name);
      // The instance the user is in wins when one edit touched several copies.
      if (!sources.has(entry.name) || preferred.has(key)) {
        sources.set(entry.name, key);
      }
    }
  }
  for (const name of Object.keys(definitions)) {
    if (definitions[name] !== before?.definitions?.[name]) {
      stale.add(name);
    }
  }
  if (stale.size === 0 && !orphans) {
    return { ok: true, model: now };
  }

  let model = now;
  if (orphans) {
    const strip = (diagram: ModelDiagram): ModelDiagram => {
      let changed = false;
      const nodes = diagram.nodes.map((node) => {
        if (!isSubsystemNode(node)) {
          return node;
        }
        const { definition, ...plain } = node.block.subsystem;
        const unknown = definition !== undefined && definitions[definition] === undefined;
        const inner = strip(plain.diagram);
        if (!unknown && inner === plain.diagram) {
          return node;
        }
        changed = true;
        return withSubsystem(node, unknown ? { ...plain, diagram: inner } : { ...node.block.subsystem, diagram: inner });
      });
      return changed ? { ...diagram, nodes } : diagram;
    };
    const stripped: Definitions = {};
    for (const [name, definition] of Object.entries(definitions)) {
      const diagram = strip(definition.diagram);
      stripped[name] = diagram === definition.diagram ? definition : { ...definition, diagram };
    }
    model = { ...model, diagram: strip(model.diagram), definitions: stripped };
  }

  // Inner definitions first: an instance of `Leg` holds copies of `Actuator`, so
  // `Actuator` has to be right before `Leg` is taken from one of its instances.
  const depends = (name: string): Set<string> => {
    const key = sources.get(name);
    const source = key === undefined ? undefined : locate(model).get(key);
    const diagram = source?.subsystem.diagram ?? model.definitions?.[name]?.diagram;
    return diagram === undefined ? new Set() : linkedNamesIn(diagram);
  };
  const order: string[] = [];
  const state = new Map<string, "open" | "done">();
  let cycle: string | null = null;
  const visit = (name: string): void => {
    if (state.get(name) === "done" || cycle !== null) {
      return;
    }
    if (state.get(name) === "open") {
      cycle = name;
      return;
    }
    state.set(name, "open");
    for (const inner of depends(name)) {
      if (model.definitions?.[inner] !== undefined) {
        visit(inner);
      }
    }
    state.set(name, "done");
    order.push(name);
  };
  for (const name of Object.keys(model.definitions ?? {}).sort()) {
    visit(name);
  }
  if (cycle !== null) {
    return {
      ok: false,
      error: `The library subsystem "${cycle}" cannot hold an instance of itself, directly or through another library subsystem.`,
    };
  }

  for (const name of order) {
    if (!stale.has(name) && !order.some((inner) => stale.has(inner) && depends(name).has(inner))) {
      continue;
    }
    const current = model.definitions?.[name];
    if (current === undefined) {
      continue;
    }
    let definition = current;
    const key = sources.get(name);
    const source = key === undefined ? undefined : locate(model).get(key);
    // A pin whose block was renamed in the edited instance: new path -> the path it had.
    const formerly = new Map<string, string>();
    if (source !== undefined) {
      // The edited instance is the definition, except where it holds a value of its own.
      // A pin names blocks; it follows them by id, so a renamed block keeps its pin, the
      // definition's value and every instance's own value. A pin of a removed block goes.
      let diagram = source.subsystem.diagram;
      let pins = current.pins;
      for (const kind of PIN_KINDS) {
        const before = pinsOf(current, kind);
        const after: string[] = [];
        for (const path of before) {
          const now = pinPathIn(current.diagram, path, diagram);
          if (now === null) {
            continue;
          }
          if (pinResolves(current.diagram, path)) {
            diagram = writePin(diagram, kind, now, readPin(current.diagram, kind, path));
          }
          if (now !== path) {
            formerly.set(`${kind}:${now}`, path);
          }
          if (!after.includes(now)) {
            after.push(now);
          }
        }
        if (after.length !== before.length || after.some((path, k) => path !== before[k])) {
          pins = { ...(pins ?? {}), [kind]: after };
          if (after.length === 0) {
            delete pins[kind];
          }
        }
      }
      if (pins !== undefined && Object.keys(pins).length === 0) {
        pins = undefined;
      }
      if (
        pins !== current.pins ||
        !sameContent(diagram, current.diagram) ||
        !sameContent(source.subsystem.ports, current.ports)
      ) {
        definition = { ...current, ports: source.subsystem.ports, diagram };
        if (pins === undefined) {
          delete definition.pins;
        } else {
          definition.pins = pins;
        }
      }
    }
    const replace = (node: SubsystemNode): Subsystem | null => {
      const subsystem = node.block.subsystem;
      if (subsystem.definition !== name) {
        return null;
      }
      const next = instanceSubsystem(definition, (kind, path) => {
        // The instance's own value, read where it has it: under the name the block had
        // before a rename, else under its name now. A value the instance has not got yet
        // (a block that is new to it) is the definition's.
        const old = formerly.get(`${kind}:${path}`);
        if (old !== undefined && pinResolves(subsystem.diagram, old)) {
          return readPin(subsystem.diagram, kind, old);
        }
        return pinResolves(subsystem.diagram, path)
          ? readPin(subsystem.diagram, kind, path)
          : undefined;
      });
      const same =
        sameContent(next.diagram, subsystem.diagram) && sameContent(next.ports, subsystem.ports);
      return same ? subsystem : next;
    };
    const nextDefinitions: Definitions = {};
    for (const [other, entry] of Object.entries(model.definitions ?? {})) {
      const base = other === name ? definition : entry;
      const result = replaceInstances(base.diagram, replace, base.ports);
      nextDefinitions[other] =
        result.diagram === base.diagram && result.ports === base.ports
          ? base
          : { ...base, diagram: result.diagram, ports: result.ports };
    }
    model = {
      ...model,
      diagram: replaceInstances(model.diagram, replace, NO_PORTS).diagram,
      definitions: nextDefinitions,
    };
    stale.add(name);
  }
  return { ok: true, model };
}

/** The key `syncLinked` knows the instance at `path` (node ids from the root) by. */
export function instanceKey(path: readonly string[]): string {
  return ["model", ...path].join("/");
}

// ---------------------------------------------------------------------------
// Making and removing links
// ---------------------------------------------------------------------------

/** Why `name` cannot name a new library subsystem, or null when it can. */
export function definitionNameProblem(
  name: string,
  definitions: Definitions | undefined,
  blockNames: readonly string[],
): string | null {
  if (name.length === 0) {
    return "Enter a name.";
  }
  if (!DEFINITION_NAME_PATTERN.test(name)) {
    return "A name starts with a letter or underscore and uses only letters, digits and underscores.";
  }
  const lower = name.toLowerCase();
  if (Object.keys(definitions ?? {}).some((entry) => entry.toLowerCase() === lower)) {
    return `The project library already has a subsystem named "${name}".`;
  }
  if (blockNames.some((entry) => entry.toLowerCase() === lower)) {
    return `The library already has a block named "${name}".`;
  }
  return null;
}

/** A name for the library subsystem made from a node called `nodeName`. */
export function suggestedDefinitionName(
  nodeName: string,
  definitions: Definitions | undefined,
  blockNames: readonly string[],
): string {
  const base = nodeName.replace(/\d+$/, "") || nodeName;
  const start = /^[A-Z]/.test(base) ? base : `${base.charAt(0).toUpperCase()}${base.slice(1)}`;
  for (const candidate of [start, ...Array.from({ length: 50 }, (_, k) => `${start}${k + 2}`)]) {
    if (definitionNameProblem(candidate, definitions, blockNames) === null) {
      return candidate;
    }
  }
  return start;
}

/** The definition a subsystem becomes when it is made reusable: no pins yet. */
export function definitionFrom(name: string, subsystem: Subsystem): SubsystemDefinition {
  return {
    format: "bgsim.subsystem",
    name,
    ports: subsystem.ports,
    diagram: subsystem.diagram,
  };
}

/** `definition` with one path pinned or unpinned. */
export function withPin(
  definition: SubsystemDefinition,
  kind: PinKind,
  path: string,
  pinned: boolean,
): SubsystemDefinition {
  const current = pinsOf(definition, kind);
  const has = current.includes(path);
  if (has === pinned) {
    return definition;
  }
  const list = pinned ? [...current, path] : current.filter((entry) => entry !== path);
  const pins = { ...(definition.pins ?? {}), [kind]: list };
  if (list.length === 0) {
    delete pins[kind];
  }
  const next: SubsystemDefinition = { ...definition, pins };
  if (Object.keys(pins).length === 0) {
    delete next.pins;
  }
  return next;
}

/** The instances of `name` in the model whose value at `path` differs from the definition. */
export function instancesWithOwnValue(
  doc: Pick<Model, "diagram" | "definitions">,
  name: string,
  kind: PinKind,
  path: string,
): string[] {
  const definition = doc.definitions?.[name];
  if (definition === undefined) {
    return [];
  }
  const base = readPin(definition.diagram, kind, path);
  const names: string[] = [];
  const walk = (diagram: ModelDiagram, prefix: string): void => {
    for (const node of diagram.nodes) {
      if (!isSubsystemNode(node)) {
        continue;
      }
      const here = prefix.length === 0 ? node.name : `${prefix}/${node.name}`;
      if (
        node.block.subsystem.definition === name &&
        readPin(node.block.subsystem.diagram, kind, path) !== base
      ) {
        names.push(here);
      }
      walk(node.block.subsystem.diagram, here);
    }
  };
  walk(doc.diagram, "");
  return names;
}

/**
 * The connections on ports `ports` of every instance of `name` in the model, as
 * `Arm/Act2.shaft → Arm/Load.p` lines: what removing those ports from the
 * definition removes.
 */
export function instancePortConnections(
  doc: Pick<Model, "diagram">,
  name: string,
  ports: readonly string[],
): string[] {
  const wanted = new Set(ports);
  const lines: string[] = [];
  const walk = (diagram: ModelDiagram, prefix: string): void => {
    const names = new Map(diagram.nodes.map((node) => [node.id, node.name]));
    const instances = new Set(
      diagram.nodes
        .filter((node) => isSubsystemNode(node) && node.block.subsystem.definition === name)
        .map((node) => node.id),
    );
    const label = (end: { node: string; port?: string }): string =>
      `${prefix}${names.get(end.node) ?? end.node}${end.port === undefined ? "" : `.${end.port}`}`;
    for (const connection of diagram.connections) {
      const hit = [connection.from, connection.to].some(
        (end) => instances.has(end.node) && end.port !== undefined && wanted.has(end.port),
      );
      if (hit) {
        lines.push(`${label(connection.from)} → ${label(connection.to)}`);
      }
    }
    for (const node of diagram.nodes) {
      // The copies inside another instance of `name` are the same connections again.
      if (isSubsystemNode(node) && node.block.subsystem.definition !== name) {
        walk(node.block.subsystem.diagram, `${prefix}${node.name}/`);
      }
    }
  };
  walk(doc.diagram, "");
  return lines;
}
