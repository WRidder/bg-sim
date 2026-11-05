/**
 * A car in the scene. All its parts hang from one group laid in the FMU's frame, so a pose from the
 * FMU goes on as it is, and everything else about the car (the world's height, the lean a circuit's
 * drawn swell gives it) is one matrix on that group.
 */

import * as THREE from "three";
import { buildBuggy } from "./buggy";
import type { Pose } from "./ghost";
import { BASE, roadHeight } from "./land";
import { buildRacecar, type CarMesh } from "./racecar";
import { BUGGY_RODS, RACECAR_RODS, type Rod } from "./rods";
import type { Kind } from "./track";
import { CARS, CORNERS, type Vehicle } from "./vehicle";

/** FMU world (x east, y north, z up) to scene (x east, y up, z south). */
export const FMU_TO_SCENE = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2);
const SPIN_AXIS = new THREE.Vector3(0, 0, 1);

const ghostMaterial = new THREE.MeshBasicMaterial({ color: new THREE.Color(0.35, 1.0, 1.6), transparent: true, opacity: 0.16, depthWrite: false });

const m = new THREE.Matrix4();
const tilt = new THREE.Quaternion();
const a = new THREE.Vector3();
const b = new THREE.Vector3();
const c = new THREE.Vector3();
const q = new THREE.Quaternion();
const scale = new THREE.Vector3();
const axis = new THREE.Vector3();
const Y = new THREE.Vector3(0, 1, 0);

export class CarModel {
  readonly root = new THREE.Group();
  readonly mesh: CarMesh;
  readonly body = new THREE.Group();
  private readonly carriers: THREE.Group[] = [];
  private readonly spinning: THREE.Group[] = [];
  private readonly rods: THREE.InstancedMesh | null = null;
  private readonly table: readonly Rod[];
  private readonly heatLevel = { value: 0 };
  /** The matrix from FMU world to scene for this frame. */
  readonly toScene = new THREE.Matrix4();

  constructor(
    readonly kind: Kind,
    readonly ghost = false,
  ) {
    this.mesh = kind === "racecar" ? buildRacecar() : buildBuggy();
    this.table = kind === "racecar" ? RACECAR_RODS : BUGGY_RODS;
    this.root.matrixAutoUpdate = false;
    this.root.add(this.body);
    this.body.add(this.mesh.body);
    for (const [i, parts] of this.mesh.wheels.entries()) {
      const carrier = new THREE.Group();
      const turning = new THREE.Group();
      turning.add(parts.wheel);
      carrier.add(turning, parts.hub);
      this.root.add(carrier);
      this.carriers[i] = carrier;
      this.spinning[i] = turning;
    }
    if (ghost) {
      this.root.traverse((part) => {
        const mesh = part as THREE.Mesh;
        if (mesh.isMesh) {
          mesh.material = ghostMaterial;
          mesh.castShadow = false;
          mesh.receiveShadow = false;
        }
      });
      this.root.visible = false;
      return;
    }
    const rod = new THREE.CylinderGeometry(1, 1, 1, 8, 1);
    rod.translate(0, 0.5, 0);
    this.rods = new THREE.InstancedMesh(rod, new THREE.MeshStandardMaterial({ roughness: 0.42, metalness: 0.75 }), this.table.length);
    const shades = [new THREE.Color(0x1a1c1e), new THREE.Color(0x8d9196), new THREE.Color(0xe0531f)];
    this.table.forEach((row, i) => (this.rods as THREE.InstancedMesh).setColorAt(i, shades[row[8]]));
    this.rods.frustumCulled = false;
    this.rods.castShadow = true;
    this.root.add(this.rods);
  }

