import * as THREE from "three";
import { expect, it, vi } from "vitest";
import { buildBuggy } from "../src/cars/buggy";
import { buildRacecar } from "../src/cars/racecar";
import { buildAeroplane } from "../src/cessna/aircraft";
import { buildFighter } from "../src/f16/aircraft";

/** Positive for a closed mesh whose triangles face outwards: the sum of signed tetrahedra. */
function signedVolume(geometry: THREE.BufferGeometry): number {
  const p = geometry.getAttribute("position");
  const index = geometry.index;
  const count = index ? index.count : p.count;
  const at = (i: number): number => (index ? index.getX(i) : i);
  const a = new THREE.Vector3();
  const b = new THREE.Vector3();
  const c = new THREE.Vector3();
  let volume = 0;
  for (let i = 0; i < count; i += 3) {
    a.fromBufferAttribute(p, at(i));
    b.fromBufferAttribute(p, at(i + 1));
    c.fromBufferAttribute(p, at(i + 2));
    volume += a.dot(b.cross(c)) / 6;
  }
  return volume;
}

// The cars paint their decals on a canvas, which no test looks at.
const painter = new Proxy({}, { get: () => () => ({ width: 0 }), set: () => true });
vi.stubGlobal("document", { createElement: () => ({ getContext: () => painter }) });

it.each([
  ["fighter", buildFighter],
  ["aeroplane", buildAeroplane],
  ["race car", () => ({ root: buildRacecar().body })],
  ["buggy", () => ({ root: buildBuggy().body })],
])("%s faces outwards: an inside-out mesh shows its far walls and the light on the wrong side", (_, build) => {
  const inverted: string[] = [];
  build().root.traverse((object) => {
    const mesh = object as THREE.Mesh;
    if (mesh.isMesh) {
      const volume = signedVolume(mesh.geometry);
      if (volume < -1e-6) {
        mesh.geometry.computeBoundingSphere();
        const at = mesh.geometry.boundingSphere?.center.toArray().map((x) => x.toFixed(2));
        inverted.push(`${mesh.geometry.getAttribute("position").count} vertices at ${at}: ${volume.toFixed(3)}`);
      }
    }
  });
  expect(inverted).toEqual([]);
});
