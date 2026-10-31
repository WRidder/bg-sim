/**
 * The user manual: the help icon in the top bar and F1 open a full-screen modal with the
 * pages of `src/manual/pages/` rendered by the Docs tab's MarkdownView. Also the guard of
 * the CLAUDE.md rule "every user-visible feature change updates the manual": the page list
 * is fixed here, every page renders, and every link in it resolves.
 */

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { resetHelpStore, useHelpStore } from "../src/app/helpStore";
import { ShortcutsOverlay } from "../src/app/ShortcutsOverlay";
import { TopBar } from "../src/app/TopBar";
import { useAppShortcuts } from "../src/app/useAppShortcuts";
import { resolveLink, type LinkContext } from "../src/docs/docsLinks";
import { MarkdownView, type LinkActions } from "../src/docs/MarkdownView";
import {
  filterPages,
  MANUAL_PAGE_IDS,
  MANUAL_PAGE_KEY,
  MANUAL_PAGES,
  SHORTCUTS_PAGE_ID,
} from "../src/manual/manualPages";
import { resetDocumentStore } from "../src/state/documentStore";

/** The manual's pages, in order. Adding or removing a page updates this list on purpose. */
const EXPECTED_PAGES = [
  "getting-started",
  "projects-and-library",
  "building-models",
  "code-and-docs",
  "parameters",
  "running-and-plotting",
  "dashboard",
  "debugging",
  "diagnostics",
  "export",
  "signal-sources",
  "background-tasks",
  "keyboard-shortcuts",
  "hydraulics",
];

const LINKS: LinkContext = { pageIds: MANUAL_PAGE_IDS, model: null, signalIds: null };

