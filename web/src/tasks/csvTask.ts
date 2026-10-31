/**
 * The plot's CSV export as a background task. The backend reads the whole run before the
 * first byte and then formats it row by row, so a long run takes seconds to minutes; a plain
 * download link shows nothing meanwhile. Here the browser fetches the CSV as a stream, the
 * task shows the rows received against the backend's `X-BGSim-Rows`, Cancel aborts the
 * request, and the finished file is saved like the link would have saved it.
 *
 * The file is assembled as a Blob, so it lives in memory until it is saved: fine for the
 * run sizes the plot handles. The task does not survive a reload (the request dies with it).
 */

import { formatBytes } from "../export/exportFormat";
import { registerCanceller, useTaskStore, type Task } from "./taskStore";

/** Progress updates at most this often while the stream runs. */
const UPDATE_MS = 150;
const NEWLINE = 10;

let csvSeq = 0;

export interface CsvExportOptions {
  url: string;
  fileName: string;
  title: string;
  project?: string | null;
  model?: string | null;
}

/** Save a Blob under a file name through a temporary object URL. */
export function saveBlob(blob: Blob, fileName: string): void {
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = fileName;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Chromium reads the object URL asynchronously after the click.
  setTimeout(() => URL.revokeObjectURL(href), 60_000);
}

async function detailOf(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    /* not JSON */
  }
  return `the backend answered ${response.status}`;
}

function receivedText(bytes: number, rows: number, total: number | null): string {
  const size = formatBytes(bytes);
  return total !== null && total > 0
    ? `Receiving rows: ${Math.min(rows, total).toLocaleString("en-US")} of ${total.toLocaleString("en-US")} (${size})`
    : `Receiving ${size}`;
}

/**
 * Start a CSV export task; resolves with the task id when it has ended (done, failed or
 * cancelled). Callers usually do not await it.
 */
export async function startCsvExport(options: CsvExportOptions): Promise<string> {
  csvSeq += 1;
  const id = `csv:${Date.now()}-${csvSeq}`;
  const controller = new AbortController();
  const store = useTaskStore.getState();
  const base: Task = {
    id,
    kind: "csv-export",
    title: options.title,
    project: options.project ?? null,
    model: options.model ?? null,
    status: "running",
    phase: "Preparing the data on the backend",
    progress: null,
    started: Date.now(),
    finished: null,
    error: null,
    unseen: false,
    cancellable: true,
    result: null,
    exportJob: null,
  };
  registerCanceller(id, () => controller.abort());
  store.putTask(base);
  const update = (patch: Partial<Task>): void => useTaskStore.getState().updateTask(id, patch);

  try {
    const response = await fetch(options.url, { signal: controller.signal });
    if (!response.ok) {
      const detail = await detailOf(response);
      update({
        status: "failed",
        phase: `Failed: ${detail}`,
        error: detail,
        finished: Date.now(),
      });
      return id;
    }
    const totalHeader = Number(response.headers.get("x-bgsim-rows"));
    const total = Number.isFinite(totalHeader) && totalHeader > 0 ? totalHeader : null;
    const chunks: Uint8Array[] = [];
    let bytes = 0;
    let lines = 0;
    if (response.body === null) {
      const blob = await response.blob();
      chunks.push(new Uint8Array(await blob.arrayBuffer()));
      bytes = blob.size;
    } else {
      const reader = response.body.getReader();
      let lastUpdate = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        chunks.push(value);
        bytes += value.byteLength;
        for (let k = 0; k < value.length; k += 1) {
          if (value[k] === NEWLINE) {
            lines += 1;
          }
        }
        const now = Date.now();
        if (now - lastUpdate >= UPDATE_MS) {
          lastUpdate = now;
          const rows = Math.max(0, lines - 1);
          update({
            phase: receivedText(bytes, rows, total),
            progress: total === null ? null : Math.min(1, rows / total),
          });
        }
      }
    }
    const blob = new Blob(chunks as BlobPart[], { type: "text/csv" });
    saveBlob(blob, options.fileName);
    update({
      status: "done",
      phase: `Saved ${options.fileName} (${formatBytes(blob.size)})`,
      progress: 1,
      finished: Date.now(),
    });
  } catch (cause) {
    if (controller.signal.aborted) {
      update({ status: "cancelled", phase: "Cancelled", progress: null, finished: Date.now() });
    } else {
      const detail = cause instanceof Error ? cause.message : String(cause);
      update({
        status: "failed",
        phase: `Failed: ${detail}`,
        error: detail,
        finished: Date.now(),
      });
    }
  }
  return id;
}
