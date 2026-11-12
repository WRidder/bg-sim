/**
 * The duck, drawn procedurally (decision W5) on the MJCF's body tree: one group per body, placed by
 * forward kinematics every frame, each carrying shapes in its own frame. The MJCF carries no meshes,
 * so the shapes are ours, sized to the distances between the joints. The robot lives in a MuJoCo
 * frame (z up); `root` turns that into three.js's y up.
 */

import * as THREE from "three";
import { BODIES, HEAD, Kinematics, LEFT_ANKLE, RIGHT_ANKLE, SITES, TRUNK } from "./kinematics";
import { MOUTH_CLOSED, MOUTH_INDEX } from "./robot";

const CREAM = new THREE.MeshStandardMaterial({ color: 0xf1ebdc, roughness: 0.55 });
const SHELL = new THREE.MeshStandardMaterial({ color: 0xe4dccb, roughness: 0.6 });
const SERVO = new THREE.MeshStandardMaterial({ color: 0x2f3438, roughness: 0.45, metalness: 0.2 });
const ORANGE = new THREE.MeshStandardMaterial({ color: 0xf29a26, roughness: 0.5 });
const EYE = new THREE.MeshStandardMaterial({ color: 0x0b0d10, roughness: 0.15 });
const GLINT = new THREE.MeshBasicMaterial({ color: 0xffffff });

const UP = new THREE.Vector3(0, 1, 0);

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
  private readonly lowerBeak = new THREE.Group();
  readonly kin = new Kinematics();

  constructor() {
    const robot = new THREE.Group();
    robot.rotation.x = -Math.PI / 2; // MuJoCo z up → three.js y up; x stays forward, y left → −z
    this.root.add(robot);
    robot.add(this.trunk);
    this.bodies.forEach((g) => this.trunk.add(g));
    this.build();
  }

  private child(body: number): THREE.Vector3[] {
    return BODIES.filter((b) => b.parent === body).map((b) => new THREE.Vector3(...b.pos));
  }

  private build(): void {
    const g = this.bodies;
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
    this.lowerBeak.rotation.y = Math.max(0, q[MOUTH_INDEX] - MOUTH_CLOSED);
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
