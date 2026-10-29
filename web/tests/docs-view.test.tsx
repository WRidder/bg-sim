import { createEvent, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DocsTree } from "../src/docs/DocsTree";
import { normalizeDisplayMath } from "../src/docs/displayMath";
import { MarkdownView, type LinkActions } from "../src/docs/MarkdownView";
import type { LinkContext } from "../src/docs/docsLinks";
import type { Docs, DocsPage } from "../src/docs/pageTree";

const links: LinkContext = { pageIds: new Set(["plant"]), model: null, signalIds: null };

function actions(): LinkActions {
  return { openPage: vi.fn(), showBlock: vi.fn(), plotSignal: vi.fn(), notify: vi.fn() };
}

function view(text: string, a: LinkActions = actions(), context: LinkContext = links) {
  return render(<MarkdownView text={text} project="demo" model="m" links={context} actions={a} />);
}

describe("MarkdownView", () => {
  it("renders inline and display math with KaTeX", () => {
    const { container } = view("Energy $E=mc^2$.\n\n$$\\int_0^1 x\\,dx$$\n");
    expect(container.querySelectorAll(".katex").length).toBe(2);
    expect(container.querySelectorAll(".katex-display").length).toBe(1);
  });

  it("treats a line that is only $$...$$ as display math, but not inside code", () => {
    expect(normalizeDisplayMath("$$a+b$$")).toBe("$$\na+b\n$$");
    expect(normalizeDisplayMath("x $$a$$ y")).toBe("x $$a$$ y");
    expect(normalizeDisplayMath("```\n$$a$$\n```\n$$b$$")).toBe("```\n$$a$$\n```\n$$\nb\n$$");
    const { container } = view("$$\\frac{a}{b}$$");
    expect(container.querySelectorAll(".katex-display").length).toBe(1);
  });

  it("renders tables, task lists and footnotes", () => {
    const { container } = view("| a | b |\n|---|---|\n| 1 | 2 |\n\n- [x] done\n- [ ] todo\n\nText[^1]\n\n[^1]: note\n");
    expect(container.querySelector("table")).not.toBeNull();
    expect(container.querySelectorAll('input[type="checkbox"]').length).toBe(2);
    expect(container.querySelector("section[data-footnotes]")).not.toBeNull();
  });

  it("drops raw HTML and scripts", () => {
    const { container } = view('<script>window.hacked = 1</script><img src=x onerror="window.hacked=1"><b>bold</b>\n\n[x](javascript:alert(1))');
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("[onerror]")).toBeNull();
    expect(container.querySelector('a[href^="javascript"]')).toBeNull();
  });

  it("follows page, block and signal links", () => {
    const a = actions();
    const context: LinkContext = {
      pageIds: new Set(["plant"]),
      model: null,
      signalIds: new Set(["Body/theta"]),
    };
    view("[p](page:plant) [s](signal:Body/theta)", a, context);
    fireEvent.click(screen.getByText("p"));
    expect(a.openPage).toHaveBeenCalledWith("plant");
    fireEvent.click(screen.getByText("s"));
    expect(a.plotSignal).toHaveBeenCalledWith("Body/theta");
  });

  it("marks unknown targets as broken with a tooltip", () => {
    view("[x](page:ghost) and [y](block:Nope)");
    const broken = screen.getAllByTestId("docs-broken-link");
    expect(broken).toHaveLength(2);
    expect(broken[0]?.getAttribute("title")).toContain('no page "ghost"');
    expect(broken[1]?.getAttribute("title")).toContain("Open the model");
  });

  it("resolves asset images against the backend and applies the width syntax", () => {
    const { container } = view("![Plant|300](assets/0123456789ab.png)");
    const img = container.querySelector("img");
    expect(img?.getAttribute("src")).toBe("/api/projects/demo/docs/m/assets/0123456789ab.png");
    expect(img?.getAttribute("alt")).toBe("Plant");
    expect(img?.style.width).toBe("300px");
    expect(screen.getByRole("button", { name: "Copy image" })).toBeTruthy();
  });

  it("marks external images and refuses other sources", () => {
    const { container } = view("![x](https://example.org/a.png)\n\n![y](images/local.png)");
    expect(screen.getByTestId("docs-image-external").textContent).toBe("external image");
    expect(container.querySelector("img")?.getAttribute("src")).toBe("https://example.org/a.png");
    expect(screen.getByTestId("docs-broken-image").textContent).toContain("not an assets/ image");
  });

  it("shows a broken-image note when the file is missing", () => {
    const { container } = view("![](assets/0123456789ab.png)");
    fireEvent.error(container.querySelector("img")!);
    expect(screen.getByTestId("docs-broken-image").textContent).toContain("missing from this model");
  });
});

function page(id: string, children: DocsPage[] = []): DocsPage {
  return { id, title: id.toUpperCase(), file: `pages/${id}.md`, children };
}

const TREE: Docs = {
  format: "bgsim.docs",
  version: 1,
  pages: [page("a", [page("b"), page("c")]), page("d")],
};

function tree(overrides: Partial<React.ComponentProps<typeof DocsTree>> = {}) {
  const props = {
    docs: TREE,
    selected: "a",
    dirty: new Set<string>(),
    onSelect: vi.fn(),
    onNewSibling: vi.fn(),
    onNewChild: vi.fn(),
    onRename: vi.fn(),
    onRemove: vi.fn(),
    onMove: vi.fn(),
    onMoveKey: vi.fn(async () => true),
    ...overrides,
  };
  render(<DocsTree {...props} />);
  return props;
}

