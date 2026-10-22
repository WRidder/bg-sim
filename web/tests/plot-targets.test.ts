/**
 * Canvas → plot targets (plan 7.5): a bond plots the effort/flow/power of its
 * port, an instance plots its recorded outputs, and a signal connection has no
 * power variables. Pure functions, so the context menu's diff stays tiny.
 */

import { describe, expect, it } from "vitest";

import type { Model } from "../src/contracts/model";
import {
  PLOT_VARIABLES,
  connectionForMenu,
  connectionPlotTargets,
  endpointPort,
  nodeForMenu,
  nodeOutputIds,
  nodeOutputTargets,
  portSignalId,
} from "../src/plot/plotTargets";
import { runSignal } from "./plotFixtures";
import dcmotorJson from "../../contracts/fixtures/model/valid/model.dcmotor.bondgraph.json";

const MODEL = dcmotorJson as unknown as Model;

function connection(id: string) {
  const found = MODEL.diagram.connections.find((entry) => entry.id === id);
  if (found === undefined) {
    throw new Error(`fixture connection ${id} is missing`);
  }
  return found;
}

describe("portSignalId", () => {
  it("uses the worker's port-field names", () => {
    expect(portSignalId("Motor1", "shaft", "effort")).toBe("Motor1/shaft.e");
    expect(portSignalId("Motor1", "shaft", "flow")).toBe("Motor1/shaft.f");
    expect(portSignalId("Motor1", "shaft", "power")).toBe("Motor1/shaft.P");
    expect(PLOT_VARIABLES).toEqual(["effort", "flow", "power"]);
  });
});

describe("connectionPlotTargets", () => {
  it("plots the source port's effort, flow and power", () => {
    const targets = connectionPlotTargets(MODEL, connection("c1"));
    expect(targets.map((target) => target.signalId)).toEqual([
      "Se1/p.e",
      "Se1/p.f",
      "Se1/p.P",
    ]);
    expect(targets.map((target) => target.label)).toEqual([
      "Plot effort",
      "Plot flow",
      "Plot power",
    ]);
    expect(targets.map((target) => target.testId)).toEqual([
      "plot-effort",
      "plot-flow",
      "plot-power",
    ]);
  });

  it("falls back to the target endpoint when the source is a junction", () => {
    const targets = connectionPlotTargets(MODEL, connection("c3"));
    expect(targets.map((target) => target.signalId)).toEqual([
      "IL/p.e",
      "IL/p.f",
      "IL/p.P",
    ]);
  });

  it("offers nothing for a signal connection or a portless connection", () => {
    const signalConnection = {
      ...connection("c1"),
      kind: "signal" as const,
    };
    expect(connectionPlotTargets(MODEL, signalConnection)).toEqual([]);

    const portless = {
      ...connection("c1"),
      from: { node: "n1" },
      to: { node: "n2" },
    };
    expect(connectionPlotTargets(MODEL, portless)).toEqual([]);
  });

  it("resolves an endpoint to the instance path and port", () => {
    expect(endpointPort(MODEL, { node: "n4", port: "p" })).toEqual({
      path: "IL",
      port: "p",
    });
    expect(endpointPort(MODEL, { node: "n2" })).toBeNull();
    expect(endpointPort(MODEL, { node: "missing", port: "p" })).toBeNull();
  });
});

describe("node outputs", () => {
  const signals = [
    runSignal("IL/w", { kind: "output", path: "IL" }),
    runSignal("IL/p.e", { kind: "port", path: "IL", unit: "V" }),
    runSignal("IL/p.f", { kind: "port", path: "IL", unit: "A" }),
    runSignal("Other/w", { kind: "output", path: "Other" }),
    runSignal("IL/x", { kind: "state", path: "IL" }),
  ];

  it("selects only the node's own recorded outputs", () => {
    const node = nodeForMenu(MODEL, "n4");
    expect(node?.name).toBe("IL");
    if (node === undefined) {
      throw new Error("the IL node is missing");
    }
    expect(nodeOutputTargets(signals, node).map((target) => target.signalId)).toEqual([
      "IL/w",
    ]);
    expect(nodeOutputIds(signals, node)).toEqual(["IL/w"]);
  });

  it("returns no outputs for another instance or an empty manifest", () => {
    const node = nodeForMenu(MODEL, "n4");
    if (node === undefined) {
      throw new Error("the IL node is missing");
    }
    expect(nodeOutputIds([runSignal("Other/w", { kind: "output", path: "Other" })], node)).toEqual([]);
    expect(nodeOutputIds([], node)).toEqual([]);
  });

  it("finds a right-clicked connection", () => {
    expect(connectionForMenu(MODEL, "c4")?.from.node).toBe("n2");
    expect(connectionForMenu(MODEL, "missing")).toBeUndefined();
    expect(nodeForMenu(MODEL, "missing")).toBeUndefined();
  });
});
