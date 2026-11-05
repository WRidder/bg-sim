import { describe, expect, it } from "vitest";
import { normalisedSlip } from "../src/cars/telemetry";
import { History, layout, plotRange, reading, share, type Section, WIDTH, zoneColour } from "../src/engine/telemetry";

describe("History", () => {
  it("keeps the newest samples in order", () => {
    const history = new History(3);
    [1, 2, 3, 4].forEach((v) => history.push(v));
    expect([history.at(0), history.at(1), history.at(2)]).toEqual([2, 3, 4]);
    expect(history.count).toBe(3);
  });

  it("reads a part-filled trace from its first sample", () => {
    const history = new History(4);
    [5, 6].forEach((v) => history.push(v));
    expect([history.at(0), history.at(1)]).toEqual([5, 6]);
    expect(history.extent()).toEqual([5, 6]);
  });

  it("turns what is not a number into zero, and clears", () => {
    const history = new History(2);
    history.push(Number.NaN);
    expect(history.at(0)).toBe(0);
    history.clear();
    expect(history.count).toBe(0);
  });
});

describe("readings", () => {
  it("holds a share to its range, and to zero for no number", () => {
    expect(share(150, 0, 100)).toBe(1);
    expect(share(-5, 0, 100)).toBe(0);
    expect(share(25, 0, 100)).toBe(0.25);
    expect(share(Number.NaN, 0, 100)).toBe(0);
  });

  it("picks digits by size and never shows a negative zero", () => {
    expect(reading(1234.5)).toBe("1235");
    expect(reading(12.34)).toBe("12.3");
    expect(reading(1.234)).toBe("1.23");
    expect(reading(-0.001, 1)).toBe("0.0");
    expect(reading(Number.POSITIVE_INFINITY)).toBe("—");
  });

  it("colours a value by the zone it is in", () => {
    expect(zoneColour(5, [[0, 10, "green"], [10, 20, "red"]], "ink")).toBe("green");
    expect(zoneColour(50, [[0, 10, "green"]], "ink")).toBe("ink");
    expect(zoneColour(50, undefined, "ink")).toBe("ink");
  });

  it("grows a plot's range to a trace past it", () => {
    const history = new History(4);
    [1, 30].forEach((v) => history.push(v));
    expect(plotRange({ min: 0, max: 10 }, [history])).toEqual([0, 30]);
    expect(plotRange({ min: 0, max: 10 }, [new History(4)])).toEqual([0, 10]);
  });
});

describe("layout", () => {
  const value = { kind: "value", label: "v", get: () => 0 } as const;
  const gauge = { kind: "gauge", label: "g", get: () => 0, min: 0, max: 1 } as const;
  const bar = { kind: "bar", label: "b", get: () => 0, min: 0, max: 1 } as const;

  it("puts three values and two gauges to a row, a bar on its own", () => {
    const sections: Section[] = [{ title: "a", items: [value, value, value, value, gauge, gauge, bar] }];
    const { placed } = layout(sections);
    const rows = new Set(placed.map((p) => p.y));
    expect(rows.size).toBe(4);
    expect(placed[0].y).toBe(placed[2].y);
    expect(placed[3].y).toBeGreaterThan(placed[0].y);
    expect(placed[4].y).toBe(placed[5].y);
  });

  it("keeps everything inside the panel", () => {
    const { placed, height } = layout([{ title: "a", items: [value, value, gauge, gauge, bar] }]);
    for (const p of placed) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x + p.w).toBeLessThanOrEqual(WIDTH);
      expect(p.y + p.h).toBeLessThanOrEqual(height);
    }
  });
});

describe("the tyre's peak in the cars' panel", () => {
  // The slick at its reference load, by hand from design/tyre.py: peak slip ratio tan(pi/3.2)/B with
  // B = 25/(1.6*1.65), peak tan(alpha) tan(pi/2.9)/B with B = 22*2200*sin(2 atan 0.4)/(1.45*1.6*2200).
  const peakKappa = Math.tan(Math.PI / 3.2) / (25 / (1.6 * 1.65));
  const peakAlpha = Math.tan(Math.PI / 2.9) / ((22 * Math.sin(2 * Math.atan(0.4))) / (1.45 * 1.6));
  const slick = { Fz0: 2200, mux: 1.65, muy: 1.6, dmu: -0.12, Kx: 25, Cx: 1.6, Ky: 22, Ky2: 2.5, Cy: 1.45 };

  it("is 1 at the top of each force curve", () => {
    expect(peakKappa).toBeCloseTo(0.158, 3);
    expect(peakAlpha).toBeCloseTo(0.288, 3);
    expect(normalisedSlip(slick, 2200, peakKappa, 0, 1)).toBeCloseTo(1, 9);
    expect(normalisedSlip(slick, 2200, 0, peakAlpha, 1)).toBeCloseTo(1, 9);
  });

  it("combines the two directions", () => {
    expect(normalisedSlip(slick, 2200, peakKappa, peakAlpha, 1)).toBeCloseTo(Math.SQRT2, 9);
  });

  it("comes sooner on a surface with less grip", () => {
    expect(normalisedSlip(slick, 2200, 0.1, 0, 0.5)).toBeCloseTo(2 * normalisedSlip(slick, 2200, 0.1, 0, 1), 6);
  });
});