/** Every inline Markdown link target `[text](target)` outside code. */
function linkTargets(text: string): string[] {
  const withoutCode = text.replace(/```[\s\S]*?```/g, "").replace(/`[^`\n]*`/g, "");
  return [...withoutCode.matchAll(/\]\(([^)\s]+)\)/g)].map((match) => match[1] ?? "");
}

function Shell() {
  useAppShortcuts();
  return (
    <>
      <TopBar theme="dark" onToggleTheme={() => {}} />
      <ShortcutsOverlay />
    </>
  );
}

async function openManual(): Promise<HTMLElement> {
  fireEvent.click(screen.getByTestId("open-manual"));
  return screen.findByTestId("user-manual", {}, { timeout: 10_000 });
}

beforeEach(() => {
  resetHelpStore();
  resetDocumentStore();
  window.localStorage.removeItem(MANUAL_PAGE_KEY);
  window.history.replaceState(null, "", "/");
});

describe("manual pages", () => {
  it("has the expected pages, each with a title", () => {
    expect(MANUAL_PAGES.map((page) => page.id)).toEqual(EXPECTED_PAGES);
    for (const page of MANUAL_PAGES) {
      expect(page.title.length, page.id).toBeGreaterThan(2);
      expect(page.text, page.id).toMatch(/^# /m);
    }
  });

  it("links only to existing manual pages or to external sites", () => {
    for (const page of MANUAL_PAGES) {
      for (const href of linkTargets(page.text)) {
        const target = resolveLink(href, LINKS);
        expect(["page", "external"], `${page.id}: ${href}`).toContain(target.kind);
      }
    }
  });

  it("lists every shortcut of the overlay on the shortcuts page", () => {
    const page = MANUAL_PAGES.find((entry) => entry.id === SHORTCUTS_PAGE_ID);
    expect(page?.text).toContain("Run the model");
    expect(page?.text).toContain("| `Ctrl` + `Enter` |");
  });

  it("filters pages by title and text", () => {
    expect(filterPages(MANUAL_PAGES, "")).toHaveLength(MANUAL_PAGES.length);
    expect(filterPages(MANUAL_PAGES, "ExportInputPass").map((page) => page.id)).toContain("export");
    expect(filterPages(MANUAL_PAGES, "DASHBOARD schedule").map((page) => page.id)).toContain("dashboard");
    expect(filterPages(MANUAL_PAGES, "no-such-word-anywhere")).toEqual([]);
  });
});

describe("the manual dialog", () => {
  it("opens from the help icon as a modal and closes with Escape, returning focus", async () => {
    render(<Shell />);
    const button = screen.getByTestId("open-manual");
    expect(button.getAttribute("aria-label")).toBe("User manual");
    expect(button.getAttribute("title")).toBe("User manual (F1)");
    button.focus();

    const dialog = await openManual();
    expect(dialog.getAttribute("role")).toBe("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(within(dialog).getByTestId("manual-page").getAttribute("data-page")).toBe("getting-started");

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByTestId("user-manual")).toBeNull();
    expect(document.activeElement).toBe(button);
  });

  it("opens with F1 when no block is selected and closes with the close button", async () => {
    render(<Shell />);
    fireEvent.keyDown(document.body, { key: "F1" });
    const dialog = await screen.findByTestId("user-manual", {}, { timeout: 10_000 });
    fireEvent.click(within(dialog).getByTestId("manual-close"));
    expect(screen.queryByTestId("user-manual")).toBeNull();
  });

  it("navigates with the page list and remembers the last page", async () => {
    render(<Shell />);
    let dialog = await openManual();
    fireEvent.click(within(dialog).getByTestId("manual-nav-dashboard"));
    expect(within(dialog).getByTestId("manual-page").getAttribute("data-page")).toBe("dashboard");
    expect(within(dialog).getByTestId("manual-nav-dashboard").getAttribute("aria-current")).toBe("page");
    expect(window.localStorage.getItem(MANUAL_PAGE_KEY)).toBe("dashboard");

    fireEvent.click(within(dialog).getByTestId("manual-close"));
    dialog = await openManual();
    expect(within(dialog).getByTestId("manual-page").getAttribute("data-page")).toBe("dashboard");
  });

  it("follows a page: link inside the dialog and focuses the new page", async () => {
    render(<Shell />);
    const dialog = await openManual();
    const content = within(dialog).getByTestId("manual-page");
    const link = within(content).getByRole("link", { name: "Diagnostics" });
    expect(link.getAttribute("data-link-kind")).toBe("page");
    fireEvent.click(link);
    expect(within(dialog).getByTestId("manual-page").getAttribute("data-page")).toBe("diagnostics");
    expect(document.activeElement).toBe(within(dialog).getByTestId("manual-page"));
  });

  it("renders every page without broken links", async () => {
    render(<Shell />);
    const dialog = await openManual();
    for (const page of MANUAL_PAGES) {
      fireEvent.click(within(dialog).getByTestId(`manual-nav-${page.id}`));
      const content = within(dialog).getByTestId("manual-page");
      expect(content.getAttribute("data-page")).toBe(page.id);
      expect(within(content).getByRole("heading", { level: 1 }).textContent).toBe(page.title);
      expect(within(content).queryAllByTestId("docs-broken-link"), page.id).toHaveLength(0);
      expect(within(content).queryAllByTestId("docs-broken-image"), page.id).toHaveLength(0);
    }
  });

  it("filters the page list with the search box", async () => {
    render(<Shell />);
    const dialog = await openManual();
    const search = within(dialog).getByTestId("manual-search");
    fireEvent.change(search, { target: { value: "breakpoint" } });
    expect(within(dialog).getByTestId("manual-nav-debugging")).toBeTruthy();
    expect(within(dialog).queryByTestId("manual-nav-dashboard")).toBeNull();
    fireEvent.change(search, { target: { value: "no-such-word-anywhere" } });
    expect(within(dialog).getByTestId("manual-no-match")).toBeTruthy();
    // Typing in the search box keeps the focus there (the dialog does not refocus itself).
    search.focus();
    fireEvent.change(search, { target: { value: "plot" } });
    expect(document.activeElement).toBe(search);
  });

  it("hands over to the shortcuts overlay", async () => {
    render(<Shell />);
    const dialog = await openManual();
    fireEvent.click(within(dialog).getByTestId("manual-shortcuts"));
    await waitFor(() => expect(screen.queryByTestId("user-manual")).toBeNull());
    expect(screen.getByTestId("shortcuts-overlay")).toBeTruthy();
    act(() => useHelpStore.getState().setShortcutsOpen(false));
  });

  it("ignores a stored page id that no longer exists", async () => {
    window.localStorage.setItem(MANUAL_PAGE_KEY, "removed-page");
    render(<Shell />);
    const dialog = await openManual();
    expect(within(dialog).getByTestId("manual-page").getAttribute("data-page")).toBe(EXPECTED_PAGES[0]);
  });
});

describe("links in the manual's link context", () => {
  it("opens external links in a new tab and page links through the action", () => {
    const opened: string[] = [];
    const actions: LinkActions = {
      openPage: (id) => opened.push(id),
      showBlock: () => undefined,
      plotSignal: () => undefined,
      notify: () => undefined,
    };
    render(
      <MarkdownView
        text={"[site](https://example.org) and [export](page:export) and [gone](page:nope)"}
        project=""
        model=""
        links={LINKS}
        actions={actions}
      />,
    );
    const external = screen.getByRole("link", { name: "site" });
    expect(external.getAttribute("target")).toBe("_blank");
    expect(external.getAttribute("rel")).toContain("noopener");
    fireEvent.click(screen.getByRole("link", { name: "export" }));
    expect(opened).toEqual(["export"]);
    expect(screen.getAllByTestId("docs-broken-link")).toHaveLength(1);
  });
});
