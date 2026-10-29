/**
 * The 3D View's playback (plan 7.6): one clock, the recorded or live samples of the bound signals, and
 * the apply loop. React-free so it can be tested with a fake frame clock.
 *
 * - **Playback** (finished run): `PlaybackClock` owns the time; the plot cursor (global inspect time) seeks it
 *   and playing or scrubbing writes the cursor back, so both views share one head.
 * - **Live** (running): the head follows the newest sample, delayed by 1.5 sample intervals, never
 *   extrapolated; the cursor is not written.
 * - A frame loop runs only while playing or live. Paused, a frame is applied once per change (seek, cursor,
 *   data, bindings), so the render scheduler stays idle.
 */

import { BindingApplier, type ApplyTarget } from "./bindingsApply";
import type { Binding } from "../contracts/model";
import { PlaybackClock, liveHead } from "./playbackClock";
import { browserClock, type FrameClock } from "./renderScheduler";
import type { SignalBuffer } from "./timeline";

/** The global inspect time (the plot cursor). */
export interface CursorPort {
  get(): number | null;
  set(time: number | null): void;
  subscribe(listener: (time: number | null) => void): () => void;
}

/** `empty`: no samples to show. */
export type PlaybackMode = "empty" | "live" | "playback";

export interface PlaybackSnapshot {
  readonly mode: PlaybackMode;
  readonly playing: boolean;
  /** Simulation time of the head, or null with no data. */
  readonly time: number | null;
  readonly start: number;
  readonly end: number;
  readonly speed: number;
  readonly loop: boolean;
  /** Joint position (after gain and offset) each position binding last set, by target. */
  readonly applied: Readonly<Record<string, number>>;
}

export interface PlaybackDeps {
  readonly now?: () => number;
  readonly frames?: FrameClock;
}

/** The cursor is written at most this often while playing (ms). */
const CURSOR_PERIOD_MS = 50;

export class ViewerPlayback {
  readonly clock = new PlaybackClock();
  private readonly now: () => number;
  private readonly frames: FrameClock;
  private readonly listeners = new Set<() => void>();
  private target: ApplyTarget | null = null;
  private bindings: readonly Binding[] = [];
  private applier: BindingApplier | null = null;
  private buffer: SignalBuffer | null = null;
  private live = false;
  private frame: number | null = null;
  private lastWritten: number | null = null;
  private lastWriteAt = Number.NEGATIVE_INFINITY;
  private fromCursor = false;
  private wasRunning = false;
  /** The cursor when the data was chosen; applied as the data (and so the range) arrives, until the user moves. */
  private pendingCursor: number | null = null;
  private head: number | null = null;
  private snapshotValue: PlaybackSnapshot;
  private readonly unsubscribe: (() => void)[] = [];
  private disposed = false;
  private active = true;

  constructor(
    private readonly cursor: CursorPort,
    deps: PlaybackDeps = {},
  ) {
    this.now = deps.now ?? (() => performance.now());
    this.frames = deps.frames ?? browserClock;
    this.snapshotValue = this.makeSnapshot();
    this.unsubscribe.push(this.clock.subscribe(() => { this.onClockChange(); }));
    this.unsubscribe.push(this.cursor.subscribe((t) => { this.onCursor(t); }));
  }

  get mode(): PlaybackMode {
    return this.buffer === null || this.buffer.length === 0 ? "empty" : this.live ? "live" : "playback";
  }