describe("DocsTree", () => {
  it("is an ARIA tree with levels, sizes and expansion", () => {
    tree();
    expect(screen.getByRole("tree", { name: "Pages" })).toBeTruthy();
    const items = screen.getAllByRole("treeitem");
    expect(items.map((i) => i.textContent)).toEqual(["▾A", "B", "C", "D"]);
    expect(items[0]?.getAttribute("aria-expanded")).toBe("true");
    expect(items[0]?.getAttribute("aria-selected")).toBe("true");
    expect(items[1]?.getAttribute("aria-level")).toBe("2");
    expect(items[1]?.getAttribute("aria-posinset")).toBe("1");
    expect(items[1]?.getAttribute("aria-setsize")).toBe("2");
    expect(items[1]?.getAttribute("aria-expanded")).toBeNull();
  });

  it("moves focus with the arrow keys and collapses with Left", () => {
    tree();
    const a = screen.getByTestId("docs-tree-item-a");
    a.focus();
    fireEvent.keyDown(a, { key: "ArrowDown" });
    expect(document.activeElement).toBe(screen.getByTestId("docs-tree-item-b"));
    fireEvent.keyDown(document.activeElement!, { key: "ArrowLeft" });
    expect(document.activeElement).toBe(a);
    fireEvent.keyDown(a, { key: "ArrowLeft" });
    expect(screen.queryByTestId("docs-tree-item-b")).toBeNull();
    fireEvent.keyDown(a, { key: "ArrowRight" });
    expect(screen.getByTestId("docs-tree-item-b")).toBeTruthy();
  });

  it("selects with Enter, renames with F2 and deletes with Delete", () => {
    const props = tree();
    const b = screen.getByTestId("docs-tree-item-b");
    b.focus();
    fireEvent.keyDown(b, { key: "Enter" });
    expect(props.onSelect).toHaveBeenCalledWith("b");
    fireEvent.keyDown(b, { key: "Delete" });
    expect(props.onRemove).toHaveBeenCalledWith("b");
    fireEvent.keyDown(b, { key: "F2" });
    const input = screen.getByLabelText("Page title");
    fireEvent.change(input, { target: { value: "Better" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(props.onRename).toHaveBeenCalledWith("b", "Better");
  });

  it("renames on double click and cancels with Escape", () => {
    const props = tree();
    fireEvent.doubleClick(screen.getByTestId("docs-tree-item-d"));
    const input = screen.getByLabelText("Page title");
    fireEvent.keyDown(input, { key: "Escape" });
    expect(props.onRename).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Page title")).toBeNull();
  });

  it("reorders and re-parents with Alt+Arrow", () => {
    const props = tree();
    const c = screen.getByTestId("docs-tree-item-c");
    for (const key of ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]) {
      fireEvent.keyDown(c, { key, altKey: true });
      expect(props.onMoveKey).toHaveBeenLastCalledWith("c", key);
    }
  });

  it("drops a dragged page before, after or inside another", () => {
    const props = tree();
    const store = new Map<string, string>();
    const dataTransfer = {
      setData: (type: string, value: string) => store.set(type, value),
      getData: (type: string) => store.get(type) ?? "",
      dropEffect: "none",
      effectAllowed: "all",
    };
    const d = screen.getByTestId("docs-tree-item-d");
    const b = screen.getByTestId("docs-tree-item-b");
    fireEvent.dragStart(d, { dataTransfer });
    vi.spyOn(b, "getBoundingClientRect").mockReturnValue({ top: 0, height: 100, bottom: 100, left: 0, right: 10, width: 10, x: 0, y: 0, toJSON: () => ({}) });
    const at = (type: "dragOver" | "drop", clientY: number): void => {
      const event = createEvent[type](b, { dataTransfer });
      Object.defineProperty(event, "clientY", { value: clientY });
      fireEvent(b, event);
    };
    at("dragOver", 10);
    expect(b.getAttribute("data-drop")).toBe("before");
    at("drop", 10);
    expect(props.onMove).toHaveBeenCalledWith("d", "b", "before");
    fireEvent.dragStart(d, { dataTransfer });
    at("drop", 50);
    expect(props.onMove).toHaveBeenLastCalledWith("d", "b", "inside");
  });

  it("does not accept a drop on the page itself or its descendants", () => {
    const props = tree();
    const store = new Map<string, string>();
    const dataTransfer = {
      setData: (type: string, value: string) => store.set(type, value),
      getData: (type: string) => store.get(type) ?? "",
      dropEffect: "none",
      effectAllowed: "all",
    };
    fireEvent.dragStart(screen.getByTestId("docs-tree-item-a"), { dataTransfer });
    fireEvent.drop(screen.getByTestId("docs-tree-item-b"), { dataTransfer });
    expect(props.onMove).not.toHaveBeenCalled();
  });

  it("marks unsaved pages", () => {
    tree({ dirty: new Set(["b"]) });
    expect(screen.getByTestId("docs-tree-item-b").getAttribute("data-dirty")).toBe("true");
    expect(screen.getByTestId("docs-tree-item-b").textContent).toContain("Unsaved changes");
  });
});
