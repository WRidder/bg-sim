import { describe, expect, it } from "vitest";

import {
  IS_LITTLE_ENDIAN,
  RUN_DATA_HEADER_BYTES,
  RunDataError,
  emptyRunDataFrame,
  parseRunData,
} from "../src/plot/runData";

/** Build one `/data` frame exactly as the backend lays it out (plan 3.7). */
function buildFrame(time: number[], columns: number[][]): ArrayBuffer {
  const nSignals = columns.length;
  const nPoints = time.length;
  const buffer = new ArrayBuffer(
    RUN_DATA_HEADER_BYTES + (nSignals + 1) * nPoints * 8,
  );
  const view = new DataView(buffer);
  view.setUint32(0, nSignals, true);
  view.setUint32(4, nPoints, true);
  const floats = new Float64Array(buffer, RUN_DATA_HEADER_BYTES);
  floats.set(time, 0);
  columns.forEach((column, index) => {
    floats.set(column, (index + 1) * nPoints);
  });
  return buffer;
}

describe("parseRunData", () => {
  it("decodes the header, the time column and one column per signal", () => {
    const frame = parseRunData(
      buildFrame(
        [0, 0.5, 1],
        [
          [1, 2, 3],
          [10, 20, 30],
        ],
      ),
    );
    expect(frame.nSignals).toBe(2);
    expect(frame.nPoints).toBe(3);
    expect(Array.from(frame.time)).toEqual([0, 0.5, 1]);
    expect(Array.from(frame.values[0])).toEqual([1, 2, 3]);
    expect(Array.from(frame.values[1])).toEqual([10, 20, 30]);
  });

  it("treats the counts and every value as little-endian", () => {
    // 0x0100000000000000 read little-endian is the huge Float64 below, not 1.
    const frame = parseRunData(
      buildFrame([0], [[-0.25]]),
    );
    expect(frame.values[0][0]).toBe(-0.25);
    expect(IS_LITTLE_ENDIAN).toBe(true);
  });

  it("accepts a frame with zero points", () => {
    const frame = parseRunData(buildFrame([], [[], []]));
    expect(frame.nPoints).toBe(0);
    expect(frame.nSignals).toBe(2);
    expect(frame.values).toHaveLength(2);
    expect(frame.values[0]).toHaveLength(0);
  });

  it("rejects a buffer shorter than the header", () => {
    expect(() => parseRunData(new ArrayBuffer(4))).toThrow(RunDataError);
    expect(() => parseRunData(new ArrayBuffer(4))).toThrow(/too short/);
  });

  it("rejects a truncated or padded answer instead of drawing garbage", () => {
    const buffer = buildFrame([0, 1], [[1, 2]]);
    expect(() => parseRunData(buffer.slice(0, buffer.byteLength - 8))).toThrow(
      /should be .* bytes, but the backend sent/,
    );
    const padded = new ArrayBuffer(buffer.byteLength + 8);
    new Uint8Array(padded).set(new Uint8Array(buffer));
    expect(() => parseRunData(padded)).toThrow(RunDataError);
  });

  it("keeps duplicate timestamps (event left/right limits) in order", () => {
    const frame = parseRunData(buildFrame([1, 1, 2], [[0, 5, 5]]));
    expect(Array.from(frame.time)).toEqual([1, 1, 2]);
    expect(Array.from(frame.values[0])).toEqual([0, 5, 5]);
  });

  it("emptyRunDataFrame has the requested column count", () => {
    const frame = emptyRunDataFrame(3);
    expect(frame.nSignals).toBe(3);
    expect(frame.values).toHaveLength(3);
    expect(frame.time).toHaveLength(0);
  });
});
