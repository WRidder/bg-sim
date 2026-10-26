/**
 * Apply one `model.check` result to the flow elements (plan 3.6 and 7.3).
 *
 * W1.1's `buildDiagram` is pure and knows nothing about the worker. This layer
 * puts the worker's adopted domain on every power edge and port, the causal
 * stroke on every bond and the unit factor on every signal wire. The values
 * win over the client-side analysis; when a check result is cleared the flow
 * falls back to exactly what `buildDiagram` computed.
 *
 * It returns new elements only when something changed, so a check result that
 * matches the client analysis does not re-render the canvas.
 */

import type { DomainName } from "../../contracts/catalog";
import type { CausalityStroke } from "../../contracts/worker-rpc";
import type { DiagramFlow, DiagramNode } from "../buildFlow";
import type { BlockNodeData } from "../nodes/BlockNode";
import type { EditorEdge, EditorEdgeData } from "./EditorEdges";
import type { CausalStrokeAt } from "./causalStroke";
import { unitFactorLabel } from "./units";

export interface CanvasDecoration {
  domains: Readonly<Record<string, DomainName>>;
  causality: Readonly<Record<string, CausalityStroke>>;
  unitFactors: Readonly<Record<string, number>>;
}

/** The worker's stroke end, or null for an absent/malformed entry. */
export function causalityStrokeAt(
  entry: CausalityStroke | null | undefined,
): CausalStrokeAt | null {
  const value = entry?.strokeAt;
  return value === "from" || value === "to" ? value : null;
}

function decoratedNode(
  node: DiagramNode,
  domains: ReadonlyMap<string, DomainName>,
): DiagramNode {
  if (!("portDomains" in node.data) || domains.size === 0) {
    return node;
  }
  const data = node.data as BlockNodeData;
  let changed = false;
  const portDomains: Record<string, DomainName> = { ...data.portDomains };
  for (const [port, domain] of domains) {
    if (portDomains[port] !== domain) {
      portDomains[port] = domain;
      changed = true;
    }
  }
  if (!changed) {
    return node;
  }
  return { ...node, data: { ...data, portDomains } } as DiagramNode;
}

function decoratedEdge(edge: EditorEdge, decoration: CanvasDecoration): EditorEdge {
  const data: EditorEdgeData | undefined = edge.data;
  if (data === undefined) {
    return edge;
  }
  const domain =
    data.kind === "signal"
      ? data.domain
      : (decoration.domains[edge.id] ?? data.domain);
  const causalStroke =
    data.kind === "bond" ? causalityStrokeAt(decoration.causality[edge.id]) : null;
  const unitFactor =
    data.kind === "signal"
      ? unitFactorLabel(decoration.unitFactors[edge.id])
      : null;
  if (
    domain === data.domain &&
    causalStroke === data.causalStroke &&
    unitFactor === data.unitFactor
  ) {
    return edge;
  }
  return { ...edge, data: { ...data, domain, causalStroke, unitFactor } };
}

/** Apply the worker's visual facts to a built diagram. */
export function decorateFlow(flow: DiagramFlow, decoration: CanvasDecoration): DiagramFlow {
  const portsByNode = new Map<string, Map<string, DomainName>>();
  for (const edge of flow.edges) {
    if (edge.data === undefined || edge.data.kind === "signal") {
      continue;
    }
    const domain = decoration.domains[edge.id];
    if (domain === undefined) {
      continue;
    }
    const endpoints: [string, string | null | undefined][] = [
      [edge.source, edge.sourceHandle],
      [edge.target, edge.targetHandle],
    ];
    for (const [nodeId, handle] of endpoints) {
      if (handle === null || handle === undefined || handle.startsWith("j-")) {
        continue;
      }
      const ports = portsByNode.get(nodeId) ?? new Map<string, DomainName>();
      ports.set(handle, domain);
      portsByNode.set(nodeId, ports);
    }
  }

  const nodes = flow.nodes.map((node) =>
    decoratedNode(node, portsByNode.get(node.id) ?? new Map()),
  );
  const edges = flow.edges.map((edge) => decoratedEdge(edge, decoration));
  return { ...flow, nodes, edges };
}
