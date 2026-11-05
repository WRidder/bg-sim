/**
 * From the flight model's frames to the scene's. The FMU flies in north-east-down with a body frame
 * of forward-right-down; the scene has x east, y up, z south, and a mesh is drawn forward-left-up.
 */

import * as THREE from "three";

const NED_TO_WORLD = new THREE.Quaternion().setFromRotationMatrix(
  new THREE.Matrix4().set(0, 1, 0, 0, 0, 0, -1, 0, -1, 0, 0, 0, 0, 0, 0, 1),
);
/** Half a turn about x: forward-left-up to forward-right-down. */
const MESH_TO_BODY = new THREE.Quaternion(1, 0, 0, 0);
const scratch = new THREE.Quaternion();

/** The world attitude of a mesh, from the body-to-NED quaternion. */
export function attitude(w: number, x: number, y: number, z: number, into: THREE.Quaternion): THREE.Quaternion {
  scratch.set(x, y, z, w).normalize();
  return into.copy(NED_TO_WORLD).multiply(scratch).multiply(MESH_TO_BODY);
}

export function worldPoint(north: number, east: number, up: number, into: THREE.Vector3): THREE.Vector3 {
  return into.set(east, up, -north);
}
