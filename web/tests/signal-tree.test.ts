/**
 * The Signals tab's tree and search (plan 7.5): nested instance paths, the
 * leaf label, counts and the multi-term search.
 */

import { describe, expect, it } from "vitest";

import {
  buildSignalTree,
  countNodeSignals,
  filterSignals,
  signalLeafName,
} from "../src/plot/signalTree";
import { runSignal } from "./plotFixtures";

const SIGNALS = [
  runSignal("Plant/Motor1/speed", { unit: "rad/s", kind: "state" }),
  runSignal("Plant/Motor1/current", { unit: "A", kind: "algebraic" }),
  runSignal("Plant/Gear/torque", { unit: "N*m", kind: "port" }),
  runSignal("Shaft/angle", { unit: "rad", kind: "output" }),
];

describe("buildSignalTree", () => {
  it("nests instance paths and keeps signals at their own node", () => {
    const tree = buildSignalTree(SIGNALS);

    expect(tree.map((node) => node.segment)).toEqual(["Plant", "Shaft"]);
    const plant = tree[0];
    expect(plant?.children.map((node) => node.segment)).toEqual([
      "Gear",
      "Motor1",
    ]);
    expect(plant?.signals).toEqual([]);
    expect(countNodeSignals(plant!)).toBe(3);
    expect(plant?.children[1]?.signals.map((signal) => signal.id)).toEqual([
      "Plant/Motor1/current",
      "Plant/Motor1/speed",
    ]);
    expect(tree[1]?.signals[0]?.id).toBe("Shaft/angle");
  });

  it("creates intermediate nodes even when only a grandchild has a signal", () => {
    const tree = buildSignalTree([
      runSignal("A/B/C/value", { unit: "1" }),
    ]);
    expect(tree[0]?.segment).toBe("A");
    expect(tree[0]?.children[0]?.segment).toBe("B");
    expect(tree[0]?.children[0]?.children[0]?.segment).toBe("C");
    expect(countNodeSignals(tree[0]!)).toBe(1);
  });
});

describe("filterSignals", () => {
  it("matches id, path, unit and kind case-insensitively", () => {
    expect(filterSignals(SIGNALS, "motor").map((signal) => signal.id)).toEqual([
      "Plant/Motor1/speed",
      "Plant/Motor1/current",
    ]);
    expect(filterSignals(SIGNALS, "RAD/S").map((signal) => signal.id)).toEqual([
      "Plant/Motor1/speed",
    ]);
    expect(filterSignals(SIGNALS, "port").map((signal) => signal.id)).toEqual([
      "Plant/Gear/torque",
    ]);
  });

  it("requires every whitespace-separated term", () => {
    expect(
      filterSignals(SIGNALS, "motor rad/s").map((signal) => signal.id),
    ).toEqual(["Plant/Motor1/speed"]);
    expect(filterSignals(SIGNALS, "motor N*m")).toEqual([]);
  });

  it("returns everything for an empty query", () => {
    expect(filterSignals(SIGNALS, "   ")).toHaveLength(SIGNALS.length);
  });
});

describe("signalLeafName", () => {
  it("strips the instance path so the tree does not repeat it", () => {
    expect(signalLeafName(SIGNALS[0]!)).toBe("speed");
    expect(signalLeafName(runSignal("rootValue", { path: "" }))).toBe(
      "rootValue",
    );
  });
});
