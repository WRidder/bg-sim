/**
 * The workshop: lofted bodies, tubes, wing sections, wheels. Everything is in the chassis frame of
 * the FMU (x forward, y left, z up), with a wheel's axle along z as in its carrier frame.
 */

import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

export interface Section {
  x: number;
  /** Half width, height above and below the section's centre, the centre's height. */
  w: number;
  top: number;
  bottom: number;
  z: number;
  /** Superellipse exponent: 2 an ellipse, higher boxier. */
  n?: number;
  /** Centre offset across the car. */
  y?: number;
}

function hermite(a: number, b: number, before: number, after: number, t: number): number {
  const m0 = (b - before) * 0.5;
  const m1 = (after - a) * 0.5;
  const t2 = t * t;
  const t3 = t2 * t;
  return (2 * t3 - 3 * t2 + 1) * a + (t3 - 2 * t2 + t) * m0 + (-2 * t3 + 3 * t2) * b + (t3 - t2) * m1;
}

/** A smooth skin through sections from the nose back, closed at both ends. */
export function loft(sections: readonly Section[], rows = 40, columns = 28, reshape?: (x: number, y: number, z: number, angle: number) => [number, number, number]): THREE.BufferGeometry {
  const positions: number[] = [];
  const indices: number[] = [];
  const last = sections.length - 1;
  for (let r = 0; r <= rows; r += 1) {
    const u = (r / rows) * last;
    const i = Math.min(Math.floor(u), last - 1);
    const t = u - i;
    const value = (read: (s: Section) => number): number =>
      hermite(read(sections[i]), read(sections[i + 1]), read(sections[Math.max(i - 1, 0)]), read(sections[Math.min(i + 2, last)]), t);
    const x = sections[i].x + (sections[i + 1].x - sections[i].x) * t;
    const w = Math.max(value((s) => s.w), 0.001);
    const top = Math.max(value((s) => s.top), 0.001);
    const bottom = Math.max(value((s) => s.bottom), 0.001);
    const z = value((s) => s.z);
    const n = value((s) => s.n ?? 2.4);
    const centre = value((s) => s.y ?? 0);
    for (let c = 0; c <= columns; c += 1) {
      const angle = (c / columns) * Math.PI * 2;
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      const y = centre + w * Math.sign(cos) * Math.abs(cos) ** (2 / n);
      const up = z + (sin >= 0 ? top : bottom) * Math.sign(sin) * Math.abs(sin) ** (2 / n);
      const p = reshape ? reshape(x, y, up, angle) : ([x, y, up] as [number, number, number]);
      positions.push(...p);
    }
  }
  const side = columns + 1;
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < columns; c += 1) {
      const a = r * side + c;
      indices.push(a, a + side, a + 1, a + 1, a + side, a + side + 1);
    }
  }
  const capRow = (row: number, flip: boolean): void => {
    const start = row * side;
    const centre = positions.length / 3;
    let [cx, cy, cz] = [0, 0, 0];
    for (let c = 0; c < columns; c += 1) {
      cx += positions[(start + c) * 3] / columns;
      cy += positions[(start + c) * 3 + 1] / columns;
      cz += positions[(start + c) * 3 + 2] / columns;
    }
    positions.push(cx, cy, cz);
    for (let c = 0; c < columns; c += 1) {
      if (flip) {
        indices.push(centre, start + c, start + c + 1);
      } else {
        indices.push(centre, start + c + 1, start + c);
      }
    }
  };
  capRow(0, true);
  capRow(rows, false);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  const normal = geometry.attributes.normal as THREE.BufferAttribute;
  for (let r = 0; r <= rows; r += 1) {
    const a = r * side;
    const b = a + columns;
    const v = new THREE.Vector3(normal.getX(a) + normal.getX(b), normal.getY(a) + normal.getY(b), normal.getZ(a) + normal.getZ(b)).normalize();
    normal.setXYZ(a, v.x, v.y, v.z);
    normal.setXYZ(b, v.x, v.y, v.z);
  }
  return geometry;
}

export function mirrored(geometry: THREE.BufferGeometry): THREE.BufferGeometry {
  const flipped = geometry.clone();
  flipped.applyMatrix4(new THREE.Matrix4().makeScale(1, -1, 1));
  if (!flipped.index) {
    const count = (flipped.attributes.position as THREE.BufferAttribute).count;
    flipped.setIndex(Array.from({ length: count }, (_, i) => i));
  }
  const index = flipped.index as THREE.BufferAttribute;
  for (let i = 0; i < index.count; i += 3) {
    const a = index.getX(i);
    index.setX(i, index.getX(i + 1));
    index.setX(i + 1, a);
  }
  return flipped;
}

export function both(geometry: THREE.BufferGeometry): THREE.BufferGeometry {
  return merge([geometry, mirrored(geometry)]);
}

/** Everything reduced to position and normal, so any mix of three's shapes will merge. */
export function merge(geometries: THREE.BufferGeometry[]): THREE.BufferGeometry {
  const clean = geometries.map((g) => {
    const part = g.clone();
    for (const name of Object.keys(part.attributes)) {
      if (name !== "position" && name !== "normal") {
        part.deleteAttribute(name);
      }
    }
    if (!part.index) {
      const count = (part.attributes.position as THREE.BufferAttribute).count;
      part.setIndex(Array.from({ length: count }, (_, i) => i));
    }
    return part;
  });
  return mergeGeometries(clean) as THREE.BufferGeometry;
}

