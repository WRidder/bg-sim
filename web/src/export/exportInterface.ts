/**
 * What an export publishes, read from the model document (plan/EXPORT_PLAN.md D-EX9, J-EX11).
 *
 * The rules are the exporter's (`BGSim.Export.scope_document` and the marker scan of
 * `export_model`); the dialog only previews them, the backend's report is the authority:
 *
 * - the whole model publishes its Export markers under their instance paths
 *   (`ExportInput` → input, `ExportInputPass` → input (pass-through in simulation),
 *   `ExportOutput` → output, `ExportParameter` → parameter);
 * - a subsystem scope publishes its ports: a signal port under its name, a scalar power port
 *   as `<port>_e`/`<port>_f` (the host imposes the effort or the flow and reads the
 *   conjugate), plus the markers inside the subsystem (`<subsystem>/<marker>`).
 */

import type { Model, ModelDiagram, ModelNode } from "../contracts/model";

export const MARKER_INPUT = "stdlib:converters/ExportInput";
export const MARKER_INPUT_PASS = "stdlib:converters/ExportInputPass";
export const MARKER_OUTPUT = "stdlib:converters/ExportOutput";
export const MARKER_PARAMETER = "stdlib:converters/ExportParameter";

/** The power-port domains a scope can take (scalar ports only). */
const SCOPE_DOMAINS = new Set([
  "Generic",
  "Electrical",
  "Translation",
  "Rotation",
  "Hydraulic",
  "Thermal",
]);

export type PowerChoice = "effort" | "flow";

export interface SubsystemOption {
  /** Instance path, the request's `scope`. */
  path: string;
  name: string;
}

export interface InterfaceEntry {
  name: string;
  /** Where it comes from, for the preview ("ExportInput", "signal port", "effort on P"). */
  detail: string;
}

export interface PowerPortEntry {
  name: string;
  domain: string;
  choice: PowerChoice;
}

export interface InterfacePreview {
  inputs: InterfaceEntry[];
  outputs: InterfaceEntry[];
  parameters: InterfaceEntry[];
  /** The scope's scalar power ports, each with its effort/flow choice. */
  powerPorts: PowerPortEntry[];
  /** Ports the scope cannot export yet (vector signals, multibond power ports). */
  problems: string[];
  /** The scope path does not name a subsystem of the model. */
  missingScope: boolean;
}

function isSubsystem(node: ModelNode): node is ModelNode & {
  block: Extract<ModelNode["block"], { subsystem: unknown }>;
} {
  return "subsystem" in node.block;
}

function* walk(diagram: ModelDiagram, prefix: string): Generator<[string, ModelNode]> {
  for (const node of diagram.nodes) {
    const path = `${prefix}${node.name}`;
    yield [path, node];
    if (isSubsystem(node)) {
      yield* walk(node.block.subsystem.diagram, `${path}/`);
    }
  }
}

/** Every subsystem of the model, depth first, by instance path. */
export function listSubsystems(doc: Pick<Model, "diagram">): SubsystemOption[] {
  const out: SubsystemOption[] = [];
  for (const [path, node] of walk(doc.diagram, "")) {
    if (isSubsystem(node)) {
      out.push({ path, name: node.name });
    }
  }
  return out;
}

/** The subsystem node at `path`, or null. */
export function findSubsystem(doc: Pick<Model, "diagram">, path: string): ModelNode | null {
  let diagram = doc.diagram;
  let node: ModelNode | null = null;
  for (const segment of path.split("/")) {
    node = diagram.nodes.find((entry) => entry.name === segment) ?? null;
    if (node === null || !isSubsystem(node)) {
      return null;
    }
    diagram = node.block.subsystem.diagram;
  }
  return node;
}

function size(shape: readonly number[] | undefined): number {
  return (shape ?? [1]).reduce((product, n) => product * n, 1);
}

