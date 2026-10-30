/**
 * The inline probe plot: automatic limits, min/max decimation per pixel column
 * (spikes survive), gaps break the line, compact tick labels.
 */

import { describe, expect, it } from "vitest";

import { autoLimits, compactNumber, decimatedPath } from "../src/probe/MiniPlot";

describe("MiniPlot", () => {
  it("pads the value range by 5 % and widens a flat signal", () => {
    const data = { time: [0, 1, 2], values: { a: [0, 10, 5], b: [3, 3, 3] } };
    expect(autoLimits(data, ["a"], 0, 2)).toEqual({ lo: -0.5, hi: 10.5 });
    expect(autoLimits(data, ["b"], 0, 2)).toEqual({ lo: 3 - 0.3, hi: 3 + 0.3 });
    expect(autoLimits(data, ["missing"], 0, 2)).toEqual({ lo: -1, hi: 1 });
    // Only the drawn time window counts.
    expect(autoLimits(data, ["a"], 1.5, 2)).toEqual({ lo: 4.5, hi: 5.5 }); // one sample: flat
  });

  it("keeps a one-sample spike after decimation to a few columns", () => {
    const n = 10_000;
    const time = Array.from({ length: n }, (_, k) => k / (n - 1));
    const values = time.map(() => 0);
    values[4321] = 1;
    const path = decimatedPath(time, values, 0, 1, 0, 1, 10, 100);
    // y = 0 for the spike (top of the frame), y = 100 for the baseline.
    expect(path).toContain(" 0.0");
    expect(path).toContain(" 100.0");
    // One move, then at most four points per column.
    expect((path.match(/M/g) ?? []).length).toBe(1);
    expect((path.match(/[ML]/g) ?? []).length).toBeLessThanOrEqual(40);
  });

  it("breaks the line at a gap", () => {
    const path = decimatedPath([0, 1, 2, 3], [0, 1, NaN, 1], 0, 3, 0, 1, 300, 100);
    expect((path.match(/M/g) ?? []).length).toBe(2);
  });

  it("formats ticks compactly", () => {
    expect(compactNumber(0)).toBe("0");
    expect(compactNumber(1.23456)).toBe("1.23");
    expect(compactNumber(-1500)).toBe("-1500");
    expect(compactNumber(2.5e-5)).toBe("2.5e-5");
    expect(compactNumber(123456)).toBe("1.2e+5");
  });
});
