/**
 * The SDF subset of plan 7.6, parsed with `DOMParser` into a typed scene description.
 *
 * Supported: `model` (nested), `link`, `visual` with `box`, `cylinder`, `sphere` and a GLB `mesh`,
 * `material/diffuse`, `joint` of type revolute, continuous, prismatic and fixed, `frame`, and
 * `pose` with `relative_to`. `collision`, `inertial`, `sensor`, `plugin` and the other
 * simulator-only elements are ignored silently. Anything else is skipped with an E306 warning;
 * a file that cannot be read (malformed XML, bad numbers, duplicate names) is E305. Both codes are
 * errors by the E-code convention; E306 does not stop the rest of the scene from being drawn.
 * Resolving the frames and the kinematic tree is `resolve.ts`.
 */

import type { Diagnostic } from "../contracts/diagnostic";
import type { Vec3 } from "./pose";

export type JointType = "revolute" | "continuous" | "prismatic" | "fixed";
export const SUPPORTED_JOINTS: readonly JointType[] = ["revolute", "continuous", "prismatic", "fixed"];

/** `x y z roll pitch yaw` (m, rad) relative to `relativeTo` (null: the element's default frame). */
export interface SdfPose {
  readonly xyz: Vec3;
  readonly rpy: Vec3;
  readonly relativeTo: string | null;
}

export type SdfGeometry =
  | { readonly kind: "box"; readonly size: Vec3 }
  | { readonly kind: "cylinder"; readonly radius: number; readonly length: number }
  | { readonly kind: "sphere"; readonly radius: number }
  | { readonly kind: "mesh"; readonly uri: string; readonly scale: Vec3 };

export interface SdfVisual {
  readonly name: string;
  readonly pose: SdfPose;
  readonly geometry: SdfGeometry;
  /** `material/diffuse` as r, g, b, a in 0..1, or null for the default grey. */
  readonly diffuse: readonly [number, number, number, number] | null;
}

export interface SdfLink {
  readonly name: string;
  readonly pose: SdfPose;
  readonly visuals: readonly SdfVisual[];
}

export interface SdfJoint {
  readonly name: string;
  readonly type: JointType;
  /** A link name (maybe `model::link`) or `world`. */
  readonly parent: string;
  readonly child: string;
  readonly pose: SdfPose;
  readonly axis: Vec3;
  /** Frame the axis is written in (`axis/xyz@expressed_in`); null: the joint frame. */
  readonly axisFrame: string | null;
}

export interface SdfFrame {
  readonly name: string;
  readonly attachedTo: string | null;
  readonly pose: SdfPose;
}

export interface SdfModel {
  readonly name: string;
  readonly pose: SdfPose;
  readonly links: readonly SdfLink[];
  readonly joints: readonly SdfJoint[];
  readonly frames: readonly SdfFrame[];
  readonly models: readonly SdfModel[];
}

export interface SdfScene {
  readonly file: string;
  readonly models: readonly SdfModel[];
}

export interface SdfParseResult {
  /** Null when the file could not be read (an E305 explains). */
  readonly scene: SdfScene | null;
  readonly diagnostics: readonly Diagnostic[];
}

/** A diagnostic path is an instance path or a scene target (`link:arm`); `null` for a problem of the whole file. */
export function e305(path: string | null, message: string, hint: string): Diagnostic {
  return { code: "E305", severity: "error", message: `scene file could not be loaded or parsed: ${message}`, hint, path };
}

export function e306(path: string | null, message: string, hint: string): Diagnostic {
  return { code: "E306", severity: "error", message: `unsupported SDF element skipped: ${message}`, hint, path };
}

/** Elements of the SDF schema that matter only to a simulator; they are dropped without a word. */
const SILENT = new Set([
  "collision", "inertial", "sensor", "plugin", "static", "self_collide", "allow_auto_disable", "enable_wind", "gravity",
  "kinematic", "must_be_base_link", "velocity_decay", "audio_source", "audio_sink", "battery", "light", "physics",
  "gui", "scene", "atmosphere", "magnetic_field", "wind", "spherical_coordinates", "state", "description", "origin",
  "transparency", "cast_shadows", "visibility_flags", "laser_retro", "meta", "script", "projector",
  "particle_emitter", "light_state", "model_state",
]);

const NAME_PATTERN = /^[A-Za-z0-9_.-]+$/;
const DEFAULT_AXIS: Vec3 = [0, 0, 1];
const ZERO_POSE: SdfPose = { xyz: [0, 0, 0], rpy: [0, 0, 0], relativeTo: null };

