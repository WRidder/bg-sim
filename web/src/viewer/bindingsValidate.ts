/**
 * Binding validation (spec "Visualization and bindings", plan 7.6), run in the browser against the built
 * scene and the signals of `model.check` / the open run:
 *
 *  - E301 unknown target (also: a target of the wrong kind for the property, or a fixed joint);
 *  - E302 unknown signal;
 *  - E303 unit mismatch (joint `position`: rad / dimensionless for revolute and continuous, m for prismatic;
 *    pose: quaternion dimensionless, position m);
 *    Rule for a signal with NO unit (null, undefined or empty: plain block-diagram signals such as integrator
 *    outputs, pose matrix entries, or bond-graph quantities of a Generic island with no concrete domain): the
 *    unit is unknown, and an unknown unit is not evidence of a mismatch. It is unchecked for every target (angle,
 *    length, quaternion) and raises no E303. A unit that IS reported and does not fit (`N`, `flow*s`, `1` on a
 *    length, `m` on an angle) still raises E303.
 *  - E304 wrong signal count (pose needs exactly 7, every other property 1).
 *
 * Diagnostics have the shape of plan 3.4; `path` is the binding target.
 */

import type { Binding } from "../contracts/model";
import type { Diagnostic } from "../contracts/diagnostic";

/** What validation needs from the built scene. */
export interface SceneLookup {
  has(ref: string): boolean;
  joint(ref: string): { readonly type: string } | null;
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

/** The problem of a signal against what the property needs, or null when it fits. */
function unitProblem(need: Need, unit: string | null | undefined, gain: number): string | null {
  // no declared unit: unchecked, not a mismatch (see the header rule)
  if ((unit ?? "").trim() === "") return null;
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

/** The signal ids of a binding, whatever its shape. */
export function signalsOf(binding: Binding): string[] {
  const s: unknown = binding.signal;
  if (Array.isArray(s)) return s.filter((x): x is string => typeof x === "string");
  return typeof s === "string" && s !== "" ? [s] : [];
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

/**
 * Validate all bindings. `signals` null skips the signal checks (E302, E303): no check or run has told
 * the viewer which signals exist yet, and a missing list must not turn every binding red.
 */
export function validateBindings(bindings: readonly Binding[], scene: SceneLookup, signals: SignalUnits | null): Diagnostic[] {
  const out: Diagnostic[] = [];
  for (const binding of bindings) {
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
    }

    const want = property === "pose" ? 7 : 1;
    const countOk = names.length === want && Array.isArray(binding.signal) === (property === "pose");
    if (!countOk) {
      out.push(
        diag(
          "E304",
          binding,
          `property "${property}" needs ${String(want)} signal${want === 1 ? "" : "s"}, got ${String(names.length)}`,
          property === "pose" ? "list exactly 7 signals: q_w, q_x, q_y, q_z, x, y, z" : "bind exactly one signal",
        ),
      );
    }

    if (signals === null) continue;
    let allKnown = true;
    for (const name of names) {
      if (!signals.has(name)) {
        allKnown = false;
        out.push(diag("E302", binding, `signal "${name}" is not a signal of the model`, "pick a signal from the list, or run Check after renaming blocks"));
      }
    }
    if (!allKnown || !targetOk || !countOk) continue;

    let need: (index: number) => Need | null = () => null;
    if (property === "position") {
      const type = scene.joint(target)?.type;
      need = () => (type === "prismatic" ? "length" : "angle");
    } else if (property === "pose") {
      need = (i) => (i < 4 ? "quaternion" : "length");
    }
    names.forEach((name, i) => {
      const wanted = need(i);
      if (wanted === null) return;
      // gain scales the position only; the quaternion is applied unscaled
      const problem = unitProblem(wanted, signals.get(name), wanted === "quaternion" ? 1 : gain);
      if (problem !== null) {
        const expect =
          property === "position" ? (wanted === "length" ? "m (prismatic joint)" : "rad (revolute or continuous joint)") : wanted === "length" ? "m" : "dimensionless";
        out.push(
          diag("E303", binding, `signal "${name}" ${problem}; "${property}" on ${target} expects ${expect}`, "bind a signal with the right unit, or convert it in the model with an output of the expected unit"),
        );
      }
    });
  }
  return out;
}
