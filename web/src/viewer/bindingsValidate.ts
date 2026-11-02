/**
 * Binding validation (spec "Visualization and bindings", plan 7.6), run in the browser against the built
 * scene and the signals of `model.check` / the open run:
 *
 *  - E301 unknown target (also: a target of the wrong kind for the property, or a fixed joint);
 *  - E302 unknown signal;
 *  - E303 unit mismatch (joint `position`: rad / dimensionless for revolute and continuous, m for prismatic;
 *    pose: quaternion dimensionless, position m);
 *    Rule for a signal with an UNKNOWN unit: none (null, undefined or empty: plain block-diagram signals such
 *    as integrator outputs, pose matrix entries), or a symbolic `effort`/`flow` unit of a Generic bond island
 *    with no concrete domain (`flow*s`; W205 treats the island as dimensionless). An unknown unit is not
 *    evidence of a mismatch: it is unchecked for every target (angle, length, quaternion) and raises no E303.
 *    A physical unit that does not fit (`N`, `1` on a length, `m` on an angle) still raises E303.
 *  - E304 wrong signal count (pose needs exactly 7, deformation 1 to 3 modal coordinates, or exactly 1 with
 *    the `linear` basis, mode-shapes 1 to 64 and no more than its mesh has morph targets (with `stress`: no
 *    more than its stress table has modes), segment 4 planar
 *    or 6 spatial end-point coordinates, every other property 1).
 *
 * Segment bindings (a bar between two moving points) raise E301 when the visual cannot stretch along the
 * segment axis (a sphere or mesh, a cylinder along anything but its own axis); their coordinates are
 * lengths (m) for E303, and the optional `broken` flag is checked like any other signal for E302.
 *
 * Deformation bindings (elastic beams) also raise E301 when the visual is no beam (a sphere or mesh, a
 * cylinder bent across its own axis, a beam y along the beam axis), when a visual has two bindings of one
 * family, when two bindings of one visual give different beam mappings, or when the `linear` basis (the
 * twist of a lumped torsion spring) is given to a bending family. Bending coordinates are lengths
 * (m), torsion coordinates angles (rad) for E303.
 *
 * Mode-shapes bindings (flexible bodies from a finite element reduction) raise E301 when the visual is no
 * mesh, when its mesh has no morph targets, or when a visual has two of them; with a stress colouring also
 * when the GLB has no stress table or the stress range is not low < high (finite). Their coordinates are lengths
 * (m) for E303.
 *
 * Diagnostics have the shape of plan 3.4; `path` is the binding target.
 */

import type { BeamMapping, Binding, DeformationBinding, ModeShapeBinding } from "../contracts/model";
import type { Diagnostic } from "../contracts/diagnostic";
import { beamFrame } from "../scene/beamMesh";
import { segmentAxis } from "../scene/segment";
import type { SdfGeometry } from "../scene/sdf";
import { maxModes } from "./beamModes";

/** Modal coordinates a mode-shapes binding may give (the contract's maximum). */
export const MAX_MESH_MODES = 64;

/** What validation needs from the built scene. */
export interface SceneLookup {
  has(ref: string): boolean;
  joint(ref: string): { readonly type: string } | null;
  /** The geometry of a visual (deformation bindings need a box or cylinder); absent: not checked. */
  visualGeometry?(ref: string): SdfGeometry | null;
  /**
   * Morph targets (mode shapes) of a loaded mesh visual: the fewest over its meshes, 0 when it has none;
   * null when the ref is no loaded mesh visual. Absent: not checked.
   */
  morphTargetCount?(ref: string): number | null;
  /**
   * Modes of the stress table of a loaded mesh visual's GLB (`asset.extras.bgsim.stress`), 0 when it has
   * none; null when the ref is no loaded mesh visual. Absent: not checked.
   */
  stressModeCount?(ref: string): number | null;
}

/** Signal id -> unit (null: the model gives none). */
export type SignalUnits = ReadonlyMap<string, string | null | undefined>;

export const BINDING_CODES: readonly string[] = ["E301", "E302", "E303", "E304"];

