/**
 * The Export dialog (W-EX1) against a stubbed backend: the request it sends, the progress,
 * the report, a refusal shown as a message, and the W209 hint.
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ExportJob } from "../src/contracts/export-job";
import type { ExportRequest } from "../src/contracts/export-request";
import type { Model } from "../src/contracts/model";
import { ExportDialog } from "../src/export/ExportDialog";
import { useExportDialogStore } from "../src/export/exportStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const fixture = <T,>(...parts: string[]): T =>
  JSON.parse(readFileSync(path.join(repoRoot, "contracts", "fixtures", ...parts), "utf8")) as T;

const model = fixture<{ model: Model }>("export-request", "valid", "export-request.scope.json").model;
const doneJob = fixture<ExportJob>("export-job", "valid", "export-job.done.json");
const refusedJob = fixture<ExportJob>("export-job", "valid", "export-job.refused.json");

interface Call {
  url: string;
  method: string;
  body: unknown;
}

function stubBackend(jobs: ExportJob[]): Call[] {
  const calls: Call[] = [];
  let index = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (method === "POST") {
        return new Response(JSON.stringify({ exportId: jobs[0]?.id }), { status: 201 });
      }
      const job = jobs[Math.min(index, jobs.length - 1)];
      index += 1;
      return new Response(JSON.stringify(job), { status: 200 });
    }),
  );
  return calls;
}

function running(job: ExportJob): ExportJob {
  return { ...job, status: "running", phase: "reference", report: null, fmu: null, finished: null };
}

beforeEach(() => {
  resetDocumentStore();
  useDocumentStore.getState().openDocument("demo", "plant", structuredClone(model));
});

afterEach(() => {
  act(() => useExportDialogStore.getState().closeExport());
  vi.unstubAllGlobals();
  resetDocumentStore();
});

describe("ExportDialog", () => {
  it("exports a subsystem with automatic settings and shows the report", async () => {
    const calls = stubBackend([running(doneJob), running(doneJob), doneJob]);
    render(<ExportDialog />);
    act(() => useExportDialogStore.getState().openExport("Plant"));

    const dialog = screen.getByTestId("export-dialog");
    expect((screen.getByTestId("export-scope-subsystem") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByTestId("export-scope-select") as HTMLSelectElement).value).toBe("Plant");
    expect((screen.getByTestId("export-power-p") as HTMLSelectElement).value).toBe("effort");
    expect(within(screen.getByTestId("export-inputs")).getByText("p_e")).toBeTruthy();
    fireEvent.change(screen.getByTestId("export-power-p"), { target: { value: "flow" } });
    expect(within(screen.getByTestId("export-inputs")).getByText("p_f")).toBeTruthy();
    expect(within(screen.getByTestId("export-outputs")).getByText("p_e")).toBeTruthy();

    fireEvent.click(screen.getByTestId("export-start"));
    await waitFor(() => expect(screen.getByTestId("export-progress").textContent).toMatch(/reference simulation/));
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe("/api/projects/demo/models/plant/export");
    const body = post?.body as ExportRequest;
    expect(body.scope).toBe("Plant");
    expect(body.powerInputs).toEqual({ p: "flow" });
    expect(body.settings).toEqual({
      method: "auto", dt: null, step: null, damping: null, jacobian: "auto", linearSolver: "auto",
    });
    expect(body.model.name).toBe("ScopeModel");

    await waitFor(() => expect(screen.getByTestId("export-report")).toBeTruthy(), { timeout: 4000 });
    expect(screen.getByTestId("export-report-method").textContent).toBe("RK4");
    expect(screen.getByTestId("export-report-dt").textContent).toBe("62.5 µs");
    expect(screen.getByTestId("export-candidate-rk4").textContent).toContain("(chosen)");
    expect(screen.getByTestId("export-candidate-rodas4p")).toBeTruthy();
    expect(screen.getByTestId("export-diagnostic-W210").textContent).toContain("at PID1");
    expect(screen.getByTestId("export-build").textContent).toContain("0 allocations after instantiate");
    expect(screen.getByTestId("export-timings").textContent).toContain("reference run 9.8 s");
    const download = screen.getByTestId("export-download") as HTMLAnchorElement;
    expect(download.getAttribute("href")).toBe(`/api/exports/${doneJob.id}/fmu`);
    expect(download.getAttribute("download")).toBe("speed_control.fmu");
    expect(dialog).toBeTruthy();
  });

  it("shows a refused export as a message with its diagnostics", async () => {
    stubBackend([refusedJob]);
    render(<ExportDialog />);
    act(() => useExportDialogStore.getState().openExport("Plant"));
    fireEvent.click(screen.getByTestId("export-start"));
    const refused = await screen.findByTestId("export-refused");
    expect(refused.textContent).toContain("cannot be exported as it is");
    expect(screen.getByTestId("export-diagnostic-E112").textContent).toContain("at Valve/P");
    expect(screen.getByTestId("export-diagnostic-E110").textContent).toContain("at Valve/Table");
    expect(screen.queryByTestId("export-report")).toBeNull();
  });

  it("sends the advanced settings and refuses an invalid step", async () => {
    const calls = stubBackend([doneJob]);
    render(<ExportDialog />);
    act(() => useExportDialogStore.getState().openExport(null));
    fireEvent.change(screen.getByTestId("export-method"), { target: { value: "rodas4p" } });
    fireEvent.change(screen.getByTestId("export-dt"), { target: { value: "-1" } });
    expect((screen.getByTestId("export-start") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId("export-dt"), { target: { value: "5e-4" } });
    fireEvent.change(screen.getByTestId("export-damping"), { target: { value: "0.5" } });
    fireEvent.change(screen.getByTestId("export-jacobian"), { target: { value: "fd" } });
    fireEvent.change(screen.getByTestId("export-linear-solver"), { target: { value: "sparse" } });
    fireEvent.click(screen.getByTestId("export-expose-all"));
    fireEvent.click(screen.getByTestId("export-start"));
    await screen.findByTestId("export-report");
    const body = calls.find((c) => c.method === "POST")?.body as ExportRequest;
    expect(body.scope).toBeUndefined();
    expect(body.settings).toEqual({
      method: "rodas4p", dt: 5e-4, step: null, damping: 0.5, jacobian: "fd",
      linearSolver: "sparse", exposeAll: true,
    });
  });

  it("folds a long run of one diagnostic code", async () => {
    const many = structuredClone(doneJob);
    const w203 = Array.from({ length: 14 }, (_, k) => ({
      code: "W203",
      severity: "warning" as const,
      message: `switching condition ${k} is evaluated once per step`,
      path: `Robot/Limit${k}`,
    }));
    if (many.report) {
      many.report.diagnostics = [...many.report.diagnostics, ...w203];
    }
    stubBackend([many]);
    render(<ExportDialog />);
    act(() => useExportDialogStore.getState().openExport(null));
    fireEvent.click(screen.getByTestId("export-start"));
    await screen.findByTestId("export-report");
    expect(screen.getByTestId("export-more-W203").querySelector("summary")?.textContent).toBe(
      "12 more W203",
    );
    expect(screen.getAllByTestId("export-diagnostic-W203")).toHaveLength(14);
    expect(screen.queryByTestId("export-more-W210")).toBeNull();
  });

  it("warns W209 when the whole model has no Export markers", () => {
    stubBackend([doneJob]);
    render(<ExportDialog />);
    act(() => useExportDialogStore.getState().openExport(null));
    expect((screen.getByTestId("export-scope-model") as HTMLInputElement).checked).toBe(true);
    expect(screen.getByTestId("export-w209").textContent).toContain("W209");
    fireEvent.click(screen.getByTestId("export-scope-subsystem"));
    expect(screen.queryByTestId("export-w209")).toBeNull();
  });

  it("reports a backend that cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("offline"))));
    render(<ExportDialog />);
    act(() => useExportDialogStore.getState().openExport(null));
    fireEvent.click(screen.getByTestId("export-start"));
    expect((await screen.findByTestId("export-error")).textContent).toMatch(/Cannot reach the bg-sim backend/);
  });
});
