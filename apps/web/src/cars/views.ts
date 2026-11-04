/**
 * Where the eye is. The engine's rig is made for things that fly; a car needs the horizon level and
 * the camera low, swinging out round a corner and tucking in under braking. The chase view follows
 * the direction of travel more than the nose, so a slide shows as a slide.
 */

import * as THREE from "three";
import type { CarModel } from "./model";
import type { Vehicle } from "./vehicle";

export type View = "chase" | "cockpit" | "nose" | "tv";
export const VIEWS: readonly View[] = ["chase", "cockpit", "nose", "tv"];

/** A camera's mount in the chassis frame: looks along x, with z up. */
const LOOK_FORWARD = new THREE.Quaternion().setFromRotationMatrix(
  new THREE.Matrix4().makeBasis(new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, 0, 1), new THREE.Vector3(-1, 0, 0)),
);

const wrap = (a: number): number => Math.atan2(Math.sin(a), Math.cos(a));

const target = new THREE.Vector3();
const eye = new THREE.Vector3();
const quaternion = new THREE.Quaternion();
const scale = new THREE.Vector3();
const world = new THREE.Matrix4();

export interface Spot {
  position: THREE.Vector3;
}

export class Views {
  view: View = "chase";
  /** Dragging looks round the car; letting go brings the view back. */
  azimuth = 0;
  elevation = 0;
  dragging = false;
  distance = 1;
  spots: Spot[] = [];
  private yaw = 0;
  private lag = 0;
  private lift = 0;
  private fresh = true;
  private spot: Spot | null = null;
  private shake = 0;

  constructor(
    private readonly camera: THREE.PerspectiveCamera,
    private readonly groundAt: (x: number, z: number) => number,
  ) {}

  snap(): void {
    this.fresh = true;
    this.spot = null;
  }

  kick(amount: number): void {
    this.shake = Math.max(this.shake, amount);
  }

  update(dt: number, car: Vehicle, model: CarModel, rumble: number, time: number): void {
    const { camera } = this;
    const speed = car.get("speed");
    // In the FMU's frame, so the swell's lean does not swing the view.
    const u = car.between("u");
    const v = car.between("v");
    const heading = car.between("yaw");
    const travel = heading + (u > 2.5 ? Math.atan2(v, u) * 0.55 : 0);
    const reversing = u < -1;
    const wanted = reversing ? travel + Math.PI : travel;
    if (this.fresh) {
      this.yaw = wanted;
      this.lag = 0;
      this.lift = 0;
    }
    this.yaw += wrap(wanted - this.yaw) * (1 - Math.exp(-dt / (this.fresh ? 1e-3 : 0.14)));
    this.yaw = wrap(this.yaw);
    target.set(0, 0, 0).applyMatrix4(model.body.matrix).applyMatrix4(model.toScene);

    this.shake *= Math.exp(-dt * 3.6);
    const tremor = this.shake + rumble;
    if (this.view === "chase") {
      if (!this.dragging) {
        const back = Math.exp(-dt / 0.5);
        this.azimuth *= back;
        this.elevation *= back;
      }
      const racecar = model.kind === "racecar";
      const pace = THREE.MathUtils.smoothstep(speed, 8, racecar ? 80 : 40);
      // Pulled back by acceleration, pushed in by the brakes.
      const surge = THREE.MathUtils.clamp(car.get("ax_g"), -2, 1.2);
      this.lag += (surge * 0.55 - this.lag) * (1 - Math.exp(-dt / 0.35));
      const back = (racecar ? 5.9 : 6.6) * this.distance + pace * 1.6 + this.lag;
      const high = (racecar ? 1.75 : 2.5) * this.distance + pace * 0.25;
      this.lift += (high - this.lift) * (this.fresh ? 1 : 1 - Math.exp(-dt / 0.2));
      const angle = this.yaw + this.azimuth;
      const dx = Math.cos(angle);
      const dz = -Math.sin(angle);
      const up = this.lift + this.elevation * 4;
      eye.set(target.x - dx * back, target.y + up, target.z - dz * back);
      const floor = this.groundAt(eye.x, eye.z) + 0.55;
      if (eye.y < floor) {
        eye.y = floor;
      }
      camera.position.copy(eye);
      camera.up.set(0, 1, 0);
      const ahead = 4 + pace * 10;
      camera.lookAt(target.x + dx * ahead, target.y + 0.55 + pace * 0.1, target.z + dz * ahead);
      camera.near = 0.3;
      camera.fov += (62 + 16 * pace - camera.fov) * Math.min(1, dt * 3);
    } else if (this.view === "cockpit" || this.view === "nose") {
      const mount = this.view === "cockpit" ? model.mesh.eye : model.kind === "racecar" ? NOSE : BUMPER;
      world.multiplyMatrices(model.toScene, model.body.matrix);
      eye.copy(mount).applyMatrix4(world);
      world.decompose(target, quaternion, scale);
      camera.position.copy(eye);
      camera.quaternion.copy(quaternion).multiply(LOOK_FORWARD);
      camera.near = 0.06;
      camera.fov += ((this.view === "cockpit" ? 74 : 70) - camera.fov) * Math.min(1, dt * 6);
    } else {
      // The nearest camera ahead of the car, panning and zooming to hold it in frame.
      if (!this.spot || this.spot.position.distanceTo(target) > 210) {
        let best = Infinity;
        for (const spot of this.spots) {
          const distance = spot.position.distanceTo(target);
          const toward = (spot.position.x - target.x) * Math.cos(heading) - (spot.position.z - target.z) * Math.sin(heading);
          if (toward > 0 && distance < best) {
            best = distance;
            this.spot = spot;
          }
        }
      }
      if (this.spot) {
        camera.position.copy(this.spot.position);
      }
      camera.up.set(0, 1, 0);
      camera.lookAt(target.x, target.y + 0.4, target.z);
      camera.near = 0.5;
      const distance = camera.position.distanceTo(target);
      camera.fov = THREE.MathUtils.clamp(THREE.MathUtils.radToDeg(2 * Math.atan(6.5 / Math.max(distance, 1))), 4.5, 58);
    }
    this.fresh = false;
    if (tremor > 0.001) {
      const size = this.view === "chase" ? 0.09 : this.view === "tv" ? 0.012 : 0.03;
      camera.position.x += Math.sin(time * 61) * tremor * size;
      camera.position.y += Math.sin(time * 77 + 1) * tremor * size;
      camera.position.z += Math.sin(time * 53 + 2) * tremor * size;
    }
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
  }
}

/** Low on the nose of the race car, and on the buggy's front bar. */
const NOSE = new THREE.Vector3(2.15, 0, -0.03);
const BUMPER = new THREE.Vector3(2.35, 0, -0.1);
