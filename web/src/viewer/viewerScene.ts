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
    this.camera.minZ = 0.01;
    this.camera.lowerRadiusLimit = 0.05;
    this.camera.wheelDeltaPercentage = 0.02;
    this.camera.pinchDeltaPercentage = 0.004;
    this.camera.panningSensibility = 2000;
    this.scene.onBeforeCameraRenderObservable.add(() => {
      this.updateOrthoBounds();
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

  /** Left drag orbits, the right button pans, the wheel zooms. */
  attachControl(): void {
    this.camera.attachControl(false, true, 2);
  }

  detachControl(): void {
    this.camera.detachControl();
  }

  setColours(colours: ViewerColours): void {
    this.colours = colours;
    this.paintHelpers();
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
    this.camera.targetScreenOffset.set(0, 0);
    this.camera.setTarget(centre);
    this.camera.setPosition(centre.add(dir.scale(distance)));
    this.camera.upperRadiusLimit = distance * 4;
    this.updateOrthoBounds();
    this.invalidate();
  }

  /** Orthographic (parallel) or perspective projection. The orthographic frustum is the perspective one's cross-section at the target. */
  setOrthographic(on: boolean): void {
    this.camera.mode = on ? Camera.ORTHOGRAPHIC_CAMERA : Camera.PERSPECTIVE_CAMERA;
    this.updateOrthoBounds();
    this.invalidate();
  }

  get orthographic(): boolean {
    return this.camera.mode === Camera.ORTHOGRAPHIC_CAMERA;
  }

  private updateOrthoBounds(): void {
    if (this.camera.mode !== Camera.ORTHOGRAPHIC_CAMERA) return;
    const half = this.camera.radius * Math.tan(this.camera.fov / 2);
    const aspect = this.scene.getEngine().getAspectRatio(this.camera) || 1;
    this.camera.orthoTop = half;
    this.camera.orthoBottom = -half;
    this.camera.orthoLeft = -half * aspect;
    this.camera.orthoRight = half * aspect;
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
