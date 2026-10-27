/**
 * Drop-on-empty suggestions.
 *
 * When a connection drag ends on the bare canvas, the editor offers to add an
 * element at that point and to connect it automatically. Only blocks (and
 * power junctions) that expose a port the drag origin may connect to are
 * listed; `checkConnection` is the same rule the canvas enforces, so every row
 * is a connection the document will accept.
 *
 * The order is a "most likely" ranking, not catalog order: a block that is
 * already wired to the dragged element comes first, then blocks of the same
 * group, then a matching unit/port name. Ties keep catalog order.
 */

import type { CatalogBlock, DomainName, ValueType } from "../contracts/catalog";
import type { JunctionType, Model } from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import { checkConnection, formatSize, type PortDescriptor } from "./connectionRules";
import { interfaceForBlock, type PortSpec } from "./nodeInterface";

/**
 * The candidate port lives on a node that does not exist yet. A unique id keeps
 * the self-connection and "already connected" checks from matching a real node.
 */
const CANDIDATE_NODE_ID = "\u0000suggestion";

/** Port names that usually receive a signal (output -> input). */
const CONVENTIONAL_INPUTS = new Set(["u", "e", "in", "input"]);
/** Port names that usually emit a signal (input -> output). */
const CONVENTIONAL_OUTPUTS = new Set(["y", "out", "output"]);

interface SuggestionBase {
  /** Stable list key. */
  key: string;
  name: string;
  group: string;
  description: string;
  icon: string;
  /** The port the automatic connection uses; null for a junction. */
  portName: string | null;
  portKind: "power" | "input" | "output" | null;
  domain: DomainName;
  type: ValueType | null;
  size: number[];
  unit: string | null;
  /** Ranking value; higher is more likely. Not shown. */
  score: number;
}

export interface BlockSuggestion extends SuggestionBase {
  kind: "block";
  block: CatalogBlock;
  junction: null;
}

export interface JunctionSuggestion extends SuggestionBase {
  kind: "junction";
  block: null;
  junction: JunctionType;
}

export type TargetSuggestion = BlockSuggestion | JunctionSuggestion;

/** The descriptor a not-yet-added block port would have. */
function descriptorForPort(port: PortSpec, nodeId: string = CANDIDATE_NODE_ID): PortDescriptor {
  if (port.kind === "power") {
    return {
      nodeId,
      portName: port.name,
      isJunction: false,
      kind: "power",
      direction: null,
      domain: port.domain,
      type: null,
      size: port.size,
      unit: port.unit,
    };
  }
  return {
    nodeId,
    portName: port.name,
    isJunction: false,
    kind: "signal",
    direction: port.kind === "input" ? "input" : "output",
    domain: "Generic",
    type: port.type,
    size: port.size,
    unit: port.unit,
  };
}

/** The descriptor of a junction that is about to be added. */
export function junctionDescriptor(
  nodeId: string = CANDIDATE_NODE_ID,
): PortDescriptor {
  return {
    nodeId,
    portName: null,
    isJunction: true,
    kind: "power",
    direction: null,
    domain: "Generic",
    type: null,
    size: [],
    unit: null,
  };
}

/** How well one candidate port fits the drag origin, ignoring the block. */
function portAffinity(origin: PortDescriptor, port: PortSpec): number {
  let score = 0;
  if (origin.kind === "power") {
    if (origin.domain !== "Generic") {
      // A concrete domain match is the strongest bond; a Generic port adopts it.
      score += port.domain === origin.domain ? 4 : port.domain === "Generic" ? 2 : 0;
    } else if (port.domain === "Generic") {
      score += 1;
    }
    return score;
  }

  if (origin.unit !== null && origin.unit === port.unit) {
    score += 6;
  }
  // y -> u, u -> y and the same convention for named in/out ports.
  if (origin.direction === "output" && CONVENTIONAL_INPUTS.has(port.name.toLowerCase())) {
    score += 2;
  }
  if (origin.direction === "input" && CONVENTIONAL_OUTPUTS.has(port.name.toLowerCase())) {
    score += 2;
  }
  return score;
}

/** The best-fitting compatible port of one block, or null. */
function bestPort(
  doc: Model,
  origin: PortDescriptor,
  block: CatalogBlock,
): { port: PortSpec; score: number } | null {
  let best: { port: PortSpec; score: number } | null = null;
  for (const port of interfaceForBlock(block).ports) {
    if (!checkConnection(doc, origin, descriptorForPort(port)).ok) {
      continue;
    }
    const score = portAffinity(origin, port);
    if (best === null || score > best.score) {
      best = { port, score };
    }
  }
  return best;
}

function blockRef(node: Model["diagram"]["nodes"][number]): string | null {
  return "ref" in node.block ? node.block.ref : null;
}

/**
 * Every element that can be added at the drop point and connected to `origin`,
 * most likely first.
 */