type Dimension = "angle" | "length" | "dimensionless" | "other";

const DEG = Math.PI / 180;

interface UnitRule {
  readonly dim: Dimension;
  /** Factor to SI; a unit that is not SI is accepted only when `gain` carries this factor. */
  readonly factor: number;
}

/**
 * Rad is dimensionless in the canonical unit form the worker reports (plan 5.3), so an angle signal arrives
 * as "1" or "rad". An empty or missing unit is the same thing. Units that are a scaled angle or length are
 * understood, but a binding must then carry the factor as its `gain` (the viewer applies nothing else).
 */
export function unitRule(unit: string | null | undefined): UnitRule {
  const u = (unit ?? "").trim();
  switch (u) {
    case "":
    case "1":
    case "rad":
      return { dim: "dimensionless", factor: 1 };
    case "deg":
    case "°":
      return { dim: "angle", factor: DEG };
    case "m":
      return { dim: "length", factor: 1 };
    case "mm":
      return { dim: "length", factor: 1e-3 };
    case "cm":
      return { dim: "length", factor: 1e-2 };
    default:
      return { dim: "other", factor: 1 };
  }
}

function describeUnit(unit: string | null | undefined): string {
  const u = (unit ?? "").trim();
  return u === "" ? "no unit" : `unit "${u}"`;
}

function near(a: number, b: number): boolean {
  return Math.abs(a - b) <= 1e-6 * Math.abs(b);
}

type Need = "angle" | "length" | "quaternion";

/**
 * A unit that says nothing physical: none at all, or one still holding the `effort`/`flow`
 * pseudo-dimensions of a pure Generic bond island (W205, "treated as dimensionless"), e.g. `flow*s`.
 */
export function isUnknownUnit(unit: string | null | undefined): boolean {
  const u = (unit ?? "").trim();
  return u === "" || /\b(effort|flow)\b/.test(u);
}

/** The problem of a signal against what the property needs, or null when it fits. */
function unitProblem(need: Need, unit: string | null | undefined, gain: number): string | null {
  // no declared unit, or one of a Generic island: unchecked, not a mismatch (see the header rule)
  if (isUnknownUnit(unit)) return null;
  const rule = unitRule(unit);
  if (need === "angle" || need === "quaternion") {
    // angles and quaternion parts are dimensionless (rad is dimensionless); deg needs the factor in gain
    if (rule.dim === "dimensionless") return null;
    if (need === "angle" && rule.dim === "angle") {
      return near(gain, rule.factor) ? null : `has ${describeUnit(unit)}; set the gain to pi/180 or output radians from the model`;
    }
    return `has ${describeUnit(unit)}, which is not ${need === "angle" ? "an angle in rad" : "dimensionless"}`;
  }
  if (rule.dim === "length") {
    return rule.factor === 1 || near(gain, rule.factor) ? null : `has ${describeUnit(unit)}; set the gain to ${String(rule.factor)} or output metres from the model`;
  }
  return `has ${describeUnit(unit)}, which is not a length in m`;
}

/** The signal ids of a binding's `signal` field, whatever its shape. */
export function signalsOf(binding: Binding): string[] {
  const s: unknown = binding.signal;
  if (Array.isArray(s)) return s.filter((x): x is string => typeof x === "string");
  return typeof s === "string" && s !== "" ? [s] : [];
}

/** Every signal id a binding reads: its `signal` field, then a segment's `broken` flag. */
export function allSignalsOf(binding: Binding): string[] {
  const out = signalsOf(binding);
  if (binding.property === "segment" && typeof binding.broken === "string" && binding.broken !== "") out.push(binding.broken);
  return out;
}

/** How many signals a property takes: [min, max] (a deformation: by its basis, `linear` takes one; a
 * segment takes 4 or 6, see `signalCountOk`). */
export function signalCount(property: string, basis?: string): readonly [number, number] {
  switch (property) {
    case "pose":
      return [7, 7];
    case "deformation":
      return [1, maxModes(basis === "linear" ? "linear" : "clamped-free")];
    case "mode-shapes":
      return [1, MAX_MESH_MODES];
    case "segment":
      return [4, 6];
    default:
      return [1, 1];
  }
}

