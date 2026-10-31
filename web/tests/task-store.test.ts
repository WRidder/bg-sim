/**
 * The background tasks registry: ordering, the "unseen" dot and the announcement when a
 * task seen running ends, the dialog that watches a task, dismissing (kept over a reload)
 * and cancelling through the registered canceller.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  cancelTask,
  endingText,
  MAX_FINISHED,
  registerCanceller,
  resetTaskStore,
  useTaskStore,
  type Task,
} from "../src/tasks/taskStore";

function task(id: string, patch: Partial<Task> = {}): Task {
  return {
    id,
    kind: "fmu-export",
    title: `FMU export · ${id}`,
    project: "demo",
    model: "plant",
    status: "running",
    phase: "Flattening the model",
    progress: null,
    started: 1000,
    finished: null,
    error: null,
    unseen: false,
    cancellable: true,
    result: null,
    exportJob: null,
    ...patch,
  };
}

const store = () => useTaskStore.getState();

beforeEach(() => {
  localStorage.clear();
  resetTaskStore();
});

afterEach(() => {
  localStorage.clear();
  resetTaskStore();
});

describe("task registry", () => {
  it("orders active tasks first, newest first in each group", () => {
    store().putTask(task("a", { status: "done", started: 1, finished: 5 }));
    store().putTask(task("b", { started: 2 }));
    store().putTask(task("c", { status: "failed", started: 3, finished: 9 }));
    store().putTask(task("d", { status: "queued", started: 4 }));
    expect(store().tasks.map((t) => t.id)).toEqual(["d", "b", "c", "a"]);
  });

  it("marks a task that ends unwatched as unseen and announces it", () => {
    store().putTask(task("a"));
    expect(store().announcement).toBeNull();
    store().putTask(task("a", { status: "done", finished: 2000 }));
    expect(store().tasks[0]?.unseen).toBe(true);
    expect(store().announcement?.text).toBe("FMU export · a finished");
    expect(store().announcement?.taskId).toBe("a");

    store().markSeen();
    expect(store().tasks[0]?.unseen).toBe(false);
  });

  it("does not announce a task that was already finished when it was first listed", () => {
    store().putTask(task("old", { status: "done", finished: 2000 }));
    expect(store().tasks[0]?.unseen).toBe(false);
    expect(store().announcement).toBeNull();
  });

  it("keeps quiet about the task a dialog watches", () => {
    store().putTask(task("a"));
    store().setViewing("a");
    store().putTask(task("a", { status: "failed", error: "boom", finished: 2000 }));
    expect(store().tasks[0]?.unseen).toBe(false);
    expect(store().announcement).toBeNull();
  });

  it("clears the unseen mark of a task a dialog starts watching", () => {
    store().putTask(task("a"));
    store().putTask(task("a", { status: "done", finished: 2000 }));
    store().setViewing("a");
    expect(store().tasks[0]?.unseen).toBe(false);
  });

  it("dismisses finished tasks, and a reload's listing does not bring them back", () => {
    store().putTask(task("a", { status: "done", finished: 2 }));
    store().putTask(task("b", { status: "cancelled", finished: 3 }));
    store().putTask(task("c"));
    store().dismissTask("c"); // active: not dismissable
    store().dismissTask("a");
    expect(store().tasks.map((t) => t.id)).toEqual(["c", "b"]);
    store().clearFinished();
    expect(store().tasks.map((t) => t.id)).toEqual(["c"]);

    resetTaskStore(); // a reload: the dismissed ids come back from localStorage
    store().putTask(task("a", { status: "done", finished: 2 }));
    store().putTask(task("b", { status: "cancelled", finished: 3 }));
    expect(store().tasks).toEqual([]);
  });

  it("keeps at most MAX_FINISHED finished tasks", () => {
    for (let k = 0; k < MAX_FINISHED + 5; k += 1) {
      store().putTask(task(`t${k}`, { status: "done", started: k, finished: k }));
    }
    expect(store().tasks).toHaveLength(MAX_FINISHED);
    expect(store().tasks[0]?.id).toBe(`t${MAX_FINISHED + 4}`);
  });

  it("cancels through the registered canceller, only while active", async () => {
    const cancel = vi.fn();
    store().putTask(task("a"));
    registerCanceller("a", cancel);
    expect(await cancelTask("a")).toBe(true);
    expect(cancel).toHaveBeenCalledTimes(1);

    store().putTask(task("a", { status: "cancelled", finished: 5 }));
    expect(await cancelTask("a")).toBe(false);
    expect(await cancelTask("missing")).toBe(false);
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it("words the end of each status", () => {
    expect(endingText({ title: "CSV export · arm", status: "cancelled" })).toBe(
      "CSV export · arm was cancelled",
    );
    expect(endingText({ title: "FMU export · arm", status: "refused" })).toBe("FMU export · arm was refused");
  });
});
