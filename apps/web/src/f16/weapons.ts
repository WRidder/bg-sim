/**
 * The AIM-9X and target-drone meshes for the browser game. They are procedural (the web games
 * carry no assets): a lofted-enough round with four moving canards and a plume, and a small red
 * delta-wing drone. The flight model and the fuze are in `missiles.ts`; this file only draws.
 */

import * as THREE from "three";
import type { Drone } from "./targets";
import type { Missile } from "./missiles";
import { attitude } from "../engine/frames";
import { Trail } from "../engine/effects";

const DEG = Math.PI / 180;
const UP = new THREE.Vector3(0, 1, 0);
const X = new THREE.Vector3(1, 0, 0);
const Z = new THREE.Vector3(0, 0, 1);

const BODY = new THREE.MeshStandardMaterial({ color: 0x9aa0a8, metalness: 0.18, roughness: 0.55 });
const DARK = new THREE.MeshStandardMaterial({ color: 0x20242a, metalness: 0.15, roughness: 0.7 });
const OLIVE = new THREE.MeshStandardMaterial({ color: 0x8b7a32, metalness: 0.05, roughness: 0.75 });
const RED = new THREE.MeshStandardMaterial({ color: 0x9e2d22, metalness: 0.05, roughness: 0.6 });
const RED_DARK = new THREE.MeshStandardMaterial({ color: 0x5e1712, metalness: 0.05, roughness: 0.75 });

function cylinder(radius: number, length: number, material: THREE.Material, x: number, segments = 20): THREE.Mesh {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, length, segments), material);
  mesh.rotation.z = Math.PI / 2;
  mesh.position.x = x;
  mesh.castShadow = true;
  return mesh;
}

function fin(radial: number, span: number, chord: number, thickness: number, material: THREE.Material): THREE.Mesh {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(chord, thickness, span), material);
  mesh.position.z = radial + span / 2;
  mesh.castShadow = true;
  return mesh;
}

export interface MissileMesh {
  root: THREE.Group;
  fins: THREE.Group[];
  plume: THREE.Mesh;
  glow: THREE.Points;
}

/** One round in the body frame (x forward, y left, z up, origin at the CG). */
export function buildMissile(): MissileMesh {
  const root = new THREE.Group();
  root.add(cylinder(0.0635, 2.15, BODY, -0.05));
  const nose = new THREE.Mesh(new THREE.ConeGeometry(0.0635, 0.38, 20), DARK);
  nose.rotation.z = -Math.PI / 2;
  nose.position.x = 1.27;
  root.add(nose);
  root.add(cylinder(0.064, 0.055, OLIVE, 0.58));
  root.add(cylinder(0.042, 0.08, DARK, -1.45, 16));
  const tail = new THREE.Mesh(new THREE.ConeGeometry(0.0635, 0.22, 20), BODY);
  tail.rotation.z = Math.PI / 2;
  tail.position.x = -1.19;
  root.add(tail);

  const fins: THREE.Group[] = [];
  for (const phi of [45, 135, 225, 315]) {
    const radians = phi * DEG;
    const hinge = new THREE.Group();
    hinge.position.set(1.12, 0.0635 * Math.cos(radians), 0.0635 * Math.sin(radians));
    hinge.quaternion.setFromAxisAngle(X, (phi - 90) * DEG);
    hinge.add(new THREE.Mesh(CANARD_GEOMETRY, DARK));
    const spin = new THREE.Group();
    hinge.add(spin);
    root.add(hinge);
    fins.push(spin);
  }
  for (const phi of [45, 135, 225, 315]) {
    const radians = phi * DEG;
    const hinge = new THREE.Group();
    hinge.position.set(-1.12, 0.0635 * Math.cos(radians), 0.0635 * Math.sin(radians));
    hinge.quaternion.setFromAxisAngle(X, (phi - 90) * DEG);
    hinge.add(fin(0, 0.16, 0.28, 0.006, BODY));
    root.add(hinge);
  }

  const plume = new THREE.Mesh(
    new THREE.ConeGeometry(0.09, 1, 16, 1, true),
    new THREE.MeshBasicMaterial({
      color: 0xff7d1f, transparent: true, opacity: 0.82, depthWrite: false,
      blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    }),
  );
  plume.rotation.z = Math.PI / 2;
  plume.position.x = -2.02;
  plume.visible = false;
  root.add(plume);

  // The motor seen from far off: a point of light a few pixels across whatever the distance,
  // bright enough to bloom. A burning rocket motor is visible for kilometres; the round is not.
  const glowGeometry = new THREE.BufferGeometry();
  glowGeometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array([-1.6, 0, 0]), 3));
  const glow = new THREE.Points(
    glowGeometry,
    new THREE.PointsMaterial({
      color: new THREE.Color(9, 4.2, 1.2), size: 5, sizeAttenuation: false,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    }),
  );
  glow.frustumCulled = false;
  glow.visible = false;
  root.add(glow);

  return { root, fins, plume, glow };
}

// The canard geometry is shared; each hinge gets its own mesh.
const CANARD_GEOMETRY = new THREE.BoxGeometry(0.15, 0.006, 0.18).translate(0, 0, 0.09);

export interface DroneMesh {
  root: THREE.Group;
}

