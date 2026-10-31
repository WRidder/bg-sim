/**
 * The top bar's background tasks indicator: idle, running with a count, the dot of a task
 * that ended unwatched, the popover (keyboard, Cancel, Show details re-opening the Export
 * dialog on the job, download, Clear finished), the live announcement and the toast.
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ExportJob } from "../src/contracts/export-job";
import type { Model } from "../src/contracts/model";
import { ExportDialog } from "../src/export/ExportDialog";
import { useExportDialogStore } from "../src/export/exportStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { exportTaskId, stopExportPolling, taskFromJob, trackExportJob } from "../src/tasks/exportTasks";
import { formatElapsed, TaskIndicator } from "../src/tasks/TaskIndicator";
import { resetTaskStore, useTaskStore } from "../src/tasks/taskStore";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const fixture = <T,>(...parts: string[]): T =>
  JSON.parse(readFileSync(path.join(repoRoot, "contracts", "fixtures", ...parts), "utf8")) as T;

const model = fixture<{ model: Model }>("export-request", "valid", "export-request.scope.json").model;
const doneJob: ExportJob = {
  ...fixture<ExportJob>("export-job", "valid", "export-job.done.json"),
  project: "demo",
  model: "plant",
};

function running(id: string): ExportJob {
  return { ...doneJob, id, status: "running", phase: "reference", report: null, fmu: null, finished: null };
}

interface Call {
  url: string;
  method: string;
}

/** GET answers `current[id]`; DELETE cancels it; the list answers `list`. */
function stubBackend(current: Record<string, ExportJob>, list: ExportJob[] = []): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method });
      if (url.startsWith("/api/exports?")) {
        return new Response(JSON.stringify(list), { status: 200 });
      }
      const id = decodeURIComponent(url.split("/").pop() ?? "");
      const job = current[id];
      if (job === undefined) {
        return new Response(JSON.stringify({ detail: "unknown" }), { status: 404 });
      }
      if (method === "DELETE") {
        current[id] = { ...job, status: "cancelled", phase: null, finished: new Date().toISOString() };
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      }
      return new Response(JSON.stringify(job), { status: 200 });
    }),
  );
  return calls;
}

const indicator = () => screen.getByTestId("tasks-indicator");

beforeEach(() => {
  localStorage.clear();
  resetTaskStore();
  resetDocumentStore();
});

afterEach(() => {
  act(() => useExportDialogStore.setState({ open: false, jobId: null, attached: false }));
  stopExportPolling();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  resetTaskStore();
  resetDocumentStore();
  localStorage.clear();
});

