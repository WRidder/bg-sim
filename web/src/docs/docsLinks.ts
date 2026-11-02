/**
 * Model-aware links of the Docs tab (W5.6):
 *
 * - `page:<id>`            opens another page of the same docs (the wiki the link is in),
 * - `project:<id>`         opens a page of the project docs (`<project>/docs/`),
 * - `model:<name>/<id>`    opens a page of the docs of model `<name>`; `model:<name>` opens its
 *                          first page,
 * - `block:<Name>`         switches to the Diagram tab and selects the node (`block:Sub/Name`
 *                          reaches a node inside subsystem `Sub`); model docs only,
 * - `signal:<signal id>`   plots the signal; model docs only.
 *
 * A target that does not exist resolves to a broken link whose `reason` says what to fix.
 */

import type { Model, ModelNode } from "../contracts/model";

export type LinkTarget =
  | { kind: "page"; id: string }
  | { kind: "project-page"; id: string }
  | { kind: "model-page"; model: string; id: string }
  | { kind: "block"; path: string[]; nodeId: string; name: string }
  | { kind: "signal"; id: string }
  | { kind: "external"; href: string }
  | { kind: "anchor"; href: string }
  | { kind: "broken"; reason: string };

export interface LinkContext {
  /** The page ids of the docs the link is in (what `page:` links reach). */
  pageIds: ReadonlySet<string>;
  /** The open model, or `null` before it is loaded. */
  model: Model | null;
  /** The signal ids of the latest run, or `null` when nothing has run yet. */
  signalIds: ReadonlySet<string> | null;
  /** The docs the link is in: a model's (the default) or the project docs. */
  wiki?: "model" | "project";
  /** The page ids of the project docs; leave out where project links cannot be followed. */
  projectPageIds?: ReadonlySet<string>;
  /**
   * The page ids of every model's docs in tree order (the first one is the model's first
   * page), by model name; leave out where links to model docs cannot be followed.
   */
  modelPages?: ReadonlyMap<string, readonly string[]>;
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

const OTHER_DOCS_HINT = "use project:<id> for the project docs or model:<name>/<id> for another model's docs";

function resolveModelPage(rest: string, context: LinkContext): LinkTarget {
  const slash = rest.indexOf("/");
  const name = slash < 0 ? rest : rest.slice(0, slash);
  const id = slash < 0 ? "" : rest.slice(slash + 1);
  if (name === "") {
    return { kind: "broken", reason: "Name the model, for example model:Plant/overview or model:Plant." };
  }
  if (context.modelPages === undefined) {
    return { kind: "broken", reason: `Links to the docs of model "${name}" work on docs pages only.` };
  }
  const pages = context.modelPages.get(name);
  if (pages === undefined) {
    return {
      kind: "broken",
      reason: `The project has no model "${name}"; check the model name (it is case-sensitive).`,
    };
  }
  if (pages.length === 0) {
    return { kind: "broken", reason: `Model "${name}" has no docs yet; write its first page or link to another page.` };
  }
  if (id === "") {
    return { kind: "model-page", model: name, id: pages[0] ?? "" };
  }
  if (!pages.includes(id)) {
    return {
      kind: "broken",
      reason: `The docs of model "${name}" have no page "${id}"; pick an existing page id or write model:${name} for its first page.`,
    };
  }
  return { kind: "model-page", model: name, id };
}

export function resolveLink(href: string | undefined, context: LinkContext): LinkTarget {
  if (href === undefined || href.trim() === "") {
    return {
      kind: "broken",
      reason: "This link has no target; write [text](page:<id>), (project:<id>), (model:<name>/<id>), (block:<name>) or (signal:<id>).",
    };
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
  const projectWiki = context.wiki === "project";
  switch (protocol) {
    case "page": {
      if (context.pageIds.has(rest)) {
        return { kind: "page", id: rest };
      }
      // Page ids are lower-case letters, digits and dashes; a slash or a dot reads as an
      // attempt to reach other docs, which a page link cannot do.
      if (/[/.]/.test(rest)) {
        return {
          kind: "broken",
          reason: `"${rest}" is not a page id: page links open pages of the same docs only; ${OTHER_DOCS_HINT}.`,
        };
      }
      return {
        kind: "broken",
        reason: `There is no page "${rest}" in these docs; pick an existing page id or create the page. Page links open pages of the same docs only; ${OTHER_DOCS_HINT}.`,
      };
    }
    case "project": {
      if (context.projectPageIds === undefined) {
        return { kind: "broken", reason: "Links to the project docs work on docs pages only." };
      }
      if (context.projectPageIds.has(rest)) {
        return { kind: "project-page", id: rest };
      }
      return {
        kind: "broken",
        reason:
          context.projectPageIds.size === 0
            ? `The project has no project docs yet, so there is no page "${rest}"; add the project docs first.`
            : `There is no page "${rest}" in the project docs; pick an existing page id or create the page.`,
      };
    }
    case "model":
      return resolveModelPage(rest, context);
    case "block": {
      if (projectWiki) {
        return {
          kind: "broken",
          reason: "Block links work in a model's docs only; from the project docs, link to a model's page with model:<name>/<id>.",
        };
      }
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
      if (projectWiki) {
        return {
          kind: "broken",
          reason: "Signal links work in a model's docs only; from the project docs, link to a model's page with model:<name>/<id>.",
        };
      }
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
        reason: `"${protocol}:" links are not supported; use page:, project:, model:, block:, signal: or an https link.`,
      };
  }
}

/** A `title` attribute text that tells what a resolved link does. */
export function describeLink(target: LinkTarget): string {
  switch (target.kind) {
    case "page":
      return `Open page ${target.id}`;
    case "project-page":
      return `Open page ${target.id} of the project docs`;
    case "model-page":
      return `Open page ${target.id} of the docs of ${target.model}`;
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

/**
 * `LinkContext.modelPages` from a list of model page trees (pre-order ids, so the first id is
 * the model's first page). `overrides` replaces the trees of models whose live state is known
 * better than the list (the open model's docs while it is being edited).
 */
export function modelPagesOf(
  models: readonly { name: string; docs: { pages: readonly PageNode[] } }[],
  overrides: Readonly<Record<string, readonly PageNode[]>> = {},
): Map<string, string[]> {
  const ids = (pages: readonly PageNode[]): string[] => pages.flatMap((page) => [page.id, ...ids(page.children)]);
  const map = new Map<string, string[]>();
  for (const model of models) {
    map.set(model.name, ids(model.docs.pages));
  }
  for (const [name, pages] of Object.entries(overrides)) {
    map.set(name, ids(pages));
  }
  return map;
}

interface PageNode {
  id: string;
  children: readonly PageNode[];
}

/** A page reference in a URL (`page=` of the project page and the editor): the link syntax. */
export type DocsRef = { wiki: "project"; id: string } | { wiki: "model"; model: string | null; id: string | null };

/**
 * Read `project:<id>`, `model:<name>/<id>`, `model:<name>` or a bare `<id>` (a page of the
 * open model's docs). Returns `null` for an empty or malformed value.
 */
export function parseDocsRef(value: string | null | undefined): DocsRef | null {
  const text = (value ?? "").trim();
  if (text === "") {
    return null;
  }
  if (text.startsWith("project:")) {
    const id = text.slice("project:".length);
    return id === "" ? null : { wiki: "project", id };
  }
  if (text.startsWith("model:")) {
    const rest = text.slice("model:".length);
    const slash = rest.indexOf("/");
    const model = slash < 0 ? rest : rest.slice(0, slash);
    const id = slash < 0 ? "" : rest.slice(slash + 1);
    return model === "" ? null : { wiki: "model", model, id: id === "" ? null : id };
  }
  return /^[a-z0-9][a-z0-9-]{0,63}$/.test(text) ? { wiki: "model", model: null, id: text } : null;
}

/** The URL form of a page reference (the inverse of `parseDocsRef`). */
export function formatDocsRef(ref: DocsRef): string {
  if (ref.wiki === "project") {
    return `project:${ref.id}`;
  }
  if (ref.model === null) {
    return ref.id ?? "";
  }
  return ref.id === null ? `model:${ref.model}` : `model:${ref.model}/${ref.id}`;
}
