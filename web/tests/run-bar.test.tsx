/**
 * The run bar's settings controls (plan 7.2): they read and write the open
 * model document's `settings`, reject invalid values without corrupting it,
 * and stay disabled until a model is open.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { RunBar } from "../src/app/RunBar";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";
import { resetRunStore } from "../src/plot/runStore";
import { formatSettingNumber } from "../src/plot/settings";

function openModel(): void {
  useDocumentStore
    .getState()
    .openDocument("project", "Model1", createEmptyModel("Model1"));
}

beforeEach(() => {
  resetDocumentStore();
  resetRunStore();
});

afterEach(() => {
  resetDocumentStore();
  resetRunStore();
});

describe("RunBar", () => {
  it("keeps Run and Stop disabled without a model", () => {
    render(<RunBar />);
    const run = screen.getByRole("button", { name: "Run simulation" });
    const stop = screen.getByRole("button", { name: "Stop simulation" });
    expect((run as HTMLButtonElement).disabled).toBe(true);
    expect((stop as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText("t_end") as HTMLInputElement).disabled).toBe(
      true,
    );
  });

  it("writes t_end and reltol into the model settings", () => {
    openModel();
    render(<RunBar />);

    const end = screen.getByLabelText("t_end") as HTMLInputElement;
    expect(end.value).toBe("1");
    fireEvent.change(end, { target: { value: "2.5" } });
    fireEvent.blur(end);

    const tolerance = screen.getByLabelText("tol") as HTMLInputElement;
    fireEvent.change(tolerance, { target: { value: "1e-9" } });
    fireEvent.blur(tolerance);

    const state = useDocumentStore.getState();
    expect(state.doc?.settings.t_end).toBe(2.5);
    expect(state.doc?.settings.reltol).toBe(1e-9);
    expect(state.revision).toBe(2);
    expect(state.saveState).toBe("dirty");
  });

  it("shows a microsecond t_end and a tiny tolerance in exponent notation", () => {
    openModel();
    render(<RunBar />);
    const end = screen.getByLabelText("t_end") as HTMLInputElement;
    fireEvent.change(end, { target: { value: "0.0000032" } });
    fireEvent.blur(end);
    expect(useDocumentStore.getState().doc?.settings.t_end).toBe(3.2e-6);
    expect(end.value).toBe("3.2e-6");
    const tolerance = screen.getByLabelText("tol") as HTMLInputElement;
    fireEvent.change(tolerance, { target: { value: "0.000001" } });
    fireEvent.blur(tolerance);
    expect(tolerance.value).toBe("1e-6");
    // ordinary values keep their plain text
    fireEvent.change(end, { target: { value: "12.5" } });
    fireEvent.blur(end);
    expect(end.value).toBe("12.5");
  });

  it("formats setting numbers losslessly", () => {
    expect(formatSettingNumber(3.2e-6)).toBe("3.2e-6");
    expect(formatSettingNumber(1.23456789e-7)).toBe("1.23456789e-7");
    expect(formatSettingNumber(0.001)).toBe("0.001");
    expect(formatSettingNumber(2.5)).toBe("2.5");
    expect(formatSettingNumber(3600)).toBe("3600");
    expect(formatSettingNumber(2e6)).toBe("2e6");
    expect(formatSettingNumber(0)).toBe("0");
    for (const value of [3.2e-6, 1.23456789e-7, 2e6, 0.1]) {
      expect(Number(formatSettingNumber(value))).toBe(value);
    }
  });

  it("rejects a non-positive t_end and restores it on Escape", () => {
    openModel();
    render(<RunBar />);

    const end = screen.getByLabelText("t_end") as HTMLInputElement;
    fireEvent.change(end, { target: { value: "0" } });
    fireEvent.blur(end);

    expect(end.getAttribute("aria-invalid")).toBe("true");
    expect(useDocumentStore.getState().doc?.settings.t_end).toBe(1);

    fireEvent.keyDown(end, { key: "Escape" });
    expect(end.value).toBe("1");
    expect(end.getAttribute("aria-invalid")).toBe("false");
  });

  it("changes the solver and shows Run as available", () => {
    openModel();
    render(<RunBar />);

    const solver = screen.getByLabelText("solver") as HTMLSelectElement;
    fireEvent.change(solver, { target: { value: "Tsit5" } });

    expect(useDocumentStore.getState().doc?.settings.solver).toBe("Tsit5");
    const run = screen.getByRole("button", { name: "Run simulation" });
    expect((run as HTMLButtonElement).disabled).toBe(false);
  });
});
