/**
 * W1.3 (plan 7.3): the diagnostics panel.
 *
 * The fixture is the 28-diagnostic sample every lane shares. The panel renders
 * it, filters it by severity, groups it by instance path, and a click selects
 * the node (or announces the source range when the diagnostic has no node).
 */

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import diagnosticsJson from "../../contracts/fixtures/diagnostic/valid/diagnostics.sample.json";
import type { Diagnostic } from "../src/contracts/diagnostic";
import type { Model, ModelNode } from "../src/contracts/model";
import type { ModelCheckResult } from "../src/contracts/worker-rpc";
import { BottomDock } from "../src/app/BottomDock";
import { DiagnosticsPanel } from "../src/diagnostics/DiagnosticsPanel";
import { OPEN_SOURCE_EVENT, type OpenSourceDetail } from "../src/diagnostics/navigation";
import { resetDiagnosticsStore, useDiagnosticsStore } from "../src/diagnostics/store";
import { resetCatalogStore } from "../src/library/catalogStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

const fixture = diagnosticsJson as unknown as Diagnostic[];

function checkResult(diagnostics: Diagnostic[]): ModelCheckResult {
  return {
    diagnostics,
    domains: {},
    causality: {},
    frames: {},
    unitFactors: {},
    signals: [],
    stats: { states: 0, equations: 0 },
  };
}

function apply(diagnostics: Diagnostic[], revision = 1): void {
  useDiagnosticsStore.getState().applyResult(checkResult(diagnostics), revision);
  useDiagnosticsStore.getState().setWorkerState("ready");
}

function node(id: string, name: string, x: number): ModelNode {
  return {
    id,
    name,
    block: { ref: "stdlib:bondgraph/R" },
    position: { x, y: 0 },
    rotation: 0,
    flipX: false,
    params: {},
    constants: {},
    starts: {},
    ui: { showLabel: true, color: null },
  };
}

function openDoc(nodes: ModelNode[]): Model {
  const doc = createEmptyModel("M");
  doc.diagram.nodes = nodes;
  useDocumentStore.getState().openDocument("p", "M", doc);
  return doc;
}

beforeEach(() => {
  resetDiagnosticsStore();
  resetDocumentStore();
  resetCatalogStore();
});

