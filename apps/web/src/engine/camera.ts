/**
 * The views of something that flies. The chase camera lags the aircraft's attitude and only partly follows its bank, so the
 * horizon stays readable. The bank it keeps out fades away towards the vertical and when inverted,
 * so there is no attitude at which the view has to snap round: a loop flies through smoothly.
 */

import * as THREE from "three";

export type View = "chase" | "cockpit" | "flyby";
export const VIEWS: readonly View[] = ["chase", "cockpit", "flyby"];

const FORWARD = new THREE.Vector3(1, 0, 0);
const WORLD_UP = new THREE.Vector3(0, 1, 0);
/** A camera looks down its own -z with y up; a mesh's forward is x, its up z. */
const MESH_TO_CAMERA = new THREE.Quaternion().setFromRotationMatrix(
  new THREE.Matrix4().makeBasis(new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, 0, 1), new THREE.Vector3(-1, 0, 0)),
);

const f = new THREE.Vector3();
const up = new THREE.Vector3();
const level = new THREE.Vector3();
const target = new THREE.Quaternion();
const roll = new THREE.Quaternion();
const orbit = new THREE.Quaternion();
const euler = new THREE.Euler();
const eye = new THREE.Vector3();

export interface RigOptions {
  /** The pilot's eye, in the mesh frame. */
  eye: THREE.Vector3;
  /** Chase distance and height above the view line, in metres. */
  distance: number;
  height: number;
  /** How much of the bank the chase view keeps out, in radians at 90 degrees. */
  keepLevel?: number;
  /** Chase field of view at rest and at `fastSpeed`, in degrees. */
  fov?: [number, number];
  fastSpeed?: number;
  cockpitFov?: number;
  flybyOffset?: number;
}

export class Rig {
  view: View = "chase";
  distance: number;
  /** Dragging the mouse looks round the aircraft; letting go brings the view back. */
  azimuth = 0;
  elevation = 0;
  dragging = false;
  private readonly smooth = new THREE.Quaternion();
  private readonly flybyAt = new THREE.Vector3();
  private fresh = true;
  private shake = 0;

  constructor(
    readonly camera: THREE.PerspectiveCamera,
    private readonly groundAt: (x: number, z: number) => number,
    private readonly options: RigOptions,
  ) {
    this.distance = options.distance;
  }

  snap(): void {
    this.fresh = true;
  }

  kick(amount: number): void {
    this.shake = Math.max(this.shake, amount);
  }

  update(dt: number, position: THREE.Vector3, attitude: THREE.Quaternion, speed: number, buffet: number, time: number): void {
    const camera = this.camera;
    target.copy(attitude);
    f.copy(FORWARD).applyQuaternion(attitude);
    up.set(0, 0, 1).applyQuaternion(attitude);
    if (this.view === "chase") {
      const vertical = Math.abs(f.dot(WORLD_UP));
      const weight = THREE.MathUtils.smoothstep(1 - vertical, 0.04, 0.45);
      level.copy(WORLD_UP).addScaledVector(f, -f.dot(WORLD_UP)).normalize();
      const bank = Math.atan2(level.clone().cross(up).dot(f), level.dot(up));
      // Sine, not the angle: it is zero both level and inverted, and continuous through both.
      roll.setFromAxisAngle(FORWARD, -(this.options.keepLevel ?? 0.62) * Math.sin(bank) * weight);
      target.multiply(roll);
    }
    target.multiply(MESH_TO_CAMERA);

    if (this.fresh) {
      this.smooth.copy(target);
      this.fresh = false;
      this.flybyAt.set(0, -1e9, 0);
    }
    this.shake *= Math.exp(-dt * 3.2);
    const rumble = this.shake + buffet;
    if (this.view === "cockpit") {
      this.smooth.copy(target);
      camera.position.copy(position).add(eye.copy(this.options.eye).applyQuaternion(attitude));
      camera.quaternion.copy(this.smooth);
      camera.near = 0.25;
      camera.fov += ((this.options.cockpitFov ?? 72) - camera.fov) * Math.min(1, dt * 6);
    } else if (this.view === "chase") {
      this.smooth.slerp(target, 1 - Math.exp(-dt / 0.2));
      if (!this.dragging) {
        const back = Math.exp(-dt / 0.5);
        this.azimuth *= back;
        this.elevation *= back;
      }
      euler.set(this.elevation, this.azimuth, 0, "YXZ");
      orbit.setFromEuler(euler);
      camera.quaternion.copy(this.smooth).multiply(orbit);
      camera.position.copy(position).add(eye.set(0, this.options.height, this.distance).applyQuaternion(camera.quaternion));
      camera.near = 1;
      const [rest, fast] = this.options.fov ?? [62, 76];
      const wide = rest + (fast - rest) * THREE.MathUtils.smoothstep(speed, (this.options.fastSpeed ?? 420) * 0.36, this.options.fastSpeed ?? 420);
      camera.fov += (wide - camera.fov) * Math.min(1, dt * 2);
    } else {
      // Stand beside the path ahead and watch it go by.
      const ahead = this.flybyAt.distanceTo(position);
      if (ahead > 900) {
        this.flybyAt
          .copy(position)
          .addScaledVector(f, Math.max(speed, 60) * 4.5)
          .addScaledVector(up, 14)
          .add(eye.set(0, 0, 1).applyQuaternion(attitude).cross(f).multiplyScalar(this.options.flybyOffset ?? 45));
      }
      camera.position.copy(this.flybyAt);
      camera.up.copy(WORLD_UP);
      camera.lookAt(position);
      camera.near = 1;
      camera.fov += (34 - camera.fov) * Math.min(1, dt * 4);
    }
    const ground = this.groundAt(camera.position.x, camera.position.z) + 3;
    if (this.view !== "cockpit" && camera.position.y < ground) {
      camera.position.y = ground;
    }
    if (rumble > 0.001) {
      const scale = this.view === "cockpit" ? 0.04 : 0.28;
      camera.position.x += Math.sin(time * 61) * rumble * scale;
      camera.position.y += Math.sin(time * 47 + 1) * rumble * scale;
      camera.position.z += Math.sin(time * 73 + 2) * rumble * scale;
    }
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
  }
}
