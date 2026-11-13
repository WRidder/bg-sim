/**
 * The duck on the MJCF's body tree: one group per body, placed by forward kinematics every frame,
 * each carrying its parts in its own frame. The parts are Pollen Robotics' CAD meshes of the
 * microduck (`duck.glb`, written by examples/microduck/design/build_visuals.py from microduck_rl's
 * MJCF: one node per body in that body's frame, the lower beak in a node `jaw` on the mouth servo's
 * horn axis; CC BY-NC-SA 4.0, see examples/microduck/meshes/NOTICE). Until the GLB has loaded, or
 * if it cannot be loaded, the duck is drawn procedurally (decision W5): shapes of ours, sized to
 * the distances between the joints. The robot lives in a MuJoCo frame (z up); `root` turns that
 * into three.js's y up.
 */

import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import duckGlbUrl from "./duck.glb?url";
import { BODIES, HEAD, Kinematics, LEFT_ANKLE, RIGHT_ANKLE, SITES, TRUNK } from "./kinematics";
import { MOUTH_CLOSED, MOUTH_INDEX } from "./robot";

/**
 * The GLB node of each body of `BODIES`, same order: the body names of microduck_rl's
 * `robot_groundcontact.xml`, the MJCF the bg-sim model and the meshes come from. kinematics.ts
 * follows microduck's `robot_walk.xml`, whose tree is the same (frames within 0.02 mm) but for
 * three names and the right ankle's frame, which is turned half a turn about the ankle axis.
 */
const MESH_NODES = [
  "trunk_base", "yaw2roll", "hip_l", "upper_leg_left", "leg", "ankle_left",
  "neck", "neck_pitch", "yaw_roll_motion", "jaw_soft",
  "bearing_roll", "hip_l_2", "upper_leg_right", "leg_2", "ankle_right",
] as const;
/** A body's mesh frame in the body frame of kinematics.ts (identity where the two MJCFs agree). */
const MESH_FRAME: Partial<Record<number, THREE.Quaternion>> = {
  [RIGHT_ANKLE]: new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI),
};

const CREAM = new THREE.MeshStandardMaterial({ color: 0xf1ebdc, roughness: 0.55 });
const SHELL = new THREE.MeshStandardMaterial({ color: 0xe4dccb, roughness: 0.6 });
const SERVO = new THREE.MeshStandardMaterial({ color: 0x2f3438, roughness: 0.45, metalness: 0.2 });
const ORANGE = new THREE.MeshStandardMaterial({ color: 0xf29a26, roughness: 0.5 });
const EYE = new THREE.MeshStandardMaterial({ color: 0x0b0d10, roughness: 0.15 });
const GLINT = new THREE.MeshBasicMaterial({ color: 0xffffff });

const UP = new THREE.Vector3(0, 1, 0);
const Z_AXIS = new THREE.Vector3(0, 0, 1);

function mesh(geometry: THREE.BufferGeometry, material: THREE.Material): THREE.Mesh {
  const m = new THREE.Mesh(geometry, material);
  m.castShadow = true;
  m.receiveShadow = true;
  return m;
}

function ellipsoid(center: readonly number[], radii: readonly number[], material: THREE.Material): THREE.Mesh {
  const m = mesh(new THREE.SphereGeometry(1, 36, 24), material);
  m.position.set(center[0], center[1], center[2]);
  m.scale.set(radii[0], radii[1], radii[2]);
  return m;
}

function capsule(a: THREE.Vector3, b: THREE.Vector3, radius: number, material: THREE.Material): THREE.Mesh {
  const along = new THREE.Vector3().subVectors(b, a);
  const m = mesh(new THREE.CapsuleGeometry(radius, Math.max(along.length(), 1e-4), 6, 16), material);
  m.position.copy(a).addScaledVector(along, 0.5);
  m.quaternion.setFromUnitVectors(UP, along.normalize());
  return m;
}

/** A servo horn: a short dark drum about the joint's axis (the body's z). */
function hinge(radius: number, width: number): THREE.Mesh {
  const m = mesh(new THREE.CylinderGeometry(radius, radius, width, 20), SERVO);
  m.rotation.x = Math.PI / 2;
  return m;
}

