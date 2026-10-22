import { describe, expect, it } from "vitest";

import {
  LRUCache,
  SeriesCache,
  cacheKey,
} from "../src/plot/runCache";

describe("cacheKey", () => {
  it("is the plan's (run, id, t0, t1, px) key", () => {
    expect(cacheKey("run-1", "Motor1/shaft.f", { t0: 0, t1: 0.5 }, 1600)).toBe(
      "run-1|Motor1/shaft.f|0:0.5|1600",
    );
  });

  it("uses * for the whole run and keeps px in the key", () => {
    expect(cacheKey("r", "s", null, 0)).toBe("r|s|*|0");
    // px = 0 is the raw request, a different resolution from a decimated one.
    expect(cacheKey("r", "s", null, 0)).not.toBe(cacheKey("r", "s", null, 1600));
  });

  it("separates windows that differ only in one bound", () => {
    expect(cacheKey("r", "s", { t0: 0, t1: 1 }, 800)).not.toBe(
      cacheKey("r", "s", { t0: 0.1, t1: 1 }, 800),
    );
  });
});

describe("LRUCache", () => {
  it("evicts the least recently used entry", () => {
    const cache = new LRUCache<string, number>(2);
    cache.set("a", 1);
    cache.set("b", 2);
    expect(cache.get("a")).toBe(1); // a is now most recent
    cache.set("c", 3); // evicts b
    expect(cache.has("b")).toBe(false);
    expect(cache.keys()).toEqual(["a", "c"]);
    expect(cache.size).toBe(2);
  });

  it("peek does not change recency, get does", () => {
    const cache = new LRUCache<string, number>(2);
    cache.set("a", 1);
    cache.set("b", 2);
    expect(cache.peek("a")).toBe(1);
    cache.set("c", 3); // a is still least recent, so it goes
    expect(cache.has("a")).toBe(false);
    expect(cache.has("b")).toBe(true);
  });

  it("rejects a non-positive capacity", () => {
    expect(() => new LRUCache(0)).toThrow(RangeError);
    expect(() => new LRUCache(-1)).toThrow(RangeError);
  });
});

describe("SeriesCache", () => {
  const frame = (values: number[]) => ({
    time: new Float64Array(values.length),
    values: new Float64Array(values),
  });

  it("stores and finds a column by the plan's key", () => {
    const cache = new SeriesCache(4);
    cache.set("r", "s", { t0: 0, t1: 1 }, 800, frame([1, 2]));
    expect(cache.get("r", "s", { t0: 0, t1: 1 }, 800)?.values).toEqual(
      new Float64Array([1, 2]),
    );
    expect(cache.get("r", "s", { t0: 0, t1: 2 }, 800)).toBeUndefined();
    expect(cache.pointCount).toBe(2);
  });

  it("evicts by capacity and keeps the point count exact", () => {
    const cache = new SeriesCache(2);
    cache.set("r", "a", null, 0, frame([1, 2, 3]));
    cache.set("r", "b", null, 0, frame([1, 2]));
    cache.set("r", "c", null, 0, frame([1]));
    expect(cache.size).toBe(2);
    expect(cache.get("r", "a", null, 0)).toBeUndefined();
    expect(cache.pointCount).toBe(3);
  });

  it("evicts by the point budget", () => {
    const cache = new SeriesCache(64, 5);
    cache.set("r", "a", null, 0, frame([1, 2, 3]));
    cache.set("r", "b", null, 0, frame([1, 2, 3]));
    // 6 points exceed the budget of 5, so the oldest column is dropped.
    expect(cache.size).toBe(1);
    expect(cache.get("r", "b", null, 0)).toBeDefined();
    expect(cache.pointCount).toBe(3);
  });

  it("invalidates every column of one run only", () => {
    const cache = new SeriesCache(8);
    cache.set("r1", "a", null, 0, frame([1]));
    cache.set("r1", "b", null, 0, frame([1]));
    cache.set("r2", "a", null, 0, frame([1]));
    cache.invalidateRun("r1");
    expect(cache.size).toBe(1);
    expect(cache.get("r2", "a", null, 0)).toBeDefined();
    expect(cache.pointCount).toBe(1);
  });
});
