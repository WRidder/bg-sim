/**
 * Model-aware links of the Docs tab (W5.6):
 *
 * - `page:<id>`            opens another docs page of the model,
 * - `block:<Name>`         switches to the Diagram tab and selects the node (`block:Sub/Name`
 *                          reaches a node inside subsystem `Sub`),
 * - `signal:<signal id>`   plots the signal.
 *
 * A target that does not exist resolves to a broken link whose `reason` says what to fix.
 */

import type { Model, ModelNode } from "../contracts/model";

export type LinkTarget =
  | { kind: "page"; id: string }
  | { kind: "block"; path: string[]; nodeId: string; name: string }
  | { kind: "signal"; id: string }
  | { kind: "external"; href: string }
  | { kind: "anchor"; href: string }
  | { kind: "broken"; reason: string };

export interface LinkContext {
  pageIds: ReadonlySet<string>;
  /** The open model, or `null` before it is loaded. */
  model: Model | null;
  /** The signal ids of the latest run, or `null` when nothing has run yet. */
  signalIds: ReadonlySet<string> | null;
}

type Nodes = readonly ModelNode[];

/** Resolve `A/B/C`: names of subsystems down to the node. Returns the subsystem path and node. */
export function findBlock(
  model: Model,
  reference: string,
): { path: string[]; nodeId: string; name: string } | null {
  const names = reference.split("/").filter((part) => part !== "");
  if (names.length === 0) {
    return null;
  }
  let nodes: Nodes = model.diagram.nodes;
  const path: string[] = [];
  for (let depth = 0; depth < names.length; depth += 1) {
    const name = names[depth];
    const node = nodes.find((candidate) => candidate.name === name);
    if (node === undefined) {
      return null;
    }
    if (depth === names.length - 1) {
      return { path, nodeId: node.id, name: node.name };
    }
    if (!("subsystem" in node.block)) {
      return null;
    }
    path.push(node.id);
    nodes = node.block.subsystem.diagram.nodes;
  }
  return null;
}

function decoded(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

export function resolveLink(href: string | undefined, context: LinkContext): LinkTarget {
  if (href === undefined || href.trim() === "") {
    return { kind: "broken", reason: "This link has no target; write [text](page:<id>), (block:<name>) or (signal:<id>)." };
  }
  if (href.startsWith("#")) {
    return { kind: "anchor", href };
  }
  const scheme = /^([a-z][a-z0-9+.-]*):(.*)$/i.exec(href);
  if (scheme === null) {
    return {
      kind: "broken",
      reason: `"${href}" is a relative link; link to a page with page:<id>, a block with block:<name> or a signal with signal:<id>.`,
    };
  }
  const protocol = (scheme[1] ?? "").toLowerCase();
  const rest = decoded(scheme[2] ?? "");
  switch (protocol) {
    case "page": {
      if (context.pageIds.has(rest)) {
        return { kind: "page", id: rest };
      }
      return {
        kind: "broken",
        reason: `There is no page "${rest}" in these docs; pick an existing page id or create the page.`,
      };
    }
    case "block": {
      if (context.model === null) {
        return { kind: "broken", reason: "Open the model to follow block links." };
      }
      const found = findBlock(context.model, rest);
      if (found === null) {
        return {
          kind: "broken",
          reason: `The model has no block "${rest}"; check the block name (use Sub/Name for a block inside a subsystem).`,
        };
      }
      return { kind: "block", ...found };
    }
    case "signal": {
      if (rest === "") {
        return { kind: "broken", reason: "Name the signal, for example signal:Body/theta." };
      }
      if (context.signalIds !== null && !context.signalIds.has(rest)) {
        return {
          kind: "broken",
          reason: `The latest run has no signal "${rest}"; check the id in the signal browser or run the model again.`,
        };
      }
      return { kind: "signal", id: rest };
    }
    case "http":
    case "https":
    case "mailto":
      return { kind: "external", href };
    default:
      return {
        kind: "broken",
        reason: `"${protocol}:" links are not supported; use page:, block:, signal: or an https link.`,
      };
  }
}

/** A `title` attribute text that tells what a resolved link does. */
export function describeLink(target: LinkTarget): string {
  switch (target.kind) {
    case "page":
      return `Open page ${target.id}`;
    case "block":
      return `Show ${target.name} in the diagram`;
    case "signal":
      return `Plot ${target.id}`;
    case "external":
      return `External link: ${target.href}`;
    case "anchor":
      return "";
    case "broken":
      return target.reason;
  }
}
