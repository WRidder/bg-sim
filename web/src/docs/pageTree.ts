/**
 * Pure operations on the page tree of a model's docs (W5.6).
 *
 * Every operation returns a new manifest (or `null` when it would change nothing or is not
 * allowed), so the store can persist the result and the tests can compare trees.
 */

import type { Docs, DocsPage } from "../contracts/docs";

export type { Docs, DocsPage };

export const EMPTY_DOCS: Docs = { format: "bgsim.docs", version: 1, pages: [] };

export const DEFAULT_TITLE = "New page";

/** One visible row of the tree, in display order. */
export interface TreeRow {
  page: DocsPage;
  depth: number;
  /** `null` for a top-level page. */
  parentId: string | null;
  /** Position among its siblings. */
  index: number;
  siblingCount: number;
}

export type DeleteMode = "subtree" | "promote";

export function slugify(title: string): string {
  const slug = title
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48)
    .replace(/-+$/g, "");
  return slug === "" ? "page" : slug;
}

export function allIds(pages: readonly DocsPage[]): Set<string> {
  const ids = new Set<string>();
  const visit = (list: readonly DocsPage[]): void => {
    for (const page of list) {
      ids.add(page.id);
      visit(page.children);
    }
  };
  visit(pages);
  return ids;
}

/** A page id derived from `title` that is not in `taken`. */
export function uniqueId(title: string, taken: ReadonlySet<string>): string {
  const base = slugify(title);
  if (!taken.has(base)) {
    return base;
  }
  for (let n = 2; ; n += 1) {
    const candidate = `${base}-${n}`;
    if (!taken.has(candidate)) {
      return candidate;
    }
  }
}

export function findPage(pages: readonly DocsPage[], id: string): DocsPage | null {
  for (const page of pages) {
    if (page.id === id) {
      return page;
    }
    const inner = findPage(page.children, id);
    if (inner !== null) {
      return inner;
    }
  }
  return null;
}

/** The ids from the top level down to `id` (inclusive), or `null`. */
export function pathTo(pages: readonly DocsPage[], id: string): string[] | null {
  for (const page of pages) {
    if (page.id === id) {
      return [page.id];
    }
    const inner = pathTo(page.children, id);
    if (inner !== null) {
      return [page.id, ...inner];
    }
  }
  return null;
}

export function firstPageId(docs: Docs): string | null {
  return docs.pages[0]?.id ?? null;
}

/** The rows to draw: collapsed pages hide their descendants. */
export function visibleRows(docs: Docs, collapsed: ReadonlySet<string>): TreeRow[] {
  const rows: TreeRow[] = [];
  const visit = (list: readonly DocsPage[], depth: number, parentId: string | null): void => {
    list.forEach((page, index) => {
      rows.push({ page, depth, parentId, index, siblingCount: list.length });
      if (!collapsed.has(page.id)) {
        visit(page.children, depth + 1, page.id);
      }
    });
  };
  visit(docs.pages, 0, null);
  return rows;
}

function clone(docs: Docs): Docs {
  return structuredClone(docs);
}

/** The list that holds `id` (`pages` itself for top-level pages) and the page's index in it. */
function locate(docs: Docs, id: string): { list: DocsPage[]; index: number; parent: DocsPage | null } | null {
  const search = (
    list: DocsPage[],
    parent: DocsPage | null,
  ): { list: DocsPage[]; index: number; parent: DocsPage | null } | null => {
    for (let index = 0; index < list.length; index += 1) {
      const page = list[index];
      if (page === undefined) {
        continue;
      }
      if (page.id === id) {
        return { list, index, parent };
      }
      const inner = search(page.children, page);
      if (inner !== null) {
        return inner;
      }
    }
    return null;
  };
  return search(docs.pages, null);
}

function newPage(docs: Docs, title: string): DocsPage {
  const id = uniqueId(title, allIds(docs.pages));
  return { id, title, file: `pages/${id}.md`, children: [] };
}

export interface Added {
  docs: Docs;
  id: string;
}

/** A new page after `afterId` among its siblings; at the end of the top level when `null`. */
export function addSibling(docs: Docs, afterId: string | null, title = DEFAULT_TITLE): Added | null {
  const next = clone(docs);
  const page = newPage(next, title);
  if (afterId === null) {
    next.pages.push(page);
    return { docs: next, id: page.id };
  }
  const where = locate(next, afterId);
  if (where === null) {
    return null;
  }
  where.list.splice(where.index + 1, 0, page);
  return { docs: next, id: page.id };
}

/** A new last child of `parentId`. */
export function addChild(docs: Docs, parentId: string, title = DEFAULT_TITLE): Added | null {
  const next = clone(docs);
  const where = locate(next, parentId);
  const parent = where?.list[where.index];
  if (parent === undefined) {
    return null;
  }
  const page = newPage(next, title);
  parent.children.push(page);
  return { docs: next, id: page.id };
}