class Reader {
  readonly diagnostics: Diagnostic[] = [];
  failed = false;
  /** Slash path of every named link, joint, frame and visual read so far -> its kind. */
  private readonly kinds = new Map<string, string>();

  constructor(readonly file: string) {}

  named(where: string, kind: string): void {
    this.kinds.set(where, kind);
  }

  /** The scene target (`link:base`) of the element at `where` or of its pose child, else null. */
  private target(where: string): string | null {
    const own = this.kinds.get(where);
    const parent = where.slice(0, where.lastIndexOf("/"));
    const kind = own ?? (where.endsWith("/pose") ? this.kinds.get(parent) : undefined);
    const path = own === undefined ? parent : where;
    return kind === undefined ? null : `${kind}:${path.slice(path.lastIndexOf("/") + 1)}`;
  }

  fail(where: string, message: string, hint: string): void {
    this.failed = true;
    this.diagnostics.push(e305(this.target(where), `${message} (in ${this.file})`, hint));
  }

  skip(where: string, message: string, hint: string): void {
    this.diagnostics.push(e306(this.target(where), `${message} (in ${this.file})`, hint));
  }
}

function kids(el: Element, tag?: string): Element[] {
  return Array.from(el.children).filter((c) => tag === undefined || c.localName === tag);
}

function first(el: Element, tag: string): Element | null {
  return kids(el, tag)[0] ?? null;
}

function text(el: Element | null): string {
  return el?.textContent.trim() ?? "";
}

function numbers(s: string): number[] | null {
  const parts = s.split(/\s+/).filter((p) => p.length > 0);
  const values = parts.map(Number);
  return values.some((v) => !Number.isFinite(v)) ? null : values;
}

function vec3Of(r: Reader, where: string, el: Element | null, fallback: Vec3): Vec3 {
  if (el === null) return fallback;
  const v = numbers(text(el));
  if (v?.length !== 3) {
    r.fail(where, `<${el.localName}> in ${where} needs three numbers, found "${text(el)}"`, "write the values as `x y z`");
    return fallback;
  }
  return [v[0] ?? 0, v[1] ?? 0, v[2] ?? 0];
}

function scalarOf(r: Reader, where: string, el: Element | null, fallback: number): number {
  if (el === null) return fallback;
  const v = numbers(text(el));
  if (v?.length !== 1 || (v[0] ?? 0) <= 0) {
    r.fail(where, `<${el.localName}> in ${where} needs one positive number, found "${text(el)}"`, "write a size in metres greater than zero");
    return fallback;
  }
  return v[0] ?? fallback;
}

function poseOf(r: Reader, where: string, el: Element): SdfPose {
  const p = first(el, "pose");
  if (p === null) return ZERO_POSE;
  const format = p.getAttribute("rotation_format");
  if (format !== null && format !== "euler_rpy") {
    r.skip(`${where}/pose`, `pose of ${where} uses rotation_format "${format}"`, "write the pose as `x y z roll pitch yaw` (the default euler_rpy format)");
    return ZERO_POSE;
  }
  const relativeTo = p.getAttribute("relative_to") || null;
  if (text(p) === "") return { ...ZERO_POSE, relativeTo };
  const v = numbers(text(p)) ?? [];
  if (v.length !== 6) {
    r.fail(`${where}/pose`, `pose of ${where} needs six numbers, found "${text(p)}"`, "write the pose as `x y z roll pitch yaw` (m, rad)");
    return ZERO_POSE;
  }
  const k = p.getAttribute("degrees") === "true" ? Math.PI / 180 : 1;
  return {
    xyz: [v[0] ?? 0, v[1] ?? 0, v[2] ?? 0],
    rpy: [(v[3] ?? 0) * k, (v[4] ?? 0) * k, (v[5] ?? 0) * k],
    relativeTo,
  };
}

function nameOf(r: Reader, where: string, el: Element): string | null {
  const n = el.getAttribute("name");
  if (n === null || n === "") {
    r.fail(where, `a <${el.localName}> in ${where} has no name`, `add a name="..." attribute to the <${el.localName}> element`);
    return null;
  }
  if (!NAME_PATTERN.test(n)) {
    r.fail(`${where}/${n}`, `the name "${n}" uses characters other than letters, digits and _ . -`, "rename it; binding targets can only refer to such names");
    return null;
  }
  return n;
}