/** True when `n` signals fit the property (a segment: 4 planar or 6 spatial coordinates). */
export function signalCountOk(property: string, n: number, basis?: string): boolean {
  if (property === "segment") return n === 4 || n === 6;
  const [min, max] = signalCount(property, basis);
  return n >= min && n <= max;
}

/** Whether a property takes a list of signals (a JSON array), even of one. */
export function takesSignalList(property: string): boolean {
  return property === "pose" || property === "deformation" || property === "mode-shapes" || property === "segment";
}

/** The kind prefixes a property can target. */
export function allowedKinds(property: string): readonly string[] {
  switch (property) {
    case "position":
      return ["joint"];
    case "pose":
      return ["link", "frame"];
    case "visible":
      return ["visual", "link"];
    default:
      return ["visual"];
  }
}

function diag(code: string, binding: Binding, message: string, hint: string): Diagnostic {
  return { code, severity: "error", message, hint, path: binding.target };
}

function sameMapping(a: BeamMapping, b: BeamMapping): boolean {
  const na = a.neutral ?? [0, 0];
  const nb = b.neutral ?? [0, 0];
  return a.axis === b.axis && (a.y ?? null) === (b.y ?? null) && (a.length ?? null) === (b.length ?? null) && na[0] === nb[0] && na[1] === nb[1];
}

/** E301 problems of a deformation binding against its shape and the deformation bindings before it. */
function deformationProblems(binding: DeformationBinding, scene: SceneLookup, earlier: readonly Binding[]): Diagnostic[] {
  const out: Diagnostic[] = [];
  if (binding.basis === "linear" && binding.family !== "torsion") {
    out.push(diag("E301", binding, `the linear basis is the twist of a torsion spring and cannot drive ${binding.family}`, "use the family torsion with the linear basis, or a modal basis (clamped-free, free-free) for bending"));
  }
  const geometry = scene.visualGeometry?.(binding.target);
  if (geometry !== undefined && geometry !== null) {
    const frame = beamFrame(geometry, binding.beam);
    if (typeof frame === "string") {
      out.push(diag("E301", binding, `visual "${binding.target}" cannot deform as a beam: ${frame}`, "bind a box or cylinder visual, and set the beam axis along its length"));
    }
  }
  for (const other of earlier) {
    if (other.property !== "deformation" || other.target !== binding.target) continue;
    if (other.family === binding.family) {
      out.push(diag("E301", binding, `visual "${binding.target}" has two ${binding.family} deformation bindings`, "list all modes of a family in one binding (up to three signals), and remove the other"));
      break;
    }
    if (!sameMapping(other.beam, binding.beam)) {
      out.push(diag("E301", binding, `the beam mapping of this ${binding.family} binding differs from the ${other.family} binding of "${binding.target}"`, "give every deformation binding of a visual the same beam axis, y axis, length and neutral axis"));
      break;
    }
  }
  return out;
}

/** E301 problems of a mode-shapes binding against its visual and the mode-shapes bindings before it. */
function modeShapeProblems(binding: ModeShapeBinding, scene: SceneLookup, earlier: readonly Binding[]): Diagnostic[] {
  const out: Diagnostic[] = [];
  const geometry = scene.visualGeometry?.(binding.target);
  if (geometry !== undefined && geometry !== null && geometry.kind !== "mesh") {
    out.push(diag("E301", binding, `visual "${binding.target}" is a ${geometry.kind}, not a mesh; mode shapes need a mesh with morph targets`, "bind the GLB mesh visual written by the FEM reduction (one morph target per mode), or use a deformation binding for a box or cylinder beam"));
  } else if (scene.morphTargetCount?.(binding.target) === 0) {
    out.push(diag("E301", binding, `the mesh of visual "${binding.target}" has no morph targets (mode shapes)`, "use the GLB written by the FEM reduction tool, which stores one morph target per elastic mode"));
  } else if (binding.stress !== undefined && scene.stressModeCount?.(binding.target) === 0) {
    out.push(
      diag(
        "E301",
        binding,
        `the mesh of visual "${binding.target}" has no stress table, so it cannot be coloured by stress`,
        "re-run the FEM reduction (julia/BGSimFEM) on the part spec: it writes the stress per mode into the GLB; or turn the stress colouring off",
      ),
    );
  }
  const range = binding.stress?.range;
  if (range !== undefined && !(Number.isFinite(range[0]) && Number.isFinite(range[1]) && range[0] < range[1])) {
    out.push(diag("E301", binding, `the stress range of visual "${binding.target}" must be two finite values, low below high (Pa)`, "set the von Mises stress at the low and the high end of the colormap, e.g. 0 to 50 MPa"));
  }
  if (earlier.some((other) => other.property === "mode-shapes" && other.target === binding.target)) {
    out.push(diag("E301", binding, `visual "${binding.target}" has two mode-shapes bindings`, "list all modal coordinates in one binding, in mode order, and remove the other"));
  }
  return out;
}

