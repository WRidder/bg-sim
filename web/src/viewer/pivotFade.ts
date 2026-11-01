/**
 * The orbit pivot dot's fade-out (after the HMI viewer, plan 7.6): it starts the moment the drag ends and is gone
 * `PIVOT_FADE_MS` later, along a smooth curve; a new drag brings it back at full strength at once. Pure timing: the
 * viewer asks for the alpha per animation frame and keeps asking (its own frames: the on-demand render scheduler
 * does not provide them) until `done`.
 */
export const PIVOT_FADE_MS = 500;

/** The fade curve: 1 at progress 0, 0 at 1, smooth at both ends (smoothstep). */
export function fadeAlpha(progress: number): number {
  const t = Math.min(1, Math.max(0, progress));
  return 1 - t * t * (3 - 2 * t);
}

export class PivotFade {
  private from: number | null = null;

  /** The fade starts at `now` (ms); a fade already running keeps its start. */
  start(now: number): void {
    this.from ??= now;
  }

  /** A new interaction: the dot is at full strength again and no fade runs. */
  reset(): void {
    this.from = null;
  }

  get fading(): boolean {
    return this.from !== null;
  }

  /** The dot's alpha at `now` (1 while no fade runs). */
  alpha(now: number): number {
    return this.from === null ? 1 : fadeAlpha((now - this.from) / PIVOT_FADE_MS);
  }

  /** The fade has run its course at `now`: the dot is to be hidden. */
  done(now: number): boolean {
    return this.from !== null && now - this.from >= PIVOT_FADE_MS;
  }
}

/** What the fade driver needs from its host: the clock, animation frames, and showing an alpha (which also asks for a redraw). */
export interface FadeEnv {
  now(): number;
  raf(callback: () => void): number;
  cancel(id: number): void;
  apply(alpha: number, done: boolean): void;
}

/** Runs `fade` frame by frame until it is done; returns a stop function (a new drag cancels the fade). */
export function driveFade(fade: PivotFade, env: FadeEnv): () => void {
  let live = true;
  let id = 0;
  const tick = (): void => {
    if (!live) return;
    const t = env.now();
    const done = fade.done(t);
    env.apply(done ? 0 : fade.alpha(t), done);
    if (!done) id = env.raf(tick);
  };
  id = env.raf(tick);
  return () => {
    live = false;
    env.cancel(id);
  };
}
