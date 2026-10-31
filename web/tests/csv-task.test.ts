/**
 * The plot's CSV export as a background task: rows received against `X-BGSim-Rows`, the
 * file saved at the end, a backend error, and Cancel aborting the request.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { startCsvExport } from "../src/tasks/csvTask";
import { cancelTask, resetTaskStore, useTaskStore } from "../src/tasks/taskStore";

const encoder = new TextEncoder();

function csvResponse(chunks: string[], rows: number, signal?: AbortSignal): Response {
  const stream = new ReadableStream<Uint8Array>({
    async pull(controller) {
      const next = chunks.shift();
      if (next === undefined) {
        controller.close();
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 5));
      if (signal?.aborted) {
        controller.error(new DOMException("aborted", "AbortError"));
        return;
      }
      controller.enqueue(encoder.encode(next));
    },
  });
  return new Response(stream, { status: 200, headers: { "x-bgsim-rows": String(rows) } });
}

let saved: { href: string; download: string }[] = [];

beforeEach(() => {
  resetTaskStore();
  saved = [];
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:csv"), revokeObjectURL: vi.fn() }));
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    saved.push({ href: this.href, download: this.download });
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  resetTaskStore();
});

describe("CSV export task", () => {
  it("streams the CSV, reports progress and saves the file", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => csvResponse(["t,a\n0,1\n", "0.5,2\n", "1,3\n"], 3)),
    );
    const done = startCsvExport({
      url: "/api/runs/run-1/export.csv?ids=a",
      fileName: "run-1.csv",
      title: "CSV export · plant (1 signal)",
      model: "plant",
    });
    const task = useTaskStore.getState().tasks[0];
    expect(task).toMatchObject({ kind: "csv-export", status: "running", cancellable: true });
    expect(task?.phase).toBe("Preparing the data on the backend");
    const phases: (string | null)[] = [];
    const progress: (number | null)[] = [];
    const unsubscribe = useTaskStore.subscribe((state) => {
      phases.push(state.tasks[0]?.phase ?? null);
      progress.push(state.tasks[0]?.progress ?? null);
    });

    const id = await done;
    unsubscribe();
    // The first chunk (header and one row) is reported against the 3 rows.
    expect(phases).toContain("Receiving rows: 1 of 3 (8 B)");
    expect(progress).toContain(1 / 3);
    const finished = useTaskStore.getState().tasks.find((t) => t.id === id);
    expect(finished?.status).toBe("done");
    expect(finished?.progress).toBe(1);
    expect(finished?.phase).toBe("Saved run-1.csv (18 B)");
    expect(saved).toEqual([{ href: "blob:csv", download: "run-1.csv" }]);
    expect(finished?.unseen).toBe(true);
  });

  it("fails with the backend's message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "unknown signal ids: x" }), { status: 400 })),
    );
    const id = await startCsvExport({ url: "/x.csv", fileName: "x.csv", title: "CSV export · x" });
    const task = useTaskStore.getState().tasks.find((t) => t.id === id);
    expect(task?.status).toBe("failed");
    expect(task?.error).toBe("unknown signal ids: x");
    expect(saved).toEqual([]);
  });

  it("cancels by aborting the request", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) =>
        csvResponse(["t,a\n", "0,1\n", "1,2\n", "2,3\n", "3,4\n"], 4, init?.signal ?? undefined),
      ),
    );
    const done = startCsvExport({ url: "/y.csv", fileName: "y.csv", title: "CSV export · y" });
    const id = useTaskStore.getState().tasks[0]?.id ?? "";
    await new Promise((resolve) => setTimeout(resolve, 8));
    expect(await cancelTask(id)).toBe(true);
    await done;
    const task = useTaskStore.getState().tasks.find((t) => t.id === id);
    expect(task?.status).toBe("cancelled");
    expect(saved).toEqual([]);
  });
});
