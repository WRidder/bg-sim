/**
 * Which recorded signals the automatic plot tab shows for the current canvas
 * selection: every signal owned by the selected block (or subsystem), or the
 * port variables / source signal of the selected connection.
 */

import type { Model, ModelConnection } from "../contracts/model";
import type { RunManifest, RunSignal } from "../contracts/run-manifest";
import {
  PLOT_VARIABLES,
  PLOT_VARIABLE_SUFFIX,
  endpointPort,
} from "../plot/plotTargets";
import { activeModel, subsystemPathCrumbs } from "../editor/subsystemPath";

export interface Selection {
  nodes: readonly string[];
  connections: readonly string[];
}

export interface AutoPlotSelection {
  /** Stable key for effects: node/connection id + resolved signal ids. */
  key: string;
  label: string;
  signalIds: string[];
}

function prefixPath(prefix: string, path: string): string {
  return prefix.length > 0 ? `${prefix}/${path}` : path;
}

function nodeSignals(
  nodePath: string,
  node: Model["diagram"]["nodes"][number],
  signals: readonly RunSignal[],
): RunSignal[] {
  if ("subsystem" in node.block) {
    // A subsystem selection shows its exposed outputs and everything recorded
    // inside it, not just signals whose path is exactly the subsystem name.
    return signals.filter(
      (signal) =>
        signal.path === nodePath || signal.path.startsWith(`${nodePath}/`),
    );
  }
  return signals.filter((signal) => signal.path === nodePath);
}

function connectionLabel(model: Model, connection: ModelConnection): string {
  const label = connection.label ?? null;
  if (label !== null && label.trim().length > 0) {
    return label;
  }
  const from = model.diagram.nodes.find((node) => node.id === connection.from.node);
  const to = model.diagram.nodes.find((node) => node.id === connection.to.node);
  const fromText = from?.name ?? connection.from.node;
  const toText = to?.name ?? connection.to.node;
  return `${fromText}/${connection.from.port ?? "·"} → ${toText}/${connection.to.port ?? "·"}`;
}

/**
 * Resolve the selected item to its recorded signal ids. The first selected
 * node wins, then the first selected connection; with no selection the tab is
 * empty.
 */
export function autoPlotSelection(
  doc: Model | null,
  activePath: readonly string[],
  selection: Selection,
  manifest: RunManifest | null,
): AutoPlotSelection | null {
  if (doc === null) {
    return null;
  }
  const model = activeModel(doc, activePath);
  if (model === null) {
    return null;
  }
  const prefix = subsystemPathCrumbs(doc, activePath)
    .map((crumb) => crumb.name)
    .join("/");
  const signals = manifest?.signals ?? [];

  const nodeId = selection.nodes[0];
  if (nodeId !== undefined) {
    const node = model.diagram.nodes.find((entry) => entry.id === nodeId);
    if (node === undefined) {
      return null;
    }
    const path = prefixPath(prefix, node.name);
    const ids = nodeSignals(path, node, signals).map((signal) => signal.id);
    return {
      key: `node:${nodeId}:${ids.join(",")}`,
      label: node.name,
      signalIds: ids,
    };
  }

  const connectionId = selection.connections[0];
  if (connectionId === undefined) {
    return null;
  }
  const connection = model.diagram.connections.find(
    (entry) => entry.id === connectionId,
  );
  if (connection === undefined) {
    return null;
  }
  const byId = new Map(signals.map((signal) => [signal.id, signal]));
  const ids: string[] = [];

  if (connection.kind === "signal") {
    const source = endpointPort(model, connection.from);
    if (source !== null) {
      const sourcePath = prefixPath(prefix, source.path);
      const exact = `${sourcePath}/${source.port}`;
      if (byId.has(exact)) {
        ids.push(exact);
      } else {
        // A subsystem/composite may expose the signal under a port alias.
        const match = signals.find(
          (signal) =>
            signal.path === sourcePath &&
            (signal.id === exact || signal.id.endsWith(`/${source.port}`)),
        );
        if (match !== undefined) {
          ids.push(match.id);
        }
      }
    }
  } else {
    const port =
      endpointPort(model, connection.from) ?? endpointPort(model, connection.to);
    if (port !== null) {
      const portPath = prefixPath(prefix, port.path);
      for (const variable of PLOT_VARIABLES) {
        const id = `${portPath}/${port.port}.${PLOT_VARIABLE_SUFFIX[variable]}`;
        if (byId.has(id)) {
          ids.push(id);
        }
      }
    }
  }

  return {
    key: `connection:${connectionId}:${ids.join(",")}`,
    label: connectionLabel(model, connection),
    signalIds: ids,
  };
}
