/**
 * Builds a resolved SDF scene (`resolve.ts`) as Babylon nodes under `ViewerScene.root`
 * (`sdf_root`, Z-up) and exposes the handle the binding loop (W5.3) drives.
 *
 * Frame convention of `setPose`: a pose is the world pose of the entity's own frame, in the SDF
 * world frame, which is the frame of `sdf_root`: Z up, metres, `(qw, qx, qy, qz, x, y, z)`, the
 * same chart as the model's spatial `Vec{7}`. It replaces the rest pose of the link or frame;
 * the scene's joint chain and visuals below it follow. (Babylon's own Y-up world is only the
 * display; nothing here is expressed in it.)
 */

import { LoadAssetContainerAsync } from "@babylonjs/core/Loading/sceneLoader";
import type { AssetContainer } from "@babylonjs/core/assetContainer";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import { Quaternion } from "@babylonjs/core/Maths/math.vector";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import type { Material } from "@babylonjs/core/Materials/material";
import { CreateBox } from "@babylonjs/core/Meshes/Builders/boxBuilder";
import { CreateCylinder } from "@babylonjs/core/Meshes/Builders/cylinderBuilder";
import { CreateSphere } from "@babylonjs/core/Meshes/Builders/sphereBuilder";
import type { Mesh } from "@babylonjs/core/Meshes/mesh";
import { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import "@babylonjs/loaders/glTF/2.0/glTFLoader";
import type { Diagnostic } from "../contracts/diagnostic";
import { tagEntity, type ViewerScene } from "../viewer/viewerScene";
import {
  compose, fromPose7, IDENTITY, inverse, jointMotion, positionOf, quaternionOf, rotationX,
  type Mat4, type Pose7,
} from "./pose";
import type { KinNode, ResolvedJoint, ResolvedScene, ResolvedVisual } from "./resolve";
import { e305 } from "./sdf";

/** Bytes of the GLB a scene's `<mesh><uri>` names. */
export type MeshSource = (uri: string) => Promise<ArrayBufferView>;

export interface BuildOptions {
  /** Where GLB meshes come from; without it a mesh visual is reported (E305) and skipped. */
  readonly loadMesh?: MeshSource | undefined;
  /** When aborted, whatever finished loading is disposed and the returned scene is already disposed. */
  readonly signal?: AbortSignal | undefined;
}

export interface BuildResult {
  readonly scene: BuiltScene;
  /** E305 for meshes that could not be loaded. */
  readonly diagnostics: readonly Diagnostic[];
}

const DEFAULT_GREY = 0.7;
const SPECULAR = 0.15;
const SPHERE_SEGMENTS = 24;
const CYLINDER_TESSELLATION = 32;
/** SDF cylinder axes are local Z, Babylon's are Y. */
const CYLINDER_TO_Z: Mat4 = rotationX(Math.PI / 2);

interface VisualRec {
  readonly node: TransformNode;
  readonly link: string;
  readonly materials: Material[];
  shown: boolean;
}

/** A scene built into a `ViewerScene`. Setters redraw (`invalidate`) by themselves. */
export class BuiltScene {
  private readonly nodes = new Map<string, TransformNode>();
  private readonly kin = new Map<string, KinNode>();
  /** Local transform each node has now (the mirror of what Babylon holds, in `sdf_root` coordinates chain). */
  private readonly locals = new Map<string, Mat4>();
  private readonly joints = new Map<string, ResolvedJoint>();
  private readonly visuals = new Map<string, VisualRec>();
  private readonly hiddenLinks = new Set<string>();
  private readonly materials: Material[] = [];
  private readonly containers: AssetContainer[] = [];
  private disposed = false;

  constructor(
    private readonly viewer: ViewerScene,
    readonly resolved: ResolvedScene,
  ) {
    for (const k of resolved.nodes) this.addNode(k);
    for (const j of resolved.joints) this.joints.set(j.ref, j);
  }

  private addNode(k: KinNode): void {
    const node = new TransformNode(k.id, this.viewer.scene);
    node.parent = k.parent === null ? this.viewer.root : (this.nodes.get(k.parent) ?? this.viewer.root);
    tagEntity(node, k.ref);
    this.nodes.set(k.id, node);
    this.kin.set(k.id, k);
    this.apply(k.id, k.local);
  }

  private apply(id: string, m: Mat4): void {
    const node = this.nodes.get(id);
    if (node === undefined) return;
    this.locals.set(id, m);
    const p = positionOf(m);
    const q = quaternionOf(m);
    node.position.set(p[0], p[1], p[2]);
    const r = node.rotationQuaternion ?? (node.rotationQuaternion = new Quaternion());
    r.set(q[1], q[2], q[3], q[0]);
  }

  /** @internal Attaches a visual built by `buildScene`. */
  attachVisual(v: ResolvedVisual, geometry: TransformNode, materials: Material[]): void {
    const node = this.nodes.get(v.node);
    if (node === undefined) return;
    geometry.parent = node;
    this.materials.push(...materials);
    this.visuals.set(v.ref, { node, link: v.link, materials, shown: true });
  }

  /** @internal */
  keepContainer(c: AssetContainer): void {
    this.containers.push(c);
  }

  get isDisposed(): boolean {
    return this.disposed;
  }

  /** Refs of everything a binding can target. */
  has(ref: string): boolean {
    return this.joints.has(ref) || this.visuals.has(ref) || (this.nodes.has(ref) && /^(link|frame|model):/.test(ref));
  }

  /** The joint, or null when the ref is not a joint of this scene. */
  joint(ref: string): ResolvedJoint | null {
    return this.joints.get(ref) ?? null;
  }

  /** The node that carries an entity (`link:`, `frame:`, `model:` or `visual:`), for tests and overlays. */
  nodeOf(ref: string): TransformNode | null {
    return this.nodes.get(ref) ?? this.visuals.get(ref)?.node ?? null;
  }

  /** Visual refs that belong to an entity: itself, a link's visuals, a model's, or a joint's moving link. */
  visualsOf(ref: string): string[] {
    if (this.visuals.has(ref)) return [ref];
    const j = this.joints.get(ref);
    if (j) return this.visualsOf(j.childLink);
    const out: string[] = [];
    if (ref.startsWith("link:")) {
      for (const v of this.resolved.visuals) if (v.link === ref) out.push(v.ref);
    } else if (ref.startsWith("model:")) {
      for (const k of this.resolved.nodes) {
        if (k.kind === "link" && this.isUnder(k.id, ref)) out.push(...this.visualsOf(k.id));
      }
    }
    return out;
  }

  private isUnder(id: string, ancestor: string): boolean {
    for (let n: string | null = id; n !== null; n = this.kin.get(n)?.parent ?? null) {
      if (n === ancestor) return true;
    }
    return false;
  }

  /** Joint position: radians (revolute, continuous) or metres (prismatic). False for an unknown or fixed joint. */
  setJointPosition(ref: string, q: number): boolean {
    const j = this.joints.get(ref);
    if (j === undefined || j.type === "fixed" || !Number.isFinite(q)) return false;
    this.apply(j.motionNode, jointMotion(j.type, j.axis, q));
    this.viewer.invalidate();
    return true;
  }

  /**
   * World pose `(qw, qx, qy, qz, x, y, z)` of a link or frame, in the SDF world frame (see the file
   * comment). The pose is applied to the node of the entity, so its joint children and visuals follow.
   */
  setPose(ref: string, pose: Pose7): boolean {
    if (!/^(link|frame):/.test(ref) || !this.nodes.has(ref) || pose.some((v) => !Number.isFinite(v))) return false;
    this.apply(ref, compose(inverse(this.parentWorld(ref)), fromPose7(pose)));
    this.viewer.invalidate();
    return true;
  }

  /** Scale of a visual along its own axes. */
  setVisualScale(ref: string, sx: number, sy: number, sz: number): boolean {
    const v = this.visuals.get(ref);
    if (v === undefined || [sx, sy, sz].some((s) => !Number.isFinite(s))) return false;
    v.node.scaling.set(sx, sy, sz);
    this.viewer.invalidate();
    return true;
  }

  /** Diffuse (albedo) colour of a visual, r, g, b in 0..1. */
  setVisualColor(ref: string, r: number, g: number, b: number): boolean {
    const v = this.visuals.get(ref);
    if (v === undefined || [r, g, b].some((c) => !Number.isFinite(c))) return false;
    const colour = new Color3(clamp01(r), clamp01(g), clamp01(b));
    for (const m of v.materials) {
      if (m instanceof StandardMaterial) m.diffuseColor = colour;
      else if ("albedoColor" in m) (m as Material & { albedoColor: Color3 }).albedoColor = colour;
    }
    this.viewer.invalidate();
    return true;
  }

  /** Shows or hides a visual, or all the visuals of a link (the links below it stay). */
  setVisible(ref: string, visible: boolean): boolean {
    const v = this.visuals.get(ref);
    if (v !== undefined) {
      v.shown = visible;
      this.refreshVisibility(v);
    } else if (ref.startsWith("link:") && this.nodes.has(ref)) {
      if (visible) this.hiddenLinks.delete(ref);
      else this.hiddenLinks.add(ref);
      for (const rec of this.visuals.values()) if (rec.link === ref) this.refreshVisibility(rec);
    } else {
      return false;
    }
    this.viewer.invalidate();
    return true;
  }

  private refreshVisibility(v: VisualRec): void {
    v.node.setEnabled(v.shown && !this.hiddenLinks.has(v.link));
  }

  /** Back to the rest pose: joints at zero, link and frame poses as the file wrote them, visuals unscaled and shown. */
  reset(): void {
    for (const k of this.resolved.nodes) {
      this.apply(k.id, k.local);
      if (k.kind === "visual") this.nodes.get(k.id)?.scaling.set(1, 1, 1);
    }
    this.hiddenLinks.clear();
    for (const v of this.visuals.values()) {
      v.shown = true;
      this.refreshVisibility(v);
    }
    this.viewer.invalidate();
  }

  /** World matrix (in `sdf_root` coordinates) of a node as it stands now. */
  worldOf(id: string): Mat4 {
    const k = this.kin.get(id);
    if (k === undefined) return IDENTITY;
    return compose(k.parent === null ? IDENTITY : this.worldOf(k.parent), this.locals.get(id) ?? IDENTITY);
  }

  private parentWorld(id: string): Mat4 {
    const parent = this.kin.get(id)?.parent ?? null;
    return parent === null ? IDENTITY : this.worldOf(parent);
  }

  /** Removes every node, mesh and material this scene created. */
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    for (const c of this.containers) c.dispose();
    for (const k of this.resolved.nodes) {
      const node = k.parent === null ? this.nodes.get(k.id) : undefined;
      if (node && !node.isDisposed()) node.dispose(false, true);
    }
    for (const m of this.materials) m.dispose();
    this.nodes.clear();
    this.visuals.clear();
    this.viewer.invalidate();
  }
}

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}

