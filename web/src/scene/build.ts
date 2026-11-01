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
import { Mesh } from "@babylonjs/core/Meshes/mesh";
import { VertexData } from "@babylonjs/core/Meshes/mesh.vertexData";
import { VertexBuffer } from "@babylonjs/core/Buffers/buffer";
import { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import type { MorphTargetManager } from "@babylonjs/core/Morph/morphTargetManager";
import "@babylonjs/loaders/glTF/2.0/glTFLoader";
import type { Diagnostic } from "../contracts/diagnostic";
import type { BeamMapping, SegmentBrokenStyle, ShapeAxis, StrainColor } from "../contracts/model";
import type { ModalSet } from "../viewer/beamModes";
import { colormapColor } from "../viewer/bindingsColormaps";
import { tagEntity, type ViewerScene } from "../viewer/viewerScene";
import { beamFrame, buildBeamMesh, deformBeamMesh, ringStrains, type BeamFrame, type BeamMesh } from "./beamMesh";
import {
  compose, fromPose7, IDENTITY, inverse, jointMotion, positionOf, quaternionOf, rotationX,
  type Mat4, type Pose7, type Vec3,
} from "./pose";
import type { KinNode, ResolvedJoint, ResolvedScene, ResolvedVisual } from "./resolve";
import { e305, type SdfGeometry } from "./sdf";
import { segmentAxis, segmentPlacement, snappedPlacements } from "./segment";

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
  /** Id of the visual's own kinematic node (its pose in the link). */
  readonly id: string;
  readonly node: TransformNode;
  readonly link: string;
  readonly materials: Material[];
  readonly geometry: SdfGeometry;
  /** The plain primitive mesh (box, cylinder, sphere); null for a GLB. Hidden while a beam mesh stands in. */
  readonly primitive: Mesh | null;
  /** The morph target managers of a GLB's meshes (one target per mode shape); empty for the rest. */
  readonly morphs: readonly MorphTargetManager[];
  /** Modal coordinates a mode-shapes binding set last (gain applied, not exaggerated); empty at rest. */
  modes: readonly number[];
  shown: boolean;
  /** A segment binding drew the bar broken and hidden. */
  segmentHidden: boolean;
  /** A segment binding drew the bar snapped: the twin shows the second stub. */
  segmentSnapped: boolean;
  /** The second stub of a snapped segment (a clone of the primitive), made on first use. */
  twin: TransformNode | null;
}

/** What a visual with deformation bindings needs (from `beamConfigs`). */
export interface BeamConfig {
  readonly beam: BeamMapping;
  /** Torsion is bound: draw longitudinal stripes so a twist shows. */
  readonly stripes: boolean;
  /** Colour by bending strain. */
  readonly strain: StrainColor | null;
}

/** A beam mesh standing in for a visual's primitive. */
interface BeamRec {
  readonly key: string;
  readonly config: BeamConfig;
  readonly frame: BeamFrame;
  readonly data: BeamMesh;
  readonly mesh: Mesh;
  readonly positions: Float32Array;
  readonly normals: Float32Array;
  readonly colors: Float32Array;
  /** Diffuse colours of the materials before strain colouring took them to white. */
  readonly savedDiffuse: (Color3 | null)[];
  sets: readonly ModalSet[];
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
  private readonly beams = new Map<string, BeamRec>();
  private exaggerationFactor = 1;
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
    const primitive = v.geometry.kind === "mesh" ? null : (geometry as Mesh);
    const morphs = v.geometry.kind === "mesh" ? morphManagers(geometry) : [];
    this.visuals.set(v.ref, {
      id: v.node, node, link: v.link, materials, geometry: v.geometry, primitive, morphs, modes: [], shown: true,
      segmentHidden: false, segmentSnapped: false, twin: null,
    });
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

  /** The SDF geometry of a visual, or null when the ref is not a visual of this scene. */
  visualGeometry(ref: string): SdfGeometry | null {
    return this.visuals.get(ref)?.geometry ?? null;
  }

