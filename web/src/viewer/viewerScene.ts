import type { AbstractEngine } from "@babylonjs/core/Engines/abstractEngine";
import { Scene } from "@babylonjs/core/scene";
import { ArcRotateCamera } from "@babylonjs/core/Cameras/arcRotateCamera";
import { Camera } from "@babylonjs/core/Cameras/camera";
import { DirectionalLight } from "@babylonjs/core/Lights/directionalLight";
import { Color3, Color4 } from "@babylonjs/core/Maths/math.color";
import { Matrix, Vector3 } from "@babylonjs/core/Maths/math.vector";
import type { Node } from "@babylonjs/core/node";
import { TransformNode } from "@babylonjs/core/Meshes/transformNode";
import type { AbstractMesh } from "@babylonjs/core/Meshes/abstractMesh";
import { CreateLines, CreateLineSystem } from "@babylonjs/core/Meshes/Builders/linesBuilder";
import type { LinesMesh } from "@babylonjs/core/Meshes/linesMesh";
import type { Material } from "@babylonjs/core/Materials/material";
import { RegisterMaterialPlugin } from "@babylonjs/core/Materials/materialPluginManager";
import "@babylonjs/core/Materials/standardMaterial";
import "@babylonjs/core/Materials/PBR/pbrMaterial";
import "@babylonjs/core/Culling/ray";
import "@babylonjs/core/Rendering/outlineRenderer";
import type { ArcRotateCameraPointersInput } from "@babylonjs/core/Cameras/Inputs/arcRotateCameraPointersInput";
import { CreateSphere } from "@babylonjs/core/Meshes/Builders/sphereBuilder";
import type { Mesh } from "@babylonjs/core/Meshes/mesh";
import { StandardMaterial } from "@babylonjs/core/Materials/standardMaterial";
import { clipPlanes, GROUND_MAX_RADII, MIN_ZOOM_DISTANCE_M, orthoZoomEye, pivotRig, rayPlane, zoomEye, zoomFactor, zoomScale, type Pivoted } from "./orbitPivot";
import { nearestTarget, PICK_RADIUS_PX, type ScreenTarget } from "./picking";
import { ToonPlugin } from "./toon";

/** Name of the Z-up root node: SDF content (W5.2) is parented under it. */
export const SDF_ROOT_NAME = "sdf_root";

/** Model-frame (Z-up) direction the camera looks *from*, for each preset. */
export const CAMERA_PRESETS = {
  iso: [1, -1, 0.8],
  top: [0, 0, 1],
  front: [1, 0, 0],
  side: [0, -1, 0],
} as const;
export type CameraPreset = keyof typeof CAMERA_PRESETS;

/** Three-point rig in camera space (right, up, forward the light travels), with intensity. */
const LIGHT_RIG: readonly { readonly name: string; readonly dir: readonly [number, number, number]; readonly intensity: number }[] = [
  { name: "key", dir: [0.6, -0.8, 1], intensity: 1.0 },
  { name: "fill", dir: [-0.9, -0.15, 1], intensity: 0.5 },
  { name: "rim", dir: [-0.2, -0.6, -1], intensity: 0.8 },
];

/** Selection outline thickness, in metres. */
const SELECTION_OUTLINE_M = 0.004;
/** The ground grid reaches this far from the origin (m), one line per metre. */
const GRID_HALF_M = 5;
const AXIS_LENGTH_M = 1;
/** What `fit()` frames while nothing but the grid and axes is in the scene: a 4 m sphere resting on the ground. */
const EMPTY_SCENE_CENTRE: readonly [number, number, number] = [0, 0, 0.5];
const EMPTY_SCENE_RADIUS_M = 2;
const FIT_MARGIN = 1.05;
/** Babylon pans about this many world units per dragged pixel times 1/panningSensibility (measured on 9.28,
 *  independent of zoom and frame rate). `updatePanning` divides it out so the grabbed point follows the cursor. */
const PAN_WORLD_PER_PX = 5.3;
/** The orbit radius (distance to the pivot along the view axis) never drops below this, m: below the closest zoom. */
const MIN_ORBIT_RADIUS_M = 1e-4;
/** The orbit pivot dot is this many CSS pixels across (its halo 2.4 times that), at any distance. */
const PIVOT_DOT_PX = 8;