function primitive(viewer: ViewerScene, v: ResolvedVisual): { mesh: Mesh; materials: Material[] } | null {
  const scene = viewer.scene;
  const g = v.geometry;
  let mesh: Mesh;
  switch (g.kind) {
    case "box":
      mesh = CreateBox(v.ref, { width: g.size[0], height: g.size[1], depth: g.size[2] }, scene);
      break;
    case "sphere":
      mesh = CreateSphere(v.ref, { diameter: 2 * g.radius, segments: SPHERE_SEGMENTS }, scene);
      break;
    case "cylinder": {
      mesh = CreateCylinder(v.ref, { height: g.length, diameter: 2 * g.radius, tessellation: CYLINDER_TESSELLATION }, scene);
      const q = quaternionOf(CYLINDER_TO_Z);
      mesh.rotationQuaternion = new Quaternion(q[1], q[2], q[3], q[0]);
      break;
    }
    case "mesh":
      return null;
  }
  const material = new StandardMaterial(`mat:${v.ref}`, scene);
  const d = v.diffuse ?? [DEFAULT_GREY, DEFAULT_GREY, DEFAULT_GREY, 1];
  material.diffuseColor = new Color3(d[0], d[1], d[2]);
  material.specularColor = new Color3(SPECULAR, SPECULAR, SPECULAR);
  material.alpha = d[3];
  mesh.material = material;
  return { mesh, materials: [material] };
}