  /**
   * The visuals that deformation bindings drive, with their beam mapping. Each gets a beam mesh (many
   * rings along the beam, stripes when torsion is bound) in place of its primitive; visuals no longer
   * in `configs` get their primitive back. Visuals that are no box or cylinder, or whose mapping does
   * not fit, are left alone (validation reports them, E301). Unchanged configurations keep their mesh.
   */
  configureBeams(configs: ReadonlyMap<string, BeamConfig>): void {
    if (this.disposed) return;
    for (const [ref, rec] of [...this.beams]) {
      const want = configs.get(ref);
      if (want === undefined || beamKey(want) !== rec.key) this.dropBeam(ref, rec);
    }
    for (const [ref, config] of configs) {
      if (this.beams.has(ref)) continue;
      const v = this.visuals.get(ref);
      if (v === undefined || v.primitive === null) continue;
      const frame = beamFrame(v.geometry, config.beam);
      if (typeof frame === "string") continue;
      const data = buildBeamMesh(frame, config.stripes);
      const mesh = new Mesh(`${ref}:beam`, this.viewer.scene);
      const vd = new VertexData();
      vd.positions = data.positions;
      vd.normals = data.normals;
      vd.indices = data.indices;
      vd.colors = data.colors;
      vd.applyToMesh(mesh, true);
      mesh.material = v.primitive.material;
      mesh.parent = v.node;
      v.primitive.setEnabled(false);
      const savedDiffuse = config.strain !== null ? v.materials.map((m) => whiten(m)) : [];
      const rec: BeamRec = {
        key: beamKey(config),
        config,
        frame,
        data,
        mesh,
        positions: new Float32Array(data.positions),
        normals: new Float32Array(data.normals),
        colors: new Float32Array(data.colors),
        savedDiffuse,
        sets: [],
      };
      this.beams.set(ref, rec);
      this.drawBeam(rec);
    }
    this.viewer.invalidate();
  }

  private dropBeam(ref: string, rec: BeamRec): void {
    rec.mesh.dispose(false, false);
    const v = this.visuals.get(ref);
    v?.primitive?.setEnabled(true);
    if (v !== undefined) {
      rec.savedDiffuse.forEach((c, i) => {
        const m = v.materials[i];
        if (m !== undefined && c !== null) setDiffuse(m, c);
      });
    }
    this.beams.delete(ref);
  }

  /** The beam mesh standing in for a visual, for tests and overlays. */
  beamMeshOf(ref: string): Mesh | null {
    return this.beams.get(ref)?.mesh ?? null;
  }

  /**
   * Modal coordinates of a visual configured as a beam (gain applied, not exaggerated): every family
   * at once. False when the visual is not a configured beam.
   */
  setDeformation(ref: string, sets: readonly ModalSet[]): boolean {
    const rec = this.beams.get(ref);
    if (rec === undefined) return false;
    rec.sets = sets;
    this.drawBeam(rec);
    this.viewer.invalidate();
    return true;
  }

  /**
   * Morph targets (mode shapes) of a mesh visual: the fewest over its meshes that have any, 0 when none
   * has; null when the ref is not a loaded mesh visual.
   */
  morphTargetCount(ref: string): number | null {
    const v = this.visuals.get(ref);
    if (v === undefined || v.geometry.kind !== "mesh") return null;
    return v.morphs.length === 0 ? 0 : Math.min(...v.morphs.map((m) => m.numTargets));
  }

  /**
   * Modal coordinates of a mesh visual with morph targets (gain applied, not exaggerated): target k of
   * every mesh of the visual gets the influence eta[k] * exaggeration; targets beyond `eta` get 0, and
   * coordinates beyond the targets are ignored. False when the visual is no mesh or has no morph targets.
   */
  setModeShapes(ref: string, eta: readonly number[]): boolean {
    const v = this.visuals.get(ref);
    if (v === undefined || v.morphs.length === 0) return false;
    v.modes = eta;
    this.drawModes(v);
    this.viewer.invalidate();
    return true;
  }