const ENTITY_KEY = "bgsimEntity";
const HELPER_KEY = "bgsimHelper";

/** Marks a node (and everything under it) as the pickable entity `ref`. */
export function tagEntity(node: Node, ref: string): void {
  node.metadata = { ...(node.metadata as Record<string, unknown> | null), [ENTITY_KEY]: ref };
}

/** The entity a node belongs to: the nearest tagged node on its parent chain. */
export function entityOfMesh(mesh: Node): string | null {
  for (let node: Node | null = mesh; node; node = node.parent) {
    const ref = (node.metadata as Record<string, unknown> | null)?.[ENTITY_KEY];
    if (typeof ref === "string") return ref;
  }
  return null;
}

function isHelper(mesh: AbstractMesh): boolean {
  return (mesh.metadata as Record<string, unknown> | null)?.[HELPER_KEY] === true;
}

export interface ViewerColours {
  readonly grid: Color3;
  readonly axisX: Color3;
  readonly axisY: Color3;
  readonly axisZ: Color3;
  readonly selection: Color3;
}

const DEFAULT_COLOURS: ViewerColours = {
  grid: new Color3(0.5, 0.55, 0.62),
  axisX: new Color3(0.95, 0.43, 0.39),
  axisY: new Color3(0.31, 0.71, 0.47),
  axisZ: new Color3(0.3, 0.55, 0.94),
  selection: new Color3(0.56, 0.71, 0.97),
};

const TOON_PLUGIN = "McfToon";

/** Standard and PBR materials get the toon ramp; others (lines, shaders) do not. */
function toonFor(material: Material): ToonPlugin | null {
  const kind = material.getClassName();
  return kind === "StandardMaterial" || kind === "PBRMaterial" ? new ToonPlugin(material) : null;
}

/**
 * Every Standard and PBR material created from now on, in any scene, gets the toon plugin.
 * Babylon forgets global plugins when the last engine is disposed, so each scene registers again.
 */
function registerToon(): void {
  RegisterMaterialPlugin(TOON_PLUGIN, toonFor);
}

/**
 * The 3D scene behind the viewer: right-handed, transparent clear colour, an orbit camera, the
 * camera-space light rig, the Z-up `sdf_root`, a ground grid with axes, toon shading on every
 * material, fit and view presets, and picking. It is also the handle the SDF loader (W5.2)
 * builds on: parent content under `root`, call `invalidate()` after changing it.
 */
export class ViewerScene {
  readonly scene: Scene;
  readonly camera: ArcRotateCamera;
  /** SDF is Z-up and right-handed; Babylon is Y-up. Parent all model content to this node. */
  readonly root: TransformNode;
  /** Outline width of a selected entity, in metres. */
  outlineWidth = SELECTION_OUTLINE_M;
  private readonly lights: DirectionalLight[] = [];
  private readonly grid: LinesMesh;
  private readonly axes: readonly LinesMesh[];
  private colours: ViewerColours = DEFAULT_COLOURS;
  private selected: ReadonlySet<string> = new Set();
  /** The orbit pivot dot and its halo, made on first use. */
  private pivot: { readonly core: Mesh; readonly halo: Mesh } | null = null;
  /** Half the orthographic view height (m), and the orbit radius it was last matched to. */
  private orthoHalf = 1;
  private orthoRadius = 0;

