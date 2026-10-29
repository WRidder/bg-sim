/**
 * Applying bindings (spec "Viewer loop"): at one playback time, interpolate the bound signals
 * (lerp; shortest-path slerp for the pose quaternion), apply `gain` and `offset`, and set the
 * property through the built scene. Only `gain` and `offset` exist; any other math belongs in the model.
 */

import type { Binding } from "../contracts/model";
import { colormapColor } from "./bindingsColormaps";
import { signalsOf } from "./bindingsValidate";
import { normalizeQuat, type SignalBuffer } from "./timeline";

/** The setters of `BuiltScene` the applier uses. */
export interface ApplyTarget {
  setJointPosition(ref: string, q: number): boolean;
  setPose(ref: string, pose: readonly [number, number, number, number, number, number, number]): boolean;
  setVisualScale(ref: string, sx: number, sy: number, sz: number): boolean;
  setVisualColor(ref: string, r: number, g: number, b: number): boolean;
  setVisible(ref: string, visible: boolean): boolean;
  /** Back to the rest pose. */
  reset(): void;
}

/** The distinct signal ids of the bindings, in first-use order: the ids to request from the stream. */
export function boundSignalIds(bindings: readonly Binding[]): string[] {
  const seen = new Set<string>();
  for (const b of bindings) for (const s of signalsOf(b)) seen.add(s);
  return [...seen];
}

/** `value * gain + offset`. */
export function gainOffset(value: number, binding: { readonly gain?: number | undefined; readonly offset?: number | undefined }): number {
  return value * (binding.gain ?? 1) + (binding.offset ?? 0);
}

const AXIS: Record<string, 0 | 1 | 2> = { "scale.x": 0, "scale.y": 1, "scale.z": 2 };

interface Compiled {
  readonly binding: Binding;
  /** Column in the buffer of each signal of the binding. */
  readonly cols: readonly number[];
}

/**
 * The bindings against one buffer layout. Bindings whose signals are not all in `ids`, or whose signal
 * count is wrong, are skipped (validation reports them; they must not stop the others).
 */
export class BindingApplier {
  private readonly compiled: Compiled[] = [];
  /** Per scale target: the scale the bound axes write into (unbound axes stay 1). */
  private readonly scales = new Map<string, [number, number, number]>();
  /** Last value each position binding set, by target, for tests and the playback bar's readout. */
  readonly applied = new Map<string, number>();

  constructor(
    private readonly scene: ApplyTarget,
    bindings: readonly Binding[],
    ids: readonly string[],
  ) {
    for (const binding of bindings) {
      const names = signalsOf(binding);
      const cols = names.map((n) => ids.indexOf(n));
      const want = binding.property === "pose" ? 7 : 1;
      if (names.length !== want || cols.some((c) => c < 0)) continue;
      this.compiled.push({ binding, cols });
    }
  }

  get count(): number {
    return this.compiled.length;
  }

  /** Set every bound property from the samples at time `t`; returns how many bindings found data. */
  apply(buffer: SignalBuffer, t: number): number {
    let n = 0;
    this.scales.clear();
    for (const { binding, cols } of this.compiled) {
      const first = cols[0];
      if (first === undefined) continue;
      switch (binding.property) {
        case "position": {
          const v = buffer.valueAt(first, t);
          if (v === null) break;
          const q = gainOffset(v, binding);
          if (this.scene.setJointPosition(binding.target, q)) this.applied.set(binding.target, q);
          n++;
          break;
        }
        case "pose": {
          const [c0, c1, c2, c3, c4, c5, c6] = cols;
          if (c0 === undefined || c1 === undefined || c2 === undefined || c3 === undefined) break;
          const q = buffer.quatAt([c0, c1, c2, c3], t);
          const x = buffer.valueAt(c4 ?? -1, t);
          const y = buffer.valueAt(c5 ?? -1, t);
          const z = buffer.valueAt(c6 ?? -1, t);
          if (q === null || x === null || y === null || z === null) break;
          // gain and offset move the position; scaling the quaternion would leave the rotation chart
          const [qw, qx, qy, qz] = normalizeQuat(q);
          this.scene.setPose(binding.target, [qw, qx, qy, qz, gainOffset(x, binding), gainOffset(y, binding), gainOffset(z, binding)]);
          n++;
          break;
        }
        case "scale.x":
        case "scale.y":
        case "scale.z": {
          const v = buffer.valueAt(first, t);
          if (v === null) break;
          const s = this.scales.get(binding.target) ?? [1, 1, 1];
          s[AXIS[binding.property] ?? 0] = gainOffset(v, binding);
          this.scales.set(binding.target, s);
          n++;
          break;
        }
        case "color": {
          const v = buffer.valueAt(first, t);
          if (v === null) break;
          const [r, g, b] = colormapColor(binding.colormap, gainOffset(v, binding), binding.range);
          this.scene.setVisualColor(binding.target, r, g, b);
          n++;
          break;
        }
        case "visible": {
          const v = buffer.valueAt(first, t);
          if (v === null) break;
          this.scene.setVisible(binding.target, gainOffset(v, binding) > 0.5);
          n++;
          break;
        }
      }
    }
    for (const [target, s] of this.scales) this.scene.setVisualScale(target, s[0], s[1], s[2]);
    return n;
  }
}
