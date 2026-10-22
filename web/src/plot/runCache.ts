/**
 * The LRU cache for plotted series (plan 7.5: "an LRU cache keyed
 * `(run, id, t0, t1, px)`").
 *
 * `/data` answers may contain several signals, but the cache stores each
 * signal column separately so a signal added later reuses the request that
 * already fetched it, and the same column can serve a second panel or a
 * pinned comparison run. Entries share the response's `Float64Array`s, so a
 * multi-signal answer costs one buffer, not one buffer per signal.
 */

/** The requested time window; `null` means the whole run. */
export interface SeriesWindow {
  t0: number;
  t1: number;
}

/** One cached signal column and its time axis. */
export interface SeriesFrame {
  time: Float64Array;
  values: Float64Array;
}

/**
 * The cache key of plan 7.5. `px = 0` is the raw "show all" request and is a
 * different entry from a decimated one, because its resolution differs.
 */
export function cacheKey(
  runId: string,
  signalId: string,
  window: SeriesWindow | null,
  px: number,
): string {
  const span = window === null ? "*" : `${window.t0}:${window.t1}`;
  return `${runId}|${signalId}|${span}|${px}`;
}

/** A minimal Map-backed LRU: `get` marks an entry as most recently used. */
export class LRUCache<K, V> {
  private readonly entries = new Map<K, V>();

  constructor(private readonly capacity: number) {
    if (!Number.isInteger(capacity) || capacity <= 0) {
      throw new RangeError(`an LRU capacity must be a positive integer, got ${capacity}`);
    }
  }

  get size(): number {
    return this.entries.size;
  }

  /** Keys from least to most recently used (for tests and diagnostics). */
  keys(): K[] {
    return [...this.entries.keys()];
  }

  has(key: K): boolean {
    return this.entries.has(key);
  }

  get(key: K): V | undefined {
    const value = this.entries.get(key);
    if (value === undefined) {
      return undefined;
    }
    this.entries.delete(key);
    this.entries.set(key, value);
    return value;
  }

  /** Read without changing the recency order (used by the point budget). */
  peek(key: K): V | undefined {
    return this.entries.get(key);
  }

  set(key: K, value: V): void {
    this.entries.delete(key);
    this.entries.set(key, value);
    while (this.entries.size > this.capacity) {
      const oldest = this.entries.keys().next().value;
      if (oldest === undefined) {
        break;
      }
      this.entries.delete(oldest);
    }
  }

  delete(key: K): boolean {
    return this.entries.delete(key);
  }

  clear(): void {
    this.entries.clear();
  }
}

/** The application-wide series cache; 64 columns is a few zoom levels of a plot. */
export class SeriesCache {
  private readonly cache: LRUCache<string, SeriesFrame>;
  private readonly capacity: number;
  private readonly maxPoints: number;
  private points = 0;

  /**
   * @param capacity Maximum columns; the plan's key makes each signal column
   *   an entry so a later panel or a pinned run can reuse it.
   * @param maxPoints Total points kept across all columns (default 8 million,
   *   about 64 MB of Float64 data). A raw 20 × 1e6 answer is larger than that,
   *   so the least recently used columns are dropped instead of exhausting
   *   the tab's memory.
   */
  constructor(capacity = 64, maxPoints = 8_000_000) {
    this.capacity = capacity;
    // The LRU's own capacity is unbounded; this class enforces both limits so
    // the point counter stays exact when capacity (not bytes) evicts.
    this.cache = new LRUCache(Number.MAX_SAFE_INTEGER);
    this.maxPoints = maxPoints;
  }

  get size(): number {
    return this.cache.size;
  }

  /** Kept points across all columns (for tests and diagnostics). */
  get pointCount(): number {
    return this.points;
  }

  keys(): string[] {
    return this.cache.keys();
  }

  get(
    runId: string,
    signalId: string,
    window: SeriesWindow | null,
    px: number,
  ): SeriesFrame | undefined {
    return this.cache.get(cacheKey(runId, signalId, window, px));
  }

  set(
    runId: string,
    signalId: string,
    window: SeriesWindow | null,
    px: number,
    frame: SeriesFrame,
  ): void {
    const points = frame.values.length;
    if (points > this.maxPoints) {
      return;
    }
    const key = cacheKey(runId, signalId, window, px);
    const existing = this.cache.peek(key);
    if (existing !== undefined) {
      this.points -= existing.values.length;
    }
    this.cache.set(key, frame);
    this.points += points;
    while (this.points > this.maxPoints || this.cache.size > this.capacity) {
      const oldest = this.cache.keys()[0];
      if (oldest === undefined) {
        break;
      }
      const entry = this.cache.peek(oldest);
      this.cache.delete(oldest);
      this.points -= entry?.values.length ?? 0;
    }
  }

  /** Drop every column of a run; used when a live run publishes its final data. */
  invalidateRun(runId: string): void {
    const prefix = `${runId}|`;
    for (const key of this.cache.keys()) {
      if (!key.startsWith(prefix)) {
        continue;
      }
      const entry = this.cache.peek(key);
      this.cache.delete(key);
      this.points -= entry?.values.length ?? 0;
    }
  }

  clear(): void {
    this.cache.clear();
    this.points = 0;
  }
}

/** The cache shared by every plot panel and by the pinned comparison. */
export const runDataCache = new SeriesCache(64);