  /** `onInvalidate` asks for a redraw (the render scheduler's `invalidate`). */
  constructor(
    engine: AbstractEngine,
    private readonly onInvalidate: () => void = () => undefined,
  ) {
    this.scene = new Scene(engine);
    this.scene.useRightHandedSystem = true;
    this.scene.clearColor = new Color4(0, 0, 0, 0);
    this.scene.skipPointerMovePicking = true;
    this.camera = new ArcRotateCamera("camera", Math.PI / 4, Math.PI / 3, 3, Vector3.Zero(), this.scene);
    // minZ and maxZ follow the view every frame (`updateClipPlanes`)
    this.camera.minZ = 0.01;
    this.camera.lowerRadiusLimit = MIN_ORBIT_RADIUS_M;
    // The wheel is ours (`zoomAt`: a fraction of the distance per notch, toward the point under the cursor), not
    // the orbit camera's percentage dolly toward the target, which crawls on large scenes and never reaches what
    // the cursor is on.
    this.camera.inputs.removeByType("ArcRotateCameraMouseWheelInput");
    // A pinch scales the distance to the pivot by the change in finger spread, at any scale.
    const pointers = this.camera.inputs.attached["pointers"] as ArcRotateCameraPointersInput | undefined;
    if (pointers) pointers.useNaturalPinchZoom = true;
    this.updatePanning();
    this.scene.onBeforeCameraRenderObservable.add(() => {
      this.updateOrthoBounds();
      this.updatePanning();
      this.updateClipPlanes();
      this.sizePivot();
    });
    for (const l of LIGHT_RIG) {
      const light = new DirectionalLight(l.name, new Vector3(0, 0, -1), this.scene);
      light.intensity = l.intensity;
      this.lights.push(light);
    }
    this.camera.onViewMatrixChangedObservable.add(() => {
      this.followCamera();
    });
    this.followCamera();

    this.root = new TransformNode(SDF_ROOT_NAME, this.scene);
    this.root.rotation.x = -Math.PI / 2;
    this.root.computeWorldMatrix(true);

    this.grid = this.buildGrid();
    this.axes = this.buildAxes();
    this.paintHelpers();

    registerToon();

    this.fit("iso");
  }

  /** Asks for a redraw; call it after changing anything in the scene. */
  invalidate(): void {
    this.onInvalidate();
  }

  /** Left drag orbits, the right button (or Ctrl+left) pans; the wheel is the host's (`zoomAt`). */
  attachControl(): void {
    this.camera.attachControl(false, true, 2);
  }

  detachControl(): void {
    this.camera.detachControl();
  }

  setColours(colours: ViewerColours): void {
    this.colours = colours;
    this.paintHelpers();
    this.paintPivot();
    this.highlight([...this.selected]);
  }

  private buildGrid(): LinesMesh {
    const lines: Vector3[][] = [];
    for (let i = -GRID_HALF_M; i <= GRID_HALF_M; i += 1) {
      lines.push([new Vector3(i, -GRID_HALF_M, 0), new Vector3(i, GRID_HALF_M, 0)]);
      lines.push([new Vector3(-GRID_HALF_M, i, 0), new Vector3(GRID_HALF_M, i, 0)]);
    }
    return this.helper(CreateLineSystem("grid", { lines }, this.scene));
  }

  private buildAxes(): LinesMesh[] {
    return [new Vector3(1, 0, 0), new Vector3(0, 1, 0), new Vector3(0, 0, 1)].map((axis, i) =>
      this.helper(CreateLines(`axis-${"xyz"[i] ?? i}`, { points: [Vector3.Zero(), axis.scale(AXIS_LENGTH_M)] }, this.scene)),
    );
  }

  private helper(mesh: LinesMesh): LinesMesh {
    mesh.parent = this.root;
    mesh.isPickable = false;
    mesh.metadata = { [HELPER_KEY]: true };
    return mesh;
  }

  private paintHelpers(): void {
    this.grid.color = this.colours.grid;
    const [x, y, z] = this.axes;
    if (x) x.color = this.colours.axisX;
    if (y) y.color = this.colours.axisY;
    if (z) z.color = this.colours.axisZ;
  }

  /** Keeps the three-point rig fixed relative to the camera, so any viewpoint is lit alike. */
  private followCamera(): void {
    const inv = this.camera.getViewMatrix().clone().invert();
    const right = Vector3.TransformNormal(new Vector3(1, 0, 0), inv).normalize();
    const up = Vector3.TransformNormal(new Vector3(0, 1, 0), inv).normalize();
    const forward = this.camera.target.subtract(this.camera.position).normalize();
    LIGHT_RIG.forEach((l, i) => {
      const light = this.lights[i];
      if (light) light.direction = right.scale(l.dir[0]).add(up.scale(l.dir[1])).add(forward.scale(l.dir[2])).normalize();
    });
  }

