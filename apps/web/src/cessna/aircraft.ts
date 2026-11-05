/**
 * A light high-wing tourer, built in code: lofted sections for the cabin and the tail cone, airfoils
 * for the flying surfaces, lathes for the wheels and the spinner. The model is in the FMU's body
 * frame (x forward, y left, z up, metres, origin at the CG), with the hinge lines and gear contacts
 * of the bg-sim scene, so the wheels stand on the FMU's ground. Paint, windows and panel lines are
 * computed per pixel from the body position, so it holds up close and costs no texture.
 */

import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

interface Station {
  x: number;
  /** Half width, and the height of the top and of the belly above and below `z`. */
  w: number;
  top: number;
  bottom: number;
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
  const before = stations[Math.max(i - 1, 0)];
  const after = stations[Math.min(i + 2, stations.length - 1)];
  const t = (x - a.x) / (b.x - a.x);
  const spline = (key: Exclude<keyof Station, "x">): number => {
    const m0 = ((b[key] - before[key]) / (before.x - b.x || 1)) * (a.x - b.x);
    const m1 = ((after[key] - a[key]) / (a.x - after.x || 1)) * (a.x - b.x);
    const t2 = t * t;
    const t3 = t2 * t;
    return (2 * t3 - 3 * t2 + 1) * a[key] + (t3 - 2 * t2 + t) * m0 + (-2 * t3 + 3 * t2) * b[key] + (t3 - t2) * m1;
  };
  return { x, w: Math.max(spline("w"), 0), top: Math.max(spline("top"), 0), bottom: Math.max(spline("bottom"), 0), z: spline("z"), n: spline("n") };
}

