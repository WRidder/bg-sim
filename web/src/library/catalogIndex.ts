/**
 * Indexes over the library catalog (plan 3.2) used by the library browser and
 * the canvas. Built once per catalog so the canvas never scans 36 blocks per
 * render.
 */

import type { Catalog, CatalogBlock, CatalogDomain, DomainName } from "../contracts/catalog";

export interface LibraryGroup {
  name: string;
  blocks: CatalogBlock[];
}

export interface CatalogIndex {
  catalog: Catalog;
  blocks: CatalogBlock[];
  blocksByRef: Map<string, CatalogBlock>;
  blocksByName: Map<string, CatalogBlock>;
  domains: Map<DomainName, CatalogDomain>;
  /** Catalog groups in first-appearance order plus the junction group. */
  groups: LibraryGroup[];
  iconIds: string[];
  junctions: Catalog["junctions"];
}

export const JUNCTION_GROUP = "Junctions";

/**
 * The two robotics categories of W-MB3. They are derived from the live catalog:
 * a block's `dimension` (C-MB1: 2 planar, 3 spatial) is authoritative, and no
 * block list is hard-coded here. A scalar block keeps its catalog group.
 */
export const DIMENSION_GROUPS = {
  2: "2D multibond",
  3: "3D multibond",
} as const;

/** The visible group of one block: the model dimension, or the catalog group. */
export function libraryGroupFor(block: CatalogBlock): string {
  if (block.dimension !== undefined) {
    return DIMENSION_GROUPS[block.dimension];
  }
  return block.group.trim() || "Other";
}

/** Group blocks by their visible group, preserving the catalog's order. */
export function groupBlocks(blocks: readonly CatalogBlock[]): LibraryGroup[] {
  const groups = new Map<string, CatalogBlock[]>();
  for (const block of blocks) {
    const key = libraryGroupFor(block);
    const list = groups.get(key);
    if (list === undefined) {
      groups.set(key, [block]);
    } else {
      list.push(block);
    }
  }
  return [...groups.entries()].map(([name, entries]) => ({ name, blocks: entries }));
}

export function buildCatalogIndex(catalog: Catalog): CatalogIndex {
  const blocksByRef = new Map<string, CatalogBlock>();
  const blocksByName = new Map<string, CatalogBlock>();
  const domains = new Map<DomainName, CatalogDomain>();
  const iconIds = new Set<string>();

  for (const block of catalog.blocks) {
    blocksByRef.set(block.ref, block);
    blocksByName.set(block.name, block);
    iconIds.add(block.icon);
  }
  for (const domain of catalog.domains) {
    domains.set(domain.name, domain);
  }
  const groups = groupBlocks(catalog.blocks);
  groups.push({ name: JUNCTION_GROUP, blocks: [] });

  return {
    catalog,
    blocks: catalog.blocks,
    blocksByRef,
    blocksByName,
    domains,
    groups,
    iconIds: [...iconIds],
    junctions: catalog.junctions,
  };
}

function haystack(block: CatalogBlock): string {
  return `${block.name}\n${block.ref}\n${block.group}\n${block.description}`.toLowerCase();
}

/**
 * Search by name, ref, group or description; an empty query returns every
 * block. Order is the catalog order so results stay stable while typing.
 */
export function searchBlocks(blocks: readonly CatalogBlock[], query: string): CatalogBlock[] {
  const needle = query.trim().toLowerCase();
  if (needle.length === 0) {
    return [...blocks];
  }
  return blocks.filter((block) => haystack(block).includes(needle));
}

/** The visible groups after a search; groups with no match are dropped. */
export function searchGroups(groups: readonly LibraryGroup[], query: string): LibraryGroup[] {
  const needle = query.trim().toLowerCase();
  if (needle.length === 0) {
    return [...groups];
  }
  return groups
    .map((group) => ({
      name: group.name,
      blocks: group.blocks.filter((block) => haystack(block).includes(needle)),
    }))
    .filter((group) => group.blocks.length > 0);
}

/** A compact parameter/port summary for the library row. */
export function blockSummary(block: CatalogBlock): string {
  const parts: string[] = [];
  parts.push(`${block.parameters.length} ${block.parameters.length === 1 ? "parameter" : "parameters"}`);
  const portCount = block.ports.length + block.inputs.length + block.outputs.length;
  parts.push(`${portCount} ${portCount === 1 ? "port" : "ports"}`);
  return parts.join(" · ");
}