  /** A model-frame (Z-up) direction as a scene (Y-up) direction. */
  toSceneDirection(d: readonly [number, number, number]): Vector3 {
    this.root.computeWorldMatrix(true);
    return Vector3.TransformNormal(new Vector3(d[0], d[1], d[2]), this.root.getWorldMatrix()).normalize();
  }

  /** The centre and radius of everything the model shows (the grid and axes do not count). */
  private contentBounds(): { centre: Vector3; radius: number } {
    const shown = (m: AbstractMesh) => !isHelper(m) && m.isEnabled() && m.isVisible && m.getTotalVertices() > 0;
    if (this.scene.meshes.some(shown)) {
      const { min, max } = this.scene.getWorldExtends(shown);
      return { centre: Vector3.Center(min, max), radius: Vector3.Distance(min, max) / 2 || 1 };
    }
    const c = EMPTY_SCENE_CENTRE;
    this.root.computeWorldMatrix(true);
    return { centre: Vector3.TransformCoordinates(new Vector3(c[0], c[1], c[2]), this.root.getWorldMatrix()), radius: EMPTY_SCENE_RADIUS_M };
  }

  /** Frames everything shown, with margin, from a preset direction or the current one. */
  fit(preset?: CameraPreset): void {
    const { centre, radius } = this.contentBounds();
    const dir = preset ? this.toSceneDirection(CAMERA_PRESETS[preset]) : this.camera.position.subtract(this.camera.target).normalize();
    const distance = (radius / Math.sin(this.camera.fov / 2)) * FIT_MARGIN;
    // the zoom-out limit first: placing the camera clamps the radius to the limit of the previous fit
    this.camera.upperRadiusLimit = distance * 4;
    this.camera.targetScreenOffset.set(0, 0);
    this.camera.setTarget(centre);
    this.camera.setPosition(centre.add(dir.scale(distance)));
    this.hidePivot();
    this.syncOrtho();
    this.updateOrthoBounds();
    this.invalidate();
  }

  /** Orthographic (parallel) or perspective projection. The orthographic frustum is the perspective one's cross-section at the target. */
  setOrthographic(on: boolean): void {
    this.camera.mode = on ? Camera.ORTHOGRAPHIC_CAMERA : Camera.PERSPECTIVE_CAMERA;
    if (on) this.syncOrtho();
    this.updateOrthoBounds();
    this.invalidate();
  }

  get orthographic(): boolean {
    return this.camera.mode === Camera.ORTHOGRAPHIC_CAMERA;
  }

  /** The orthographic view becomes the perspective cross-section at the target. */
  private syncOrtho(): void {
    this.orthoHalf = this.camera.radius * Math.tan(this.camera.fov / 2);
    this.orthoRadius = this.camera.radius;
  }

  /**
   * The orthographic frustum: `orthoHalf`, scaled with any change of the orbit radius the camera's own inputs make
   * (a pinch). A pivot changes the radius without changing the view, so `applyPivot` resets `orthoRadius`.
   */
  private updateOrthoBounds(): void {
    if (this.camera.mode !== Camera.ORTHOGRAPHIC_CAMERA) return;
    const r = this.camera.radius;
    if (this.orthoRadius > 0 && r !== this.orthoRadius) this.orthoHalf *= r / this.orthoRadius;
    this.orthoRadius = r;
    const half = this.orthoHalf;
    const aspect = this.scene.getEngine().getAspectRatio(this.camera) || 1;
    this.camera.orthoTop = half;
    this.camera.orthoBottom = -half;
    this.camera.orthoLeft = -half * aspect;
    this.camera.orthoRight = half * aspect;
  }

  /**
   * Pan speed follows the zoom: one dragged pixel moves the view by one pixel's worth of the scene at the
   * target, so a zoomed-out or large scene pans as fast as a close-up. The visible height at the target is the
   * same in both projections (the orthographic frustum is the perspective cross-section there).
   */
  private updatePanning(): void {
    const engine = this.scene.getEngine();
    const heightPx = engine.getRenderingCanvas()?.clientHeight || engine.getRenderHeight(true) || 1;
    const visible = this.orthographic ? 2 * this.orthoHalf : 2 * this.camera.radius * Math.tan(this.camera.fov / 2);
    this.camera.panningSensibility = (PAN_WORLD_PER_PX * heightPx) / Math.max(visible, 1e-6);
  }