function loft(stations: readonly Station[], rows: number, columns: number): THREE.BufferGeometry {
  const positions: number[] = [];
  const indices: number[] = [];
  const front = stations[0].x;
  const back = stations[stations.length - 1].x;
  for (let r = 0; r <= rows; r += 1) {
    const x = front + (back - front) * (r / rows);
    const s = interpolate(stations, x);
    for (let c = 0; c <= columns; c += 1) {
      const angle = (c / columns) * Math.PI * 2;
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      const e = 2 / s.n;
      positions.push(x, s.w * Math.sign(cos) * Math.abs(cos) ** e, s.z + (sin >= 0 ? s.top : s.bottom) * Math.sign(sin) * Math.abs(sin) ** e);
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
  const normal = geometry.attributes.normal as THREE.BufferAttribute;
  for (let r = 0; r <= rows; r += 1) {
    const a = r * side;
    const b = a + columns;
    const n = new THREE.Vector3(normal.getX(a) + normal.getX(b), normal.getY(a) + normal.getY(b), normal.getZ(a) + normal.getZ(b)).normalize();
    normal.setXYZ(a, n.x, n.y, n.z);
    normal.setXYZ(b, n.x, n.y, n.z);
  }
  return geometry;
}

/** Half thickness of a cambered section at chord fraction u: a flat-bottomed light-aircraft wing. */
function section(u: number, upper: boolean, camber: number): number {
  const t = 0.5 * (0.2969 * 2 * Math.sqrt(u) - 0.252 * u - 0.7032 * u * u + 0.5686 * u ** 3 - 0.2072 * u ** 4);
  return (upper ? t * (1 + camber) : -t * (1 - camber));
}

interface Panel {
  /** Leading and trailing edge x, the span position and the height, at the root and at the tip. */
  root: { le: number; te: number; span: number; up: number };
  tip: { le: number; te: number; span: number; up: number };
  thickness: number;
  camber?: number;
  /** Span along z, not y: a fin. */
  vertical?: boolean;
  side?: 1 | -1;
  /** Round the tip off over this fraction of the span. */
  rounded?: number;
}

function surface(panel: Panel, spanRows = 16, chordRows = 20): THREE.BufferGeometry {
  const positions: number[] = [];
  const indices: number[] = [];
  const side = panel.side ?? 1;
  const camber = panel.camber ?? 0;
  const ring = chordRows * 2;
  const rounded = panel.rounded ?? 0;
  for (let s = 0; s <= spanRows; s += 1) {
    const v = s / spanRows;
    let le = panel.root.le + (panel.tip.le - panel.root.le) * v;
    let te = panel.root.te + (panel.tip.te - panel.root.te) * v;
    const span = panel.root.span + (panel.tip.span - panel.root.span) * v;
    const up = panel.root.up + (panel.tip.up - panel.root.up) * v;
    let taper = s === spanRows ? 0.03 : 1;
    if (rounded > 0 && v > 1 - rounded) {
      const w = (v - (1 - rounded)) / rounded;
      const keep = Math.sqrt(Math.max(1 - w * w, 0.0025));
      const middle = le * 0.62 + te * 0.38;
      le = middle + (le - middle) * keep;
      te = middle + (te - middle) * keep;
      taper = keep;
    }
    const chord = le - te;
    for (let c = 0; c < ring; c += 1) {
      const phase = c / ring;
      const upper = phase < 0.5;
      const u = 0.5 - 0.5 * Math.cos((upper ? phase * 2 : 2 - phase * 2) * Math.PI);
      const t = section(u, upper, camber) * chord * panel.thickness * taper;
      const x = le - chord * u;
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
  // The end caps: a fan is enough on a thin section.
  const cap = (first: number, flip: boolean): void => {
    for (let c = 1; c < ring - 1; c += 1) {
      if (flip) {
        indices.push(first, first + c + 1, first + c);
      } else {
        indices.push(first, first + c, first + c + 1);
      }
    }
  };
  cap(0, side > 0 === !panel.vertical);
  cap(spanRows * ring, !(side > 0 === !panel.vertical));
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

/** A tube between two points, round or flattened to `flat` of its width. */
function rod(a: THREE.Vector3Like, b: THREE.Vector3Like, radius: number, flat = 1, end = radius): THREE.BufferGeometry {
  const from = new THREE.Vector3().copy(a);
  const to = new THREE.Vector3().copy(b);
  const length = from.distanceTo(to);
  const geometry = new THREE.CylinderGeometry(end, radius, length, 14, 1);
  geometry.scale(1, 1, flat);
  geometry.rotateX(Math.PI / 2);
  const look = new THREE.Matrix4().lookAt(from, to, new THREE.Vector3(1, 0, 0.01));
  geometry.applyMatrix4(look);
  geometry.translate((from.x + to.x) / 2, (from.y + to.y) / 2, (from.z + to.z) / 2);
  return geometry;
}

/** A shape of revolution about the x axis: pairs of radius and x. */
function revolve(profile: readonly [number, number][], segments: number): THREE.BufferGeometry {
  // A lathe faces outward when its profile climbs its axis.
  const climbing = profile[0][1] < profile[profile.length - 1][1] ? profile : [...profile].reverse();
  const geometry = new THREE.LatheGeometry(climbing.map(([r, x]) => new THREE.Vector2(r, x)), segments);
  geometry.rotateZ(-Math.PI / 2);
  return geometry;
}

const FUSELAGE: Station[] = [
  { x: 1.98, w: 0.25, top: 0.2, bottom: 0.26, z: -0.23, n: 2.2 },
  { x: 1.72, w: 0.4, top: 0.28, bottom: 0.38, z: -0.22, n: 2.5 },
  { x: 1.32, w: 0.49, top: 0.32, bottom: 0.46, z: -0.21, n: 2.8 },
  { x: 0.98, w: 0.53, top: 0.36, bottom: 0.5, z: -0.21, n: 3 },
  { x: 0.5, w: 0.56, top: 0.85, bottom: 0.54, z: -0.19, n: 3.1 },
  { x: 0.1, w: 0.57, top: 0.87, bottom: 0.56, z: -0.2, n: 3.3 },
  { x: -0.7, w: 0.57, top: 0.86, bottom: 0.54, z: -0.2, n: 3.3 },
  { x: -1.3, w: 0.53, top: 0.82, bottom: 0.46, z: -0.15, n: 3 },
  { x: -2.1, w: 0.4, top: 0.56, bottom: 0.33, z: 0.0, n: 2.7 },
  { x: -3.1, w: 0.27, top: 0.33, bottom: 0.25, z: 0.1, n: 2.4 },
  { x: -4.3, w: 0.15, top: 0.2, bottom: 0.16, z: 0.13, n: 2.2 },
  { x: -5.5, w: 0.07, top: 0.1, bottom: 0.08, z: 0.14, n: 2 },
  { x: -5.82, w: 0.02, top: 0.03, bottom: 0.03, z: 0.15, n: 2 },
];

const PAINT = /* glsl */ `
float seam(float d, float width) {
  float aa = fwidth(d);
  return (1.0 - smoothstep(width, width + aa, abs(d))) * smoothstep(0.12, 0.02, aa);
}
/** Signed distance to a rounded box round \`c\` in the plane, negative inside. */
float box(vec2 p, vec2 c, vec2 size, float r) {
  vec2 q = abs(p - c) - size + r;
  return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}
/** Whether a point on the cabin is glass, and the frame round it. */
vec2 glazing(vec3 b) {
  float fuselage = step(abs(b.y), 0.62) * step(b.x, 1.1) * step(-2.4, b.x);
  // The windshield leans back from the cowling to the wing's leading edge.
  float shield = max(max(0.17 - b.z, b.x - 0.93), 0.47 - b.x);
  // Side windows: the door's and the one behind it, then the rear window round the back.
  vec2 side = vec2(b.x, b.z);
  float front = box(side, vec2(0.0, 0.33), vec2(0.40, 0.25), 0.07);
  front = max(front, -(side.y - 0.24 + (side.x - 0.44) * 0.0) - 0.34);
  float rear = box(side, vec2(-0.82, 0.31), vec2(0.34, 0.23), 0.1);
  rear = max(rear, (side.y - 0.56) + (side.x + 1.16) * -0.3);
  float windows = min(front, rear);
  float wall = smoothstep(0.42, 0.5, abs(b.y));
  float cabin = windows < 0.0 ? wall : 0.0;
  float glass = max(step(shield, 0.0) * step(abs(b.y), 0.56), cabin) * fuselage;
  float frame = (seam(windows, 0.012) * wall + seam(shield, 0.012)) * fuselage;
  // The post down the middle of the windshield.
  frame += seam(b.y, 0.012) * step(shield, 0.0) * fuselage;
  return vec2(glass, frame);
}
`;

function paintMaterial(): THREE.MeshPhysicalMaterial {
  const material = new THREE.MeshPhysicalMaterial({
    color: 0xffffff,
    metalness: 0.02,
    roughness: 0.34,
    clearcoat: 0.35,
    clearcoatRoughness: 0.2,
    envMapIntensity: 0.5,
  });
  material.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nattribute vec3 aBody;\nvarying vec3 vBody;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvBody = aBody;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", `#include <common>\nvarying vec3 vBody;\nfloat vGlass;\n${PAINT}`)
      .replace(
        "#include <color_fragment>",
        /* glsl */ `#include <color_fragment>
        vec3 b = vBody;
        vec3 cream = vec3(0.6, 0.57, 0.48);
        vec3 teal = vec3(0.006, 0.075, 0.1);
        vec3 coral = vec3(0.62, 0.075, 0.03);
        vec3 paint = cream;
        float span = abs(b.y);
        float cabinBody = step(span, 0.72) * step(b.x, 2.1);
        // The sweep: a broad teal belly rising to the tail, a coral line along its edge.
        float swoop = -0.30 + 0.17 * smoothstep(-0.2, -5.5, b.x) + 0.1 * smoothstep(1.0, 2.0, b.x);
        float edge = b.z - swoop;
        if (cabinBody > 0.5) {
          paint = mix(paint, teal, 1.0 - smoothstep(-0.002, 0.002, edge));
          paint = mix(paint, coral, smoothstep(0.0, 0.002, edge) * (1.0 - smoothstep(0.075, 0.08, edge)));
        }
        // The wheel pants are the belly's colour.
        if (b.z < -0.8) {
          paint = teal;
        }
        // The fin and the rudder carry the same two colours, the tail surfaces their tips.
        if (b.z > 0.26 && span < 0.2 && b.x < -3.8) {
          float slant = b.z - 0.86 - (b.x + 5.0) * 0.2;
          paint = mix(teal, cream, smoothstep(-0.002, 0.002, slant));
          paint = mix(paint, coral, smoothstep(-0.002, 0.002, slant - 0.18) * (1.0 - smoothstep(0.0, 0.004, slant - 0.32)));
        }
        if (b.z > 0.5 && span > 0.7) {
          // Wing: the tips dipped in teal, a coral stripe inboard of them.
          float tip = span - 4.72 - (b.x + 0.2) * 0.1;
          paint = mix(paint, coral, smoothstep(-0.005, 0.0, tip + 0.12));
          paint = mix(paint, teal, smoothstep(-0.005, 0.0, tip));
        }
        if (b.x < -4.5 && span > 0.2 && b.z < 0.3) {
          float tip = span - 1.3;
          paint = mix(paint, teal, smoothstep(-0.005, 0.0, tip));
        }
        // The cowling's panel: a slightly darker shade, its fasteners and seam.
        vec2 glass = glazing(b);
        float cowl = seam(b.x - 0.96, 0.006) * cabinBody;
        float door = seam(b.x - 0.47, 0.005) + seam(b.x + 0.47, 0.005);
        door *= step(abs(b.z + 0.03), 0.62) * step(0.42, span) * cabinBody;
        float rib = seam(fract(span / 0.46) - 0.5, 0.008) * step(0.7, span) * step(0.45, b.z) * step(span, 5.3);
        float marks = max(max(cowl, door), rib * 0.35);
        paint *= 1.0 - 0.6 * marks;
        // Cooling intakes either side of the nose bowl.
        float intake = step(box(vec2(abs(b.y), b.z), vec2(0.27, -0.02), vec2(0.13, 0.05), 0.04), 0.0) * step(1.92, b.x) * step(b.x, 2.1);
        paint = mix(paint, vec3(0.012), intake);
        vec3 sky = vec3(0.02, 0.035, 0.05);
        paint = mix(paint, sky, glass.x);
        paint = mix(paint, vec3(0.04), clamp(glass.y, 0.0, 1.0));
        vGlass = glass.x * (1.0 - clamp(glass.y, 0.0, 1.0));
        diffuseColor.rgb = paint;
        `,
      )
      .replace(
        "#include <roughnessmap_fragment>",
        /* glsl */ `#include <roughnessmap_fragment>
        roughnessFactor = mix(roughnessFactor, 0.06, vGlass);`,
      )
      .replace(
        "#include <metalnessmap_fragment>",
        /* glsl */ `#include <metalnessmap_fragment>
        metalnessFactor = mix(metalnessFactor, 0.5, vGlass);`,
      );
  };
  return material;
}

/** Stamps each geometry with where its points are on the airframe, whatever hinge carries it. */
function stamped(geometry: THREE.BufferGeometry): THREE.BufferGeometry {
  const clean = geometry.index ? geometry.toNonIndexed() : geometry;
  clean.deleteAttribute("uv");
  clean.setAttribute("aBody", (clean.attributes.position as THREE.BufferAttribute).clone());
  return clean;
}

export interface LightAircraft {
  root: THREE.Group;
  aileronLeft: THREE.Group;
  aileronRight: THREE.Group;
  flapLeft: THREE.Group;
  flapRight: THREE.Group;
  elevator: THREE.Group;
  rudder: THREE.Group;
  /** Turns about the leg's axis with the steering. */
  noseWheel: THREE.Group;
  /** The three wheels, for spinning at the ground speed. */
  wheels: THREE.Object3D[];
  propeller: THREE.Group;
  disc: THREE.Mesh;
  discOpacity: { value: number };
  discAngle: { value: number };
  strobe: THREE.Mesh;
  beacon: THREE.Mesh;
}

const DISC_VERTEX = /* glsl */ `
varying vec2 vDisc;
void main() {
  vDisc = position.xy;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

/** A camera shutter's smear of two blades: a dark haze, with a bright ring where the tips are. */
const DISC_FRAGMENT = /* glsl */ `
uniform float uOpacity;
uniform float uAngle;
varying vec2 vDisc;
void main() {
  float r = length(vDisc) / 0.9525;
  if (r > 1.0) discard;
  float a = atan(vDisc.y, vDisc.x) + uAngle;
  float blades = pow(abs(cos(a)), 6.0);
  float tip = smoothstep(0.86, 0.9, r) * (1.0 - smoothstep(0.96, 1.0, r));
  float haze = 0.07 + 0.11 * blades * (1.0 - r * 0.4);
  vec3 color = mix(vec3(0.03), vec3(0.95, 0.82, 0.25), tip * 0.8);
  gl_FragColor = vec4(color, (haze + tip * 0.1) * uOpacity);
}
`;

export function buildAeroplane(): LightAircraft {
  const paint = paintMaterial();
  const root = new THREE.Group();
  const tyre = new THREE.MeshStandardMaterial({ color: 0x0c0c0d, roughness: 0.92 });
  const metal = new THREE.MeshStandardMaterial({ color: 0xa8acb0, roughness: 0.32, metalness: 0.9, envMapIntensity: 1 });
  const steel = new THREE.MeshStandardMaterial({ color: 0x2c3034, roughness: 0.42, metalness: 0.6 });

  const add = (parent: THREE.Object3D, geometry: THREE.BufferGeometry, material: THREE.Material): THREE.Mesh => {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    return mesh;
  };

  // ---- The fixed airframe, all in one mesh ----------------------------------------------------
  const WING_ROOT = 0.66;
  const WING_TIP = 0.74;
  const heightAt = (span: number): number => WING_ROOT + ((WING_TIP - WING_ROOT) * span) / 5.5;
  const wing = (from: number, to: number, le0: number, te0: number, le1: number, te1: number, rounded = 0, rows = 12): THREE.BufferGeometry[] =>
    ([1, -1] as const).map((side) => surface({
      root: { le: le0, te: te0, span: from, up: heightAt(from) },
      tip: { le: le1, te: te1, span: to, up: heightAt(to) },
      thickness: 0.14,
      camber: 0.42,
      side,
      rounded,
    }, rows));
  const body: THREE.BufferGeometry[] = [
    loft(FUSELAGE, 150, 56),
    // The wing is one straight spar: the cabin's roof carries it.
    ...wing(0.3, 2.95, 0.5, -0.59, 0.5, -0.59),
    ...wing(2.95, 5.2, 0.5, -0.63, 0.44, -0.63),
    ...wing(5.2, 5.5, 0.44, -0.95, 0.38, -0.82, 0.9, 10),
    // Roof fairing, where the wing meets the cabin.
    loft([
      { x: 0.58, w: 0.03, top: 0.03, bottom: 0.03, z: 0.71, n: 2 },
      { x: 0.42, w: 0.52, top: 0.09, bottom: 0.09, z: 0.68, n: 3.4 },
      { x: -0.5, w: 0.56, top: 0.09, bottom: 0.08, z: 0.67, n: 3.4 },
      { x: -1.1, w: 0.46, top: 0.06, bottom: 0.08, z: 0.64, n: 3 },
      { x: -2.1, w: 0.03, top: 0.02, bottom: 0.03, z: 0.58, n: 2 },
    ], 30, 28),
    // The stabiliser, ahead of the elevator's hinge.
    ...([1, -1] as const).map((side) => surface({
      root: { le: -4.55, te: -5.2, span: 0.05, up: 0.1 },
      tip: { le: -4.92, te: -5.2, span: 1.7, up: 0.13 },
      thickness: 0.16,
      side,
    }, 10, 14)),
    // The fin, swept back, with a long fillet running forward along the spine.
    surface({
      root: { le: -3.95, te: -5.53, span: 0.16, up: 0 },
      tip: { le: -5.28, te: -5.64, span: 1.62, up: 0 },
      thickness: 0.15,
      vertical: true,
    }, 14, 16),
    surface({
      root: { le: -3.1, te: -4.5, span: 0.2, up: 0 },
      tip: { le: -4.2, te: -4.5, span: 0.46, up: 0 },
      thickness: 0.07,
      vertical: true,
    }, 6, 10),
  ];
  // The lift struts.
  for (const side of [1, -1]) {
    body.push(rod({ x: 0.0, y: side * 0.54, z: -0.63 }, { x: 0.14, y: side * 2.95, z: heightAt(2.95) - 0.06 }, 0.045, 0.32));
  }
  add(root, mergeGeometries(body.map(stamped)), paint);

  // ---- The gear -------------------------------------------------------------------------------
  const gear: THREE.BufferGeometry[] = [];
  const pants: THREE.BufferGeometry[] = [];
  const wheels: THREE.Object3D[] = [];
  const wheelGeometry = (radius: number, width: number): THREE.BufferGeometry => {
    const w = width / 2;
    const tread = new THREE.LatheGeometry(
      ([[0.001, -w * 0.9], [radius * 0.52, -w * 0.9], [radius * 0.66, -w], [radius * 0.93, -w], [radius, -w * 0.5], [radius, w * 0.5], [radius * 0.93, w], [radius * 0.66, w], [radius * 0.52, w * 0.9], [0.001, w * 0.9]] as [number, number][])
        .map(([r, y]) => new THREE.Vector2(r, y)),
      28,
    );
    return tread;
  };
  const fairing = (x: number, y: number, z: number, length: number, half: number, tall: number): THREE.BufferGeometry => {
    // A teardrop: full over the axle, and drawn out long behind it.
    const geometry = loft([
      [0.46, 0.04], [0.38, 0.5], [0.24, 0.82], [0.06, 1], [-0.14, 0.92], [-0.34, 0.6], [-0.52, 0.26], [-0.64, 0.03],
    ].map(([along, size]) => ({ x: x + length * along, w: half * size, top: tall * size, bottom: tall * size, z: z + Math.max(-along, 0) * 0.06, n: 2.1 })), 24, 20);
    // Keep the tyre's bottom visible under the fairing.
    const p = geometry.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < p.count; i += 1) {
      p.setZ(i, Math.max(p.getZ(i), z - tall * 0.5));
    }
    geometry.computeVertexNormals();
    geometry.translate(0, y, 0);
    return geometry;
  };
  for (const side of [1, -1]) {
    const y = side * 1.092;
    const hub = -1.075;
    // A spring-steel leg: a flat blade curving out and down to the axle.
    gear.push(rod({ x: -0.3, y: side * 0.46, z: -0.72 }, { x: -0.32, y: side * 1.0, z: hub }, 0.05, 0.3, 0.03));
    pants.push(fairing(-0.32, y, hub, 0.98, 0.095, 0.27));
    const wheel = new THREE.Group();
    wheel.position.set(-0.32, y, hub);
    add(wheel, wheelGeometry(0.22, 0.14), tyre);
    root.add(wheel);
    wheels.push(wheel);
  }
  add(root, mergeGeometries(gear.map(stamped)), steel);
  // The pants wear the belly's colour: well below the sweep line.
  add(root, mergeGeometries(pants.map(stamped)), paint);

  const noseWheel = new THREE.Group();
  noseWheel.position.set(1.331, 0, -1.217);
  add(root, stamped(rod({ x: 1.28, y: 0, z: -0.62 }, { x: 1.331, y: 0, z: -1.0 }, 0.04)), metal);
  add(root, stamped(rod({ x: 1.22, y: 0, z: -0.56 }, { x: 1.29, y: 0, z: -0.9 }, 0.055)), steel);
  const noseTyre = new THREE.Group();
  add(noseTyre, wheelGeometry(0.18, 0.12), tyre);
  noseWheel.add(noseTyre);
  wheels.push(noseTyre);
  const nosePant = fairing(0, 0, 0, 0.74, 0.08, 0.22);
  nosePant.translate(1.331, 0, -1.217);
  const nose = new THREE.Mesh(stamped(nosePant), paint);
  nose.geometry.translate(-1.331, 0, 1.217);
  nose.castShadow = true;
  noseWheel.add(nose);
  const fork = new THREE.Mesh(rod({ x: 0, y: 0, z: 0.22 }, { x: 0, y: 0, z: 0.04 }, 0.035), metal);
  noseWheel.add(fork);
  root.add(noseWheel);

  // ---- Small fittings -------------------------------------------------------------------------
  const details: THREE.BufferGeometry[] = [
    // The exhaust stub under the cowling.
    rod({ x: 1.2, y: 0.2, z: -0.58 }, { x: 0.95, y: 0.22, z: -0.74 }, 0.03),
    // Whip aerial on the roof, and the pitot under the left wing.
    rod({ x: -0.6, y: 0, z: 0.74 }, { x: -1.05, y: 0, z: 1.28 }, 0.007, 1, 0.003),
    rod({ x: 0.72, y: 2.3, z: 0.62 }, { x: 0.25, y: 2.3, z: 0.62 }, 0.008),
    // Step and door handle.
    rod({ x: -0.1, y: 0.56, z: -0.82 }, { x: -0.1, y: 0.84, z: -0.82 }, 0.012),
    rod({ x: 0.06, y: 0.585, z: 0.0 }, { x: -0.1, y: 0.585, z: 0.0 }, 0.012),
    rod({ x: 0.06, y: -0.585, z: 0.0 }, { x: -0.1, y: -0.585, z: 0.0 }, 0.012),
  ];
  add(root, mergeGeometries(details.map((g) => g.toNonIndexed())), metal);

  // Tip lights, red on the left, green on the right, the strobe on the tail. The FMU has no lights;
  // they make the aeroplane easy to find against a dark hill.
  const lens = (color: number): THREE.MeshBasicMaterial => new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(3), toneMapped: false });
  const tipLight = new THREE.SphereGeometry(0.035, 10, 8);
  const red = new THREE.Mesh(tipLight, lens(0xff2010));
  red.position.set(0.06, 5.5, WING_TIP + 0.02);
  const green = new THREE.Mesh(tipLight, lens(0x10ff50));
  green.position.set(0.06, -5.5, WING_TIP + 0.02);
  const strobe = new THREE.Mesh(tipLight, new THREE.MeshBasicMaterial({ color: new THREE.Color(9, 9, 9), toneMapped: false }));
  strobe.position.set(-5.66, 0, 1.68);
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.05, 10, 8), new THREE.MeshBasicMaterial({ color: new THREE.Color(9, 0.8, 0.3), toneMapped: false }));
  beacon.position.set(-1.6, 0, 0.5);
  root.add(red, green, strobe, beacon);

  // ---- The moving surfaces, on the hinges of the bg-sim scene ---------------------------------
  const hinged = (x: number, y: number, z: number, parts: THREE.BufferGeometry[]): THREE.Group => {
    const group = new THREE.Group();
    group.position.set(x, y, z);
    const geometry = mergeGeometries(parts.map(stamped));
    geometry.translate(-x, -y, -z);
    add(group, geometry, paint);
    root.add(group);
    return group;
  };
  const flap = (side: 1 | -1): THREE.BufferGeometry => surface({
    root: { le: -0.60, te: -0.99, span: 0.62, up: heightAt(0.62) - 0.02 },
    tip: { le: -0.60, te: -0.99, span: 2.94, up: heightAt(2.94) - 0.02 },
    thickness: 0.17,
    camber: 0.3,
    side,
  }, 6, 12);
  const aileron = (side: 1 | -1): THREE.BufferGeometry => surface({
    root: { le: -0.64, te: -0.99, span: 2.97, up: heightAt(2.97) },
    tip: { le: -0.64, te: -0.96, span: 5.2, up: heightAt(5.2) },
    thickness: 0.16,
    side,
  }, 6, 12);
  const flapLeft = hinged(-0.59, 1.785, 0.63, [flap(1)]);
  const flapRight = hinged(-0.59, -1.785, 0.63, [flap(-1)]);
  const aileronLeft = hinged(-0.63, 4.09, 0.66, [aileron(1)]);
  const aileronRight = hinged(-0.63, -4.09, 0.66, [aileron(-1)]);
  const elevator = hinged(-5.2, 0, 0.1, ([1, -1] as const).map((side) => surface({
    root: { le: -5.21, te: -5.63, span: 0.03, up: 0.1 },
    tip: { le: -5.21, te: -5.52, span: 1.72, up: 0.13 },
    thickness: 0.15,
    side,
    rounded: 0.14,
  }, 12, 12)));
  const rudder = hinged(-5.55, 0, 0.1, [surface({
    root: { le: -5.55, te: -6.1, span: 0.1, up: 0 },
    tip: { le: -5.66, te: -6.02, span: 1.62, up: 0 },
    thickness: 0.16,
    vertical: true,
    rounded: 0.12,
  }, 14, 12)]);

  // ---- The propeller --------------------------------------------------------------------------
  const propeller = new THREE.Group();
  propeller.position.set(2.116, 0, -0.226);
  const spinnerMaterial = new THREE.MeshPhysicalMaterial({ color: 0xb8280e, roughness: 0.25, clearcoat: 0.8, clearcoatRoughness: 0.15 });
  add(propeller, revolve([[0.001, 0.32], [0.05, 0.3], [0.11, 0.23], [0.16, 0.12], [0.185, 0], [0.185, -0.1], [0.14, -0.13]], 28), spinnerMaterial);
  const blade = surface({
    root: { le: 0.09, te: -0.09, span: 0.13, up: 0 },
    tip: { le: 0.05, te: -0.04, span: 0.9525, up: 0 },
    thickness: 0.28,
    camber: 0.3,
    vertical: true,
    rounded: 0.12,
  }, 18, 10);
  // Twist: coarse at the root, fine at the tip; the section's chord is along x before this.
  const p = blade.attributes.position as THREE.BufferAttribute;
  for (let i = 0; i < p.count; i += 1) {
    const r = p.getZ(i);
    const twist = (1.15 - 0.72 * (r / 0.95));
    const across = p.getX(i);
    const out = p.getY(i);
    p.setX(i, -across * Math.sin(twist) * 0.7 + out * Math.cos(twist));
    p.setY(i, across * Math.cos(twist) + out * Math.sin(twist));
  }
  // That turn is also a mirror, which turns every triangle inside out.
  const corners = blade.index as THREE.BufferAttribute;
  for (let i = 0; i < corners.count; i += 3) {
    const first = corners.getX(i);
    corners.setX(i, corners.getX(i + 1));
    corners.setX(i + 1, first);
  }
  blade.computeVertexNormals();
  const other = blade.clone();
  other.rotateX(Math.PI);
  const bladeMaterial = new THREE.MeshStandardMaterial({ color: 0x1b1c1e, roughness: 0.46, metalness: 0.3 });
  add(propeller, mergeGeometries([blade, other]), bladeMaterial);
  root.add(propeller);

  const discOpacity = { value: 0 };
  const discAngle = { value: 0 };
  const disc = new THREE.Mesh(
    new THREE.CircleGeometry(0.9525, 48),
    new THREE.ShaderMaterial({
      vertexShader: DISC_VERTEX,
      fragmentShader: DISC_FRAGMENT,
      uniforms: { uOpacity: discOpacity, uAngle: discAngle },
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
    }),
  );
  disc.rotation.y = Math.PI / 2;
  disc.position.set(2.14, 0, -0.226);
  disc.renderOrder = 4;
  root.add(disc);

  return { root, aileronLeft, aileronRight, flapLeft, flapRight, elevator, rudder, noseWheel, wheels, propeller, disc, discOpacity, discAngle, strobe, beacon };
}

/** The same shape seen from above, for the shadow on the ground. */
export function aeroplaneShadow(): THREE.Mesh {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 256;
  const c = canvas.getContext("2d") as CanvasRenderingContext2D;
  c.filter = "blur(2px)";
  c.fillStyle = "#000";
  // Metres from the CG on a 12 m square, nose up.
  const px = (x: number, y: number): [number, number] => [128 + y * (256 / 12.5), 128 - x * (256 / 12.5)];
  const shape = (points: [number, number][]): void => {
    c.beginPath();
    for (const [x, y] of points) {
      c.lineTo(...px(x, y));
    }
    c.closePath();
    c.fill();
  };
  shape([[0.5, 5.5], [0.5, -5.5], [-1, -5.5], [-1, 5.5]]);
  shape([[2.1, 0.4], [2.1, -0.4], [0.9, -0.55], [-1.4, -0.5], [-5.6, -0.1], [-5.6, 0.1], [-1.4, 0.5], [0.9, 0.55]]);
  shape([[-4.6, 1.75], [-4.6, -1.75], [-5.6, -1.75], [-5.6, 1.75]]);
  const texture = new THREE.CanvasTexture(canvas);
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(12.5, 12.5),
    new THREE.MeshBasicMaterial({ map: texture, transparent: true, opacity: 0.55, depthWrite: false, alphaTest: 0.01 }),
  );
  mesh.geometry.rotateX(-Math.PI / 2);
  mesh.visible = false;
  return mesh;
}
