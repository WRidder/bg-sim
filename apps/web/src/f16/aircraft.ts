/**
 * A single-engine fighter, built in code: lofted sections for the fuselage, airfoils for the
 * flying surfaces. The model is in the FMU's mesh frame (x forward, y left, z up, metres), with the
 * hinge lines of the bg-sim scene (examples/f16/scenes/f16-sim.sdf). Paint and panel lines are
 * computed per pixel from the body position, so it holds up in close-ups at no texture cost.
 */

import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

interface Station {
  x: number;
  /** Half width, and the height of the top and of the belly above and below the centre line. */
  w: number;
  top: number;
  bottom: number;
  /** Height of the centre line. */
  z: number;
  /** Superellipse exponent: 2 is an ellipse, higher is boxier. */
  n: number;
}

function interpolate(stations: readonly Station[], x: number): Station {
  let i = 0;
  while (i < stations.length - 2 && x < stations[i + 1].x) {
    i += 1;
  }
  const a = stations[i];
  const b = stations[i + 1];
  const previous = stations[Math.max(i - 1, 0)];
  const next = stations[Math.min(i + 2, stations.length - 1)];
  const t = (x - a.x) / (b.x - a.x);
  const spline = (key: Exclude<keyof Station, "x">): number => {
    const m0 = ((b[key] - previous[key]) / (previous.x - b.x || 1)) * (a.x - b.x);
    const m1 = ((next[key] - a[key]) / (a.x - next.x || 1)) * (a.x - b.x);
    const t2 = t * t;
    const t3 = t2 * t;
    return (2 * t3 - 3 * t2 + 1) * a[key] + (t3 - 2 * t2 + t) * m0 + (-2 * t3 + 3 * t2) * b[key] + (t3 - t2) * m1;
  };
  return { x, w: Math.max(spline("w"), 0), top: Math.max(spline("top"), 0), bottom: Math.max(spline("bottom"), 0), z: spline("z"), n: spline("n") };
}

function point(s: Station, angle: number): [number, number] {
  const c = Math.cos(angle);
  const d = Math.sin(angle);
  const e = 2 / s.n;
  const y = s.w * Math.sign(c) * Math.abs(c) ** e;
  const z = s.z + (d >= 0 ? s.top : s.bottom) * Math.sign(d) * Math.abs(d) ** e;
  return [y, z];
}

function loft(stations: readonly Station[], rows: number, columns: number, reshape?: (x: number, angle: number, p: [number, number]) => [number, number]): THREE.BufferGeometry {
  const positions: number[] = [];
  const indices: number[] = [];
  const front = stations[0].x;
  const back = stations[stations.length - 1].x;
  for (let r = 0; r <= rows; r += 1) {
    // Crowd the rows at the nose, where the shape changes fastest.
    const u = r / rows;
    const x = front + (back - front) * (0.45 * u * u + 0.55 * u);
    const s = interpolate(stations, x);
    for (let c = 0; c <= columns; c += 1) {
      const angle = (c / columns) * Math.PI * 2;
      let p = point(s, angle);
      if (reshape) {
        p = reshape(x, angle, p);
      }
      positions.push(x, p[0], p[1]);
    }
  }
  const side = columns + 1;
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < columns; c += 1) {
      const a = r * side + c;
      indices.push(a, a + side, a + 1, a + 1, a + side, a + side + 1);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return closeSeam(geometry, rows, columns);
}

/** The first and last column are the same points: their normals must agree, or a seam shows. */
function closeSeam(geometry: THREE.BufferGeometry, rows: number, columns: number): THREE.BufferGeometry {
  const normal = geometry.attributes.normal as THREE.BufferAttribute;
  const side = columns + 1;
  for (let r = 0; r <= rows; r += 1) {
    const a = r * side;
    const b = a + columns;
    const n = new THREE.Vector3(
      normal.getX(a) + normal.getX(b),
      normal.getY(a) + normal.getY(b),
      normal.getZ(a) + normal.getZ(b),
    ).normalize();
    normal.setXYZ(a, n.x, n.y, n.z);
    normal.setXYZ(b, n.x, n.y, n.z);
  }
  return geometry;
}

/** Half thickness of a thin symmetric airfoil at chord fraction u. */
function airfoil(u: number): number {
  return 2.2 * (0.2969 * Math.sqrt(u) - 0.126 * u - 0.3516 * u * u + 0.2843 * u ** 3 - 0.1036 * u ** 4) * 0.5;
}