  /** Where the camera really looks from (the orbit position less the screen offset), in scene coordinates. */
  eye(): Vector3 {
    return this.camera.getViewMatrix().clone().invert().getTranslation();
  }

  /** The unit view direction. */
  private forward(): Vector3 {
    return this.camera.target.subtract(this.camera.position).normalize();
  }

  /**
   * Near and far clip planes from the view: the near plane follows the orbit radius and stays in front of the
   * nearest object the camera is outside of, the far plane takes in every object (bounding spheres, as of the
   * last frame). A close-up does not clip and a km-scale scene keeps its depth precision.
   */
  private updateClipPlanes(): void {
    const eye = this.eye();
    let farthest = 0;
    let gap: number | null = null;
    for (const m of this.scene.meshes) {
      if (!m.isEnabled() || !m.isVisible || m.getTotalVertices() === 0 || m === this.pivot?.core || m === this.pivot?.halo) continue;
      // this frame's pose (a binding may just have moved it); the render reuses it
      m.computeWorldMatrix();
      const s = m.getBoundingInfo().boundingSphere;
      const d = Vector3.Distance(eye, s.centerWorld);
      if (!Number.isFinite(d)) continue;
      farthest = Math.max(farthest, d + s.radiusWorld);
      if (d > s.radiusWorld) gap = Math.min(gap ?? Infinity, d - s.radiusWorld);
    }
    const { near, far } = clipPlanes(this.camera.radius, gap, farthest);
    this.camera.minZ = near;
    this.camera.maxZ = far;
  }

  /** Visible geometry a zoom or orbit can aim at (not the grid, the axes or the pivot dot). */
  private readonly aimable = (m: AbstractMesh): boolean => m.isPickable && m.isEnabled() && m.isVisible && !isHelper(m);

  /** The scene point of the geometry under the canvas point (CSS px), else null. */
  surfaceAt(x: number, y: number): Vector3 | null {
    const ray = this.scene.createPickingRay(x, y, Matrix.Identity(), this.camera);
    const hit = this.scene.pickWithRay(ray, this.aimable);
    return hit?.hit && hit.pickedPoint ? hit.pickedPoint.clone() : null;
  }

  /**
   * The point a wheel zoom at the canvas point heads for: the geometry under it, else the ground (z = 0 of the
   * model) when it is not far beyond the pivot (not toward the horizon), else the plane through the orbit target
   * facing the camera.
   */
  zoomPointAt(x: number, y: number): Vector3 | null {
    const ray = this.scene.createPickingRay(x, y, Matrix.Identity(), this.camera);
    const hit = this.scene.pickWithRay(ray, this.aimable);
    if (hit?.hit && hit.pickedPoint) return hit.pickedPoint.clone();
    const dir = ray.direction.normalize();
    this.root.computeWorldMatrix(true);
    const origin = Vector3.TransformCoordinates(Vector3.Zero(), this.root.getWorldMatrix());
    const ground = rayPlane(ray.origin, dir, origin, this.toSceneDirection([0, 0, 1]));
    if (ground && Vector3.Distance(this.eye(), ground) <= GROUND_MAX_RADII * this.camera.radius) return ground;
    return rayPlane(ray.origin, dir, this.camera.target, this.forward());
  }

  private radiusAllowed(r: number): boolean {
    const c = this.camera;
    return Number.isFinite(r) && r >= (c.lowerRadiusLimit ?? 0) && r <= (c.upperRadiusLimit ?? Infinity);
  }

  /** Puts the orbit target at the pivot, the view unchanged (see `orbitPivot.ts`). */
  private applyPivot(p: Pivoted): void {
    const c = this.camera;
    c.targetScreenOffset.set(p.offset[0], p.offset[1]);
    c.setTarget(p.target, false, true);
    c.setPosition(p.position);
    c.rebuildAnglesAndRadius();
    this.orthoRadius = c.radius;
    this.updateOrthoBounds();
  }