  /** Sets the group's matrix so a car at (x, y) stands on the drawn ground and leans with it. */
  private place(x: number, y: number): void {
    const kind = this.kind;
    const height = roadHeight(kind, x, y);
    const groundZ = kind === "buggy" ? height - BASE : 0;
    this.toScene.makeRotationFromQuaternion(FMU_TO_SCENE);
    m.identity();
    if (kind === "racecar") {
      // The FMU's ground is flat, so the swell the circuit is drawn on leans the whole car.
      const e = 4;
      const nx = roadHeight(kind, x - e, y) - roadHeight(kind, x + e, y);
      const nz = roadHeight(kind, x, y + e) - roadHeight(kind, x, y - e);
      axis.set(nx, 2 * e, nz).normalize();
      tilt.setFromUnitVectors(Y, axis);
      m.makeRotationFromQuaternion(tilt);
    }
    a.set(x, 0, -y);
    b.copy(a).applyMatrix4(m);
    m.setPosition(a.x - b.x, height - groundZ - b.y, a.z - b.z);
    this.toScene.premultiply(m);
    this.root.matrix.copy(this.toScene);
    this.root.matrixWorldNeedsUpdate = true;
  }

  private pose(car: Vehicle, prefix: string, target: THREE.Object3D): void {
    const names = car as unknown as { between(name: string): number };
    target.position.set(names.between(`${prefix}_px`), names.between(`${prefix}_py`), names.between(`${prefix}_pz`));
    target.quaternion.set(names.between(`${prefix}_qx`), names.between(`${prefix}_qy`), names.between(`${prefix}_qz`), names.between(`${prefix}_qw`)).normalize();
  }

  /** Puts everything where the FMU says, between its last two steps. */
  update(car: Vehicle, dt: number): void {
    this.place(car.between("chassis_px"), car.between("chassis_py"));
    this.pose(car, "chassis", this.body);
    CORNERS.forEach((corner, i) => {
      this.pose(car, corner, this.carriers[i]);
      this.spinning[i].quaternion.setFromAxisAngle(SPIN_AXIS, car.between(`${corner}_spin`));
    });
    this.body.updateMatrix();
    this.carriers.forEach((carrier) => carrier.updateMatrix());
    const rods = this.rods as THREE.InstancedMesh;
    this.table.forEach((row, i) => {
      a.set(row[1], row[2], row[3]).applyMatrix4(this.body.matrix);
      b.set(row[4], row[5], row[6]).applyMatrix4(this.carriers[row[0]].matrix);
      c.subVectors(b, a);
      const length = c.length();
      q.setFromUnitVectors(Y, c.divideScalar(length));
      scale.set(row[7], length, row[7]);
      m.compose(a, q, scale);
      rods.setMatrixAt(i, m);
    });
    rods.instanceMatrix.needsUpdate = true;
    const pedal = car.u[2];
    this.mesh.brake.value += (pedal > 0.05 ? 1 : -this.mesh.brake.value) * Math.min(1, dt * 18) * (pedal > 0.05 ? 1 - this.mesh.brake.value : 1);
    // The discs heat with the energy going through them, and cool in the air.
    const power = pedal * Math.max(car.get("speed"), 0) * 0.05;
    this.heatLevel.value = Math.max(0, this.heatLevel.value + (power - this.heatLevel.value * 0.55) * dt);
    this.mesh.heat.value = THREE.MathUtils.smoothstep(this.heatLevel.value, 0.55, 2);
  }

  /** A ghost: the chassis as it was recorded, the wheels where they sit at rest. */
  updateGhost(pose: Pose): void {
    this.place(pose.x, pose.y);
    this.body.position.set(pose.x, pose.y, pose.z);
    this.body.quaternion.set(pose.qx, pose.qy, pose.qz, pose.w).normalize();
    this.body.updateMatrix();
    const data = CARS[this.kind];
    for (let i = 0; i < 4; i += 1) {
      const along = i < 2 ? data.front : data.rear;
      const across = i % 2 === 0 ? data.track / 2 : -data.track / 2;
      const carrier = this.carriers[i];
      carrier.position.set(along, across, data.wheelRadius - data.rideHeight).applyMatrix4(this.body.matrix);
      // A carrier's frame is x forward, y down, z left: a quarter turn from the chassis.
      carrier.quaternion.copy(this.body.quaternion).multiply(q.setFromAxisAngle(a.set(1, 0, 0), Math.PI / 2));
      if (i < 2) {
        carrier.quaternion.multiply(tilt.setFromAxisAngle(a.set(0, 1, 0), pose.steer * data.lock));
      }
    }
  }
}