/** A webbed foot in the sole site's frame: x forward, y left, z up; sole at z = 0. */
function webbedFoot(): THREE.Mesh {
  const s = new THREE.Shape();
  s.moveTo(-0.018, 0);
  s.quadraticCurveTo(-0.018, 0.012, -0.004, 0.014);
  s.lineTo(0.036, 0.024);
  s.quadraticCurveTo(0.034, 0.012, 0.04, 0.008);
  s.quadraticCurveTo(0.036, 0, 0.044, 0);
  s.quadraticCurveTo(0.036, 0, 0.04, -0.008);
  s.quadraticCurveTo(0.034, -0.012, 0.036, -0.024);
  s.lineTo(-0.004, -0.014);
  s.quadraticCurveTo(-0.018, -0.012, -0.018, 0);
  const geometry = new THREE.ExtrudeGeometry(s, { depth: 0.004, bevelEnabled: true, bevelThickness: 0.001, bevelSize: 0.001, bevelSegments: 2 });
  geometry.translate(0, 0, 0.001);
  return mesh(geometry, ORANGE);
}

export class DuckModel {
  /** In three.js's world: y up. Its child `robot` is the MuJoCo world. */
  readonly root = new THREE.Group();
  /** The trunk's pose in the MuJoCo world goes here. */
  readonly trunk = new THREE.Group();
  private readonly bodies = BODIES.map(() => new THREE.Group());
  /** The procedural shapes of each body, shown until the meshes have loaded (and if they fail to). */
  private readonly prims = BODIES.map(() => new THREE.Group());
  private readonly lowerBeak = new THREE.Group();
  /** The lower beak of the meshes: its node turns about its own z, the mouth servo's horn axis. */
  private jaw: THREE.Object3D | null = null;
  private readonly jawRest = new THREE.Quaternion();
  private readonly jawTurn = new THREE.Quaternion();
  readonly kin = new Kinematics();
  /** Resolves true once the CAD meshes replace the procedural shapes, false if they could not be loaded. */
  readonly meshes: Promise<boolean>;

  constructor(meshUrl: string | null = duckGlbUrl) {
    const robot = new THREE.Group();
    robot.rotation.x = -Math.PI / 2; // MuJoCo z up → three.js y up; x stays forward, y left → −z
    this.root.add(robot);
    robot.add(this.trunk);
    this.bodies.forEach((g, i) => {
      this.trunk.add(g);
      g.add(this.prims[i]);
    });
    this.build();
    this.meshes = meshUrl === null ? Promise.resolve(false) : this.loadMeshes(meshUrl);
  }