const UP = new THREE.Vector3(0, 1, 0);

/** A round tube between two points; three's cylinder stands along its own y. */
export function tube(ax: number, ay: number, az: number, bx: number, by: number, bz: number, radius: number, sides = 8): THREE.BufferGeometry {
  const a = new THREE.Vector3(ax, ay, az);
  const b = new THREE.Vector3(bx, by, bz);
  const along = b.clone().sub(a);
  const geometry = new THREE.CylinderGeometry(radius, radius, along.length(), sides, 1);
  geometry.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(UP, along.normalize()));
  geometry.translate((ax + bx) / 2, (ay + by) / 2, (az + bz) / 2);
  return geometry;
}

/** Tubes through a list of points, with a ball at each bend to hide the joint. */
export function bent(points: readonly (readonly [number, number, number])[], radius: number, sides = 8): THREE.BufferGeometry {
  const parts: THREE.BufferGeometry[] = [];
  points.forEach((p, i) => {
    const ball = new THREE.SphereGeometry(radius, sides, 6);
    ball.translate(p[0], p[1], p[2]);
    parts.push(ball);
    if (i > 0) {
      const q = points[i - 1];
      parts.push(tube(q[0], q[1], q[2], p[0], p[1], p[2], radius, sides));
    }
  });
  return merge(parts);
}

/** A smooth tube along a curve through the points. */
export function hose(points: readonly (readonly [number, number, number])[], radius: number, closed = false, rows = 48): THREE.BufferGeometry {
  const curve = new THREE.CatmullRomCurve3(points.map((p) => new THREE.Vector3(...p)), closed, "centripetal");
  return new THREE.TubeGeometry(curve, rows, radius, 10, closed);
}

export function box(x0: number, y0: number, z0: number, x1: number, y1: number, z1: number): THREE.BufferGeometry {
  const geometry = new THREE.BoxGeometry(Math.abs(x1 - x0), Math.abs(y1 - y0), Math.abs(z1 - z0));
  geometry.translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2);
  return geometry;
}

/** A wing: an airfoil of `chord` from `x` backwards, across y from -span to span, at height z. */
export function wing(x: number, chord: number, z: number, span: number, thick = 0.09, pitch = 0, droop = 0, rows = 18): THREE.BufferGeometry {
  const positions: number[] = [];
  const indices: number[] = [];
  const stations = 12;
  const c = Math.cos(pitch);
  const s = Math.sin(pitch);
  const ring = stations * 2;
  for (let r = 0; r <= rows; r += 1) {
    const v = -1 + (2 * r) / rows;
    const lift = droop * v * v;
    for (let i = 0; i < ring; i += 1) {
      const lower = i >= stations;
      const u = lower ? (ring - i) / stations : i / stations;
      const half = thick * chord * 2.2 * 0.5 * (0.2969 * Math.sqrt(u) - 0.126 * u - 0.3516 * u * u + 0.2843 * u ** 3 - 0.1036 * u ** 4);
      const camber = 0.05 * chord * Math.sin(u * Math.PI);
      const px = -u * chord;
      const pz = (lower ? -half : half) + camber;
      positions.push(x + px * c - pz * s, v * span, z + lift + px * s + pz * c);
    }
  }
  for (let r = 0; r < rows; r += 1) {
    for (let i = 0; i < ring; i += 1) {
      const a = r * ring + i;
      const b = r * ring + (i + 1) % ring;
      indices.push(a, a + ring, b, b, a + ring, b + ring);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

/** A surface of revolution about z, the wheel's axle, from a (radius, along-axle) profile. */
export function turned(profile: readonly (readonly [number, number])[], segments = 44): THREE.BufferGeometry {
  const lathe = new THREE.LatheGeometry(profile.map(([r, a]) => new THREE.Vector2(r, a)), segments);
  lathe.rotateX(Math.PI / 2);
  lathe.computeVertexNormals();
  return lathe;
}

export function steel(color: number, roughness = 0.45, metalness = 0.9): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color, roughness, metalness });
}

export function matte(color: number, roughness = 0.75): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({ color, roughness, metalness: 0 });
}

/** Wound fibre: dark, with a fine weave that catches the light. */
export function carbon(): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial({ color: 0x0e1012, roughness: 0.42, metalness: 0.25 });
  material.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vWeave;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvWeave = position;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vWeave;")
      .replace(
        "#include <color_fragment>",
        `#include <color_fragment>
        vec2 w = vec2(vWeave.x + vWeave.z, vWeave.y - vWeave.z) * 160.0;
        diffuseColor.rgb *= 0.8 + 0.5 * step(0.5, fract((floor(w.x) + floor(w.y)) * 0.5));`,
      );
  };
  return material;
}

export interface WheelParts {
  /** Turns with the wheel. */
  wheel: THREE.Group;
  /** Stays with the upright: the caliper. */
  hub: THREE.Group;
}

export type Glow = { value: number };