function scalarPowerPorts(node: ModelNode): { name: string; domain: string }[] {
  if (!isSubsystem(node)) {
    return [];
  }
  return node.block.subsystem.ports
    .filter((port) => port.kind === "power")
    .filter((port) => SCOPE_DOMAINS.has(port.domain) && size(port.size) === 1)
    .map((port) => ({ name: port.name, domain: port.domain }));
}

/** Effort for every scalar power port of the scope (the dialog's default). */
export function defaultPowerInputs(
  doc: Pick<Model, "diagram">,
  scope: string | null,
): Record<string, PowerChoice> {
  const node = scope === null ? null : findSubsystem(doc, scope);
  const out: Record<string, PowerChoice> = {};
  if (node !== null) {
    for (const port of scalarPowerPorts(node)) {
      out[port.name] = "effort";
    }
  }
  return out;
}

function markers(diagram: ModelDiagram, prefix: string, preview: InterfacePreview): void {
  for (const [path, node] of walk(diagram, prefix)) {
    const ref = "ref" in node.block ? node.block.ref : null;
    if (ref === MARKER_INPUT) {
      preview.inputs.push({ name: path, detail: "ExportInput" });
    } else if (ref === MARKER_INPUT_PASS) {
      preview.inputs.push({ name: path, detail: "ExportInputPass" });
    } else if (ref === MARKER_OUTPUT) {
      preview.outputs.push({ name: path, detail: "ExportOutput" });
    } else if (ref === MARKER_PARAMETER) {
      preview.parameters.push({ name: path, detail: "ExportParameter" });
    }
  }
}

/** The interface an export of `scope` (null: the whole model) publishes. */
export function previewInterface(
  doc: Pick<Model, "diagram">,
  scope: string | null,
  powerInputs: Record<string, PowerChoice>,
): InterfacePreview {
  const preview: InterfacePreview = {
    inputs: [],
    outputs: [],
    parameters: [],
    powerPorts: [],
    problems: [],
    missingScope: false,
  };
  if (scope === null) {
    markers(doc.diagram, "", preview);
    return preview;
  }
  const node = findSubsystem(doc, scope);
  if (node === null || !isSubsystem(node)) {
    preview.missingScope = true;
    return preview;
  }
  for (const port of node.block.subsystem.ports) {
    if (port.kind === "signal") {
      if (size(port.size) !== 1) {
        preview.problems.push(
          `The vector signal port ${port.name} cannot be an export interface yet (E112).`,
        );
      } else if (port.direction === "input") {
        preview.inputs.push({ name: port.name, detail: "signal port" });
      } else {
        preview.outputs.push({ name: port.name, detail: "signal port" });
      }
      continue;
    }
    if (!SCOPE_DOMAINS.has(port.domain) || size(port.size) !== 1) {
      preview.problems.push(
        `The ${port.domain} power port ${port.name} cannot be an export interface yet (E112).`,
      );
      continue;
    }
    const choice: PowerChoice = powerInputs[port.name] ?? "effort";
    preview.powerPorts.push({ name: port.name, domain: port.domain, choice });
    const [imposed, measured] = choice === "effort" ? ["e", "f"] : ["f", "e"];
    const conjugate = choice === "effort" ? "flow" : "effort";
    preview.inputs.push({ name: `${port.name}_${imposed}`, detail: `${choice} on ${port.name}` });
    preview.outputs.push({
      name: `${port.name}_${measured}`,
      detail: `${conjugate} on ${port.name}${choice === "effort" ? ", into the subsystem" : ""}`,
    });
  }
  // The scoped model has the subsystem at its root: markers inside are <name>/<marker>.
  markers(node.block.subsystem.diagram, `${node.name}/`, preview);
  return preview;
}

/** True when the export would publish nothing (W209). */
export function isEmptyInterface(preview: InterfacePreview): boolean {
  return preview.inputs.length === 0 && preview.outputs.length === 0;
}
