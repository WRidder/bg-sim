export interface FrameClock {
  readonly request: (cb: (now: number) => void) => number;
  readonly cancel: (id: number) => void;
}

export const browserClock: FrameClock = {
  request: (cb) => requestAnimationFrame(cb),
  cancel: (id) => {
    cancelAnimationFrame(id);
  },
};

/**
 * On-demand rendering: a frame is drawn only when something asked for one (a pose
 * sample, an input, a prop change) or the previous frame reported ongoing motion
 * (interpolation between samples, camera inertia).  While the view is hidden (tab in the
 * background, canvas scrolled away) nothing is drawn; becoming visible draws once.
 */
export class RenderScheduler {
  private pending: number | null = null;
  private visible = true;
  private disposed = false;
  private framesDrawn = 0;

  /** `draw` renders one frame and returns whether another frame would differ. */
  constructor(
    private readonly draw: (now: number) => boolean,
    private readonly clock: FrameClock = browserClock,
  ) {}

  get frames(): number {
    return this.framesDrawn;
  }

  get idle(): boolean {
    return this.pending === null;
  }

  invalidate(): void {
    if (this.disposed || !this.visible || this.pending !== null) return;
    this.pending = this.clock.request((now) => {
      this.pending = null;
      if (this.disposed || !this.visible) return;
      this.framesDrawn += 1;
      if (this.draw(now)) this.invalidate();
    });
  }

  setVisible(visible: boolean): void {
    if (visible === this.visible) return;
    this.visible = visible;
    if (!visible && this.pending !== null) {
      this.clock.cancel(this.pending);
      this.pending = null;
    }
    if (visible) this.invalidate();
  }

  dispose(): void {
    this.disposed = true;
    if (this.pending !== null) this.clock.cancel(this.pending);
    this.pending = null;
  }
}

/** Hardware scaling for a device pixel ratio capped at `cap` (Babylon renders at 1/level). */
export function hardwareScaling(devicePixelRatio: number, cap: number): number {
  const dpr = Number.isFinite(devicePixelRatio) && devicePixelRatio > 0 ? devicePixelRatio : 1;
  return 1 / Math.min(dpr, cap);
}