describe("TaskIndicator", () => {
  it("is a muted, focusable button when idle and says so in the popover", () => {
    stubBackend({});
    render(<TaskIndicator />);
    expect(indicator().getAttribute("data-state")).toBe("idle");
    expect(indicator().getAttribute("aria-label")).toBe("Background tasks: none running");
    expect(screen.queryByTestId("tasks-count")).toBeNull();
    fireEvent.click(indicator());
    expect(screen.getByTestId("tasks-empty").textContent).toContain("No background tasks");
    expect((screen.getByTestId("tasks-clear") as HTMLButtonElement).disabled).toBe(true);
  });

  it("lists the project's exports on load (a reload keeps a running export)", async () => {
    const calls = stubBackend({ "export-a": running("export-a") }, [running("export-a")]);
    useDocumentStore.getState().openDocument("demo", "plant", structuredClone(model));
    render(<TaskIndicator />);
    await waitFor(() => expect(indicator().getAttribute("data-state")).toBe("running"));
    expect(calls[0]?.url).toBe("/api/exports?project=demo");
    expect(screen.getByTestId("tasks-count").textContent).toBe("1");
    expect(indicator().getAttribute("aria-label")).toBe("Background tasks: 1 running");
  });

  it("opens a popover with the running task, cancels it, and closes on Escape", async () => {
    const current = { "export-a": running("export-a") };
    const calls = stubBackend(current);
    render(<TaskIndicator />);
    act(() => trackExportJob(running("export-a")));
    indicator().focus();
    fireEvent.click(indicator());
    const panel = screen.getByTestId("tasks-panel");
    expect(indicator().getAttribute("aria-expanded")).toBe("true");
    expect(document.activeElement).toBe(panel);
    const item = within(panel).getByTestId("task-item");
    expect(item.getAttribute("data-status")).toBe("running");
    expect(within(item).getByTestId("task-phase").textContent).toBe("Running the reference simulation");
    expect(within(item).getByRole("progressbar")).toBeTruthy();
    expect(within(item).queryByTestId("task-dismiss")).toBeNull();

    fireEvent.click(within(item).getByTestId("task-cancel"));
    await waitFor(() =>
      expect(screen.getByTestId("task-item").getAttribute("data-status")).toBe("cancelled"),
    );
    expect(calls.some((c) => c.method === "DELETE" && c.url === "/api/exports/export-a")).toBe(true);

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByTestId("tasks-panel")).toBeNull();
    expect(document.activeElement).toBe(indicator());
  });

  it("shows a dot and announces a task that ended unwatched, until the list is opened", () => {
    stubBackend({});
    render(<TaskIndicator />);
    act(() => useTaskStore.getState().putTask(taskFromJob(running("export-a"))));
    act(() =>
      useTaskStore.getState().putTask(
        taskFromJob({ ...doneJob, id: "export-a", status: "failed", error: "gcc crashed", report: null, fmu: null }),
      ),
    );
    expect(indicator().getAttribute("data-state")).toBe("attention");
    expect(screen.getByTestId("tasks-dot").className).toContain("is-error");
    expect(screen.getByTestId("tasks-live").textContent).toBe("FMU export · plant failed");
    expect(screen.getByTestId("task-toast").textContent).toContain("FMU export · plant failed");

    fireEvent.click(indicator());
    expect(screen.queryByTestId("task-toast")).toBeNull();
    expect(within(screen.getByTestId("task-item")).getByTestId("task-phase").textContent).toBe("gcc crashed");
    fireEvent.click(indicator());
    expect(indicator().getAttribute("data-state")).toBe("idle");
    expect(screen.queryByTestId("tasks-dot")).toBeNull();
  });

  it("re-opens the Export dialog on a finished job with its report and download", () => {
    stubBackend({});
    useDocumentStore.getState().openDocument("demo", "plant", structuredClone(model));
    render(
      <>
        <TaskIndicator />
        <ExportDialog />
      </>,
    );
    act(() => useTaskStore.getState().putTask(taskFromJob(running(doneJob.id))));
    act(() => useTaskStore.getState().putTask(taskFromJob(doneJob)));
    fireEvent.click(indicator());
    const item = screen.getByTestId("task-item");
    expect(within(item).getByTestId("task-download").getAttribute("href")).toBe(`/api/exports/${doneJob.id}/fmu`);
    fireEvent.click(within(item).getByTestId("task-details"));

    expect(screen.queryByTestId("tasks-panel")).toBeNull();
    const dialog = screen.getByTestId("export-dialog");
    expect(within(dialog).getByTestId("export-report-method").textContent).toBe("RK4");
    expect(within(dialog).getByTestId("export-download").getAttribute("href")).toBe(
      `/api/exports/${doneJob.id}/fmu`,
    );
    expect(within(dialog).getByTestId("export-start").textContent).toBe("Export again");
    expect(useTaskStore.getState().viewing).toBe(exportTaskId(doneJob.id));
  });

  it("shows another model's export without the form, with live progress", async () => {
    const current = { "export-x": { ...running("export-x"), model: "other" } };
    stubBackend(current);
    useDocumentStore.getState().openDocument("demo", "plant", structuredClone(model));
    render(
      <>
        <TaskIndicator />
        <ExportDialog />
      </>,
    );
    act(() => trackExportJob(current["export-x"]));
    act(() => useExportDialogStore.getState().showExport("export-x"));
    expect(screen.getByTestId("export-foreign").textContent).toContain("other");
    expect(screen.getByText("Export FMU · other")).toBeTruthy();
    expect(screen.queryByTestId("export-start")).toBeNull();
    expect(screen.getByTestId("export-progress").textContent).toMatch(/reference simulation/);

    current["export-x"] = { ...doneJob, id: "export-x", model: "other" };
    await waitFor(() => expect(screen.getByTestId("export-report")).toBeTruthy(), { timeout: 3000 });
    // The dialog watched it end: no dot, no toast.
    expect(indicator().getAttribute("data-state")).toBe("idle");
    expect(screen.queryByTestId("task-toast")).toBeNull();
  });

  it("opens a fresh form for the open model while another model's export runs", () => {
    const current = { "export-y": { ...running("export-y"), model: "other" } };
    stubBackend(current);
    useDocumentStore.getState().openDocument("demo", "plant", structuredClone(model));
    render(<ExportDialog />);
    act(() => trackExportJob(current["export-y"]));
    act(() => useExportDialogStore.getState().showExport("export-y"));
    expect(screen.getByTestId("export-foreign")).toBeTruthy();
    act(() => useExportDialogStore.getState().closeExport());
    act(() => useExportDialogStore.getState().openExport(null));
    expect(screen.queryByTestId("export-foreign")).toBeNull();
    expect((screen.getByTestId("export-start") as HTMLButtonElement).disabled).toBe(false);
    expect(useTaskStore.getState().tasks[0]?.status).toBe("running");
  });

  it("offers Show in the toast and clears finished tasks", () => {
    stubBackend({});
    useDocumentStore.getState().openDocument("demo", "plant", structuredClone(model));
    render(
      <>
        <TaskIndicator />
        <ExportDialog />
      </>,
    );
    act(() => useTaskStore.getState().putTask(taskFromJob(running(doneJob.id))));
    act(() => useTaskStore.getState().putTask(taskFromJob(doneJob)));
    fireEvent.click(screen.getByTestId("task-toast-show"));
    expect(screen.getByTestId("export-report")).toBeTruthy();
    expect(screen.queryByTestId("task-toast")).toBeNull();
    act(() => useExportDialogStore.getState().closeExport());

    fireEvent.click(indicator());
    fireEvent.click(screen.getByTestId("tasks-clear"));
    expect(screen.getByTestId("tasks-empty")).toBeTruthy();
  });

  it("formats elapsed time", () => {
    expect(formatElapsed(8_400)).toBe("8 s");
    expect(formatElapsed(184_000)).toBe("3 min 04 s");
    expect(formatElapsed(3_720_000)).toBe("1 h 02 min");
  });
});
