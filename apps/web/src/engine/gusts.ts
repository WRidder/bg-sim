/** First-order filtered gusts on three axes: a stand-in for a Dryden filter, enough to feel. */
export class Gusts {
  /** Metres per second, one sigma. */
  intensity = 0;
  private readonly state = [0, 0, 0];

  constructor(
    /** The gusts' length scale, in metres. */
    private readonly length: number,
  ) {}

  /** Writes the gust into `into` at `at`, `at + 1` and `at + 2`. */
  sample(dt: number, speed: number, into: Float64Array, at: number): void {
    if (this.intensity > 0) {
      const a = Math.exp((-dt * Math.max(speed, 30)) / this.length);
      const b = Math.sqrt(1 - a * a) * this.intensity;
      for (let i = 0; i < 3; i += 1) {
        const normal = Math.sqrt(-2 * Math.log(1 - Math.random())) * Math.cos(2 * Math.PI * Math.random());
        this.state[i] = a * this.state[i] + b * normal;
      }
    }
    into[at] = this.state[0];
    into[at + 1] = this.state[1];
    into[at + 2] = this.state[2];
  }
}
