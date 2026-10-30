import { describe, expect, it } from "vitest";

import {
  EMPTY_DOCS,
  addChild,
  addSibling,
  allIds,
  dropPage,
  indentPage,
  keyboardMove,
  moveDown,
  moveUp,
  movePage,
  outdentPage,
  removePage,
  renamePage,
  slugify,
  uniqueId,
  visibleRows,
  type Docs,
  type DocsPage,
} from "../src/docs/pageTree";

function page(id: string, children: DocsPage[] = []): DocsPage {
  return { id, title: id, file: `pages/${id}.md`, children };
}

function docs(...pages: DocsPage[]): Docs {
  return { format: "bgsim.docs", version: 1, pages };
}

/** `a(b,c(d)),e` */
function show(tree: Docs): string {
  const render = (pages: DocsPage[]): string =>
    pages.map((p) => (p.children.length === 0 ? p.id : `${p.id}(${render(p.children)})`)).join(",");
  return render(tree.pages);
}

const SAMPLE = docs(page("a", [page("b"), page("c", [page("d")])]), page("e"));

describe("ids", () => {
  it("slugifies titles into page ids", () => {
    expect(slugify("Plant model")).toBe("plant-model");
    expect(slugify("  Überblick: LQR/PID  ")).toBe("uberblick-lqr-pid");
    expect(slugify("!!!")).toBe("page");
    expect(slugify("x".repeat(100)).length).toBeLessThanOrEqual(48);
  });

  it("keeps ids unique and stable", () => {
    expect(uniqueId("Notes", new Set(["notes", "notes-2"]))).toBe("notes-3");
    const first = addSibling(EMPTY_DOCS, null, "Notes");
    const second = first && addSibling(first.docs, null, "Notes");
    expect(second && [...allIds(second.docs.pages)]).toEqual(["notes", "notes-2"]);
  });

  it("renaming changes the title, not the id or the file", () => {
    const renamed = renamePage(SAMPLE, "b", "Brand new");
    expect(renamed?.pages[0]?.children[0]).toEqual({
      id: "b",
      title: "Brand new",
      file: "pages/b.md",
      children: [],
    });
    expect(renamePage(SAMPLE, "b", "  ")).toBeNull();
    expect(renamePage(SAMPLE, "b", "b")).toBeNull();
    expect(renamePage(SAMPLE, "zzz", "x")).toBeNull();
  });
});

describe("adding", () => {
  it("adds a sibling after a page, also nested, or at the end", () => {
    expect(show(addSibling(SAMPLE, "b")!.docs)).toBe("a(b,new-page,c(d)),e");
    expect(show(addSibling(SAMPLE, "e")!.docs)).toBe("a(b,c(d)),e,new-page");
    expect(show(addSibling(SAMPLE, null)!.docs)).toBe("a(b,c(d)),e,new-page");
    expect(addSibling(SAMPLE, "missing")).toBeNull();
  });

  it("adds a child as the last child", () => {
    const added = addChild(SAMPLE, "c")!;
    expect(show(added.docs)).toBe("a(b,c(d,new-page)),e");
    expect(added.id).toBe("new-page");
    expect(addChild(SAMPLE, "missing")).toBeNull();
  });

  it("does not change the original tree", () => {
    addChild(SAMPLE, "a");
    expect(show(SAMPLE)).toBe("a(b,c(d)),e");
  });
});

describe("deleting", () => {
  it("deletes a subtree", () => {
    const result = removePage(SAMPLE, "c", "subtree")!;
    expect(show(result.docs)).toBe("a(b),e");
    expect(result.removed).toEqual(["c", "d"]);
  });

  it("moves the children up in place", () => {
    const result = removePage(SAMPLE, "a", "promote")!;
    expect(show(result.docs)).toBe("b,c(d),e");
    expect(result.removed).toEqual(["a"]);
    expect(show(removePage(SAMPLE, "c", "promote")!.docs)).toBe("a(b,d),e");
  });

  it("ignores an unknown page", () => {
    expect(removePage(SAMPLE, "zzz", "subtree")).toBeNull();
  });
});

describe("reordering and re-parenting", () => {
  it("moves up and down among siblings", () => {
    expect(show(moveDown(SAMPLE, "b")!)).toBe("a(c(d),b),e");
    expect(show(moveUp(SAMPLE, "c")!)).toBe("a(c(d),b),e");
    expect(show(moveUp(SAMPLE, "e")!)).toBe("e,a(b,c(d))");
    expect(moveUp(SAMPLE, "a")).toBeNull();
    expect(moveDown(SAMPLE, "e")).toBeNull();
  });

  it("indents under the previous sibling and outdents after the parent", () => {
    expect(show(indentPage(SAMPLE, "e")!)).toBe("a(b,c(d),e)");
    expect(show(indentPage(SAMPLE, "c")!)).toBe("a(b(c(d))),e");
    expect(indentPage(SAMPLE, "b")).toBeNull();
    expect(show(outdentPage(SAMPLE, "d")!)).toBe("a(b,c,d),e");
    expect(show(outdentPage(SAMPLE, "b")!)).toBe("a(c(d)),b,e");
    expect(outdentPage(SAMPLE, "a")).toBeNull();
  });

  it("maps the Alt+Arrow keys", () => {
    expect(show(keyboardMove(SAMPLE, "e", "ArrowUp")!)).toBe("e,a(b,c(d))");
    expect(show(keyboardMove(SAMPLE, "b", "ArrowDown")!)).toBe("a(c(d),b),e");
    expect(show(keyboardMove(SAMPLE, "e", "ArrowRight")!)).toBe("a(b,c(d),e)");
    expect(show(keyboardMove(SAMPLE, "d", "ArrowLeft")!)).toBe("a(b,c,d),e");
    expect(keyboardMove(SAMPLE, "e", "Enter")).toBeNull();
  });

  it("refuses to move a page into itself or its descendants", () => {
    expect(movePage(SAMPLE, "a", "a", 0)).toBeNull();
    expect(movePage(SAMPLE, "a", "d", 0)).toBeNull();
    expect(dropPage(SAMPLE, "a", "d", "inside")).toBeNull();
    expect(dropPage(SAMPLE, "a", "b", "after")).toBeNull();
    expect(dropPage(SAMPLE, "a", "a", "inside")).toBeNull();
  });

  it("drops before, after and inside a page", () => {
    expect(show(dropPage(SAMPLE, "e", "b", "before")!)).toBe("a(e,b,c(d))");
    expect(show(dropPage(SAMPLE, "e", "b", "after")!)).toBe("a(b,e,c(d))");
    expect(show(dropPage(SAMPLE, "e", "c", "inside")!)).toBe("a(b,c(d,e))");
    expect(show(dropPage(SAMPLE, "d", "a", "before")!)).toBe("d,a(b,c),e");
    expect(show(dropPage(SAMPLE, "a", "e", "after")!)).toBe("e,a(b,c(d))");
    expect(dropPage(SAMPLE, "e", "a", "after")).toBeNull(); // already there
  });
});

describe("visible rows", () => {
  it("lists depth-first and hides collapsed subtrees", () => {
    const rows = visibleRows(SAMPLE, new Set());
    expect(rows.map((r) => `${r.page.id}:${r.depth}`)).toEqual(["a:0", "b:1", "c:1", "d:2", "e:0"]);
    expect(rows[1]).toMatchObject({ parentId: "a", index: 0, siblingCount: 2 });
    expect(visibleRows(SAMPLE, new Set(["a"])).map((r) => r.page.id)).toEqual(["a", "e"]);
  });
});
