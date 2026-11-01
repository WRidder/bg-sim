/**
 * The health indicator of the top bar: it polls GET /api/health and must show
 * each of the four worker states from plan 3.7, plus the fake-worker marker
 * (`data-testid="worker-status"` / `data-state` are the e2e contract).
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useWorkerStore } from "../src/api/workerStore";
import { WorkerStatus } from "../src/app/WorkerStatus";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function health(worker: string, versions: Record<string, string | number | boolean> = {}): Response {
  return jsonResponse({ backend: "0.1.0", worker, versions });
}

const fetchMock = vi.fn<typeof fetch>();

const initialWorker = useWorkerStore.getState();

afterEach(() => {
  fetchMock.mockReset();
  useWorkerStore.setState(initialWorker, true);
});

describe("worker health indicator", () => {
  it.each(["starting", "warming", "ready", "crashed"] as const)(
    "shows the %s state from the backend",
    async (state) => {
      vi.stubGlobal("fetch", fetchMock);
      fetchMock.mockResolvedValue(health(state));

      render(<WorkerStatus pollIntervalMs={1000} />);
      const status = await screen.findByTestId("worker-status");

      await waitFor(() => expect(status.getAttribute("data-state")).toBe(state));
      expect(status.textContent).toContain(state === "warming" ? "warming up" : state);
      expect(fetchMock).toHaveBeenCalledWith("/api/health", expect.objectContaining({ signal: expect.any(AbortSignal) }));
    },
  );

  it("starts in `starting` before the first answer arrives", () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReturnValue(new Promise(() => undefined));

    render(<WorkerStatus pollIntervalMs={1000} />);

    expect(screen.getByTestId("worker-status").getAttribute("data-state")).toBe("starting");
  });

  it("marks the worker as fake when the backend reports one", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(health("ready", { fakeWorker: true, bgsim: "0.1.0" }));

    render(<WorkerStatus pollIntervalMs={1000} />);
    const status = await screen.findByTestId("worker-status");

    await waitFor(() => expect(status.getAttribute("data-fake")).toBe("true"));
    expect(status.textContent).toContain("fake worker");
    expect(status.textContent).toContain("ready");
  });

  it("reports `crashed` when the backend cannot be reached", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));

    render(<WorkerStatus pollIntervalMs={1000} />);
    const status = await screen.findByTestId("worker-status");

    await waitFor(() => expect(status.getAttribute("data-state")).toBe("crashed"));
    expect(status.getAttribute("title")).toContain("Cannot reach the bg-sim backend");
  });

  it("polls on its interval and stops when unmounted", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(health("ready"));

    const { unmount } = render(<WorkerStatus pollIntervalMs={20} />);
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2));

    unmount();
    const callsAtUnmount = fetchMock.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 80));
    expect(fetchMock.mock.calls.length).toBe(callsAtUnmount);
  });
});

describe("worker store", () => {
  it("bumps readyEpoch when the worker becomes ready, not on every ready poll", () => {
    const { report } = useWorkerStore.getState();
    report({ state: "starting", fake: false, detail: "" });
    expect(useWorkerStore.getState().readyEpoch).toBe(0);
    report({ state: "ready", fake: false, detail: "" });
    report({ state: "ready", fake: false, detail: "" });
    expect(useWorkerStore.getState().readyEpoch).toBe(1);
    report({ state: "crashed", fake: false, detail: "" });
    report({ state: "ready", fake: false, detail: "" });
    expect(useWorkerStore.getState().readyEpoch).toBe(2);
  });

  it("shows only the dot; the state is in the tooltip and the accessible name", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(health("starting"));
    render(<WorkerStatus pollIntervalMs={60_000} />);
    const status = await screen.findByTestId("worker-status");
    await waitFor(() => expect(useWorkerStore.getState().known).toBe(true));
    expect(status.querySelector(".worker-status__label")?.classList.contains("visually-hidden")).toBe(true);
    expect(status.getAttribute("title")).toMatch(/available when it is ready/);
  });
});