  snapshot(): PlaybackSnapshot {
    return this.snapshotValue;
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  /** The scene to drive (null: none). */
  setTarget(target: ApplyTarget | null): void {
    this.target = target;
    this.rebuild(false);
  }

  setBindings(bindings: readonly Binding[]): void {
    this.bindings = bindings;
    this.rebuild(true);
  }

  /** The samples to show, live or recorded. Null clears them. */
  setData(buffer: SignalBuffer | null, live: boolean): void {
    this.pendingCursor = live ? null : this.cursor.get();
    this.buffer = buffer;
    this.live = live;
    this.rebuild(false);
    this.dataChanged();
  }

  /** Frames were appended to the buffer. */
  dataChanged(): void {
    const span = this.buffer?.span ?? null;
    if (span !== null && !this.live) {
      // a longer range is not a seek of the user: it must not move the plot cursor
      this.fromCursor = true;
      this.clock.setRange(span.t0, span.t1, this.now());
      if (this.pendingCursor !== null) this.clock.seek(this.pendingCursor, this.now());
      this.fromCursor = false;
    }
    this.requestFrame();
  }

  /** The live run ended: keep the data, switch to clock playback standing where the live head was. */
  finishLive(): void {
    if (!this.live) return;
    const span = this.buffer?.span ?? null;
    const head = this.head;
    this.live = false;
    if (span !== null) {
      this.fromCursor = true;
      this.clock.setRange(span.t0, span.t1, this.now());
      this.clock.seek(head ?? span.t1, this.now());
      this.fromCursor = false;
    }
    this.requestFrame();
  }

  play(): void {
    this.pendingCursor = null;
    if (this.mode === "playback") this.clock.play(this.now());
  }

  pause(): void {
    this.clock.pause(this.now());
  }

  toggle(): void {
    if (this.clock.playing(this.now())) this.pause();
    else this.play();
  }

  seek(t: number): void {
    this.pendingCursor = null;
    if (this.mode === "playback") this.clock.seek(t, this.now());
  }

  setSpeed(speed: number): void {
    this.clock.setSpeed(speed, this.now());
  }

  setLoop(loop: boolean): void {
    this.clock.setLoop(loop, this.now());
  }

  /** False while the 3D View is hidden: no frames are applied, the clock keeps its time. */
  setActive(active: boolean): void {
    this.active = active;
    if (active) this.requestFrame();
    else if (this.frame !== null) {
      this.frames.cancel(this.frame);
      this.frame = null;
    }
  }

  dispose(): void {
    this.disposed = true;
    for (const u of this.unsubscribe) u();
    if (this.frame !== null) this.frames.cancel(this.frame);
    this.frame = null;
    this.listeners.clear();
  }

  private rebuild(resetScene: boolean): void {
    if (resetScene) this.target?.reset();
    this.applier = this.target !== null && this.buffer !== null ? new BindingApplier(this.target, this.bindings, this.buffer.ids) : null;
    this.requestFrame();
  }

  private seekTo(t: number): void {
    this.fromCursor = true;
    this.clock.seek(t, this.now());
    this.fromCursor = false;
  }

  private onCursor(t: number | null): void {
    if (this.disposed || t === null || t === this.lastWritten) return;
    this.pendingCursor = null;
    if (this.mode !== "playback") return;
    this.seekTo(t);
  }

  private onClockChange(): void {
    if (this.disposed) return;
    if (!this.fromCursor && this.mode === "playback") this.writeCursor(this.clock.time(this.now()), true);
    this.requestFrame();
  }

  private writeCursor(t: number, force: boolean): void {
    const now = this.now();
    if (!force && now - this.lastWriteAt < CURSOR_PERIOD_MS) return;
    this.lastWriteAt = now;
    this.lastWritten = t;
    this.cursor.set(t);
  }

  private requestFrame(): void {
    if (this.disposed || !this.active || this.frame !== null) return;
    this.frame = this.frames.request(() => {
      this.frame = null;
      this.tick();
    });
  }

  private headTime(now: number): number | null {
    const buffer = this.buffer;
    if (buffer === null || buffer.length === 0) return null;
    return this.live ? liveHead(buffer.span, buffer.interval) : this.clock.time(now);
  }

  private tick(): void {
    if (this.disposed) return;
    const now = this.now();
    const t = this.headTime(now);
    this.head = t;
    if (t !== null && this.applier !== null && this.buffer !== null) this.applier.apply(this.buffer, t);
    const running = this.mode === "live" || (this.mode === "playback" && this.clock.playing(now));
    if (this.mode === "playback" && t !== null && (running || this.wasRunning)) this.writeCursor(t, !running);
    this.wasRunning = running;
    this.snapshotValue = this.makeSnapshot();
    for (const l of this.listeners) l();
    if (running) this.requestFrame();
  }

  private makeSnapshot(): PlaybackSnapshot {
    const now = this.now();
    const mode = this.mode;
    const span = this.buffer?.span ?? null;
    return {
      mode,
      playing: mode === "playback" && this.clock.playing(now),
      time: this.head,
      start: this.live ? (span?.t0 ?? 0) : this.clock.start,
      end: this.live ? (span?.t1 ?? 0) : this.clock.end,
      speed: this.clock.speed,
      loop: this.clock.loop,
      applied: Object.fromEntries(this.applier?.applied ?? []),
    };
  }
}
