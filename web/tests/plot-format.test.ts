import { describe, expect, it } from "vitest";

import {
  formatAxisTime,
  formatCursorTime,
  formatDuration,
  formatLegendValue,
  formatNumber,
  formatProgress,
  trimZeros,
} from "../src/plot/format";

describe("formatNumber", () => {
  it("uses three decimals in the normal range and trims zeros", () => {
    expect(formatNumber(0.42)).toBe("0.42");
    expect(formatNumber(1234)).toBe("1234");
    expect(formatNumber(-1.5)).toBe("-1.5");
  });

  it("switches to scientific notation outside the range", () => {
    expect(formatNumber(1.23e-5)).toBe("1.23e-5");
    expect(formatNumber(2.5e6)).toBe("2.5e6");
  });

  it("renders zero and non-finite values explicitly", () => {
    expect(formatNumber(0)).toBe("0");
    expect(formatNumber(Number.NaN)).toBe("—");
    expect(formatNumber(Number.POSITIVE_INFINITY)).toBe("—");
  });

  it("trimZeros never eats an integer's digits", () => {
    expect(trimZeros("1234")).toBe("1234");
    expect(trimZeros("1.500")).toBe("1.5");
    expect(trimZeros("-0.0")).toBe("0");
  });
});

describe("formatLegendValue", () => {
  it("appends the unit and spells Bool and Int semantically", () => {
    expect(formatLegendValue(2.5, "rad/s", "Real")).toBe("2.5 rad/s");
    expect(formatLegendValue(1, null, "Bool")).toBe("true");
    expect(formatLegendValue(0, null, "Bool")).toBe("false");
    expect(formatLegendValue(2.6, null, "Int")).toBe("3");
  });

  it("uses an em dash for a missing point and omits an empty unit", () => {
    expect(formatLegendValue(null, "V", "Real")).toBe("—");
    expect(formatLegendValue(Number.NaN, "V", "Real")).toBe("—");
    expect(formatLegendValue(1.5, "  ", "Real")).toBe("1.5");
  });
});

describe("time formatting", () => {
  it("formats the cursor with adaptive precision", () => {
    expect(formatCursorTime(1.23456)).toBe("1.235 s");
    expect(formatCursorTime(42.346)).toBe("42.35 s");
    expect(formatCursorTime(null)).toBe("—");
  });

  it("formats the x axis without a unit", () => {
    expect(formatAxisTime(0.5)).toBe("0.5");
    expect(formatAxisTime(1500)).toBe("1500");
  });

  it("formats durations and progress", () => {
    expect(formatDuration(0.94)).toBe("0.94 s");
    expect(formatDuration(12.34)).toBe("12.3 s");
    expect(formatProgress(0.42, 1)).toBe("0.42 / 1 s");
  });
});
