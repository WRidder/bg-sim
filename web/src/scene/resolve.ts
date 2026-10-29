/**
 * Frames and the kinematic tree of an SDF scene (plan 7.6), free of Babylon.
 *
 * Every named frame (model, link, joint, frame) gets a rest-pose world matrix in the SDF world
 * frame (`sdf_root`, Z-up), resolved through `relative_to` with the SDF 1.7+ defaults: a link pose
 * is relative to its model frame, a joint pose to its child link, a frame pose to its
 * `attached_to` frame, a visual pose to its link, a nested model pose to its parent model.
 * The scene graph the builder creates follows the "static joint frame, child = pure joint motion"
 * structure:
 *
 *   parent link --- jointFrame (local = X_parent^-1 X_child X_childJoint)
 *                      '-- jointMotion (local = the joint motion only)
 *                             '-- child link (local = X_childJoint^-1)
 *
 * Root links hang under their model node, models under their parent model (or `sdf_root`).
 *
 * Entity refs are the binding targets of the spec: `link:cart`, `joint:shoulder`, `frame:tool`,
 * `visual:motor_body`, plus `model:robot`. Names of a nested model are prefixed with its path
 * (`arm.link1`); the name of a lone top-level model is not part of its members' refs. A visual
 * ref is the bare visual name when that is unique in the scene, else `<link>.<visual>`.
 */

import type { Diagnostic } from "../contracts/diagnostic";
import {
  compose, fromPose, IDENTITY, inverse, jointMotion, multiply, normalize3, transformDirection,
  type Mat4, type Vec3,
} from "./pose";
import { e305, type JointType, type SdfGeometry, type SdfLink, type SdfModel, type SdfPose, type SdfScene, type SdfVisual } from "./sdf";

export type EntityKind = "model" | "link" | "joint" | "frame" | "visual";
export type NodeKind = "model" | "link" | "jointFrame" | "jointMotion" | "frame" | "visual";

/** One TransformNode of the scene graph. Parents come before their children in `ResolvedScene.nodes`. */
export interface KinNode {
  readonly id: string;
  readonly kind: NodeKind;
  /** The entity (`link:x`, `joint:y`, ...) the node belongs to. */
  readonly ref: string;
  /** Id of the parent node; null: directly under `sdf_root`. */
  readonly parent: string | null;
  /** Rest-pose local transform. */
  readonly local: Mat4;
}

export interface ResolvedJoint {
  readonly ref: string;
  readonly name: string;
  readonly type: JointType;
  /** Unit axis in the joint frame. */
  readonly axis: Vec3;
  readonly frameNode: string;
  readonly motionNode: string;
  readonly parentLink: string | null;
  readonly childLink: string;
}

export interface ResolvedVisual {
  readonly ref: string;
  readonly name: string;
  readonly link: string;
  readonly node: string;
  readonly geometry: SdfGeometry;
  readonly diffuse: SdfVisual["diffuse"];
}

/** A row of the scene tree (outliner). */
export interface TreeEntry {
  readonly ref: string;
  readonly kind: EntityKind;
  readonly label: string;
  /** Joints: `revolute`, ...; empty otherwise. */
  readonly detail: string;
  readonly children: readonly TreeEntry[];
}

export interface ResolvedScene {
  readonly file: string;
  readonly nodes: readonly KinNode[];
  readonly joints: readonly ResolvedJoint[];
  readonly visuals: readonly ResolvedVisual[];
  readonly tree: readonly TreeEntry[];
  /** Rest-pose world matrix of every model, link, joint, frame and visual, by ref. */
  readonly world: ReadonlyMap<string, Mat4>;
}

export interface ResolveResult {
  /** Null when the scene cannot be built (E305). */
  readonly scene: ResolvedScene | null;
  readonly diagnostics: readonly Diagnostic[];
}

type Member = { readonly kind: "link" | "joint" | "frame" | "model"; readonly frame: string };

interface ModelInfo {
  readonly model: SdfModel;
  readonly parent: ModelInfo | null;
  /** Path of model names from the top-level model, e.g. `robot.arm`. */
  readonly path: string;
  /** Prefix of member refs: the path without a lone top-level model's name, plus a dot, or "". */
  readonly prefix: string;
  readonly members: Map<string, Member>;
  readonly children: Map<string, ModelInfo>;
}

type FrameDef = { readonly what: string; readonly base: string | null; readonly local: Mat4 };