interface Panel {
  /** Leading and trailing edge x, and the span position, at the root and at the tip. */
  root: { le: number; te: number; span: number; up: number };
  tip: { le: number; te: number; span: number; up: number };
  thickness: number;
  /** 0: span along y (a wing), 1: span along z (a fin). */
  vertical?: boolean;
  /** Mirror across the centre plane. */
  side?: 1 | -1;
}

function surface(panel: Panel, spanRows = 14, chordRows = 22): THREE.BufferGeometry {
  const positions: number[] = [];
  const indices: number[] = [];
  const side = panel.side ?? 1;
  const ring = chordRows * 2;
  for (let s = 0; s <= spanRows; s += 1) {
    const v = s / spanRows;
    const le = panel.root.le + (panel.tip.le - panel.root.le) * v;
    const te = panel.root.te + (panel.tip.te - panel.root.te) * v;
    const span = panel.root.span + (panel.tip.span - panel.root.span) * v;
    const up = panel.root.up + (panel.tip.up - panel.root.up) * v;
    const chord = le - te;
    // The tip closes to a thin edge rather than an open end.
    const taper = s === spanRows ? 0.02 : 1 - 0.25 * v ** 6;
    for (let c = 0; c < ring; c += 1) {
      const phase = c / ring;
      const upper = phase < 0.5;
      const u = upper ? phase * 2 : 2 - phase * 2;
      const u2 = 0.5 - 0.5 * Math.cos(u * Math.PI);
      const t = airfoil(u2) * chord * panel.thickness * taper * (upper ? 1 : -1);
      const x = le - chord * u2;
      if (panel.vertical) {
        positions.push(x, t, span);
      } else {
        positions.push(x, span * side, up + t);
      }
    }
  }
  for (let s = 0; s < spanRows; s += 1) {
    for (let c = 0; c < ring; c += 1) {
      const a = s * ring + c;
      const b = s * ring + (c + 1) % ring;
      const d = a + ring;
      const e = b + ring;
      if (side > 0 === !panel.vertical) {
        indices.push(a, d, b, b, d, e);
      } else {
        indices.push(a, b, d, b, e, d);
      }
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

/** Turns a profile given nose first; a lathe faces outwards when it runs the other way. */
function revolve(profile: readonly [number, number][], segments: number): THREE.BufferGeometry {
  return new THREE.LatheGeometry(profile.map(([r, x]) => new THREE.Vector2(r, x)).reverse(), segments);
}

function along(geometry: THREE.BufferGeometry, x: number, y: number, z: number): THREE.BufferGeometry {
  // Lathe geometry runs along +y: turn it to run along +x, forward.
  geometry.rotateZ(-Math.PI / 2);
  geometry.translate(x, y, z);
  return geometry;
}

const FUSELAGE: Station[] = [
  { x: 7.75, w: 0.004, top: 0.004, bottom: 0.004, z: -0.05, n: 2 },
  { x: 7.3, w: 0.13, top: 0.13, bottom: 0.13, z: -0.04, n: 2 },
  { x: 6.5, w: 0.3, top: 0.3, bottom: 0.3, z: 0.0, n: 2 },
  { x: 5.5, w: 0.47, top: 0.48, bottom: 0.43, z: 0.06, n: 2 },
  { x: 4.5, w: 0.55, top: 0.56, bottom: 0.46, z: 0.12, n: 2.1 },
  { x: 3.4, w: 0.6, top: 0.58, bottom: 0.55, z: 0.14, n: 2.3 },
  { x: 2.4, w: 0.66, top: 0.56, bottom: 0.62, z: 0.13, n: 2.5 },
  { x: 1.2, w: 0.88, top: 0.54, bottom: 0.65, z: 0.13, n: 2.8 },
  { x: 0.0, w: 1.04, top: 0.57, bottom: 0.64, z: 0.12, n: 3.2 },
  { x: -1.5, w: 1.1, top: 0.62, bottom: 0.56, z: 0.12, n: 3.2 },
  { x: -3.0, w: 1.0, top: 0.6, bottom: 0.52, z: 0.13, n: 3 },
  { x: -4.6, w: 0.82, top: 0.62, bottom: 0.56, z: 0.16, n: 2.5 },
  { x: -5.9, w: 0.62, top: 0.6, bottom: 0.58, z: 0.2, n: 2.2 },
  { x: -6.5, w: 0.51, top: 0.51, bottom: 0.51, z: 0.22, n: 2 },
];

/** The ventral intake: a duct slung under the fuselage, its lip well behind the nose. */
const INTAKE: Station[] = [
  { x: 2.86, w: 0.56, top: 0.34, bottom: 0.33, z: -0.62, n: 3.4 },
  { x: 2.7, w: 0.58, top: 0.36, bottom: 0.36, z: -0.62, n: 3.4 },
  { x: 1.7, w: 0.6, top: 0.4, bottom: 0.38, z: -0.58, n: 3.2 },
  { x: 0.2, w: 0.62, top: 0.42, bottom: 0.3, z: -0.48, n: 3.2 },
  { x: -1.6, w: 0.6, top: 0.42, bottom: 0.16, z: -0.34, n: 3 },
  { x: -2.8, w: 0.4, top: 0.4, bottom: 0.02, z: -0.3, n: 2.6 },
];

/** Blends the sides into the strakes: a thin horizontal fairing from the canopy to the wing. */
function strake(side: 1 | -1): THREE.BufferGeometry {
  return surface({
    root: { le: 3.15, te: -0.4, span: 0.45, up: 0.1 },
    tip: { le: -0.15, te: -0.7, span: 1.42, up: 0.1 },
    thickness: 0.36,
    side,
  }, 12, 14);
}

export interface FighterParts {
  root: THREE.Group;
  stabilators: THREE.Group;
  flapLeft: THREE.Group;
  flapRight: THREE.Group;
  rudder: THREE.Group;
  burnerGlow: THREE.Mesh;
  flame: THREE.Mesh;
  flameTime: { value: number };
  flamePower: { value: number };
}

const PAINT = /* glsl */ `
float paintHash(vec2 p) {
  vec3 q = fract(vec3(p.xyx) * 0.1031);
  q += dot(q, q.yzx + 33.33);
  return fract((q.x + q.y) * q.z);
}
float paintNoise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(paintHash(i), paintHash(i + vec2(1, 0)), f.x), mix(paintHash(i + vec2(0, 1)), paintHash(i + vec2(1, 1)), f.x), f.y);
}
float paintFbm(vec2 p) { return paintNoise(p) * 0.6 + paintNoise(p * 2.3 + 4.0) * 0.28 + paintNoise(p * 5.1) * 0.12; }

/** 1 in the groove of a panel line. */
float panel(vec3 b, float width) {
  float across = abs(b.y) + abs(b.z) * 0.7;
  vec2 size = vec2(1.34, 0.83);
  vec2 cells = vec2(b.x, across) / size;
  float row = floor(cells.y);
  cells.x += paintHash(vec2(row, 4.0)) * 0.8;
  vec2 id = floor(cells);
  vec2 edge = (0.5 - abs(fract(cells) - 0.5)) * size;
  vec2 aa = fwidth(cells) * size;
  // A short section of each seam is missing, so the grid never reads as brickwork.
  float lineX = (1.0 - smoothstep(width, width + aa.x, edge.x)) * step(0.3, paintHash(id + 3.0));
  float lineY = (1.0 - smoothstep(width, width + aa.y, edge.y)) * step(0.5, paintHash(id.yx + 9.0));
  // Lines thinner than a pixel fade out instead of crawling.
  return max(lineX, lineY) * smoothstep(0.07, 0.015, max(aa.x, aa.y));
}
`;

function paintMaterial(): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial({ color: 0xffffff, metalness: 0.08, roughness: 0.5, envMapIntensity: 0.42 });
  material.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vBody;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvBody = position;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", `#include <common>\nvarying vec3 vBody;\n${PAINT}`)
      .replace(
        "#include <color_fragment>",
        /* glsl */ `#include <color_fragment>
        vec2 skin = vec2(vBody.x, vBody.y + vBody.z * 1.3);
        float blotch = paintFbm(skin * 0.34 + 2.0);
        vec3 light = vec3(0.235, 0.255, 0.285);
        vec3 mid = vec3(0.145, 0.16, 0.185);
        vec3 dark = vec3(0.088, 0.098, 0.115);
        vec3 paint = mix(light, mid, smoothstep(0.47, 0.49, blotch));
        paint = mix(paint, dark, smoothstep(0.58, 0.60, blotch + (vBody.z - 0.2) * 0.05));
        // The belly is the lightest tone, as on real low-visibility schemes.
        paint = mix(paint, light * 1.14, smoothstep(0.0, -0.38, vBody.z));
        // The radome is a separate, darker part.
        paint = mix(paint, vec3(0.20, 0.215, 0.235), smoothstep(5.92, 5.90, 12.0 - vBody.x - 0.1));
        float grime = paintFbm(skin * vec2(1.3, 5.0));
        paint *= 0.86 + 0.26 * grime;
        float groove = panel(vBody, 0.0028);
        paint *= 1.0 - 0.55 * groove;
        diffuseColor.rgb = paint;
        `,
      )
      .replace(
        "#include <roughnessmap_fragment>",
        /* glsl */ `#include <roughnessmap_fragment>
        roughnessFactor = clamp(roughnessFactor + (paintFbm(vBody.xy * 2.1) - 0.5) * 0.3, 0.2, 1.0);`,
      );
  };
  return material;
}

const FLAME_VERTEX = /* glsl */ `
varying vec2 vRing;
void main() {
  vRing = vec2(uv.y, length(position.xz));
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const FLAME_FRAGMENT = /* glsl */ `
uniform float uTime;
uniform float uPower;
varying vec2 vRing;
void main() {
  float along = 1.0 - vRing.x;
  // Shock diamonds: bright knots that stand still in the plume.
  float diamonds = 0.55 + 0.45 * cos(along * 34.0 * (1.0 - along * 0.3));
  float core = exp(-along * 3.6);
  float flicker = 0.9 + 0.1 * sin(uTime * 83.0 + along * 13.0) * sin(uTime * 51.0);
  vec3 hot = mix(vec3(1.0, 0.55, 0.22), vec3(0.42, 0.62, 1.0), core);
  vec3 color = hot * (2.2 + 9.0 * core * diamonds) * flicker;
  gl_FragColor = vec4(color * uPower * smoothstep(1.0, 0.55, along), 1.0);
}
`;

export function buildFighter(): FighterParts {
  const paint = paintMaterial();
  const root = new THREE.Group();

  const canopyCut = (x: number, angle: number, p: [number, number]): [number, number] => {
    // The spine: a raised dorsal behind the canopy that runs into the fin.
    const up = Math.sin(angle);
    if (up > 0 && x < 2.2 && x > -5.7) {
      const fade = Math.min(1, (2.2 - x) / 1.6) * Math.min(1, (x + 5.7) / 1.2);
      const near = Math.exp(-((p[0] / 0.46) ** 4));
      return [p[0], p[1] + 0.17 * fade * near];
    }
    return p;
  };

  const parts: THREE.BufferGeometry[] = [
    loft(FUSELAGE, 220, 72, canopyCut),
    loft(INTAKE, 70, 48),
    strake(1),
    strake(-1),
  ];

  for (const side of [1, -1] as const) {
    // Main wing, without the flaperon cut-out's inner chord.
    parts.push(surface({
      root: { le: 0.25, te: -2.05, span: 0.86, up: 0.08 },
      tip: { le: -3.05, te: -4.0, span: 4.72, up: 0.08 },
      thickness: 0.34,
      side,
    }));
    parts.push(surface({
      root: { le: -2.0, te: -3.1, span: 0.9, up: 0.08 },
      tip: { le: -2.6, te: -3.3, span: 1.3, up: 0.08 },
      thickness: 0.28,
      side,
    }, 6, 12));
    // Strake wing root fairing into the fuselage's flank.
    parts.push(surface({
      root: { le: 1.0, te: -3.0, span: 0.84, up: 0.09 },
      tip: { le: 0.3, te: -3.1, span: 1.32, up: 0.08 },
      thickness: 0.2,
      side,
    }, 8, 12));
    // Ventral fins under the engine bay.
    const fin = surface({
      root: { le: -3.9, te: -5.15, span: -0.34, up: 0 },
      tip: { le: -4.75, te: -5.4, span: -1.06, up: 0 },
      thickness: 0.5,
      vertical: true,
    }, 8, 10);
    fin.rotateX(side * 0.3);
    fin.translate(0, side * 0.58, 0);
    parts.push(fin);
    // Tail strakes, carrying the stabilator pivots.
    parts.push(surface({
      root: { le: -3.0, te: -6.1, span: 0.72, up: 0.18 },
      tip: { le: -4.5, te: -6.15, span: 1.3, up: 0.17 },
      thickness: 0.3,
      side,
    }, 8, 12));
  }

  // The fin, in two parts: the rudder hangs on its trailing edge.
  parts.push(surface({
    root: { le: -3.25, te: -5.75, span: 0.5, up: 0 },
    tip: { le: -5.9, te: -6.72, span: 3.25, up: 0 },
    thickness: 0.34,
    vertical: true,
  }));

  // Wing-tip rails and short-range missiles.
  for (const side of [1, -1] as const) {
    const y = side * 4.82;
    const rail = new THREE.BoxGeometry(2.7, 0.1, 0.13);
    rail.translate(-3.3, y, 0.08);
    parts.push(rail.toNonIndexed());
  }
  // The pitot, ahead of the radome.
  parts.push(along(revolve([[0, 0.72], [0.012, 0.66], [0.016, 0], [0.04, -0.2], [0.05, -0.5]], 10), 8.0, 0, -0.05).toNonIndexed());

  const merged = mergeGeometries(parts.map((g) => {
    const clean = g.index ? g.toNonIndexed() : g;
    clean.deleteAttribute("uv");
    return clean;
  }));
  const body = new THREE.Mesh(merged, paint);
  body.castShadow = true;
  body.receiveShadow = true;
  root.add(body);

  const dark = new THREE.MeshStandardMaterial({ color: 0x0b0c0e, roughness: 0.9, metalness: 0.2 });
  const metal = new THREE.MeshStandardMaterial({ color: 0x3c3a38, roughness: 0.38, metalness: 0.85, envMapIntensity: 0.8 });
  const pale = new THREE.MeshStandardMaterial({ color: 0xc8cccf, roughness: 0.4, metalness: 0.2 });

  // The intake's mouth: a dark throat inside the lip.
  const mouth = new THREE.Mesh(new THREE.CapsuleGeometry(0.31, 0.62, 8, 24), dark);
  mouth.rotation.x = Math.PI / 2;
  mouth.scale.set(1, 1, 0.92);
  mouth.position.set(2.875, 0, -0.62);
  mouth.scale.x = 0.04;
  root.add(mouth);

  // The canopy: a one-piece bubble of tinted glass.
  const glass = new THREE.MeshPhysicalMaterial({
    color: 0x3a2f12,
    metalness: 0.65,
    roughness: 0.05,
    transparent: true,
    opacity: 0.86,
    envMapIntensity: 1.5,
    clearcoat: 1,
    clearcoatRoughness: 0.04,
    side: THREE.DoubleSide,
  });
  const bubble = loft([
    { x: 4.75, w: 0.01, top: 0.01, bottom: 0.01, z: 0.62, n: 2 },
    { x: 4.3, w: 0.27, top: 0.14, bottom: 0.06, z: 0.64, n: 2 },
    { x: 3.5, w: 0.42, top: 0.36, bottom: 0.05, z: 0.68, n: 2 },
    { x: 2.7, w: 0.42, top: 0.38, bottom: 0.05, z: 0.72, n: 2 },
    { x: 1.9, w: 0.3, top: 0.2, bottom: 0.05, z: 0.78, n: 2 },
    { x: 1.45, w: 0.01, top: 0.01, bottom: 0.01, z: 0.84, n: 2 },
  ], 70, 48);
  const canopy = new THREE.Mesh(bubble, glass);
  canopy.renderOrder = 3;
  root.add(canopy);
  const seat = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.4, 0.5), dark);
  seat.position.set(2.62, 0, 0.82);
  root.add(seat);
  const helmet = new THREE.Mesh(new THREE.SphereGeometry(0.135, 20, 14), pale);
  helmet.position.set(2.92, 0, 1.0);
  root.add(helmet);
  const frame = new THREE.Mesh(new THREE.TorusGeometry(0.42, 0.018, 10, 40, Math.PI), dark);
  frame.rotation.set(Math.PI / 2, 0, Math.PI / 2);
  frame.rotation.set(0, 0, 0);
  frame.rotateY(Math.PI / 2);
  frame.rotateZ(-Math.PI / 2);
  frame.rotation.set(Math.PI / 2, Math.PI / 2, 0);
  frame.position.set(3.1, 0, 0.73);
  root.add(frame);

  // Missiles on the wing tips, painted white with their guidance bands.
  for (const side of [1, -1] as const) {
    const missile = along(revolve([[0.001, 1.46], [0.03, 1.32], [0.063, 1.14], [0.063, -1.42], [0.05, -1.46], [0.001, -1.46]], 16), -3.2, side * 4.82, -0.02);
    const mesh = new THREE.Mesh(missile, pale);
    mesh.castShadow = true;
    root.add(mesh);
    for (const [x, span] of [[-1.05, 0.15], [1.0, 0.13]] as const) {
      for (const angle of [0.78, 2.35, 3.93, 5.5]) {
        const fin = new THREE.BoxGeometry(0.3, 0.008, span);
        fin.translate(0, 0, 0.063 + span / 2);
        fin.rotateX(angle);
        fin.translate(-3.2 + x, side * 4.82, -0.02);
        root.add(new THREE.Mesh(fin, pale));
      }
    }
  }

  // The engine: a metal shroud with the nozzle's petals, the turbine dark behind.
  const petals = 15;
  const nozzle = new THREE.LatheGeometry(
    ([[0.5, -0.5], [0.47, -0.1], [0.415, 0.28], [0.36, 0.56], [0.345, 0.6], [0.325, 0.58], [0.32, 0.1], [0.26, -0.2]] as [number, number][]).map(([r, x]) => new THREE.Vector2(r, x)),
    petals * 6,
  );
  const n = nozzle.attributes.position as THREE.BufferAttribute;
  for (let i = 0; i < n.count; i += 1) {
    const a = Math.atan2(n.getX(i), n.getZ(i));
    const fold = 1 + 0.03 * Math.abs(Math.sin((a * petals) / 2)) * Math.max(0, (n.getY(i) + 0.3) / 0.9);
    n.setX(i, n.getX(i) * fold);
    n.setZ(i, n.getZ(i) * fold);
  }
  nozzle.computeVertexNormals();
  nozzle.rotateZ(Math.PI / 2);
  nozzle.translate(-6.72, 0, 0.22);
  const shroud = new THREE.Mesh(nozzle, metal);
  shroud.castShadow = true;
  root.add(shroud);

  const flameTime = { value: 0 };
  const flamePower = { value: 0 };
  const burnerGlow = new THREE.Mesh(
    new THREE.CircleGeometry(0.29, 32),
    new THREE.MeshBasicMaterial({ color: new THREE.Color(0, 0, 0), toneMapped: false }),
  );
  burnerGlow.rotation.y = -Math.PI / 2;
  burnerGlow.position.set(-6.95, 0, 0.22);
  root.add(burnerGlow);

  const flame = new THREE.Mesh(
    new THREE.CylinderGeometry(0.34, 0.03, 5.2, 28, 48, true),
    new THREE.ShaderMaterial({
      vertexShader: FLAME_VERTEX,
      fragmentShader: FLAME_FRAGMENT,
      uniforms: { uTime: flameTime, uPower: flamePower },
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
    }),
  );
  flame.rotation.z = -Math.PI / 2;
  flame.position.set(-9.7, 0, 0.22);
  flame.visible = false;
  root.add(flame);

  // Moving surfaces hang on the hinges of the bg-sim scene.
  const hinged = (x: number, y: number, z: number): THREE.Group => {
    const group = new THREE.Group();
    group.position.set(x, y, z);
    root.add(group);
    return group;
  };
  const add = (group: THREE.Group, geometry: THREE.BufferGeometry): void => {
    const clean = geometry;
    clean.deleteAttribute("uv");
    const mesh = new THREE.Mesh(clean, paint);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    group.add(mesh);
  };

  const stabilators = hinged(-5.0, 0, 0.05);
  for (const side of [1, -1] as const) {
    add(stabilators, surface({
      root: { le: 0.75, te: -1.55, span: 0.86, up: 0.1 },
      tip: { le: -1.4, te: -2.28, span: 2.75, up: 0.0 },
      thickness: 0.3,
      side,
    }));
  }
  const flapLeft = hinged(-2.419, 1.25, 0);
  const flapRight = hinged(-2.419, -1.25, 0);
  for (const [group, side] of [[flapLeft, 1], [flapRight, -1]] as const) {
    add(group, surface({
      root: { le: 0.0, te: -0.82, span: 0.05, up: 0.08 },
      tip: { le: -0.34, te: -0.86, span: 2.22, up: 0.08 },
      thickness: 0.22,
      side,
    }, 10, 12));
  }
  const rudder = hinged(-5.75, 0, 0.9);
  add(rudder, surface({
    root: { le: 0.0, te: -0.82, span: -0.32, up: 0 },
    tip: { le: -0.1, te: -0.74, span: 2.2, up: 0 },
    thickness: 0.22,
    vertical: true,
  }, 10, 12));

  return { root, stabilators, flapLeft, flapRight, rudder, burnerGlow, flame, flameTime, flamePower };
}