/**
 * Validate all bindings. `signals` null skips the signal checks (E302, E303): no check or run has told
 * the viewer which signals exist yet, and a missing list must not turn every binding red.
 */
export function validateBindings(bindings: readonly Binding[], scene: SceneLookup, signals: SignalUnits | null): Diagnostic[] {
  return validateBindingRows(bindings, scene, signals).flat();
}

/** The diagnostics of each binding, in order (the binding table shows them under their row). */
export function validateBindingRows(bindings: readonly Binding[], scene: SceneLookup, signals: SignalUnits | null): Diagnostic[][] {
  return bindings.map((binding, index) => validateOne(binding, scene, signals, bindings.slice(0, index)));
}

function validateOne(binding: Binding, scene: SceneLookup, signals: SignalUnits | null, earlier: readonly Binding[]): Diagnostic[] {
  const out: Diagnostic[] = [];
  const target = typeof binding.target === "string" ? binding.target : "";
  const property: string = binding.property;
  const kind = target.split(":")[0] ?? "";
  const names = signalsOf(binding);
  const gain = typeof binding.gain === "number" ? binding.gain : 1;

  let targetOk = true;
  if (!scene.has(target)) {
    targetOk = false;
    out.push(diag("E301", binding, `binding target "${target}" is not in the scene`, "pick an existing joint, link, frame or visual in the Bindings table, or add it to the scene file"));
  } else if (!allowedKinds(property).includes(kind)) {
    targetOk = false;
    out.push(
      diag(
        "E301",
        binding,
        `property "${property}" cannot drive ${kind} "${target}"`,
        `"${property}" needs a ${allowedKinds(property).join(" or ")} target; pick another target or change the property`,
      ),
    );
  } else if (property === "position" && scene.joint(target)?.type === "fixed") {
    targetOk = false;
    out.push(diag("E301", binding, `joint "${target}" is fixed and has no position`, "bind a revolute, continuous or prismatic joint, or remove this binding"));
  } else if (binding.property === "deformation") {
    const problems = deformationProblems(binding, scene, earlier);
    if (problems.length > 0) targetOk = false;
    out.push(...problems);
  } else if (binding.property === "mode-shapes") {
    const problems = modeShapeProblems(binding, scene, earlier);
    if (problems.length > 0) targetOk = false;
    out.push(...problems);
  } else if (binding.property === "segment") {
    const geometry = scene.visualGeometry?.(target);
    if (geometry !== undefined && geometry !== null) {
      const axis = segmentAxis(geometry, binding.axis);
      if (typeof axis === "string") {
        targetOk = false;
        out.push(diag("E301", binding, `visual "${target}" cannot be stretched as a bar: ${axis}`, "bind a box or cylinder visual, and set the segment axis along its length"));
      }
    }
  }

  const isList = takesSignalList(property);
  const basis = binding.property === "deformation" ? binding.basis : undefined;
  const [min, max] = signalCount(property, basis);
  let countOk = signalCountOk(property, names.length, basis) && Array.isArray(binding.signal) === isList;
  if (countOk && targetOk && property === "mode-shapes") {
    const targets = scene.morphTargetCount?.(target);
    if (typeof targets === "number" && targets > 0 && names.length > targets) {
      countOk = false;
      out.push(
        diag(
          "E304",
          binding,
          `the mesh of visual "${target}" has ${String(targets)} morph target${targets === 1 ? "" : "s"} (mode shapes), but the binding lists ${String(names.length)} modal coordinates`,
          `bind at most ${String(targets)} signals (eta[1] to eta[${String(targets)}]), or regenerate the GLB with more modes`,
        ),
      );
    }
    const table = binding.property === "mode-shapes" && binding.stress !== undefined ? scene.stressModeCount?.(target) : undefined;
    if (countOk && typeof table === "number" && table > 0 && names.length > table) {
      countOk = false;
      out.push(
        diag(
          "E304",
          binding,
          `the stress table of the mesh of visual "${target}" has ${String(table)} mode${table === 1 ? "" : "s"}, but the binding lists ${String(names.length)} modal coordinates`,
          `bind at most ${String(table)} signals, or re-run the FEM reduction so that the GLB's stress table has every mode`,
        ),
      );
    }
  }
  if (!countOk && !out.some((d) => d.code === "E304")) {
    const want = property === "segment" ? "4 or 6" : min === max ? String(min) : `${String(min)} to ${String(max)}`;
    out.push(
      diag(
        "E304",
        binding,
        `property "${property}" needs ${want} signal${max === 1 ? "" : "s"}, got ${String(names.length)}`,
        property === "pose"
          ? "list exactly 7 signals: q_w, q_x, q_y, q_z, x, y, z"
          : property === "deformation"
            ? binding.property === "deformation" && binding.basis === "linear"
              ? "the linear basis takes one signal: the twist of end B relative to end A"
              : "list the modal coordinates of the family, one signal per mode (1 to 3 modes)"
            : property === "mode-shapes"
              ? `list the modal coordinates eta[1..n] in mode order, one signal per morph target (1 to ${String(MAX_MESH_MODES)})`
              : property === "segment"
                ? "list the end points A then B: uA, vA, uB, vB in the plane of the binding, or xA, yA, zA, xB, yB, zB"
                : "bind exactly one signal",
      ),
    );
  }

  if (signals === null) return out;
  let allKnown = true;
  for (const name of allSignalsOf(binding)) {
    if (!signals.has(name)) {
      allKnown = false;
      out.push(diag("E302", binding, `signal "${name}" is not a signal of the model`, "pick a signal from the list, or run Check after renaming blocks"));
    }
  }
  if (!allKnown || !targetOk || !countOk) return out;

  let need: (index: number) => Need | null = () => null;
  if (property === "position") {
    const type = scene.joint(target)?.type;
    need = () => (type === "prismatic" ? "length" : "angle");
  } else if (property === "pose") {
    need = (i) => (i < 4 ? "quaternion" : "length");
  } else if (binding.property === "deformation") {
    const torsion = binding.family === "torsion";
    need = () => (torsion ? "angle" : "length");
  } else if (property === "mode-shapes" || property === "segment") {
    need = () => "length";
  }
  names.forEach((name, i) => {
    const wanted = need(i);
    if (wanted === null) return;
    // gain scales the position only; the quaternion is applied unscaled
    const problem = unitProblem(wanted, signals.get(name), wanted === "quaternion" ? 1 : gain);
    if (problem !== null) {
      const expect =
        property === "position"
          ? wanted === "length"
            ? "m (prismatic joint)"
            : "rad (revolute or continuous joint)"
          : property === "deformation"
            ? wanted === "length"
              ? "m (bending modal coordinate)"
              : "rad (torsion modal coordinate)"
            : property === "mode-shapes"
              ? "m (modal coordinate)"
              : wanted === "length"
                ? "m"
                : "dimensionless";
      out.push(
        diag("E303", binding, `signal "${name}" ${problem}; "${property}" on ${target} expects ${expect}`, "bind a signal with the right unit, or convert it in the model with an output of the expected unit"),
      );
    }
  });
  return out;
}