const WORLD = "world";

function poseMatrix(p: SdfPose): Mat4 {
  return fromPose(p.xyz[0], p.xyz[1], p.xyz[2], p.rpy[0], p.rpy[1], p.rpy[2]);
}

/** Ref of an entity: the kind prefix plus the qualified name. */
export function refOf(kind: EntityKind, name: string): string {
  return `${kind}:${name}`;
}

/** Resolve a parsed scene. */
export function resolveScene(sdf: SdfScene): ResolveResult {
  const diagnostics: Diagnostic[] = [];
  /** `where` is a scene target (`link:a`) or a description such as `link a`; anything else is a problem of the whole file. */
  const fail = (where: string, message: string, hint: string) => {
    const target = /^(joint|link|frame|visual):[A-Za-z0-9_.-]+$/.test(where) ? where : where.replace(/^(joint|link|frame) ([A-Za-z0-9_.-]+)$/, "$1:$2");
    diagnostics.push(e305(/^(joint|link|frame|visual):[A-Za-z0-9_.-]+$/.test(target) ? target : null, `${message} (in ${sdf.file})`, hint));
  };

  // ---- index every model and its members
  const dropTop = sdf.models.length === 1;
  const infos: ModelInfo[] = [];
  const defs = new Map<string, FrameDef>();
  const modelRoots: ModelInfo[] = [];

  const index = (model: SdfModel, parent: ModelInfo | null): ModelInfo => {
    const path = parent === null ? model.name : `${parent.path}.${model.name}`;
    const prefix = dropTop ? (parent === null ? "" : `${path.slice(path.indexOf(".") + 1)}.`) : `${path}.`;
    const info: ModelInfo = { model, parent, path, prefix, members: new Map(), children: new Map() };
    infos.push(info);
    for (const l of model.links) info.members.set(l.name, { kind: "link", frame: `link:${prefix}${l.name}` });
    for (const j of model.joints) info.members.set(j.name, { kind: "joint", frame: `joint:${prefix}${j.name}` });
    for (const f of model.frames) info.members.set(f.name, { kind: "frame", frame: `frame:${prefix}${f.name}` });
    for (const m of model.models) {
      const child = index(m, info);
      info.members.set(m.name, { kind: "model", frame: `model:${child.path}` });
      info.children.set(m.name, child);
    }
    return info;
  };
  for (const m of sdf.models) modelRoots.push(index(m, null));

  const modelFrame = (info: ModelInfo) => `model:${info.path}`;

  /** The frame id `name` denotes inside `info`; `world`, `__model__` and `a::b::name` included. */
  const lookup = (info: ModelInfo | null, name: string): string | null => {
    if (name === WORLD) return WORLD;
    if (info === null) return null;
    if (name === "__model__") return modelFrame(info);
    const sep = name.indexOf("::");
    if (sep < 0) return info.members.get(name)?.frame ?? null;
    const nested = info.children.get(name.slice(0, sep));
    return nested === undefined ? null : lookup(nested, name.slice(sep + 2));
  };

  const memberOf = (info: ModelInfo, name: string): { info: ModelInfo; member: Member | undefined; leaf: string } => {
    const sep = name.indexOf("::");
    if (sep < 0) return { info, member: info.members.get(name), leaf: name };
    const nested = info.children.get(name.slice(0, sep));
    return nested === undefined ? { info, member: undefined, leaf: name } : memberOf(nested, name.slice(sep + 2));
  };

  // ---- frame definitions: (base frame, pose relative to it)
  const base = (info: ModelInfo | null, pose: SdfPose, fallback: string, what: string): string | null => {
    if (pose.relativeTo === null) return fallback;
    const id = lookup(info, pose.relativeTo);
    if (id === null) {
      fail(what, `${what} has pose relative_to "${pose.relativeTo}", which is not a frame of its model`, "name a link, joint, frame or nested model of the same model, or `world`");
    }
    return id;
  };

  for (const info of infos) {
    const prefix = info.prefix;
    const parentScope = info.parent;
    const modelBase = base(parentScope, info.model.pose, parentScope === null ? WORLD : modelFrame(parentScope), `model ${info.path}`);
    defs.set(modelFrame(info), { what: `model ${info.path}`, base: modelBase, local: poseMatrix(info.model.pose) });
    for (const l of info.model.links) {
      const what = `link ${prefix}${l.name}`;
      defs.set(`link:${prefix}${l.name}`, { what, base: base(info, l.pose, modelFrame(info), what), local: poseMatrix(l.pose) });
    }
    for (const f of info.model.frames) {
      const what = `frame ${prefix}${f.name}`;
      let fallback: string | null = modelFrame(info);
      if (f.attachedTo !== null) {
        fallback = lookup(info, f.attachedTo);
        if (fallback === null) fail(what, `${what} is attached_to "${f.attachedTo}", which is not a frame of its model`, "name a link, joint, frame or nested model of the same model, or `world`");
      }
      defs.set(`frame:${prefix}${f.name}`, { what, base: fallback === null ? null : base(info, f.pose, fallback, what), local: poseMatrix(f.pose) });
    }
    for (const j of info.model.joints) {
      const what = `joint ${prefix}${j.name}`;
      const child = lookup(info, j.child);
      defs.set(`joint:${prefix}${j.name}`, { what, base: child === null ? null : base(info, j.pose, child, what), local: poseMatrix(j.pose) });
    }
  }

  // ---- world matrices through the frame graph
  const worlds = new Map<string, Mat4>();
  const visiting = new Set<string>();
  let broken = false;
  const worldOf = (id: string): Mat4 => {
    if (id === WORLD) return IDENTITY;
    const known = worlds.get(id);
    if (known !== undefined) return known;
    const def = defs.get(id);
    if (def === undefined || def.base === null) return IDENTITY;
    if (visiting.has(id)) {
      if (!broken) fail(def.what, `${def.what} depends on itself through relative_to or attached_to`, "break the cycle: express one of the poses relative to the model frame");
      broken = true;
      return IDENTITY;
    }
    visiting.add(id);
    const m = multiply(worldOf(def.base), def.local);
    visiting.delete(id);
    worlds.set(id, m);
    return m;
  };
  for (const id of defs.keys()) worldOf(id);

  // ---- joints: parent and child links, loops
  interface JointInfo { readonly info: ModelInfo; readonly sdfName: string; readonly ref: string; readonly type: JointType; readonly parent: string | null; readonly child: string; readonly axisFrame: string | null; readonly axis: Vec3 }
  const joints: JointInfo[] = [];
  const childOf = new Map<string, JointInfo>();
  for (const info of infos) {
    for (const j of info.model.joints) {
      const ref = `joint:${info.prefix}${j.name}`;
      const where = `joint ${info.prefix}${j.name}`;
      const child = memberOf(info, j.child);
      if (child.member?.kind !== "link") {
        fail(where, `${where} has child "${j.child}", which is not a link of its model`, "name a link of the same model (or `nested_model::link`) as the child");
        continue;
      }
      let parent: string | null = null;
      if (j.parent !== WORLD) {
        const p = memberOf(info, j.parent);
        if (p.member?.kind !== "link") {
          fail(where, `${where} has parent "${j.parent}", which is not a link of its model`, "name a link of the same model (or `nested_model::link`), or `world`, as the parent");
          continue;
        }
        parent = p.member.frame;
      }
      const axisFrame = j.axisFrame === null ? null : lookup(info, j.axisFrame);
      if (j.axisFrame !== null && axisFrame === null) {
        fail(where, `the axis of ${where} is expressed_in "${j.axisFrame}", which is not a frame of its model`, "name a link, joint, frame or nested model of the same model");
        continue;
      }
      const ji: JointInfo = { info, sdfName: j.name, ref, type: j.type, parent, child: child.member.frame, axisFrame, axis: j.axis };
      const clash = childOf.get(ji.child);
      if (clash !== undefined) {
        fail(where, `link ${ji.child.slice(5)} is the child of both ${clash.ref.slice(6)} and ${ji.ref.slice(6)}, which closes a kinematic loop`, "the viewer draws tree-structured mechanisms: remove one of the two joints");
        continue;
      }
      childOf.set(ji.child, ji);
      joints.push(ji);
    }
  }
  for (const j of joints) {
    const seen = new Set<string>([j.child]);
    for (let p = j.parent; p !== null; p = childOf.get(p)?.parent ?? null) {
      if (seen.has(p)) {
        fail(j.ref, `joint ${j.ref.slice(6)} is part of a kinematic loop through link ${p.slice(5)}`, "the viewer draws tree-structured mechanisms: remove one joint of the loop");
        break;
      }
      seen.add(p);
    }
  }

  if (broken || diagnostics.length > 0) return { scene: null, diagnostics };

  // ---- the scene graph
  const nodes: KinNode[] = [];
  const emitted = new Set<string>();
  const pending = new Set<string>();
  const nodeOfFrame = new Map<string, string>(); // frame id -> node id that carries it
  const linkInfo = new Map<string, { info: ModelInfo; link: SdfLink }>();
  const frameInfo = new Map<string, { info: ModelInfo; attached: string | null }>();
  for (const info of infos) {
    for (const l of info.model.links) linkInfo.set(`link:${info.prefix}${l.name}`, { info, link: l });
    for (const f of info.model.frames) {
      frameInfo.set(`frame:${info.prefix}${f.name}`, { info, attached: f.attachedTo === null ? modelFrame(info) : lookup(info, f.attachedTo) });
    }
  }
  const jointOfChild = childOf;
  const jointByRef = new Map(joints.map((j) => [j.ref, j] as const));

  const relative = (parentFrame: string | null, frame: string): Mat4 =>
    parentFrame === null ? worldOf(frame) : multiply(inverse(worldOf(parentFrame)), worldOf(frame));

  const jointFrameId = (j: JointInfo) => `${j.ref}#frame`;
  const jointMotionId = (j: JointInfo) => `${j.ref}#motion`;

  /** Emits the node that carries `frame` (a model, link or frame id) and everything it hangs under. */
  const emit = (frame: string): string => {
    const existing = nodeOfFrame.get(frame);
    if (existing !== undefined) return existing;
    if (pending.has(frame)) {
      fail(frame, `${frame} is attached_to itself through a chain of frames`, "attach the frame to a link or to the model instead");
      return frame;
    }
    pending.add(frame);
    const kind = frame.slice(0, frame.indexOf(":")) as EntityKind;
    let parentNode: string | null = null;
    let local: Mat4;
    if (kind === "model") {
      const info = infos.find((i) => modelFrame(i) === frame);
      const outer = info?.parent ? modelFrame(info.parent) : null;
      if (outer !== null) parentNode = emit(outer);
      local = relative(outer, frame);
    } else if (kind === "link") {
      const li = linkInfo.get(frame);
      const j = jointOfChild.get(frame);
      if (li === undefined) throw new Error(`internal: unknown link ${frame}`);
      if (j !== undefined) {
        emitJoint(j);
        parentNode = jointMotionId(j);
        local = inverse(childJointPose(j));
      } else {
        const outer = modelFrame(li.info);
        parentNode = emit(outer);
        local = relative(outer, frame);
      }
    } else {
      const fi = frameInfo.get(frame);
      if (fi === undefined) throw new Error(`internal: unknown frame ${frame}`);
      let attached = fi.attached ?? modelFrame(fi.info);
      if (attached.startsWith("joint:")) {
        const aj = jointByRef.get(attached);
        if (aj !== undefined) attached = aj.child;
      }
      if (attached === WORLD) {
        local = worldOf(frame);
      } else {
        parentNode = emit(attached);
        local = relative(attached, frame);
      }
    }
    nodes.push({ id: frame, kind: kind === "model" ? "model" : kind === "link" ? "link" : "frame", ref: frame, parent: parentNode, local });
    nodeOfFrame.set(frame, frame);
    pending.delete(frame);
    return frame;
  };

  const childJointPose = (j: JointInfo): Mat4 => multiply(inverse(worldOf(j.child)), worldOf(j.ref));

  const emitJoint = (j: JointInfo): void => {
    if (emitted.has(j.ref)) return;
    emitted.add(j.ref);
    const parentNode = j.parent === null ? null : emit(j.parent);
    nodes.push({ id: jointFrameId(j), kind: "jointFrame", ref: j.ref, parent: parentNode, local: relative(j.parent, j.ref) });
    nodes.push({ id: jointMotionId(j), kind: "jointMotion", ref: j.ref, parent: jointFrameId(j), local: IDENTITY });
  };

  for (const info of infos) emit(modelFrame(info));
  for (const id of linkInfo.keys()) emit(id);
  for (const id of frameInfo.keys()) emit(id);
  for (const j of joints) emitJoint(j);

  // ---- visuals, refs and the outliner tree
  const nameCount = new Map<string, number>();
  for (const { link } of linkInfo.values()) for (const v of link.visuals) nameCount.set(v.name, (nameCount.get(v.name) ?? 0) + 1);
  const visuals: ResolvedVisual[] = [];
  const visualRefs = new Map<string, TreeEntry>();
  for (const [linkId, { info, link }] of linkInfo) {
    for (const v of link.visuals) {
      const ref = `visual:${(nameCount.get(v.name) ?? 0) > 1 ? `${linkId.slice(5)}.${v.name}` : v.name}`;
      const vFrame = v.pose.relativeTo === null ? linkId : lookup(info, v.pose.relativeTo);
      if (vFrame === null) {
        fail(ref, `visual ${ref.slice(7)} has pose relative_to "${v.pose.relativeTo ?? ""}", which is not a frame of its model`, "name a link, joint, frame or nested model of the same model, or `world`");
        continue;
      }
      const world = multiply(worldOf(vFrame), poseMatrix(v.pose));
      worlds.set(ref, world);
      nodes.push({ id: ref, kind: "visual", ref, parent: linkId, local: multiply(inverse(worldOf(linkId)), world) });
      visuals.push({ ref, name: v.name, link: linkId, node: ref, geometry: v.geometry, diffuse: v.diffuse });
      visualRefs.set(ref, { ref, kind: "visual", label: v.name, detail: v.geometry.kind, children: [] });
    }
  }
  if (diagnostics.length > 0) return { scene: null, diagnostics };

  const treeOf = (info: ModelInfo): TreeEntry => {
    const links = info.model.links.map<TreeEntry>((l) => {
      const ref = `link:${info.prefix}${l.name}`;
      return { ref, kind: "link", label: l.name, detail: "", children: visuals.filter((v) => v.link === ref).map((v) => visualRefs.get(v.ref) as TreeEntry) };
    });
    const js = info.model.joints.filter((j) => jointByRef.has(`joint:${info.prefix}${j.name}`)).map<TreeEntry>((j) => ({ ref: `joint:${info.prefix}${j.name}`, kind: "joint", label: j.name, detail: j.type, children: [] }));
    const fs = info.model.frames.map<TreeEntry>((f) => ({ ref: `frame:${info.prefix}${f.name}`, kind: "frame", label: f.name, detail: "", children: [] }));
    const ms = [...info.children.values()].map(treeOf);
    return { ref: modelFrame(info), kind: "model", label: info.model.name, detail: "", children: [...links, ...js, ...fs, ...ms] };
  };

  const world = new Map<string, Mat4>(worlds);
  const resolvedJoints = joints.map<ResolvedJoint>((j) => {
    const axisInJoint = j.axisFrame === null ? j.axis : transformDirection(multiply(inverse(worldOf(j.ref)), worldOf(j.axisFrame)), j.axis);
    return {
      ref: j.ref,
      name: j.ref.slice(6),
      type: j.type,
      axis: normalize3(axisInJoint),
      frameNode: jointFrameId(j),
      motionNode: jointMotionId(j),
      parentLink: j.parent,
      childLink: j.child,
    };
  });

  return { scene: { file: sdf.file, nodes, joints: resolvedJoints, visuals, tree: modelRoots.map(treeOf), world }, diagnostics };
}

/** Rest-pose local transform of a node with joint positions applied (`q` by joint ref; missing = 0). */
function localAt(scene: ResolvedScene, node: KinNode, q: ReadonlyMap<string, number> | Readonly<Record<string, number>>): Mat4 {
  if (node.kind !== "jointMotion") return node.local;
  const joint = scene.joints.find((j) => j.motionNode === node.id);
  if (joint === undefined) return node.local;
  const v = q instanceof Map ? q.get(joint.ref) : (q as Readonly<Record<string, number>>)[joint.ref];
  return jointMotion(joint.type, joint.axis, v ?? 0);
}

/**
 * Forward kinematics: the world matrix (in `sdf_root` coordinates) of every node for the joint
 * positions `q` (rad or m, keyed by joint ref). The Babylon builder reproduces exactly this tree.
 */
export function forwardKinematics(scene: ResolvedScene, q: ReadonlyMap<string, number> | Readonly<Record<string, number>>): Map<string, Mat4> {
  const out = new Map<string, Mat4>();
  for (const node of scene.nodes) {
    const parent = node.parent === null ? IDENTITY : (out.get(node.parent) ?? IDENTITY);
    out.set(node.id, compose(parent, localAt(scene, node, q)));
  }
  return out;
}