  /** Puts the CAD meshes of `url` on the bodies and drops the procedural shapes; keeps them on failure. */
  private async loadMeshes(url: string): Promise<boolean> {
    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      const gltf = await new GLTFLoader().parseAsync(await response.arrayBuffer(), "");
      const nodes = MESH_NODES.map((name) => gltf.scene.getObjectByName(name));
      const missing = MESH_NODES.filter((_, i) => nodes[i] === undefined);
      if (missing.length > 0) {
        throw new Error(`no node for ${missing.join(", ")}`);
      }
      gltf.scene.traverse((o) => {
        if ((o as THREE.Mesh).isMesh) {
          o.castShadow = true;
          o.receiveShadow = true;
        }
      });
      nodes.forEach((node, i) => {
        const holder = new THREE.Group();
        const fix = MESH_FRAME[i];
        if (fix !== undefined) {
          holder.quaternion.copy(fix);
        }
        holder.add(...node!.children);
        this.prims[i].visible = false;
        this.bodies[i].add(holder);
      });
      this.jaw = gltf.scene.getObjectByName("jaw") ?? null;
      if (this.jaw !== null) {
        this.jawRest.copy(this.jaw.quaternion);
      }
      return true;
    } catch (error) {
      console.warn(`microduck: the CAD meshes did not load, drawing the duck procedurally (${error instanceof Error ? error.message : String(error)})`);
      return false;
    }
  }

  private child(body: number): THREE.Vector3[] {
    return BODIES.filter((b) => b.parent === body).map((b) => new THREE.Vector3(...b.pos));
  }

  private build(): void {
    const g = this.prims;
    const O = new THREE.Vector3();
    // Trunk: a plump body, a tail, folded wings, and the hip block underneath.
    const t = g[TRUNK];
    t.add(ellipsoid([-0.014, 0, 0.012], [0.062, 0.047, 0.042], CREAM));
    const tail = mesh(new THREE.ConeGeometry(0.02, 0.045, 20), CREAM);
    tail.position.set(-0.074, 0, 0.03);
    tail.quaternion.setFromUnitVectors(UP, new THREE.Vector3(-1, 0, 0.7).normalize());
    t.add(tail);
    for (const side of [1, -1]) {
      const wing = ellipsoid([-0.022, side * 0.045, 0.016], [0.042, 0.009, 0.026], SHELL);
      wing.rotation.y = 0.25;
      t.add(wing);
    }
    const hips = mesh(new THREE.BoxGeometry(0.044, 0.064, 0.018), SERVO);
    hips.position.set(0.006, 0, -0.012);
    t.add(hips);

    // Legs: a drum at every joint, a limb to the next joint, a webbed foot on the sole site.
    const legs = [
      [1, 2, 3, 4, 5],
      [10, 11, 12, 13, 14],
    ];
    for (const chain of legs) {
      const [yaw, roll, pitch, knee, ankle] = chain;
      g[yaw].add(hinge(0.011, 0.02));
      g[roll].add(hinge(0.01, 0.02));
      g[pitch].add(hinge(0.012, 0.026));
      g[knee].add(hinge(0.011, 0.024));
      g[ankle].add(hinge(0.01, 0.022));
      g[roll].add(capsule(O, this.child(roll)[0], 0.008, SERVO));
      g[pitch].add(capsule(O, this.child(pitch)[0], 0.012, CREAM));
      g[knee].add(capsule(O, this.child(knee)[0], 0.009, CREAM));
      const site = ankle === LEFT_ANKLE ? SITES.leftFoot : SITES.rightFoot;
      const sole = new THREE.Vector3(...site.pos);
      g[ankle].add(capsule(O, sole.clone().multiplyScalar(0.8), 0.007, ORANGE));
      const foot = new THREE.Group();
      foot.position.copy(sole);
      // The MJCF's sole sites: (0, 0, .707, .707) left, (0, 0, .707, −.707) right, w first.
      const s = Math.SQRT1_2;
      foot.quaternion.set(0, s, ankle === RIGHT_ANKLE ? -s : s, 0);
      foot.add(webbedFoot());
      g[ankle].add(foot);
    }

    // Neck: two links of the same cream, the head on top.
    g[6].add(capsule(O, this.child(6)[0], 0.012, CREAM));
    g[6].add(hinge(0.012, 0.026));
    g[7].add(capsule(O, this.child(7)[0], 0.011, CREAM));
    g[7].add(hinge(0.011, 0.024));
    g[8].add(hinge(0.01, 0.018));

    // Head (bottom_head_shell): x up, −z forward, y left at home.
    const h = g[HEAD];
    h.add(ellipsoid([0.004, 0, -0.035], [0.037, 0.034, 0.043], CREAM));
    for (const side of [1, -1]) {
      h.add(ellipsoid([0.016, side * 0.025, -0.062], [0.0068, 0.0068, 0.0068], EYE));
      const glint = new THREE.Mesh(new THREE.SphereGeometry(0.0018, 8, 6), GLINT);
      glint.position.set(0.019, side * 0.026, -0.0675);
      h.add(glint);
    }
    h.add(ellipsoid([-0.0015, 0, -0.072], [0.0065, 0.016, 0.022], ORANGE));
    this.lowerBeak.position.set(-0.007, 0, -0.058);
    this.lowerBeak.add(ellipsoid([-0.003, 0, -0.014], [0.0045, 0.014, 0.019], ORANGE));
    h.add(this.lowerBeak);
  }

  /** Places every body for joint angles `q` (15) and the trunk pose, MuJoCo world, w x y z. */
  update(q: ArrayLike<number>, position: ArrayLike<number>, quaternion: ArrayLike<number>): void {
    this.kin.update(q);
    this.bodies.forEach((group, i) => {
      group.position.copy(this.kin.position[i]);
      group.quaternion.copy(this.kin.orientation[i]);
    });
    const open = Math.max(0, q[MOUTH_INDEX] - MOUTH_CLOSED);
    this.lowerBeak.rotation.y = open;
    if (this.jaw !== null) {
      // the horn axis is the head's y, as for the procedural beak: a positive turn opens it
      this.jaw.quaternion.copy(this.jawRest).multiply(this.jawTurn.setFromAxisAngle(Z_AXIS, open));
    }
    this.trunk.position.set(position[0], position[1], position[2]);
    this.trunk.quaternion.set(quaternion[1], quaternion[2], quaternion[3], quaternion[0]).normalize();
  }

  /** A sole's position in three.js's world, after `update`. */
  sole(foot: 0 | 1, out: THREE.Vector3): THREE.Vector3 {
    this.kin.site(foot === 0 ? SITES.leftFoot : SITES.rightFoot, out);
    this.root.updateMatrixWorld();
    return out.applyMatrix4(this.trunk.matrixWorld);
  }
}

/** MuJoCo world (x forward, y left, z up) to three.js (x, z up → y, y → −z). */
export const toThree = (x: number, y: number, z: number, out = new THREE.Vector3()): THREE.Vector3 => out.set(x, z, -y);