export function renamePage(docs: Docs, id: string, title: string): Docs | null {
  const trimmed = title.trim();
  const current = findPage(docs.pages, id);
  if (current === null || trimmed === "" || trimmed === current.title) {
    return null;
  }
  const next = clone(docs);
  const target = findPage(next.pages, id);
  if (target === null) {
    return null;
  }
  target.title = trimmed.slice(0, 200);
  return next;
}

export interface Removed {
  docs: Docs;
  /** The ids whose files go away. */
  removed: string[];
}

function idsOf(page: DocsPage): string[] {
  return [page.id, ...page.children.flatMap(idsOf)];
}

export function removePage(docs: Docs, id: string, mode: DeleteMode): Removed | null {
  const next = clone(docs);
  const where = locate(next, id);
  const page = where?.list[where.index];
  if (where === null || page === undefined) {
    return null;
  }
  if (mode === "promote") {
    where.list.splice(where.index, 1, ...page.children);
    return { docs: next, removed: [id] };
  }
  where.list.splice(where.index, 1);
  return { docs: next, removed: idsOf(page) };
}

/**
 * Move `id` under `targetParentId` (`null` = top level) at `index` among the target's children
 * (counted after the page has been taken out). Moving a page into itself or a descendant is
 * refused, and so is a move that leaves the page where it was.
 */
export function movePage(
  docs: Docs,
  id: string,
  targetParentId: string | null,
  index: number,
): Docs | null {
  const moving = findPage(docs.pages, id);
  if (moving === null) {
    return null;
  }
  if (targetParentId !== null && findPage([moving], targetParentId) !== null) {
    return null;
  }
  const next = clone(docs);
  const from = locate(next, id);
  const page = from?.list[from.index];
  if (from === null || page === undefined) {
    return null;
  }
  from.list.splice(from.index, 1);
  let targetList: DocsPage[];
  if (targetParentId === null) {
    targetList = next.pages;
  } else {
    const target = findPage(next.pages, targetParentId);
    if (target === null) {
      return null;
    }
    targetList = target.children;
  }
  const at = Math.max(0, Math.min(index, targetList.length));
  const unchanged = from.parent?.id === targetParentId || (from.parent === null && targetParentId === null);
  if (unchanged && at === from.index) {
    return null;
  }
  targetList.splice(at, 0, page);
  return next;
}

/** One step up among the siblings (Alt+Up). */
export function moveUp(docs: Docs, id: string): Docs | null {
  const where = locate(docs, id);
  if (where === null || where.index === 0) {
    return null;
  }
  return movePage(docs, id, where.parent?.id ?? null, where.index - 1);
}

/** One step down among the siblings (Alt+Down). */
export function moveDown(docs: Docs, id: string): Docs | null {
  const where = locate(docs, id);
  if (where === null || where.index >= where.list.length - 1) {
    return null;
  }
  return movePage(docs, id, where.parent?.id ?? null, where.index + 1);
}

/** Become the last child of the previous sibling (Alt+Right). */
export function indentPage(docs: Docs, id: string): Docs | null {
  const where = locate(docs, id);
  const previous = where === null ? undefined : where.list[where.index - 1];
  if (where === null || previous === undefined) {
    return null;
  }
  return movePage(docs, id, previous.id, previous.children.length);
}

/** Become the sibling right after the parent (Alt+Left). */
export function outdentPage(docs: Docs, id: string): Docs | null {
  const where = locate(docs, id);
  if (where === null || where.parent === null) {
    return null;
  }
  const parentWhere = locate(docs, where.parent.id);
  if (parentWhere === null) {
    return null;
  }
  return movePage(docs, id, parentWhere.parent?.id ?? null, parentWhere.index + 1);
}

/** Map the Alt+Arrow keys of the tree to their operation. */
export function keyboardMove(docs: Docs, id: string, key: string): Docs | null {
  switch (key) {
    case "ArrowUp":
      return moveUp(docs, id);
    case "ArrowDown":
      return moveDown(docs, id);
    case "ArrowRight":
      return indentPage(docs, id);
    case "ArrowLeft":
      return outdentPage(docs, id);
    default:
      return null;
  }
}

export type DropPosition = "before" | "after" | "inside";

/** Drag and drop: drop `id` before/after/inside `targetId`. */
export function dropPage(
  docs: Docs,
  id: string,
  targetId: string,
  position: DropPosition,
): Docs | null {
  if (id === targetId) {
    return null;
  }
  if (position === "inside") {
    const target = findPage(docs.pages, targetId);
    return target === null ? null : movePage(docs, id, targetId, target.children.length);
  }
  const moving = findPage(docs.pages, id);
  if (moving !== null && findPage([moving], targetId) !== null) {
    return null;
  }
  // Take the page out first so the target index is counted without it.
  const without = removePage(docs, id, "subtree");
  const where = without === null ? null : locate(without.docs, targetId);
  if (where === null) {
    return null;
  }
  const parentId = where.parent?.id ?? null;
  const index = position === "before" ? where.index : where.index + 1;
  // movePage recounts after its own removal, which matches the index computed without the page.
  return movePage(docs, id, parentId, index);
}