export function suggestTargets(
  doc: Model,
  index: CatalogIndex,
  origin: PortDescriptor,
): TargetSuggestion[] {
  const nodes = doc.diagram.nodes;
  const originNode = nodes.find((node) => node.id === origin.nodeId);
  const originRef = originNode === undefined ? null : blockRef(originNode);
  const originGroup =
    originRef === null ? null : (index.blocksByRef.get(originRef)?.group ?? null);

  // Blocks already in the diagram (other than the dragged element) and blocks
  // directly wired to the dragged element's instances.
  const usedRefs = new Set<string>();
  const originNodeIds = new Set<string>();
  const refByNode = new Map<string, string>();
  for (const node of nodes) {
    const ref = blockRef(node);
    if (ref === null) {
      continue;
    }
    refByNode.set(node.id, ref);
    if (node.id === origin.nodeId || ref === originRef) {
      originNodeIds.add(node.id);
    } else {
      usedRefs.add(ref);
    }
  }
  const linkedRefs = new Set<string>();
  for (const connection of doc.diagram.connections) {
    const fromOrigin = originNodeIds.has(connection.from.node);
    const toOrigin = originNodeIds.has(connection.to.node);
    if (fromOrigin === toOrigin) {
      continue;
    }
    const peer = fromOrigin ? connection.to.node : connection.from.node;
    const peerRef = refByNode.get(peer);
    if (peerRef !== undefined) {
      linkedRefs.add(peerRef);
    }
  }

  const suggestions: TargetSuggestion[] = [];

  for (const block of index.blocks) {
    const match = bestPort(doc, origin, block);
    if (match === null) {
      continue;
    }
    const { port } = match;
    let score = match.score;
    const iface = interfaceForBlock(block);
    if (originGroup !== null && block.group === originGroup) {
      score += 2;
    }
    if (origin.kind === "signal") {
      // A pure signal block is a more likely continuation of a signal line than
      // a power element that merely exposes a modulation input.
      if (!iface.ports.some((entry) => entry.kind === "power")) {
        score += 2;
      }
      // Dragging out of an input usually asks for a source to drive it.
      if (
        origin.direction === "input" &&
        !iface.ports.some((entry) => entry.kind === "input")
      ) {
        score += 2;
      }
    }
    if (usedRefs.has(block.ref)) {
      score += 3;
    }
    if (linkedRefs.has(block.ref)) {
      score += 8;
    }
    // Another instance of the dragged block is legal but rarely the next step.
    if (block.ref === originRef) {
      score -= 2;
    }
    suggestions.push({
      kind: "block",
      key: block.ref,
      name: block.name,
      group: block.group,
      description: block.description,
      icon: block.icon,
      block,
      junction: null,
      portName: port.name,
      portKind: port.kind,
      domain: port.domain,
      type: port.type,
      size: port.size,
      unit: port.unit,
      score,
    });
  }

  // Junctions are dimensionless power elements; checkConnection filters the
  // ones that cannot take this bond.
  if (origin.kind === "power") {
    for (const entry of index.junctions) {
      const kind: JunctionType = entry.ref.split(":").pop() === "1" ? "1" : "0";
      if (!checkConnection(doc, origin, junctionDescriptor()).ok) {
        continue;
      }
      const score = origin.domain === "Generic" ? 1 : 4;
      suggestions.push({
        kind: "junction",
        key: `junction-${kind}`,
        name: `Junction ${kind}`,
        group: "Junctions",
        description:
          kind === "0"
            ? "0 junction: equal efforts, flows sum to zero."
            : "1 junction: equal flows, efforts sum to zero.",
        icon: "junction",
        block: null,
        junction: kind,
        portName: null,
        portKind: null,
        domain: "Generic",
        type: null,
        size: [],
        unit: null,
        score,
      });
    }
  }

  // Array.prototype.sort is stable, so equal scores keep catalog order and
  // junctions follow blocks.
  return suggestions.sort((a, b) => b.score - a.score);
}

/** The port hint shown under a suggestion's name. */
export function suggestionPortLabel(suggestion: TargetSuggestion): string {
  if (suggestion.kind === "junction") {
    return "power junction · one more bond";
  }
  if (suggestion.portKind === "power") {
    return `power ${suggestion.portName} · ${suggestion.domain}`;
  }
  const size = suggestion.size.length > 0 ? ` · ${formatSize(suggestion.size)}` : "";
  const unit = suggestion.unit !== null ? ` · ${suggestion.unit}` : "";
  return `${suggestion.portKind} ${suggestion.portName} · ${suggestion.type ?? "?"}${size}${unit}`;
}

/** Filter the compatible list; every whitespace-separated token must match. */
export function filterSuggestions(
  suggestions: readonly TargetSuggestion[],
  query: string,
): TargetSuggestion[] {
  const tokens = query.trim().toLowerCase().split(/\s+/).filter((token) => token.length > 0);
  if (tokens.length === 0) {
    return [...suggestions];
  }
  return suggestions.filter((suggestion) => {
    const direct = [
      suggestion.name,
      suggestion.kind,
      suggestion.group,
      suggestion.portName ?? "",
      suggestionPortLabel(suggestion),
      suggestion.kind === "block" ? suggestion.block.ref : "junction",
    ]
      .join("\n")
      .toLowerCase();
    const description = suggestion.description.toLowerCase();
    return tokens.every(
      (token) =>
        direct.includes(token) ||
        // One-letter tokens are port hints; letting them match prose ("u" in
        // "tunable") defeats the hint and makes the filter feel random.
        (token.length > 1 && description.includes(token)),
    );
  });
}
