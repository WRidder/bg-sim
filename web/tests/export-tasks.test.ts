/**
 * FMU export jobs as background tasks: the task of a job document, the listing on load (old
 * finished jobs stay out), the poll loop that runs only while a job is active, a job that
 * disappears from the backend, and Cancel as a DELETE.
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ExportJob } from "../src/contracts/export-job";
import {
  EXPORT_POLL_MS,
  exportTaskId,
  isExportPolling,
  RECENT_MS,
  refreshExports,
  stopExportPolling,
  taskFromJob,
  trackExportJob,
} from "../src/tasks/exportTasks";
import { cancelTask, resetTaskStore, useTaskStore } from "../src/tasks/taskStore";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const fixture = (name: string): ExportJob =>
  JSON.parse(
    readFileSync(path.join(repoRoot, "contracts", "fixtures", "export-job", "valid", name), "utf8"),
  ) as ExportJob;

const doneJob = fixture("export-job.done.json");
const refusedJob = fixture("export-job.refused.json");

function running(job: ExportJob, id = job.id): ExportJob {
  return { ...job, id, status: "running", phase: "reference", report: null, fmu: null, finished: null };
}

interface Call {
  url: string;
  method: string;
}

/** A backend whose GET /api/exports/{id} answers from `jobs` (a queue per id). */
function stubBackend(options: { list?: ExportJob[]; jobs?: Record<string, ExportJob[]>; missing?: string[] }) {
  const calls: Call[] = [];
  const queues = new Map(Object.entries(options.jobs ?? {}).map(([id, list]) => [id, [...list]]));
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method });
      if (url.startsWith("/api/exports?")) {
        return new Response(JSON.stringify(options.list ?? []), { status: 200 });
      }
      const id = decodeURIComponent(url.split("/").pop() ?? "");
      if (method === "DELETE") {
        const queue = queues.get(id);
        const last = queue?.[queue.length - 1];
        if (last !== undefined) {
          queues.set(id, [{ ...last, status: "cancelled", phase: null, finished: "2026-10-30T10:17:00Z" }]);
        }
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      }
      if (options.missing?.includes(id)) {
        return new Response(JSON.stringify({ detail: `unknown export '${id}'` }), { status: 404 });
      }
      const queue = queues.get(id) ?? [];
      const next = queue.length > 1 ? queue.shift() : queue[0];
      return new Response(JSON.stringify(next), { status: 200 });
    }),
  );
  return calls;
}

beforeEach(() => {
  localStorage.clear();
  resetTaskStore();
});

afterEach(() => {
  stopExportPolling();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  resetTaskStore();
});

describe("export tasks", () => {
  it("maps a job document to a task", () => {
    const done = taskFromJob(doneJob);
    expect(done).toMatchObject({
      id: `export:${doneJob.id}`,
      kind: "fmu-export",
      title: "FMU export · speed-control",
      project: "dc-motor",
      model: "speed-control",
      status: "done",
      phase: "speed_control.fmu (89.1 KB)",
      started: Date.parse("2026-10-30T10:15:00Z"),
      finished: Date.parse("2026-10-30T10:16:12Z"),
      cancellable: true,
    });
    expect(done.result).toEqual({
      href: `/api/exports/${doneJob.id}/fmu`,
      fileName: "speed_control.fmu",
      label: "Download speed_control.fmu (89.1 KB)",
    });

    const live = taskFromJob(running(doneJob));
    expect(live.phase).toBe("Running the reference simulation");
    expect(live.result).toBeNull();
    expect(taskFromJob({ ...running(doneJob), status: "queued", phase: null }).phase).toBe(
      "Waiting for another export to finish",
    );

    const refused = taskFromJob(refusedJob);
    expect(refused.status).toBe("refused");
    expect(refused.error).toBe(refusedJob.error);
    expect(refused.title).toContain(" / ");
  });

  it("lists the project's jobs on load and leaves old finished ones out", async () => {
    const now = Date.parse("2026-10-30T12:00:00Z");
    const old = { ...doneJob, id: "export-old", finished: new Date(now - RECENT_MS - 1000).toISOString() };
    const calls = stubBackend({
      list: [running(doneJob, "export-live"), doneJob, old],
      jobs: { "export-live": [running(doneJob, "export-live")] },
    });
    await refreshExports("dc-motor", now);
    expect(calls[0]?.url).toBe("/api/exports?project=dc-motor");
    expect(useTaskStore.getState().tasks.map((t) => t.id)).toEqual([
      exportTaskId("export-live"),
      exportTaskId(doneJob.id),
    ]);
    expect(isExportPolling()).toBe(true);
  });

  it("polls only while a job is active and announces its end", async () => {
    vi.useFakeTimers();
    const id = "export-poll";
    const calls = stubBackend({
      jobs: { [id]: [running(doneJob, id), running(doneJob, id), { ...doneJob, id }] },
    });
    trackExportJob(running(doneJob, id));
    expect(isExportPolling()).toBe(true);

    for (let k = 0; k < 3; k += 1) {
      await vi.advanceTimersByTimeAsync(EXPORT_POLL_MS);
    }
    const task = useTaskStore.getState().tasks.find((t) => t.id === exportTaskId(id));
    expect(task?.status).toBe("done");
    expect(task?.unseen).toBe(true);
    expect(useTaskStore.getState().announcement?.text).toBe("FMU export · speed-control finished");
    expect(isExportPolling()).toBe(false);

    const gets = calls.length;
    await vi.advanceTimersByTimeAsync(EXPORT_POLL_MS * 4);
    expect(calls.length).toBe(gets);
  });

  it("fails a job the backend no longer knows", async () => {
    vi.useFakeTimers();
    stubBackend({ missing: ["export-gone"] });
    trackExportJob(running(doneJob, "export-gone"));
    await vi.advanceTimersByTimeAsync(EXPORT_POLL_MS);
    const task = useTaskStore.getState().tasks[0];
    expect(task?.status).toBe("failed");
    expect(task?.phase).toBe("The export is no longer on the backend");
    expect(isExportPolling()).toBe(false);
  });

  it("keeps polling through a backend that cannot be reached", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("offline"))));
    trackExportJob(running(doneJob, "export-offline"));
    await vi.advanceTimersByTimeAsync(EXPORT_POLL_MS);
    expect(useTaskStore.getState().connectionError).toMatch(/Cannot reach the bg-sim backend/);
    expect(useTaskStore.getState().tasks[0]?.status).toBe("running");
    expect(isExportPolling()).toBe(true);
  });

  it("cancels with a DELETE and reads the job back", async () => {
    const id = "export-cancel";
    const calls = stubBackend({ jobs: { [id]: [running(doneJob, id)] } });
    trackExportJob(running(doneJob, id));
    expect(await cancelTask(exportTaskId(id))).toBe(true);
    expect(calls.some((c) => c.method === "DELETE" && c.url === `/api/exports/${id}`)).toBe(true);
    expect(useTaskStore.getState().tasks[0]?.status).toBe("cancelled");
  });
});
