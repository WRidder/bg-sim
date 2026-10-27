/**
 * Signals an oscilloscope probe can tap from one circuit connection.
 *
 * A probe is a side-channel observer: these ids are only plot signals, never
 * equations. Bonds and wires expose effort/flow/power; a signal connection
 * exposes the driving output value.
 */

import type { Model, ModelConnection, ModelDiagram, ModelProbe } from "../contracts/model";
import {
  PLOT_VARIABLE_SUFFIX,
  PLOT_VARIABLES,
} from "../plot/plotTargets";

export interface ProbeSignalOption {
  id: string;
  label: string;
  detail: string;
}

function endpointPort(
  diagram: ModelDiagram,
  endpoint: ModelConnection["from"],
): { path: string; port: string } | null {
  const port = endpoint.port?.trim() ?? "";
  if (port.length === 0) {
    return null;
  }
  const node = diagram.nodes.find((entry) => entry.id === endpoint.node);
  return node === undefined ? null : { path: node.name, port };
}

export function probeSignalOptions(
  diagram: ModelDiagram,
  connection: ModelConnection,
): ProbeSignalOption[] {
  const port =
    endpointPort(diagram, connection.from) ?? endpointPort(diagram, connection.to);
  if (port === null) {
    return [];
  }
  if (connection.kind === "signal") {
    return [
      {
        id: `${port.path}/${port.port}`,
        label: `${port.path}.${port.port}`,
        detail: "signal value",
      },
    ];
  }
  return PLOT_VARIABLES.map((variable) => ({
    id: `${port.path}/${port.port}.${PLOT_VARIABLE_SUFFIX[variable]}`,
    label: `${port.path}.${port.port} ${variable}`,
    detail: `${port.path}/${port.port}.${PLOT_VARIABLE_SUFFIX[variable]}`,
  }));
}

/** Every signal selected by the probe's leads, in low-noise first-seen order. */
export function probeSignalIds(model: Model, probe: ModelProbe): string[] {
  const seen = new Set<string>();
  const ids: string[] = [];
  for (const link of probe.links) {
    const connection = model.diagram.connections.find(
      (entry) => entry.id === link.connection,
    );
    if (connection === undefined) {
      continue;
    }
    const available = probeSignalOptions(model.diagram, connection);
    const selected = link.signals;
    for (const id of selected) {
      if (available.some((option) => option.id === id) && !seen.has(id)) {
        seen.add(id);
        ids.push(id);
      }
    }
  }
  return ids;
}

/** All options across the probe's leads, keyed by signal id. */
export function probeOptions(model: Model, probe: ModelProbe): ProbeSignalOption[] {
  const seen = new Set<string>();
  const options: ProbeSignalOption[] = [];
  for (const link of probe.links) {
    const connection = model.diagram.connections.find(
      (entry) => entry.id === link.connection,
    );
    if (connection === undefined) {
      continue;
    }
    for (const option of probeSignalOptions(model.diagram, connection)) {
      if (!seen.has(option.id)) {
        seen.add(option.id);
        options.push(option);
      }
    }
  }
  return options;
}
