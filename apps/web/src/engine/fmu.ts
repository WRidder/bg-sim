/**
 * An FMU compiled to WebAssembly: one instance in a static arena (shim/sim_shim.c), driven by
 * variable name. The FMU's parameters can only be set before initialisation, so a restart builds
 * a new instance. Values cross as 64-bit floats through one shared buffer: a step allocates nothing.
 */

export interface FmuModel {
  guid: string;
  step: number;
  refs: Record<string, number>;
  wasm: string;
}

interface Exports {
  memory: WebAssembly.Memory;
  _initialize(): void;
  sim_text(): number;
  sim_buffer(): number;
  sim_refs(): number;
  sim_instantiate(): number;
  sim_set(n: number): number;
  sim_get(n: number): number;
  sim_start(): number;
  sim_step(t: number, h: number): number;
}

function bytes(base64: string): Uint8Array<ArrayBuffer> {
  const text = atob(base64);
  const out = new Uint8Array(text.length);
  for (let i = 0; i < text.length; i += 1) {
    out[i] = text.charCodeAt(i);
  }
  return out;
}

export class Fmu {
  readonly step: number;
  time = 0;
  private readonly refs: Uint32Array;
  private readonly values: Float64Array;

  private constructor(
    private readonly x: Exports,
    private readonly model: FmuModel,
  ) {
    this.step = model.step;
    this.refs = new Uint32Array(x.memory.buffer, x.sim_refs(), 256);
    this.values = new Float64Array(x.memory.buffer, x.sim_buffer(), 256);
    new Uint8Array(x.memory.buffer).set(new TextEncoder().encode(`${model.guid}\0`), x.sim_text());
  }

  static async load(model: FmuModel): Promise<Fmu> {
    const { instance } = await WebAssembly.instantiate(bytes(model.wasm));
    const x = instance.exports as unknown as Exports;
    x._initialize();
    return new Fmu(x, model);
  }

  /** The value references of `names`, in order: what `write` and `read` take. */
  select(names: readonly string[]): Uint32Array {
    return Uint32Array.from(names, (name) => {
      const ref = this.model.refs[name];
      if (ref === undefined) {
        throw new Error(`the FMU has no variable ${name}`);
      }
      return ref;
    });
  }

  /** The instance's memory as doubles, for a host that must reach what the FMU has no input for. */
  memory(): Float64Array {
    return new Float64Array(this.x.memory.buffer);
  }

  /** A fresh instance at `parameters`, initialised at t = 0. */
  restart(parameters: Record<string, number>): void {
    if (!this.x.sim_instantiate()) {
      throw new Error("fmi2Instantiate failed");
    }
    const names = Object.keys(parameters);
    this.write(this.select(names), names.map((name) => parameters[name]));
    if (!this.x.sim_start()) {
      throw new Error("the FMU did not initialise");
    }
    this.time = 0;
  }

  write(refs: Uint32Array, values: ArrayLike<number>): void {
    this.refs.set(refs);
    this.values.set(values);
    if (this.x.sim_set(refs.length) !== 0) {
      throw new Error("fmi2SetReal refused");
    }
  }

  read(refs: Uint32Array, into: Float64Array): void {
    this.refs.set(refs);
    if (this.x.sim_get(refs.length) !== 0) {
      throw new Error("fmi2GetReal refused");
    }
    into.set(this.values.subarray(0, refs.length));
  }

  /** One communication step; false when the FMU stopped (a non-finite state, a model stop). */
  advance(): boolean {
    const status = this.x.sim_step(this.time, this.step);
    this.time += this.step;
    return status === 0;
  }
}
