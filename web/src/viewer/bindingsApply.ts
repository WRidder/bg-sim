/**
 * Applying bindings (spec "Viewer loop"): at one playback time, interpolate the bound signals
 * (lerp; shortest-path slerp for the pose quaternion), apply `gain` and `offset`, and set the
 * property through the built scene. Only `gain` and `offset` exist; any other math belongs in the model.
 * A `deformation` binding hands its modal coordinates (times `gain`) to the scene, which evaluates the
 * mode shapes per vertex (`beamModes.ts`); all families of one visual go in one call.
 */

import type { Binding, DeformationBinding, SegmentBinding, SegmentBrokenStyle, ShapeAxis } from "../contracts/model";
import type { BeamConfig } from "../scene/build";
import type { Vec3 } from "../scene/pose";
import { planarPoint } from "../scene/segment";
import type { ModalSet } from "./beamModes";
import { colormapColor } from "./bindingsColormaps";
import { allSignalsOf, signalCountOk, signalsOf } from "./bindingsValidate";
import { normalizeQuat, type SignalBuffer } from "./timeline";

/** The setters of `BuiltScene` the applier uses. */
export interface ApplyTarget {
  setJointPosition(ref: string, q: number): boolean;
  setPose(ref: string, pose: readonly [number, number, number, number, number, number, number]): boolean;
  setVisualScale(ref: string, sx: number, sy: number, sz: number): boolean;
  setVisualColor(ref: string, r: number, g: number, b: number): boolean;
  setVisible(ref: string, visible: boolean): boolean;
  /** The visuals deformation bindings drive (beam meshes); called whenever the bindings or the scene change. */
  configureBeams?(configs: ReadonlyMap<string, BeamConfig>): void;
  /** Modal coordinates of a configured beam visual, all its families at once (gain applied). */
  setDeformation?(ref: string, sets: readonly ModalSet[]): boolean;
  /** A bar between two world points (segment binding); `broken` draws a failed bar. */
  setSegment?(ref: string, a: Vec3, b: Vec3, axis: ShapeAxis | undefined, broken: SegmentBrokenStyle | null): boolean;
  /** Back to the rest pose. */
  reset(): void;
}

/**
 * Per visual target of deformation bindings: the beam mapping (of its first deformation binding),
 * stripes when torsion is bound, and the strain colouring (of the first binding that asks for it).
 */
export function beamConfigs(bindings: readonly Binding[]): Map<string, BeamConfig> {
  const out = new Map<string, BeamConfig>();
  for (const b of bindings) {
    if (b.property !== "deformation") continue;
    const before = out.get(b.target);
    out.set(b.target, {
      beam: before?.beam ?? b.beam,
      stripes: (before?.stripes ?? false) || b.family === "torsion",
      strain: before?.strain ?? (b.family !== "torsion" ? (b.strain ?? null) : null),
    });
  }
  return out;
}
/** The distinct signal ids of the bindings, in first-use order: the ids to request from the stream. */
export function boundSignalIds(bindings: readonly Binding[]): string[] {
  const seen = new Set<string>();
  for (const b of bindings) for (const s of allSignalsOf(b)) seen.add(s);
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
  /** Per deformation target: the modal sets of its bindings, applied together after the loop. */
  private readonly deformations = new Map<string, ModalSet[]>();
  /** Last value each position binding set, by target, for tests and the playback bar's readout. */
  readonly applied = new Map<string, number>();

  constructor(
    private readonly scene: ApplyTarget,
    bindings: readonly Binding[],
    ids: readonly string[],
  ) {
    for (const binding of bindings) {
      const names = allSignalsOf(binding);
      const cols = names.map((n) => ids.indexOf(n));
      const basis = binding.property === "deformation" ? binding.basis : undefined;
      if (!signalCountOk(binding.property, signalsOf(binding).length, basis) || cols.some((c) => c < 0)) continue;
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
    this.deformations.clear();
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
        case "deformation": {
          const set = modalSet(binding, cols.map((c) => buffer.valueAt(c, t)));
          if (set === null) break;
          const sets = this.deformations.get(binding.target) ?? [];
          sets.push(set);
          this.deformations.set(binding.target, sets);
          this.applied.set(`${binding.target}#${binding.family}`, set.eta[0] ?? 0);
          n++;
          break;
        }
        case "segment": {
          const seg = segmentEnds(binding, cols.map((c) => buffer.valueAt(c, t)));
          if (seg === null) break;
          this.scene.setSegment?.(binding.target, seg.a, seg.b, binding.axis, seg.broken);
          this.applied.set(binding.target, seg.broken === null ? 0 : 1);
          n++;
          break;
        }
      }
    }
    for (const [target, s] of this.scales) this.scene.setVisualScale(target, s[0], s[1], s[2]);
    for (const [target, sets] of this.deformations) this.scene.setDeformation?.(target, sets);
    return n;
  }
}

/**
 * The world end points of a segment binding from its sampled signals (positions first, then the optional
 * broken flag): planar (u, v) pairs go through `plane` and `depth`, `gain` and `offset` apply to every
 * coordinate (not to the depth). Null when a sample is missing.
 */
export function segmentEnds(binding: SegmentBinding, values: readonly (number | null)[]): { a: Vec3; b: Vec3; broken: SegmentBrokenStyle | null } | null {
  const n = binding.signal.length;
  const coords: number[] = [];
  for (let k = 0; k < n; k++) {
    const v = values[k];
    if (v === null || v === undefined) return null;
    coords.push(gainOffset(v, binding));
  }
  const c = (k: number): number => coords[k] ?? 0;
  let a: Vec3;
  let b: Vec3;
  if (n === 4) {
    a = planarPoint(c(0), c(1), binding.plane, binding.depth ?? 0);
    b = planarPoint(c(2), c(3), binding.plane, binding.depth ?? 0);
  } else {
    a = [c(0), c(1), c(2)];
    b = [c(3), c(4), c(5)];
  }
  let broken: SegmentBrokenStyle | null = null;
  if (binding.broken !== undefined) {
    const f = values[n];
    if (f !== null && f !== undefined && f > 0.5) broken = binding.brokenStyle ?? "snapped";
  }
  return { a, b, broken };
}

/** The modal coordinates of a deformation binding from its sampled signals (gain applied), or null when a sample is missing. */
function modalSet(binding: DeformationBinding, values: readonly (number | null)[]): ModalSet | null {
  const eta: number[] = [];
  for (const v of values) {
    if (v === null) return null;
    eta.push(v * (binding.gain ?? 1));
  }
  return { family: binding.family, basis: binding.basis, eta };
}
