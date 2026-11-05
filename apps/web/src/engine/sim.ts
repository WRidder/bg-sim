/**
 * An FMU on a fixed step, paced by the frame clock: names instead of value references, the last two
 * outputs for drawing between steps, and a hook after each step for what the game checks.
 */

import { Fmu } from "./fmu";
import { Pacer } from "./pacer";

export class Sim<Output extends string> {
  readonly pacer: Pacer;
  readonly u: Float64Array;
  y: Float64Array;
  previous: Float64Array;
  paused = false;
  /** Set when the run is over: steps stop until the next restart. */
  stopped = false;
  private readonly inRefs: Uint32Array;
  private readonly outRefs: Uint32Array;
  private readonly index: Record<Output, number>;

  protected constructor(
    protected readonly fmu: Fmu,
    inputs: readonly string[],
    outputs: readonly Output[],
  ) {
    this.pacer = new Pacer(fmu.step);
    this.u = new Float64Array(inputs.length);
    this.y = new Float64Array(outputs.length);
    this.previous = new Float64Array(outputs.length);
    this.inRefs = fmu.select(inputs);
    this.outRefs = fmu.select(outputs);
    this.index = Object.fromEntries(outputs.map((name, i) => [name, i])) as Record<Output, number>;
  }

  get time(): number {
    return this.fmu.time;
  }

  get(name: Output): number {
    return this.y[this.index[name]];
  }

  /** A value between the last two steps, for drawing. */
  between(name: Output): number {
    const i = this.index[name];
    return this.previous[i] + (this.y[i] - this.previous[i]) * this.pacer.fraction;
  }

  /** Back to the start: `u` holds the inputs to begin with once `init` has run. */
  protected restart(params: Record<string, number>, init: () => void): void {
    this.fmu.restart(params);
    this.u.fill(0);
    init();
    this.fmu.write(this.inRefs, this.u);
    this.fmu.read(this.outRefs, this.y);
    this.previous.set(this.y);
    this.pacer.reset();
    this.stopped = false;
  }

  /** Runs as many fixed steps as a frame of `dt` seconds holds. */
  advance(dt: number): void {
    if (this.paused || this.stopped) {
      this.pacer.reset();
      return;
    }
    const steps = this.pacer.stepsFor(dt);
    for (let i = 0; i < steps && !this.stopped; i += 1) {
      this.beforeStep();
      [this.previous, this.y] = [this.y, this.previous];
      this.fmu.write(this.inRefs, this.u);
      const running = this.fmu.advance();
      this.fmu.read(this.outRefs, this.y);
      this.afterStep(running && this.y.every(Number.isFinite));
    }
  }

  protected beforeStep(): void {}

  /** `healthy` is false when the FMU stopped or an output stopped being a number. */
  protected afterStep(healthy: boolean): void {
    if (!healthy) {
      this.stopped = true;
    }
  }
}