  /**
   * Wheel zoom at the canvas point (CSS px): `notches` > 0 zooms in. The camera moves along the ray through the
   * point toward the scene point under it (`zoomPointAt`), a fixed fraction of the distance per notch, and that
   * point becomes the orbit pivot; the point stays under the cursor. In the orthographic projection the view
   * shrinks by the same fraction about the point. Returns false when the view did not change (nothing to aim
   * at, or at the closest or farthest distance).
   */
  zoomAt(x: number, y: number, notches: number): boolean {
    if (notches === 0) return false;
    const point = this.zoomPointAt(x, y);
    if (!point) return false;
    const eye = this.eye();
    const forward = this.forward();
    const max = this.camera.upperRadiusLimit ?? Infinity;
    let next: Vector3 | null;
    let half: number | null = null;
    if (this.orthographic) {
      const tan = Math.tan(this.camera.fov / 2);
      half = zoomScale(this.orthoHalf, zoomFactor(notches), MIN_ZOOM_DISTANCE_M * tan, max * tan);
      next = half === null ? null : orthoZoomEye(eye, forward, point, half / this.orthoHalf);
    } else {
      next = zoomEye(eye, point, zoomFactor(notches), MIN_ZOOM_DISTANCE_M, max);
    }
    if (!next) return false;
    const p = pivotRig(next, forward, point, this.camera.getViewMatrix());
    if (!this.radiusAllowed(p.radius)) return false;
    if (half !== null) this.orthoHalf = half;
    this.applyPivot(p);
    if (this.pivot?.core.isEnabled()) this.pivot.core.position.copyFrom(point);
    this.invalidate();
    return true;
  }

  /**
   * A press to orbit or pan: the geometry point under the canvas point becomes the orbit pivot, and the view
   * does not move (the camera keeps its place and orientation; the point's offset from the view axis becomes
   * the camera's screen offset). Returns the pivot, or null when nothing is under the point (the pivot stays).
   */
  pivotAt(x: number, y: number): Vector3 | null {
    const point = this.surfaceAt(x, y);
    if (!point) return null;
    const p = pivotRig(this.eye(), this.forward(), point, this.camera.getViewMatrix());
    if (!this.radiusAllowed(p.radius)) return null;
    this.applyPivot(p);
    return point;
  }

  /** Marks the orbit pivot with a dot in the selection colour, drawn over the scene, a few pixels across at any distance. */
  showPivot(point: Vector3): void {
    if (!this.pivot) {
      const make = (name: string, diameter: number) => {
        const m = CreateSphere(name, { diameter, segments: 12 }, this.scene);
        const mat = new StandardMaterial(`${name}:material`, this.scene);
        mat.disableLighting = true;
        m.material = mat;
        m.isPickable = false;
        m.renderingGroupId = 1;
        m.metadata = { [HELPER_KEY]: true };
        return m;
      };
      const core = make("orbit-pivot", 1);
      const halo = make("orbit-pivot-halo", 2.4);
      halo.parent = core;
      this.pivot = { core, halo };
      this.paintPivot();
    }
    this.setPivotAlpha(1);
    this.pivot.core.position.copyFrom(point);
    this.pivot.core.setEnabled(true);
    this.sizePivot();
    this.invalidate();
  }

  hidePivot(): void {
    if (!this.pivot?.core.isEnabled()) return;
    this.pivot.core.setEnabled(false);
    this.invalidate();
  }

  /** The pivot dot's strength, 1 = full (the fade-out sets it per frame). */
  setPivotAlpha(alpha: number): void {
    const p = this.pivot;
    if (!p) return;
    (p.core.material as StandardMaterial).alpha = alpha;
    (p.halo.material as StandardMaterial).alpha = 0.35 * alpha;
    this.invalidate();
  }

  /** The pivot dot's centre, null while hidden. */
  pivotPoint(): Vector3 | null {
    return this.pivot?.core.isEnabled() ? this.pivot.core.position.clone() : null;
  }

  private paintPivot(): void {
    if (!this.pivot) return;
    for (const m of [this.pivot.core, this.pivot.halo]) (m.material as StandardMaterial).emissiveColor = this.colours.selection;
  }

