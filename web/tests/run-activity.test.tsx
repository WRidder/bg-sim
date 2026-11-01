/**
 * The run indicators: the stage names from the worker phases, the elapsed-time format, the 3D overlay that
 * covers the view while the model compiles, and the "waiting for the worker" state of the library and
 * the diagram (a 503 while the worker starts is not an error, and the session retries when it is ready).
 */

import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useWorkerStore } from "../src/api/workerStore";
import { describeRunActivity, formatElapsed, runStage } from "../src/app/runActivity";
import { WaitingForWorker } from "../src/app/WaitingForWorker";
import { useRunStore } from "../src/plot/runStore";
import { RunActivityOverlay } from "../src/viewer/RunActivityOverlay";

const initialRun = useRunStore.getState();
const initialWorker = useWorkerStore.getState();

afterEach(() => {
  useRunStore.setState(initialRun, true);
  useWorkerStore.setState(initialWorker, true);
});

describe("run stages", () => {
  it("maps the worker phases to the stages the user sees", () => {
    expect(runStage("starting", null)).toBe("prepare");
    expect(runStage("running", "causality")).toBe("prepare");
    expect(runStage("running", "mtkcompile")).toBe("compile");
    expect(runStage("running", "init")).toBe("init");
    expect(runStage("running", "simulate")).toBe("simulate");
    expect(runStage("running", "cancelling")).toBe("cancel");
    expect(runStage("done", "simulate")).toBeNull();
  });

  it("is preparing until the first sample, and idle while paused in the debugger", () => {
    expect(describeRunActivity("running", "mtkcompile", false)).toMatchObject({ busy: true, preparing: true, label: "Compiling" });
    expect(describeRunActivity("running", "simulate", false)).toMatchObject({ busy: true, preparing: false, label: "Simulating" });
    // the first step of a large model takes a while: still preparing until a sample past the initial row
    expect(describeRunActivity("running", "simulate", false, false)).toMatchObject({ preparing: true, label: "Starting the solver" });
    expect(describeRunActivity("running", "simulate", true).busy).toBe(false);
  });

  it("formats the elapsed time", () => {
    expect(formatElapsed(4_900)).toBe("4 s");
    expect(formatElapsed(65_000)).toBe("1:05");
    expect(formatElapsed(3_725_000)).toBe("1:02:05");
  });
});

describe("3D view overlay", () => {
  it("lists the stages while the model compiles and leaves with the first samples", () => {
    useRunStore.setState({ status: "running", phase: "mtkcompile", runId: "r1", startedAt: Date.now() - 12_000, phaseAt: Date.now() - 3_000 });
    const { container } = render(<RunActivityOverlay />);
    const overlay = screen.getByTestId("run-overlay");
    expect(overlay.getAttribute("data-stage")).toBe("compile");
    const states = [...container.querySelectorAll(".run-overlay__step")].map((li) => li.getAttribute("data-state"));
    expect(states).toEqual(["done", "active", "todo", "todo"]);
    expect(overlay.textContent).toContain("12 s");
    act(() => useRunStore.setState({ phase: "simulate", progress: { t: 0, rows: 1 } }));
    expect(screen.getByTestId("run-overlay").textContent).toContain("Starting the solver");
    act(() => useRunStore.setState({ progress: { t: 0.01, rows: 2 } }));
    expect(screen.queryByTestId("run-overlay")).toBeNull();
  });
});

describe("waiting for the worker", () => {
  it("says what the worker does and offers Retry only when it is down", () => {
    useWorkerStore.setState({ state: "warming" });
    const { rerender } = render(<WaitingForWorker what="the library" detail="503" onRetry={() => undefined} testId="w" />);
    expect(screen.getByTestId("w").textContent).toContain("warming up");
    expect(screen.queryByRole("button")).toBeNull();
    act(() => useWorkerStore.setState({ state: "crashed" }));
    rerender(<WaitingForWorker what="the library" detail="503" onRetry={() => undefined} testId="w" />);
    expect(screen.getByRole("button", { name: "Retry now" })).toBeTruthy();
  });
});
