/**
 * The policies, run by ONNX Runtime Web on its plain WebAssembly backend, single-threaded, so the
 * page needs no cross-origin isolation (decision W3). The runtime is imported only when this page
 * asks for it, so no other game's bundle grows.
 *
 * I/O as `duck-control/src/policy.rs` and `docs/recurrent-policies.md` of pollen-robotics/microduck
 * define it: float32 `obs [1, 61]` in, one `[1, 14]` out (named `actions` in every file of the set).
 * A recurrent export adds `h_in`/`c_in` → `h_out`/`c_out`, carried between ticks and zeroed when
 * its network starts driving; the published set has none, but a downloaded one may.
 */

import type * as Ort from "onnxruntime-web";
import type { Brain } from "./controller";
import { ACTION_LEN, OBS_LEN } from "./robot";

type OrtModule = typeof Ort;

/** The browser build of the runtime, its Wasm located explicitly so a bundler cannot lose it. */
export async function loadOrt(): Promise<OrtModule> {
  const [ort, wasm] = await Promise.all([import("onnxruntime-web/wasm"), import("onnxruntime-web/ort-wasm-simd-threaded.wasm?url")]);
  ort.env.wasm.numThreads = 1;
  ort.env.wasm.wasmPaths = { wasm: new URL(wasm.default, location.href).href };
  return ort;
}

interface Net {
  session: Ort.InferenceSession;
  output: string;
  /** Recurrent state, when the export has one: [h, c] with their shapes. */
  state: { h: Float32Array; c: Float32Array; shape: number[] } | null;
}

export class OnnxBrain implements Brain {
  private readonly nets = new Map<string, Net>();
  /** Milliseconds of the last inference, for the HUD. */
  lastMs = 0;

  constructor(private readonly ort: OrtModule) {}

  has(net: string): boolean {
    return this.nets.has(net);
  }

  get loaded(): string[] {
    return [...this.nets.keys()];
  }

  async load(slot: string, bytes: Uint8Array): Promise<void> {
    const session = await this.ort.InferenceSession.create(bytes, { executionProviders: ["wasm"], graphOptimizationLevel: "all" });
    if (!session.inputNames.includes("obs")) {
      throw new Error(`${slot}: no input named obs (has ${session.inputNames.join(", ")})`);
    }
    const recurrent = session.inputNames.includes("h_in") && session.inputNames.includes("c_in");
    const output = session.outputNames.includes("actions") ? "actions" : session.outputNames[0];
    let state: Net["state"] = null;
    if (recurrent) {
      const meta = session.inputMetadata.find((m) => m.name === "h_in");
      const shape = meta && meta.isTensor ? meta.shape.map((d) => (typeof d === "number" ? d : 1)) : null;
      if (!shape || shape.length !== 3) {
        throw new Error(`${slot}: recurrent state of an unknown shape`);
      }
      const size = shape.reduce((a, b) => a * b, 1);
      state = { h: new Float32Array(size), c: new Float32Array(size), shape };
    }
    this.nets.set(slot, { session, output, state });
  }

  async infer(slot: string, obs: Float32Array, fresh: boolean): Promise<Float32Array> {
    const net = this.nets.get(slot);
    if (!net) {
      throw new Error(`no ${slot} policy loaded`);
    }
    if (obs.length !== OBS_LEN) {
      throw new Error("an observation is 61 wide");
    }
    const started = performance.now();
    const feeds: Record<string, Ort.Tensor> = { obs: new this.ort.Tensor("float32", Float32Array.from(obs), [1, OBS_LEN]) };
    if (net.state) {
      if (fresh) {
        net.state.h.fill(0);
        net.state.c.fill(0);
      }
      feeds.h_in = new this.ort.Tensor("float32", Float32Array.from(net.state.h), net.state.shape);
      feeds.c_in = new this.ort.Tensor("float32", Float32Array.from(net.state.c), net.state.shape);
    }
    const out = await net.session.run(feeds);
    const action = Float32Array.from(out[net.output].data as Float32Array);
    if (action.length !== ACTION_LEN || !action.every(Number.isFinite)) {
      throw new Error(`${slot}: ${action.length} actions, not 14 finite ones`);
    }
    if (net.state) {
      net.state.h.set(out.h_out.data as Float32Array);
      net.state.c.set(out.c_out.data as Float32Array);
    }
    this.lastMs = performance.now() - started;
    return action;
  }
}
