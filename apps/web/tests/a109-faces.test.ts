import * as THREE from "three";
import { describe, expect, it, vi } from "vitest";
import { buildHelicopter, poseGear } from "../src/a109/aircraft";

/**
 * A surface drawn inside out shows through to its far side, and from most angles only a close look
 * finds it. So: rays from all round, and whatever each meets first must face it. Materials go double
 * sided here so that a wrong face is hit and counted rather than quietly passed through.
 */
function solid(root: THREE.Object3D): THREE.Mesh[] {
  root.updateWorldMatrix(true, true);
  const meshes: THREE.Mesh[] = [];
  root.traverse((object) => {
    if (object instanceof THREE.Mesh && !(object.material instanceof THREE.ShaderMaterial) && object.geometry.type !== "CircleGeometry") {
      (object.material as THREE.Material).side = THREE.DoubleSide;
      meshes.push(object);
    }
  });
  return meshes;
}

/** Rays from eight corners of the sky at a sample of every mesh's triangles, so no small part is missed. */
function* rays(meshes: THREE.Mesh[]): Generator<THREE.Ray> {
  const corner = new THREE.Vector3();
  const at = new THREE.Vector3();
  const other = new THREE.Vector3();
  for (const mesh of meshes) {
    const place = mesh.geometry.attributes.position as THREE.BufferAttribute;
    const index = mesh.geometry.index;
    const triangles = (index ?? place).count / 3;
    const step = Math.max(1, Math.floor(triangles / 25));
    for (let t = 0; t < triangles; t += step) {
      at.set(0, 0, 0);
      for (let v = 0; v < 3; v += 1) {
        at.add(other.fromBufferAttribute(place, index ? index.getX(t * 3 + v) : t * 3 + v));
      }
      at.multiplyScalar(1 / 3).applyMatrix4(mesh.matrixWorld);
      for (let c = 0; c < 8; c += 1) {
        corner.set(c & 1 ? 1 : -1, c & 2 ? 1 : -1, c & 4 ? 1 : -1).normalize();
        yield new THREE.Ray(at.clone().addScaledVector(corner, 20), corner.clone().negate());
      }
    }
  }
}

function inverted(meshes: THREE.Mesh[], source: Iterable<THREE.Ray>): { rays: number; wrong: Map<string, number>; shaded: Map<string, number> } {
  const caster = new THREE.Raycaster();
  const wrong = new Map<string, number>();
  const normal = new THREE.Vector3();
  const matrix = new THREE.Matrix3();
  const a = new THREE.Vector3();
  const b = new THREE.Vector3();
  const c = new THREE.Vector3();
  let count = 0;
  const shaded = new Map<string, number>();
  for (const ray of source) {
    caster.ray.copy(ray);
    const hit = caster.intersectObjects(meshes, false)[0];
    if (!hit?.face) {
      continue;
    }
    count += 1;
    const mesh = hit.object as THREE.Mesh;
    const place = mesh.geometry.attributes.position as THREE.BufferAttribute;
    a.fromBufferAttribute(place, hit.face.a).applyMatrix4(mesh.matrixWorld);
    b.fromBufferAttribute(place, hit.face.b).applyMatrix4(mesh.matrixWorld);
    c.fromBufferAttribute(place, hit.face.c).applyMatrix4(mesh.matrixWorld);
    // The winding in the world, which is what the rasteriser culls by.
    normal.subVectors(b, a).cross(c.clone().sub(a));
    if (normal.dot(ray.direction) > 0) {
      const name = `${mesh.geometry.type} ${(mesh.material as THREE.MeshStandardMaterial).color.getHexString()} tris ${(mesh.geometry.index ?? place).count / 3}`;
      wrong.set(name, (wrong.get(name) ?? 0) + 1);
    }
    // And the normals the lighting uses must agree with it.
    const shading = mesh.geometry.attributes.normal as THREE.BufferAttribute | undefined;
    if (shading) {
      matrix.getNormalMatrix(mesh.matrixWorld);
      a.fromBufferAttribute(shading, hit.face.a);
      b.fromBufferAttribute(shading, hit.face.b);
      c.fromBufferAttribute(shading, hit.face.c);
      // A smooth normal may lean past a grazing ray at a sharp edge; turned well away it is wrong.
      if (a.add(b).add(c).applyMatrix3(matrix).normalize().dot(ray.direction) > 0.6) {
        const name = `${mesh.geometry.type} ${(mesh.material as THREE.MeshStandardMaterial).color.getHexString()} tris ${(mesh.geometry.index ?? place).count / 3}`;
        shaded.set(name, (shaded.get(name) ?? 0) + 1);
      }
    }
  }
  return { rays: count, wrong, shaded };
}

describe("the helicopter's faces", () => {
  for (const [name, away] of [["gear down", 0], ["gear away", 1]] as const) {
    it(`all face outward, ${name}`, () => {
      const heli = buildHelicopter();
      poseGear(heli, away);
      const meshes = solid(heli.root);
      const found = inverted(meshes, rays(meshes));
      expect(found.rays).toBeGreaterThan(1500);
      expect([...found.wrong.entries()]).toEqual([]);
      expect([...found.shaded.entries()]).toEqual([]);
    }, 120000);
  }

  it("all face the pilot in the cockpit", async () => {
    const context = new Proxy({}, { get: () => () => ({ addColorStop: () => {} }), set: () => true });
    vi.stubGlobal("document", { createElement: () => ({ width: 0, height: 0, getContext: () => context }) });
    const { Cockpit, EYE } = await import("../src/a109/cockpit");
    const cockpit = new Cockpit();
    const meshes: THREE.Mesh[] = [];
    cockpit.group.updateWorldMatrix(true, true);
    cockpit.group.traverse((object) => {
      if (object instanceof THREE.Mesh) {
        (object.material as THREE.Material).side = THREE.DoubleSide;
        meshes.push(object);
      }
    });
    const eyes = function* (): Generator<THREE.Ray> {
      const golden = Math.PI * (3 - Math.sqrt(5));
      for (let i = 0; i < 6000; i += 1) {
        const z = 1 - (2 * (i + 0.5)) / 6000;
        const r = Math.sqrt(1 - z * z);
        yield new THREE.Ray(EYE.clone(), new THREE.Vector3(r * Math.cos(i * golden), r * Math.sin(i * golden), z));
      }
    };
    const found = inverted(meshes, eyes());
    vi.unstubAllGlobals();
    expect(found.rays).toBeGreaterThan(500);
    expect([...found.wrong.entries()]).toEqual([]);
  });
});
