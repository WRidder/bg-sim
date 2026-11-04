/**
 * Fixed-step pacing: whole steps per frame, the remainder carried to the next, and a bounded
 * catch-up. A frame later than `maxSteps` drops the backlog, so a slow machine slows the flight
 * down instead of spiralling.
 */
export class Pacer {
  private accumulated = 0;
  behind = 0;

  constructor(
    readonly step: number,
    readonly maxSteps = 24,
  ) {}

  stepsFor(dt: number): number {
    this.accumulated += Math.max(0, dt);
    const steps = Math.floor((this.accumulated + 1e-12) / this.step);
    this.accumulated -= steps * this.step;
    if (steps > this.maxSteps) {
      this.behind += 1;
      return this.maxSteps;
    }
    return steps;
  }

  /** Where the drawn state lies between the last two steps: 0 the previous, 1 the last. */
  get fraction(): number {
    return Math.min(1, this.accumulated / this.step);
  }

  reset(): void {
    this.accumulated = 0;
  }
}
