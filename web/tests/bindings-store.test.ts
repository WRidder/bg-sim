import { beforeEach, describe, expect, it } from "vitest";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

describe("setBindings", () => {
  beforeEach(() => {
    resetDocumentStore();
    useDocumentStore.getState().openDocument("p", "M", createEmptyModel("M"));
  });

  it("is one undoable edit and removes the field when emptied", () => {
    const store = useDocumentStore;
    store.getState().setBindings([{ target: "joint:j", property: "position", signal: "A/x", gain: 2 }]);
    expect(store.getState().doc?.bindings).toEqual([{ target: "joint:j", property: "position", signal: "A/x", gain: 2 }]);
    expect(store.getState().saveState).toBe("dirty");
    store.getState().setBindings([{ target: "joint:j", property: "position", signal: "A/x", gain: 3 }]);
    store.getState().undo();
    expect(store.getState().doc?.bindings?.[0]?.gain).toBe(2);
    store.getState().undo();
    expect(store.getState().doc?.bindings ?? []).toEqual([]);
    store.getState().redo();
    expect(store.getState().doc?.bindings?.[0]?.gain).toBe(2);
    store.getState().setBindings([]);
    expect(store.getState().doc && "bindings" in store.getState().doc!).toBe(false);
  });
});
