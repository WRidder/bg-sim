/**
 * The pages of the user manual: `pages/NN-<id>.md`, bundled as raw text (no backend needed).
 * The number prefix sets the order, the rest of the file name is the page id that
 * `page:<id>` links use, and the first `# heading` is the title.
 *
 * Every user-visible feature change updates the relevant page in the same branch (CLAUDE.md).
 */

import { SHORTCUT_GROUPS } from "../app/shortcuts";

export interface ManualPage {
  id: string;
  title: string;
  /** The Markdown source, ready for `MarkdownView`. */
  text: string;
}

const SOURCES = import.meta.glob<string>("./pages/*.md", { query: "?raw", import: "default", eager: true });

/** The page that shows the generated shortcut table below its own text. */
export const SHORTCUTS_PAGE_ID = "keyboard-shortcuts";

function escapeCell(value: string): string {
  return value.replace(/\|/g, "\\|");
}

/** The shortcut overlay's list as Markdown tables, so the manual never drifts from it. */
export function shortcutsMarkdown(): string {
  return SHORTCUT_GROUPS.map((group) => {
    const rows = group.entries.map((entry) => {
      const keys = entry.keys.map((combo) => combo.map((cap) => `\`${cap}\``).join(" + ")).join(" or ");
      return `| ${escapeCell(keys)} | ${escapeCell(entry.description)} |`;
    });
    return [`## ${group.title}`, "", "| Keys | Action |", "| --- | --- |", ...rows].join("\n");
  }).join("\n\n");
}

function parse(path: string, source: string): ManualPage & { order: string } {
  const file = /\/(\d+)-([a-z0-9-]+)\.md$/.exec(path);
  if (file === null) {
    throw new Error(`Manual page ${path} must be named NN-<id>.md`);
  }
  const id = file[2] ?? "";
  const heading = /^#\s+(.+)$/m.exec(source);
  const title = heading?.[1]?.trim() ?? id;
  const text = id === SHORTCUTS_PAGE_ID ? `${source.trimEnd()}\n\n${shortcutsMarkdown()}\n` : source;
  return { id, title, text, order: file[1] ?? "" };
}

export const MANUAL_PAGES: readonly ManualPage[] = Object.entries(SOURCES)
  .map(([path, source]) => parse(path, source))
  .sort((a, b) => Number(a.order) - Number(b.order))
  .map(({ id, title, text }) => ({ id, title, text }));

export const MANUAL_PAGE_IDS: ReadonlySet<string> = new Set(MANUAL_PAGES.map((page) => page.id));

/** Pages whose title or text contains every word of the query (case-insensitive). */
export function filterPages(pages: readonly ManualPage[], query: string): ManualPage[] {
  const words = query.toLowerCase().split(/\s+/).filter((word) => word !== "");
  if (words.length === 0) {
    return [...pages];
  }
  return pages.filter((page) => {
    const haystack = `${page.title}\n${page.text}`.toLowerCase();
    return words.every((word) => haystack.includes(word));
  });
}

export const MANUAL_PAGE_KEY = "bgsim.manual.page";

export function loadLastPage(): string | null {
  try {
    const value = window.localStorage.getItem(MANUAL_PAGE_KEY);
    return value !== null && MANUAL_PAGE_IDS.has(value) ? value : null;
  } catch {
    return null;
  }
}

export function saveLastPage(id: string): void {
  try {
    window.localStorage.setItem(MANUAL_PAGE_KEY, id);
  } catch {
    // Storage blocked (private window): the manual still works, it just forgets the page.
  }
}