/** A red target drone: fuselage, delta wing and fin, about 4 m across. */
export function buildDrone(): DroneMesh {
  const root = new THREE.Group();
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.44, 3.2, 14), RED);
  body.rotation.z = Math.PI / 2;
  root.add(body);
  const nose = new THREE.Mesh(new THREE.ConeGeometry(0.32, 0.8, 14), RED_DARK);
  nose.rotation.z = -Math.PI / 2;
  nose.position.x = 2.0;
  root.add(nose);
  const wing = new THREE.Mesh(new THREE.BoxGeometry(1.7, 0.08, 4.2), RED);
  wing.position.x = -0.55;
  root.add(wing);
  const tail = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.07, 1.8), RED_DARK);
  tail.position.x = -1.55;
  root.add(tail);
  const rudder = new THREE.Mesh(new THREE.BoxGeometry(0.9, 1.1, 0.07), RED_DARK);
  rudder.position.set(-1.45, 0.55, 0);
  root.add(rudder);
  const exhaust = new THREE.Mesh(
    new THREE.ConeGeometry(0.26, 0.9, 12, 1, true),
    new THREE.MeshBasicMaterial({ color: 0xff6d20, transparent: true, opacity: 0.7, depthWrite: false, blending: THREE.AdditiveBlending }),
  );
  exhaust.rotation.z = Math.PI / 2;
  exhaust.position.set(-2.2, 0, 0);
  root.add(exhaust);
  root.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      child.castShadow = true;
    }
  });
  return { root };
}

/** The smoke: a point every `TRAIL_STEP` seconds, so it hangs in the air for about ten. */
const TRAIL_POINTS = 240;
const TRAIL_STEP = 0.04;
/** About a pixel and a half on a 1080-line screen. */
const TRAIL_MIN_ANGLE = 0.0014;

export class MissileView {
  readonly mesh = buildMissile();
  private readonly q = new THREE.Quaternion();
  private readonly at = new THREE.Vector3();
  // Lit on one edge, in its own shade on the other: it reads against the sky and against the land.
  private readonly trail = new Trail(
    TRAIL_POINTS, 0.3, new THREE.Color(1.5, 1.5, 1.52), 0.7, TRAIL_MIN_ANGLE, new THREE.Color(0.1, 0.11, 0.13),
  );
  /** Trail points laid since the round was spent. */
  private spent = 0;
  private since = TRAIL_STEP;

  constructor(parent: THREE.Scene) {
    parent.add(this.mesh.root, this.trail.mesh);
    this.hide();
  }

  /**
   * Draws the round, `dt` seconds on; true once it is spent and its smoke has faded, when the
   * view is free again.
   */
  update(missile: Missile, eye: THREE.Vector3, dt: number): boolean {
    if (!missile.active) {
      this.mesh.root.visible = false;
      return false;
    }
    this.mesh.root.visible = !missile.done;
    this.trail.mesh.visible = true;
    if (this.spent > TRAIL_POINTS) {
      return true;
    }
    const at = missile.worldPosition(this.at);
    const burning = missile.thrust > 1 && !missile.done;
    this.since += dt;
    if (this.since >= TRAIL_STEP) {
      this.since = 0;
      // Thick smoke while the motor burns, a thin wake after it: the round coasts most of the way.
      this.trail.add(at, missile.done ? 0 : burning ? 1 : 0.4);
      this.spent = missile.done ? this.spent + 1 : 0;
    } else if (!missile.done) {
      this.trail.move(at);
    }
    this.mesh.glow.visible = burning;
    this.trail.update(eye);
    this.mesh.root.position.copy(at);
    this.mesh.root.quaternion.copy(missile.worldQuaternion(this.q));
    for (let i = 0; i < 4; i += 1) {
      this.mesh.fins[i].quaternion.setFromAxisAngle(Z, missile.fin(i as 0 | 1 | 2 | 3) * DEG);
    }
    const thrust = Math.max(0, missile.thrust);
    if (thrust > 1 && !missile.done) {
      const length = Math.max(0.08, thrust / 20000);
      this.mesh.plume.visible = true;
      this.mesh.plume.scale.set(length, 1, 1);
      this.mesh.plume.position.x = -1.5 - 0.5 * length;
    } else {
      this.mesh.plume.visible = false;
    }
    return false;
  }

  /** Out of the picture, ready for the next round. */
  hide(): void {
    this.mesh.root.visible = false;
    this.trail.mesh.visible = false;
    this.trail.clear();
    this.spent = 0;
    this.since = TRAIL_STEP;
  }
}

export class DroneView {
  readonly mesh = buildDrone();
  private readonly q = new THREE.Quaternion();

  private readonly turn = new THREE.Quaternion();

  constructor(parent: THREE.Scene) {
    parent.add(this.mesh.root);
    this.hide();
  }

  update(drone: Drone): void {
    this.mesh.root.visible = drone.alive;
    if (!drone.alive) {
      return;
    }
    this.mesh.root.position.set(drone.east, drone.alt, -drone.north);
    // A drone heading h has its body x along north*cos(h) + east*sin(h).
    attitude(1, 0, 0, 0, this.q);
    this.q.premultiply(this.turn.setFromAxisAngle(UP, -drone.heading * DEG));
    this.mesh.root.quaternion.copy(this.q);
  }

  hide(): void {
    this.mesh.root.visible = false;
  }
}
