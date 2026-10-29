/** Playback clock of the 3D View (pattern of the HMI `PlaybackClock`): wall time x speed, re-anchored on every change. */

export const PLAYBACK_SPEEDS: readonly number[] = [0.1, 0.25, 0.5, 1, 2, 4];

/** Delay of live playback behind the newest sample, in sample intervals (never extrapolates). */
export const LIVE_DELAY_INTERVALS = 1.5;

/**
 * Simulation time `start..end` played at `speed` times wall time. `now` is always passed in (ms), so
 * the clock is deterministic. A speed change, seek, pause or `setRange` re-anchors at the time shown, so
 * nothing jumps. Playing stops at the end, or wraps to the start when `loop` is on; playing from the end
 * starts over.
 */
export class PlaybackClock {
  private anchorT: number;
  private anchorNow = 0;
  private playingFlag = false;
  private speedValue = 1;
  private loopFlag = false;
  private startT: number;
  private endT: number;
  private readonly listeners = new Set<() => void>();

  constructor(start = 0, end = 0) {
    this.startT = start;
    this.endT = Math.max(start, end);
    this.anchorT = start;
  }

  get start(): number {
    return this.startT;
  }

  get end(): number {
    return this.endT;
  }

  get duration(): number {
    return this.endT - this.startT;
  }

  get speed(): number {
    return this.speedValue;
  }

  get loop(): boolean {
    return this.loopFlag;
  }

  /** Playing at `now` (false once the end is reached without looping). */
  playing(now: number): boolean {
    return this.playingFlag && (this.loopFlag || this.rawTime(now) < this.endT);
  }

  /** The time at `now`, wrapped when looping and clamped to the range otherwise. */
  time(now: number): number {
    const raw = this.rawTime(now);
    if (this.loopFlag && this.playingFlag && this.duration > 0 && raw >= this.endT) {
      return this.startT + ((raw - this.startT) % this.duration);
    }
    return this.clamp(raw);
  }

  play(now: number): void {
    this.settle(now);
    if (this.playingFlag) return;
    const t = this.time(now);
    this.anchorT = t >= this.endT ? this.startT : t;
    this.anchorNow = now;
    this.playingFlag = true;
    this.notify();
  }

  pause(now: number): void {
    this.reanchor(now);
    this.playingFlag = false;
    this.notify();
  }

  seek(t: number, now: number): void {
    this.settle(now);
    this.anchorT = this.clamp(t);
    this.anchorNow = now;
    this.notify();
  }

  rewind(now: number): void {
    this.seek(this.startT, now);
  }

  setSpeed(speed: number, now: number): void {
    if (!(speed > 0) || !Number.isFinite(speed)) return;
    this.reanchor(now);
    this.speedValue = speed;
    this.notify();
  }

  setLoop(loop: boolean, now: number): void {
    if (loop === this.loopFlag) return;
    this.reanchor(now);
    this.loopFlag = loop;
    this.notify();
  }

  /** The recorded time range changed (the run finished, or a new run was chosen); the head is kept inside it. */
  setRange(start: number, end: number, now: number): void {
    this.reanchor(now);
    this.startT = start;
    this.endT = Math.max(start, end);
    this.anchorT = this.clamp(this.anchorT);
    this.notify();
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private reanchor(now: number): void {
    this.settle(now);
    this.anchorT = this.time(now);
    this.anchorNow = now;
  }

  /** A playback that reached the end has stopped there. */
  private settle(now: number): void {
    if (this.playingFlag && !this.loopFlag && this.rawTime(now) >= this.endT) {
      this.anchorT = this.endT;
      this.anchorNow = now;
      this.playingFlag = false;
    }
  }

  private rawTime(now: number): number {
    return this.playingFlag ? this.anchorT + ((now - this.anchorNow) / 1000) * this.speedValue : this.anchorT;
  }

  private clamp(t: number): number {
    return Math.max(this.startT, Math.min(this.endT, t));
  }

  private notify(): void {
    for (const l of this.listeners) l();
  }
}

/**
 * The head of live playback: the newest sample time minus 1.5 sample intervals, held inside the data
 * (the first sample time while the buffer is shorter than the delay). Null without data.
 */
export function liveHead(span: { readonly t0: number; readonly t1: number } | null, interval: number | null): number | null {
  if (span === null) return null;
  const delay = (interval ?? 0) * LIVE_DELAY_INTERVALS;
  return Math.max(span.t0, span.t1 - delay);
}
