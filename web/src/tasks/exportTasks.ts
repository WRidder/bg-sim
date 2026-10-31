/**
 * FMU export jobs as background tasks. The jobs run on the backend (one at a time, in a
 * Julia process of their own), so a task outlives the Export dialog and the page:
 *
 * - `refreshExports(project)` lists the project's jobs (`GET /api/exports?project=`) on app
 *   load, on a project change and when the window regains focus. Active jobs always become
 *   tasks; finished ones only when they ended in the last day (older history stays in the
 *   project's `exports/` folder, not in the indicator).
 * - `trackExportJob(job)` puts one job (the Export dialog calls it after starting one).
 * - While any export task is active, one poll loop reads each active job every
 *   `EXPORT_POLL_MS` and stops by itself when none is left.
 */

import type { ExportJob } from "../contracts/export-job";
import { cancelExport, ExportApiError, fmuUrl, getExport, isFinished, listExports } from "../export/exportApi";
import { formatBytes, progressLabel } from "../export/exportFormat";
import { isActive, registerCanceller, useTaskStore, type Task } from "./taskStore";

export const EXPORT_POLL_MS = 500;
/** Finished jobs younger than this come back as tasks after a reload. */
export const RECENT_MS = 24 * 3600 * 1000;

export function exportTaskId(jobId: string): string {
  return `export:${jobId}`;
}

export function exportJobIdOf(taskId: string): string | null {
  return taskId.startsWith("export:") ? taskId.slice("export:".length) : null;
}

function parseTime(text: string | null | undefined): number | null {
  if (!text) {
    return null;
  }
  const value = Date.parse(text);
  return Number.isNaN(value) ? null : value;
}

function firstLine(text: string | null | undefined): string | null {
  if (!text) {
    return null;
  }
  const line = text.split("\n").find((entry) => entry.trim().length > 0);
  return line === undefined ? null : line.trim();
}

/** The task of an export job document. */
export function taskFromJob(job: ExportJob): Task {
  const target = job.scope ? `${job.model} / ${job.scope}` : job.model;
  let phase: string | null;
  switch (job.status) {
    case "queued":
    case "running":
      phase = progressLabel(job.status, job.phase);
      break;
    case "done":
      phase = job.fmu ? `${job.fmu.file} (${formatBytes(job.fmu.bytes)})` : "Done";
      break;
    case "cancelled":
      phase = "Cancelled";
      break;
    default:
      phase = firstLine(job.error) ?? (job.status === "refused" ? "Refused" : "Failed");
  }
  return {
    id: exportTaskId(job.id),
    kind: "fmu-export",
    title: `FMU export · ${target}`,
    project: job.project,
    model: job.model,
    status: job.status,
    phase,
    progress: null,
    started: parseTime(job.created) ?? Date.now(),
    finished: parseTime(job.finished),
    error: job.status === "failed" || job.status === "refused" ? (job.error ?? null) : null,
    unseen: false,
    cancellable: true,
    result:
      job.status === "done" && job.fmu
        ? {
            href: fmuUrl(job.id),
            fileName: job.fmu.file,
            label: `Download ${job.fmu.file} (${formatBytes(job.fmu.bytes)})`,
          }
        : null,
    exportJob: job,
  };
}

/** Put a job into the registry (and poll it while it runs). */
export function trackExportJob(job: ExportJob): void {
  const id = exportTaskId(job.id);
  registerCanceller(id, async () => {
    await cancelExport(job.id);
    trackExportJob(await getExport(job.id));
  });
  useTaskStore.getState().putTask(taskFromJob(job));
  if (!isFinished(job)) {
    ensureExportPolling();
  }
}

/** Load the project's export jobs into the registry. */
export async function refreshExports(project: string, now: number = Date.now()): Promise<void> {
  let jobs: ExportJob[];
  try {
    jobs = await listExports(project);
  } catch (cause) {
    if (cause instanceof ExportApiError && cause.status === 404) {
      return; // a project the backend does not know (yet): nothing to list
    }
    useTaskStore.getState().setConnectionError(errorText(cause));
    return;
  }
  useTaskStore.getState().setConnectionError(null);
  const known = new Set(useTaskStore.getState().tasks.map((task) => task.id));
  // Oldest first, so the registry's order settles like it would have live.
  for (const job of [...jobs].reverse()) {
    const finished = parseTime(job.finished) ?? parseTime(job.created) ?? 0;
    if (isFinished(job) && !known.has(exportTaskId(job.id)) && now - finished > RECENT_MS) {
      continue;
    }
    trackExportJob(job);
  }
}

function errorText(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}

let timer: ReturnType<typeof setTimeout> | null = null;
let polling = false;

function activeExportJobs(): string[] {
  return useTaskStore
    .getState()
    .tasks.filter((task) => task.kind === "fmu-export" && isActive(task))
    .map((task) => exportJobIdOf(task.id))
    .filter((id): id is string => id !== null);
}

async function pollOnce(): Promise<void> {
  for (const jobId of activeExportJobs()) {
    try {
      const job = await getExport(jobId);
      useTaskStore.getState().setConnectionError(null);
      useTaskStore.getState().putTask(taskFromJob(job));
    } catch (cause) {
      if (cause instanceof ExportApiError && cause.status === 404) {
        // The project was deleted or the job pruned: it will not report again.
        useTaskStore.getState().updateTask(exportTaskId(jobId), {
          status: "failed",
          phase: "The export is no longer on the backend",
          error: "The export is no longer on the backend.",
          finished: Date.now(),
        });
      } else {
        useTaskStore.getState().setConnectionError(errorText(cause));
      }
    }
  }
}

function schedule(): void {
  if (timer !== null || !polling) {
    return;
  }
  timer = setTimeout(() => {
    timer = null;
    void pollOnce().finally(() => {
      if (activeExportJobs().length === 0) {
        polling = false;
      } else {
        schedule();
      }
    });
  }, EXPORT_POLL_MS);
}

/** Start the poll loop unless it runs; it stops when no export task is active. */
export function ensureExportPolling(): void {
  if (polling) {
    return;
  }
  polling = true;
  schedule();
}

export function isExportPolling(): boolean {
  return polling;
}

/** Tests: stop the loop. */
export function stopExportPolling(): void {
  polling = false;
  if (timer !== null) {
    clearTimeout(timer);
    timer = null;
  }
}