describe("the diagnostics panel", () => {
  it("renders the sample fixture, its severity counts and one group per path", () => {
    openDoc([]);
    apply(fixture);
    render(<DiagnosticsPanel />);

    expect(screen.getByTestId("diagnostics-count-error").textContent).toContain("26");
    expect(screen.getByTestId("diagnostics-count-warning").textContent).toContain("7");
    expect(screen.getByTestId("diagnostics-count-info").textContent).toContain("0");
    expect(screen.getAllByTestId(/^diagnostic-item-\d+$/)).toHaveLength(33);
    expect(screen.getAllByTestId("diagnostics-group")).toHaveLength(24);
    expect(screen.getByTestId("diagnostics-status").textContent).toContain("Revision 1 checked");
  });

  it("groups by path and keeps the fixture order inside a group", () => {
    openDoc([]);
    apply(fixture);
    const { container } = render(<DiagnosticsPanel />);

    const controller = container.querySelector(
      '[data-testid="diagnostics-group"][data-path="Ctrl/PI1"]',
    );
    expect(controller).not.toBeNull();
    expect(within(controller as HTMLElement).getAllByTestId(/^diagnostic-item-\d+$/)).toHaveLength(4);

    const motor = container.querySelector(
      '[data-testid="diagnostics-group"][data-path="Plant/Motor1"]',
    );
    expect(within(motor as HTMLElement).getAllByTestId(/^diagnostic-item-\d+$/)).toHaveLength(2);

    const groups = [...container.querySelectorAll('[data-testid="diagnostics-group"]')].map(
      (group) => group.getAttribute("data-path"),
    );
    expect(groups.slice(0, 2)).toEqual(["Ctrl", "Ctrl/Compare1"]);
  });

  it("puts model-wide diagnostics in a Model group first", () => {
    openDoc([]);
    apply([
      ...fixture,
      { code: "W299", severity: "warning", message: "model-wide warning", path: null, node: null },
    ]);
    const { container } = render(<DiagnosticsPanel />);

    const groups = [...container.querySelectorAll('[data-testid="diagnostics-group"]')];
    expect(groups[0]?.getAttribute("data-path")).toBe("");
    expect(within(groups[0] as HTMLElement).getByText("Model")).toBeTruthy();
    expect(within(groups[0] as HTMLElement).getByTestId(/^diagnostic-item-/)).toBeTruthy();
  });

  it("filters by severity, shows the empty-filter state and restores all", () => {
    openDoc([]);
    apply(fixture);
    render(<DiagnosticsPanel />);

    fireEvent.click(screen.getByTestId("diagnostics-filter-error"));
    expect(screen.getAllByTestId(/^diagnostic-item-\d+$/)).toHaveLength(7);
    expect(screen.getByTestId("diagnostics-filter-error").getAttribute("aria-pressed")).toBe(
      "false",
    );

    fireEvent.click(screen.getByTestId("diagnostics-filter-warning"));
    expect(screen.queryAllByTestId(/^diagnostic-item-\d+$/)).toHaveLength(0);
    expect(screen.getByTestId("diagnostics-filter-empty").textContent).toContain(
      "No diagnostics match the filter.",
    );

    fireEvent.click(screen.getByTestId("diagnostics-show-all"));
    expect(screen.getAllByTestId(/^diagnostic-item-\d+$/)).toHaveLength(33);
    expect(screen.getByTestId("diagnostics-filter-error").getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("selects and focuses the node of a clicked diagnostic", () => {
    openDoc([node("n7", "Filter1", 0), node("n12", "PI1", 200)]);
    apply(fixture);
    render(<DiagnosticsPanel />);

    const details: OpenSourceDetail[] = [];
    const listener = (event: Event): void => {
      details.push((event as CustomEvent<OpenSourceDetail>).detail);
    };
    window.addEventListener(OPEN_SOURCE_EVENT, listener);

    fireEvent.click(screen.getByTestId("diagnostic-item-0"));

    expect(useDocumentStore.getState().selection.nodes).toEqual(["n7"]);
    expect(useDiagnosticsStore.getState().focus?.nodeId).toBe("n7");
    expect(useDiagnosticsStore.getState().sourceFocus).toMatchObject({
      ref: "inline:n7",
      line: 9,
      col: 1,
    });
    expect(details).toHaveLength(1);
    expect(details[0]).toMatchObject({ kind: "inline", ref: "inline:n7", line: 9, col: 1 });

    window.removeEventListener(OPEN_SOURCE_EVENT, listener);
  });

  it("navigates a related path and ignores diagnostics with no editor target", () => {
    openDoc([
      node("n3", "Motor1", 0),
      node("n22", "Gear1", 200),
      node("n12", "PI1", 400),
    ]);
    apply(fixture);
    render(<DiagnosticsPanel />);

    // E103 has two related entries: Plant/Motor1 and Plant/Gear1.
    fireEvent.click(screen.getByTestId("diagnostic-item-10"));
    expect(useDocumentStore.getState().selection.nodes).toEqual(["n3"]);

    fireEvent.click(screen.getByTestId("diagnostic-related-10-1"));
    expect(useDocumentStore.getState().selection.nodes).toEqual(["n22"]);
    expect(useDiagnosticsStore.getState().focus?.nodeId).toBe("n22");

    // E301 is a binding diagnostic: it has no node and no source range.
    const noTarget = screen.getByTestId("diagnostic-item-16");
    expect(noTarget.getAttribute("data-target")).toBe("none");
    const before = useDocumentStore.getState().selection.nodes;
    fireEvent.click(noTarget);
    expect(useDocumentStore.getState().selection.nodes).toEqual(before);
  });

  it("shows a quiet wait state while the worker warms up and guidance when there is no model", () => {
    openDoc([]);
    useDiagnosticsStore.setState({ workerState: "warming", status: "waiting" });
    const { unmount } = render(<DiagnosticsPanel />);
    expect(screen.getByTestId("diagnostics-waiting").textContent).toContain("checks paused");
    unmount();

    resetDocumentStore();
    render(<DiagnosticsPanel />);
    expect(screen.getByText("No model open")).toBeTruthy();
  });

  it("feeds the dock's Diagnostics badges from the store", () => {
    openDoc([]);
    render(<BottomDock active="diagnostics" onSelect={() => undefined} />);
    // Apply after the dock mounts: its runtime starts its own check loop and
    // clears stale results when it observes a newly opened document.
    act(() => {
      apply(fixture);
    });

    const tab = screen.getByRole("tab", { name: /^Diagnostics/ });
    expect(within(tab).getByLabelText("26 errors")).toBeTruthy();
    expect(within(tab).getByLabelText("7 warnings")).toBeTruthy();
  });
});