  private sizePivot(): void {
    const p = this.pivot;
    if (!p?.core.isEnabled()) return;
    // the height the view shows at the dot's depth, over the canvas height: metres per pixel there
    const visible = this.orthographic ? 2 * this.orthoHalf : 2 * Vector3.Distance(this.eye(), p.core.position) * Math.tan(this.camera.fov / 2);
    const engine = this.scene.getEngine();
    const heightPx = engine.getRenderingCanvas()?.clientHeight || engine.getRenderHeight(true) || 1;
    p.core.scaling.setAll(Math.max((visible / heightPx) * PIVOT_DOT_PX, 1e-6));
  }

  /**
   * The camera for e2e tests: effective eye and orbit target (scene frame, Y up), orbit radius, whether the pivot
   * dot shows, the view matrix (Babylon order, row vectors) and the vertical field of view.
   */
  cameraState(): {
    readonly eye: readonly number[];
    readonly target: readonly number[];
    readonly radius: number;
    readonly pivot: boolean;
    readonly view: readonly number[];
    readonly fov: number;
  } {
    const e = this.eye();
    const t = this.camera.target;
    return {
      eye: [e.x, e.y, e.z],
      target: [t.x, t.y, t.z],
      radius: this.camera.radius,
      pivot: this.pivotPoint() !== null,
      view: Array.from(this.camera.getViewMatrix().m),
      fov: this.camera.fov,
    };
  }

  /** The ray pick under the finger (canvas CSS px), else the nearest entity centre within the touch radius. */
  pickEntity(x: number, y: number, radiusPx: number = PICK_RADIUS_PX): string | null {
    const scene = this.scene;
    const pickable = (m: AbstractMesh) => m.isPickable && m.isEnabled() && m.isVisible && entityOfMesh(m) !== null;
    const hit = scene.pick(x, y, pickable);
    const direct = hit.hit && hit.pickedMesh ? entityOfMesh(hit.pickedMesh) : null;
    if (direct) return direct;
    const engine = scene.getEngine();
    const scale = engine.getHardwareScalingLevel();
    const viewport = this.camera.viewport.toGlobal(engine.getRenderWidth(), engine.getRenderHeight());
    const transform = scene.getTransformMatrix();
    const forward = this.camera.getForwardRay().direction;
    const targets: ScreenTarget[] = [];
    const seen = new Set<string>();
    for (const m of scene.meshes) {
      if (!pickable(m)) continue;
      const ref = entityOfMesh(m);
      if (!ref || seen.has(ref)) continue;
      seen.add(ref);
      const c = m.getBoundingInfo().boundingSphere.centerWorld;
      const p = Vector3.Project(c, Matrix.Identity(), transform, viewport);
      targets.push({ ref, x: p.x * scale, y: p.y * scale, depth: Vector3.Dot(c.subtract(this.camera.position), forward) });
    }
    return nearestTarget(targets, x, y, radiusPx);
  }

  /** Outlines every mesh of the selected entities; an empty list or null clears the selection. */
  highlight(refs: readonly string[] | string | null): void {
    const wanted = new Set(refs === null ? [] : typeof refs === "string" ? [refs] : refs);
    this.selected = wanted;
    for (const m of this.scene.meshes) {
      const e = entityOfMesh(m);
      const on = e !== null && wanted.has(e) && m.getClassName() === "Mesh";
      if (on || m.renderOutline) m.renderOutline = on;
      if (!on) continue;
      m.outlineColor = this.colours.selection;
      m.outlineWidth = this.outlineWidth;
    }
    this.invalidate();
  }

  /** Refs currently outlined. */
  get selection(): ReadonlySet<string> {
    return this.selected;
  }

  /** True while camera inertia still moves the view (another frame would differ). */
  get cameraMoving(): boolean {
    const c = this.camera;
    return (
      c.inertialAlphaOffset !== 0 ||
      c.inertialBetaOffset !== 0 ||
      c.inertialRadiusOffset !== 0 ||
      c.inertialPanningX !== 0 ||
      c.inertialPanningY !== 0
    );
  }

  dispose(): void {
    this.scene.dispose();
  }
}