function geometryOf(r: Reader, where: string, visual: Element): SdfGeometry | null {
  const g = first(visual, "geometry");
  const shape = g === null ? undefined : kids(g)[0];
  if (shape === undefined) {
    r.skip(where, `visual ${where} has no geometry`, "add a <geometry> with a <box>, <cylinder>, <sphere> or <mesh>");
    return null;
  }
  switch (shape.localName) {
    case "box":
      return { kind: "box", size: vec3Of(r, where, first(shape, "size"), [1, 1, 1]) };
    case "cylinder":
      return { kind: "cylinder", radius: scalarOf(r, where, first(shape, "radius"), 0.5), length: scalarOf(r, where, first(shape, "length"), 1) };
    case "sphere":
      return { kind: "sphere", radius: scalarOf(r, where, first(shape, "radius"), 0.5) };
    case "mesh": {
      const uri = text(first(shape, "uri"));
      if (!/\.glb$/i.test(uri.split(/[?#]/)[0] ?? "")) {
        r.skip(where, `mesh "${uri || "(no uri)"}" in ${where} is not a GLB file`, "upload the mesh (STL, OBJ, DAE or GLB) to the project; it is stored as meshes/<name>.glb, then reference that path in <uri>");
        return null;
      }
      return { kind: "mesh", uri, scale: vec3Of(r, where, first(shape, "scale"), [1, 1, 1]) };
    }
    default:
      r.skip(where, `geometry <${shape.localName}> of ${where} is not supported`, "use <box>, <cylinder>, <sphere> or a GLB <mesh> instead");
      return null;
  }
}

function diffuseOf(r: Reader, where: string, visual: Element): SdfVisual["diffuse"] {
  const material = first(visual, "material");
  const d = material === null ? null : first(material, "diffuse");
  if (d === null) return null;
  const v = numbers(text(d));
  if (v === null || (v.length !== 3 && v.length !== 4)) {
    r.fail(where, `<diffuse> of ${where} needs r g b a, found "${text(d)}"`, "write four numbers between 0 and 1, for example `0.8 0.2 0.2 1`");
    return null;
  }
  return [v[0] ?? 0, v[1] ?? 0, v[2] ?? 0, v[3] ?? 1];
}

function visualOf(r: Reader, linkPath: string, el: Element): SdfVisual | null {
  const name = nameOf(r, linkPath, el);
  if (name === null) return null;
  const where = `${linkPath}/${name}`;
  r.named(where, "visual");
  const geometry = geometryOf(r, where, el);
  if (geometry === null) return null;
  return { name, pose: poseOf(r, where, el), geometry, diffuse: diffuseOf(r, where, el) };
}

function linkOf(r: Reader, modelPath: string, el: Element): SdfLink | null {
  const name = nameOf(r, modelPath, el);
  if (name === null) return null;
  const where = `${modelPath}/${name}`;
  r.named(where, "link");
  const visuals: SdfVisual[] = [];
  const seen = new Set<string>();
  for (const c of kids(el)) {
    if (c.localName === "visual") {
      const v = visualOf(r, where, c);
      if (v === null) continue;
      if (seen.has(v.name)) r.fail(`${where}/${v.name}`, `link ${where} has two visuals named "${v.name}"`, "give each visual of a link its own name");
      seen.add(v.name);
      visuals.push(v);
    } else if (c.localName !== "pose" && !SILENT.has(c.localName)) {
      r.skip(where, `<${c.localName}> in link ${where} is not supported`, "remove it; the viewer draws visuals only");
    }
  }
  return { name, pose: poseOf(r, where, el), visuals };
}

function jointOf(r: Reader, modelPath: string, el: Element): SdfJoint | null {
  const name = nameOf(r, modelPath, el);
  if (name === null) return null;
  const where = `${modelPath}/${name}`;
  r.named(where, "joint");
  const type = el.getAttribute("type") ?? "";
  if (!(SUPPORTED_JOINTS as readonly string[]).includes(type)) {
    r.skip(where, `joint ${where} has type "${type || "(none)"}"`, "use a revolute, continuous, prismatic or fixed joint; the linked bodies stay at their static poses");
    return null;
  }
  const parent = text(first(el, "parent"));
  const child = text(first(el, "child"));
  if (parent === "" || child === "") {
    r.fail(where, `joint ${where} needs both <parent> and <child>`, "name the parent link (or world) and the child link");
    return null;
  }
  const axisEl = first(el, "axis");
  const xyz = axisEl === null ? null : first(axisEl, "xyz");
  const axis = vec3Of(r, where, xyz, DEFAULT_AXIS);
  if (type !== "fixed" && Math.hypot(...axis) === 0) {
    r.fail(where, `the axis of joint ${where} has length zero`, "give <axis><xyz> a non-zero direction such as `0 0 1`");
  }
  return { name, type: type as JointType, parent, child, pose: poseOf(r, where, el), axis, axisFrame: xyz?.getAttribute("expressed_in") || null };
}

function modelOf(r: Reader, parentPath: string, el: Element): SdfModel | null {
  const name = nameOf(r, parentPath, el);
  if (name === null) return null;
  const where = parentPath === "" ? name : `${parentPath}/${name}`;
  const links: SdfLink[] = [];
  const joints: SdfJoint[] = [];
  const frames: SdfFrame[] = [];
  const models: SdfModel[] = [];
  for (const c of kids(el)) {
    switch (c.localName) {
      case "link": {
        const l = linkOf(r, where, c);
        if (l) links.push(l);
        break;
      }
      case "joint": {
        const j = jointOf(r, where, c);
        if (j) joints.push(j);
        break;
      }
      case "frame": {
        const f = nameOf(r, where, c);
        if (f !== null) r.named(`${where}/${f}`, "frame");
        if (f !== null) frames.push({ name: f, attachedTo: c.getAttribute("attached_to") || null, pose: poseOf(r, `${where}/${f}`, c) });
        break;
      }
      case "model": {
        const m = modelOf(r, where, c);
        if (m) models.push(m);
        break;
      }
      case "pose":
        break;
      case "include":
        r.skip(where, `<include> in model ${where} is not supported`, "paste the included model into the scene file instead");
        break;
      default:
        if (!SILENT.has(c.localName)) r.skip(where, `<${c.localName}> in model ${where} is not supported`, "remove it; the viewer draws links, joints, frames and visuals only");
    }
  }
  const taken = new Map<string, string>();
  const claim = (kind: string, n: string) => {
    const other = taken.get(n);
    if (other !== undefined) r.fail(`${where}/${n}`, `model ${where} has a ${other} and a ${kind} both named "${n}"`, "give every link, joint, frame and nested model of a model a different name");
    taken.set(n, kind);
  };
  for (const l of links) claim("link", l.name);
  for (const j of joints) claim("joint", j.name);
  for (const f of frames) claim("frame", f.name);
  for (const m of models) claim("model", m.name);
  return { name, pose: poseOf(r, where, el), links, joints, frames, models };
}

/** Parse SDF text. `file` (for example `scenes/arm.sdf`) names the source in diagnostic paths. */
export function parseSdf(source: string, file: string): SdfParseResult {
  const r = new Reader(file);
  const doc = new DOMParser().parseFromString(source, "application/xml");
  const bad = doc.getElementsByTagName("parsererror")[0];
  if (bad !== undefined) {
    const lines = (bad.textContent ?? "").split("\n").map((l) => l.trim()).filter((l) => l !== "");
    const detail = lines.find((l) => !/^this page contains/i.test(l)) ?? "parse error";
    return { scene: null, diagnostics: [e305(null, `${file} is not well-formed XML (${detail})`, "fix the XML in the scene file (a tag is probably not closed), or choose another scene in the model")] };
  }
  const root = doc.documentElement;
  if (root.localName !== "sdf") {
    return { scene: null, diagnostics: [e305(null, `${file} starts with <${root.localName}>, not <sdf>`, 'wrap the models in `<sdf version="1.7">...</sdf>`')] };
  }
  const version = Number.parseFloat(root.getAttribute("version") ?? "");
  if (Number.isFinite(version) && version < 1.7) {
    r.skip("sdf", `${file} declares SDF version ${root.getAttribute("version")}; the viewer applies the SDF 1.7+ pose and axis rules`, 'set version="1.7" after checking that joint poses are relative to the child link and axes are in the joint frame');
  }
  const models: SdfModel[] = [];
  const addAll = (parent: Element) => {
    for (const c of kids(parent)) {
      if (c.localName === "model") {
        const m = modelOf(r, "", c);
        if (m) models.push(m);
      } else if (c.localName === "world" && parent === root) {
        addAll(c);
      } else if (!SILENT.has(c.localName)) {
        r.skip("sdf", `<${c.localName}> in ${file} is not supported`, "remove it; the viewer draws <model> elements only");
      }
    }
  };
  addAll(root);
  if (!r.failed && models.length === 0) {
    r.fail("sdf", `${file} contains no <model>`, "add a <model> with at least one <link>");
  }
  const names = new Set<string>();
  for (const m of models) {
    if (names.has(m.name)) r.fail(m.name, `${file} has two top-level models named "${m.name}"`, "rename one of them");
    names.add(m.name);
  }
  return { scene: r.failed ? null : { file, models }, diagnostics: r.diagnostics };
}
