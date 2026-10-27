/**
 * Which run signals a canvas element can plot (plan 7.5: "The canvas context
 * menu on a port, bond or instance offers 'Plot effort / flow / power' and
 * 'Plot all outputs'").
 *
 * The mapping is deliberately pure and independent of the editor: a power
 * connection contributes the `e`, `f` and `P` fields of one of its ports, and
 * an instance contributes the recorded signals of kind `output` on its path.
 * Signal ids are the worker's own names (plan 3.5), e.g. `Motor1/shaft.f`, so
 * the menu can hand an id straight to the run store.
 */

import type {
  Model,
  ModelConnection,
  ModelEndpoint,
  ModelNode,
} from "../contracts/model";
import type { RunSignal } from "../contracts/run-manifest";

/** The three plot variables of a power port (plan 7.5). */
export type PlotVariable = "effort" | "flow" | "power";

export interface PlotTarget {
  /** The manifest signal id, e.g. `Motor1/shaft.f`. */
  signalId: string;
  /** Menu text: "Plot effort". */
  label: string;
  /** Stable test id: `plot-effort`. */
  testId: string;
  /** Longer text for the item's title, naming the port. */
  detail: string;
}

/** The variable suffix of each plot variable in a signal id. */
export const PLOT_VARIABLE_SUFFIX: Record<PlotVariable, "e" | "f" | "P"> = {
  effort: "e",
  flow: "f",
  power: "P",
};

export const PLOT_VARIABLES: readonly PlotVariable[] = [
  "effort",
  "flow",
  "power",
];

/** `path/port.e`, with the port part omitted for a flat instance signal. */
export function portSignalId(
  path: string,
  port: string,
  variable: PlotVariable,
): string {
  return `${path}/${port}.${PLOT_VARIABLE_SUFFIX[variable]}`;
}

function nodeById(model: Model, nodeId: string): ModelNode | undefined {
  return model.diagram.nodes.find((node) => node.id === nodeId);
}

/** The port a connection endpoint names, resolved to its instance path. */
export function endpointPort(
  model: Model,
  endpoint: ModelEndpoint,
): { path: string; port: string } | null {
  const port = endpoint.port?.trim() ?? "";
  if (port.length === 0) {
    return null;
  }
  const node = nodeById(model, endpoint.node);
  if (node === undefined) {
    return null;
  }
  return { path: node.name, port };
}

/**
 * The plot targets of a bond or wire. The source endpoint wins (the bond's
 * direction is `from -> to`); a junction endpoint has no port, so the target
 * endpoint is used instead. Signal connections carry no effort/flow pair.
 *
 * The targets are returned even before a run exists: the store then tells the
 * user to run the model, which is friendlier than a hidden feature.
 */
export function connectionPlotTargets(
  model: Model,
  connection: ModelConnection,
): PlotTarget[] {
  if (connection.kind === "signal") {
    return [];
  }
  const port =
    endpointPort(model, connection.from) ?? endpointPort(model, connection.to);
  if (port === null) {
    return [];
  }
  return PLOT_VARIABLES.map((variable) => ({
    signalId: portSignalId(port.path, port.port, variable),
    label: `Plot ${variable}`,
    testId: `plot-${variable}`,
    detail: `${port.path}/${port.port}.${PLOT_VARIABLE_SUFFIX[variable]}`,
  }));
}

/**
 * Every recorded output of one instance, in manifest order. The worker gives
 * flat instances the path of the node name (`Motor1/w`), so an exact path
 * match is the instance's own outputs and not those of a nested subsystem.
 *
 * `pathPrefix` is the active subsystem path without a trailing slash (for
 * example `Rig/Axis`); outputs of a node inside it are recorded as
 * `Rig/Axis/Motor1/w`.
 */
export function nodeOutputTargets(
  signals: readonly RunSignal[],
  node: ModelNode,
  pathPrefix = "",
): PlotTarget[] {
  const prefix = pathPrefix.replace(/\/+$/, "");
  const path = prefix.length > 0 ? `${prefix}/${node.name}` : node.name;
  return signals
    .filter((signal) => signal.kind === "output" && signal.path === path)
    .map((signal) => ({
      signalId: signal.id,
      label: "Plot all outputs",
      testId: "plot-all-outputs",
      detail: signal.id,
    }));
}

/** The unique output ids of a node (one id for the shared menu item). */
export function nodeOutputIds(
  signals: readonly RunSignal[],
  node: ModelNode,
  pathPrefix = "",
): string[] {
  const seen = new Set<string>();
  const ids: string[] = [];
  for (const target of nodeOutputTargets(signals, node, pathPrefix)) {
    if (!seen.has(target.signalId)) {
      seen.add(target.signalId);
      ids.push(target.signalId);
    }
  }
  return ids;
}

/** The node of a right-clicked xyflow element, or undefined. */
export function nodeForMenu(
  model: Model,
  nodeId: string,
): ModelNode | undefined {
  return nodeById(model, nodeId);
}

/** The connection of a right-clicked xyflow element, or undefined. */
export function connectionForMenu(
  model: Model,
  connectionId: string,
): ModelConnection | undefined {
  return model.diagram.connections.find(
    (connection) => connection.id === connectionId,
  );
}
