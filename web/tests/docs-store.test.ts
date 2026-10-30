import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../src/docs/docsApi";
import { dirtyPageIds, resetDocsStore, useDocsStore } from "../src/docs/docsStore";
import { hasUnsavedDocs } from "../src/docs/leaveGuard";
import type { Docs } from "../src/docs/pageTree";

vi.mock("../src/docs/docsApi");

const api_ = vi.mocked(api);

const TREE: Docs = {
  format: "bgsim.docs",
  version: 1,
  pages: [
    { id: "a", title: "A", file: "pages/a.md", children: [{ id: "b", title: "B", file: "pages/b.md", children: [] }] },
  ],
};

beforeEach(() => {
  resetDocsStore();
  api_.fetchManifest.mockResolvedValue(structuredClone(TREE));
  api_.listAssets.mockResolvedValue({ assets: [{ file: "0123456789ab.png", bytes: 3, used: false }], unused: 1 });
  api_.fetchPage.mockImplementation(async (_p, _m, id) => `text of ${id}`);
  api_.savePage.mockResolvedValue();
  api_.saveManifest.mockImplementation(async (_p, _m, docs) => docs);
});

describe("docs store", () => {
  it("loads the tree, selects the first page and reads its text", async () => {
    await useDocsStore.getState().load("demo", "m");
    const state = useDocsStore.getState();
    expect(state.status).toBe("ready");
    expect(state.selected).toBe("a");
    expect(state.saved).toEqual({ a: "text of a" });
    expect(state.unusedImages).toBe(1);
    expect([...state.assets]).toEqual(["0123456789ab.png"]);
  });

  it("tracks unsaved edits and clears them on save", async () => {
    await useDocsStore.getState().load("demo", "m");
    expect(hasUnsavedDocs()).toBe(false);
    useDocsStore.getState().setDraft("a", "changed");
    expect(dirtyPageIds(useDocsStore.getState())).toEqual(["a"]);
    expect(hasUnsavedDocs()).toBe(true);
    useDocsStore.getState().setDraft("a", "text of a");
    expect(hasUnsavedDocs()).toBe(false); // back to the saved text is not a change

    useDocsStore.getState().setDraft("a", "changed");
    expect(await useDocsStore.getState().saveAll()).toBe(true);
    expect(api_.savePage).toHaveBeenCalledWith("demo", "m", "a", "changed");
    expect(useDocsStore.getState().saved.a).toBe("changed");
    expect(hasUnsavedDocs()).toBe(false);
  });

  it("keeps the draft and reports the problem when a save fails", async () => {
    await useDocsStore.getState().load("demo", "m");
    api_.savePage.mockRejectedValue(new Error("disk full"));
    useDocsStore.getState().setDraft("a", "changed");
    expect(await useDocsStore.getState().save("a")).toBe(false);
    expect(useDocsStore.getState().problem).toBe("disk full");
    expect(hasUnsavedDocs()).toBe(true);
  });

  it("saves unsaved edits before another model is opened", async () => {
    await useDocsStore.getState().load("demo", "m");
    useDocsStore.getState().setDraft("a", "changed");
    await useDocsStore.getState().load("demo", "other");
    expect(api_.savePage).toHaveBeenCalledWith("demo", "m", "a", "changed");
    expect(useDocsStore.getState().model).toBe("other");
    expect(useDocsStore.getState().drafts).toEqual({});
  });

  it("creates pages, saving the tree each time, and rolls back on failure", async () => {
    await useDocsStore.getState().load("demo", "m");
    await useDocsStore.getState().newChild("a");
    expect(useDocsStore.getState().docs.pages[0]?.children.map((c) => c.id)).toEqual(["b", "new-page"]);
    expect(useDocsStore.getState().selected).toBe("new-page");
    expect(api_.saveManifest).toHaveBeenCalledTimes(1);

    api_.saveManifest.mockRejectedValue(new Error("read-only"));
    await useDocsStore.getState().newSibling("a");
    expect(useDocsStore.getState().docs.pages.map((p) => p.id)).toEqual(["a"]);
    expect(useDocsStore.getState().problem).toBe("read-only");
  });

  it("deletes with the chosen mode and drops the page texts", async () => {
    await useDocsStore.getState().load("demo", "m");
    await useDocsStore.getState().select("b");
    useDocsStore.getState().setDraft("b", "edit");
    api_.deletePage.mockResolvedValue([]);
    await useDocsStore.getState().remove("a", "subtree");
    expect(api_.deletePage).toHaveBeenCalledWith("demo", "m", "a", "delete");
    const state = useDocsStore.getState();
    expect(state.docs.pages).toEqual([]);
    expect(state.selected).toBeNull();
    expect(state.drafts).toEqual({});
    expect(state.saved).toEqual({});

    await useDocsStore.getState().load("demo", "m2");
    api_.deletePage.mockResolvedValue([{ id: "b", title: "B", file: "pages/b.md", children: [] }]);
    await useDocsStore.getState().remove("a", "promote");
    expect(api_.deletePage).toHaveBeenLastCalledWith("demo", "m2", "a", "promote");
    expect(useDocsStore.getState().docs.pages.map((p) => p.id)).toEqual(["b"]);
    expect(useDocsStore.getState().selected).toBe("b");
  });

  it("saves the pages before cleaning up unused images", async () => {
    await useDocsStore.getState().load("demo", "m");
    useDocsStore.getState().setDraft("a", "uses ![](assets/0123456789ab.png)");
    api_.deleteUnusedAssets.mockResolvedValue([]);
    await useDocsStore.getState().cleanUpImages();
    expect(api_.savePage.mock.invocationCallOrder[0]!).toBeLessThan(
      api_.deleteUnusedAssets.mock.invocationCallOrder[0]!,
    );
  });
});