  private drawModes(v: VisualRec): void {
    const f = this.exaggerationFactor;
    for (const manager of v.morphs) {
      for (let k = 0; k < manager.numTargets; k++) {
        const eta = v.modes[k] ?? 0;
        manager.getTarget(k).influence = Number.isFinite(eta) ? eta * f : 0;
      }
    }
  }

  /** The display factor on every deformation (1: true scale). Strain colours always use the true deformation. */
  setExaggeration(factor: number): void {
    const f = Number.isFinite(factor) && factor > 0 ? factor : 1;
    if (f === this.exaggerationFactor) return;
    this.exaggerationFactor = f;
    for (const rec of this.beams.values()) this.drawBeam(rec);
    for (const v of this.visuals.values()) if (v.modes.length > 0) this.drawModes(v);
    this.viewer.invalidate();
  }

  get exaggeration(): number {
    return this.exaggerationFactor;
  }

  private drawBeam(rec: BeamRec): void {
    deformBeamMesh(rec.data, rec.frame, rec.sets, this.exaggerationFactor, rec.positions, rec.normals);
    rec.mesh.updateVerticesData(VertexBuffer.PositionKind, rec.positions, false, false);
    rec.mesh.updateVerticesData(VertexBuffer.NormalKind, rec.normals, false, false);
    const strain = rec.config.strain;
    if (strain !== null) {
      const eps = ringStrains(rec.data, rec.frame, rec.sets);
      const colours = [...eps].map((e) => colormapColor(strain.colormap, e, strain.range));
      for (let k = 0; k < rec.data.vertexCount; k++) {
        const c = colours[rec.data.ring[k] ?? 0] ?? [1, 1, 1];
        const sh = rec.data.shade[k] ?? 1;
        rec.colors[4 * k] = c[0] * sh;
        rec.colors[4 * k + 1] = c[1] * sh;
        rec.colors[4 * k + 2] = c[2] * sh;
      }
      rec.mesh.updateVerticesData(VertexBuffer.ColorKind, rec.colors, false, false);
    }
    rec.mesh.refreshBoundingInfo();
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

  /**
   * A bar between two world points (SDF world frame, m): the visual is centred between A and B, its `axis`
   * (default per shape) turned onto B - A and stretched to |AB|. `broken` draws a failed bar: `snapped`
   * as two drooping stubs from A and from B (the second is a clone of the primitive), `hidden` not at all.
   * False when the visual is not a box or cylinder that fits the axis, or a point is not finite.
   */
  setSegment(ref: string, a: Vec3, b: Vec3, axis: ShapeAxis | undefined, broken: SegmentBrokenStyle | null): boolean {
    const v = this.visuals.get(ref);
    if (v === undefined || v.primitive === null || [...a, ...b].some((c) => !Number.isFinite(c))) return false;
    const ax = segmentAxis(v.geometry, axis);
    if (typeof ax === "string") return false;
    const toParent = inverse(this.parentWorld(v.id));
    const scaling = (s: number): [number, number, number] => {
      const out: [number, number, number] = [1, 1, 1];
      out[ax.index] = s;
      return out;
    };
    if (broken === "snapped") {
      const [first, second] = snappedPlacements(a, b, ax);
      this.apply(v.id, compose(toParent, first.world));
      v.node.scaling.set(...scaling(first.scale));
      const twin = this.twinOf(ref, v);
      setNodeMatrix(twin, compose(toParent, second.world));
      twin.scaling.set(...scaling(second.scale));
    } else {
      const p = segmentPlacement(a, b, ax);
      this.apply(v.id, compose(toParent, p.world));
      v.node.scaling.set(...scaling(p.scale));
    }
    v.segmentHidden = broken === "hidden";
    v.segmentSnapped = broken === "snapped";
    this.refreshVisibility(v);
    this.viewer.invalidate();
    return true;
  }

  /** The second stub of a snapped segment: a sibling of the visual node holding a clone of its primitive. */
  private twinOf(ref: string, v: VisualRec): TransformNode {
    if (v.twin !== null) return v.twin;
    const twin = new TransformNode(`${ref}:twin`, this.viewer.scene);
    twin.parent = v.node.parent;
    tagEntity(twin, ref);
    twin.rotationQuaternion = new Quaternion();
    v.primitive?.clone(`${ref}:twin-mesh`, twin);
    v.twin = twin;
    return twin;
  }

  /** The second stub of a snapped segment visual, for tests and overlays. */
  segmentTwinOf(ref: string): TransformNode | null {
    return this.visuals.get(ref)?.twin ?? null;
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
    const shown = v.shown && !this.hiddenLinks.has(v.link) && !v.segmentHidden;
    v.node.setEnabled(shown);
    v.twin?.setEnabled(shown && v.segmentSnapped);
  }

  /** Back to the rest pose: joints at zero, link and frame poses as the file wrote them, visuals unscaled, shown and undeformed. */
  reset(): void {
    for (const k of this.resolved.nodes) {
      this.apply(k.id, k.local);
      if (k.kind === "visual") this.nodes.get(k.id)?.scaling.set(1, 1, 1);
    }
    this.hiddenLinks.clear();
    for (const v of this.visuals.values()) {
      v.shown = true;
      v.segmentHidden = false;
      v.segmentSnapped = false;
      this.refreshVisibility(v);
      if (v.morphs.length > 0) {
        v.modes = [];
        this.drawModes(v);
      }
    }
    for (const rec of this.beams.values()) {
      rec.sets = [];
      this.drawBeam(rec);
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
    for (const rec of this.beams.values()) if (!rec.mesh.isDisposed()) rec.mesh.dispose();
    for (const v of this.visuals.values()) if (v.twin !== null && !v.twin.isDisposed()) v.twin.dispose(false, false);
    this.beams.clear();
    this.nodes.clear();
    this.visuals.clear();
    this.viewer.invalidate();
  }
}

/**
 * The morph target managers of a GLB visual's meshes (the glTF loader creates them from `targets`). In
 * texture mode (WebGL2) every target is active and the loader pins one shader for all of them; this
 * makes sure of it. Vertex-attribute mode (no float textures) draws at most
 * `MorphTargetManager.MaxActiveMorphTargetsInVertexAttributeMode` (8) non-zero targets. The morphed
 * vertices are not in the CPU bounds, so the meshes are never frustum-culled by their rest shape.
 */
function morphManagers(root: TransformNode): MorphTargetManager[] {
  const out: MorphTargetManager[] = [];
  for (const mesh of root.getChildMeshes(false)) {
    const m = mesh.morphTargetManager;
    if (m === null || m.numTargets === 0) continue;
    if (m.isUsingTextureForTargets) {
      m.optimizeInfluencers = false;
      m.numMaxInfluencers = m.numTargets;
    }
    mesh.alwaysSelectAsActiveMesh = true;
    if (!out.includes(m)) out.push(m);
  }
  return out;
}

/** Sets a plain node (not in the kinematic maps) to a rigid transform. */
function setNodeMatrix(node: TransformNode, m: Mat4): void {
  const p = positionOf(m);
  const q = quaternionOf(m);
  node.position.set(p[0], p[1], p[2]);
  const r = node.rotationQuaternion ?? (node.rotationQuaternion = new Quaternion());
  r.set(q[1], q[2], q[3], q[0]);
}

function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}

function beamKey(config: BeamConfig): string {
  return JSON.stringify([config.beam.axis, config.beam.y ?? null, config.beam.length ?? null, config.beam.neutral ?? null, config.stripes, config.strain]);
}

function diffuseOf(m: Material): Color3 | null {
  if (m instanceof StandardMaterial) return m.diffuseColor.clone();
  if ("albedoColor" in m) return (m as Material & { albedoColor: Color3 }).albedoColor.clone();
  return null;
}

function setDiffuse(m: Material, c: Color3): void {
  if (m instanceof StandardMaterial) m.diffuseColor = c.clone();
  else if ("albedoColor" in m) (m as Material & { albedoColor: Color3 }).albedoColor = c.clone();
}

/** Strain colours come from the vertex colours, which the diffuse colour multiplies: white keeps them true. */
function whiten(m: Material): Color3 | null {
  const before = diffuseOf(m);
  setDiffuse(m, Color3.White());
  return before;
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