async function glbMesh(viewer: ViewerScene, v: ResolvedVisual, bytes: ArrayBufferView): Promise<{ root: TransformNode; container: AssetContainer }> {
  const container = await LoadAssetContainerAsync(bytes, viewer.scene, { pluginExtension: ".glb", name: v.ref });
  container.addAllToScene();
  const root = new TransformNode(`${v.ref}:glb`, viewer.scene);
  // The GLB loader leaves the content in the SDF frame (no handedness flip with a right-handed scene);
  // the converter keeps the coordinates of the source mesh, which SDF reads as Z-up.
  for (const n of [...container.transformNodes, ...container.meshes]) if (n.parent === null) n.parent = root;
  if (v.geometry.kind === "mesh") root.scaling.set(...v.geometry.scale);
  return { root, container };
}

/**
 * Builds `resolved` into `viewer`. Primitive visuals are ready on return; GLB meshes load
 * asynchronously and a mesh that cannot be read is reported (E305) and left out.
 */
export async function buildScene(viewer: ViewerScene, resolved: ResolvedScene, options: BuildOptions = {}): Promise<BuildResult> {
  const built = new BuiltScene(viewer, resolved);
  const diagnostics: Diagnostic[] = [];
  const cache = new Map<string, Promise<ArrayBufferView>>();
  const loadOnce = (uri: string): Promise<ArrayBufferView> => {
    const load = options.loadMesh;
    if (load === undefined) return Promise.reject(new Error("no mesh source is configured"));
    let p = cache.get(uri);
    if (p === undefined) {
      p = load(uri);
      cache.set(uri, p);
    }
    return p;
  };
  const pending: Promise<void>[] = [];
  for (const v of resolved.visuals) {
    const prim = primitive(viewer, v);
    if (prim !== null) {
      built.attachVisual(v, prim.mesh, prim.materials);
      continue;
    }
    pending.push(
      (async () => {
        try {
          const { root, container } = await glbMesh(viewer, v, await loadOnce(v.geometry.kind === "mesh" ? v.geometry.uri : ""));
          if (built.isDisposed || options.signal?.aborted) {
            container.dispose();
            root.dispose();
            return;
          }
          built.keepContainer(container);
          built.attachVisual(v, root, container.materials);
        } catch (e) {
          const why = e instanceof Error ? e.message : String(e);
          const uri = v.geometry.kind === "mesh" ? v.geometry.uri : "";
          diagnostics.push(e305(v.ref, `mesh "${uri}" of ${v.ref} could not be loaded (${why}; in ${resolved.file})`, "upload the mesh to the project's meshes/ folder as a GLB (the upload converts STL, OBJ and DAE) and check the <uri> in the scene"));
        }
      })(),
    );
  }
  await Promise.all(pending);
  if (options.signal?.aborted) built.dispose();
  else if (!built.isDisposed) viewer.invalidate();
  return { scene: built, diagnostics };
}
