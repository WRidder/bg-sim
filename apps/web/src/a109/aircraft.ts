/**
 * A twin-engine light helicopter, built in code: lofted sections for the cabin and boom, airfoils for
 * the fins and blades. The model is in the FMU's mesh frame (x forward, y left, z up, metres, origin
 * at the CG), with the hubs and wheels where the flight model has them. The livery, the glass and the
 * panel lines are computed per pixel from the body position, so it holds up in close-ups at no
 * texture cost.
 */

import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { HUB, ROTOR_RADIUS, SHAFT_TILT, TAIL_HUB, TAIL_RADIUS } from "./flight";

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
  return [s.w * Math.sign(c) * Math.abs(c) ** e, s.z + (d >= 0 ? s.top : s.bottom) * Math.sign(d) * Math.abs(d) ** e];
}

function loft(stations: readonly Station[], rows: number, columns: number): THREE.BufferGeometry {
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
      const [y, z] = point(s, (c / columns) * Math.PI * 2);
      positions.push(x, y, z);
    }
  }
  const side = columns + 1;
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < columns; c += 1) {
      const a = r * side + c;
      // Rows run aft and columns from the left side up over the top: this order faces outward.
      indices.push(a, a + side, a + 1, a + 1, a + side, a + side + 1);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  // The first and last column are the same points: their normals must agree, or a seam shows.
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

/** Half thickness of a thin symmetric airfoil at chord fraction u. */
function airfoil(u: number): number {
  return 2.2 * (0.2969 * Math.sqrt(u) - 0.126 * u - 0.3516 * u * u + 0.2843 * u ** 3 - 0.1036 * u ** 4) * 0.5;
}

interface Panel {
  /** Leading and trailing edge x, and the span position, at the root and at the tip. */
  root: { le: number; te: number; span: number; up: number };
  tip: { le: number; te: number; span: number; up: number };
  thickness: number;
  /** A fin: the span runs along z. */
  vertical?: boolean;
  /** Mirror across the centre plane. */
  side?: 1 | -1;
  /** Runs on into another panel: no taper, and no closing tip. */
  open?: boolean;
}

function surface(panel: Panel, spanRows = 10, chordRows = 14): THREE.BufferGeometry {
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
    const taper = panel.open ? 1 : s === spanRows ? 0.02 : 1 - 0.25 * v ** 6;
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
  const rising = panel.tip.span > panel.root.span;
  for (let s = 0; s < spanRows; s += 1) {
    for (let c = 0; c < ring; c += 1) {
      const a = s * ring + c;
      const b = s * ring + (c + 1) % ring;
      const d = a + ring;
      const e = b + ring;
      // A mirrored panel, or one built downward, has its span reversed: only then does the order flip.
      if ((side > 0 === !panel.vertical) === rising) {
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

/** Noses the cabin into the boom in one line, with no break at the cabin's end. */
const FUSELAGE: Station[] = [
  { x: 3.02, w: 0.015, top: 0.012, bottom: 0.012, z: -0.3, n: 2 },
  { x: 2.96, w: 0.18, top: 0.1, bottom: 0.12, z: -0.3, n: 2 },
  { x: 2.72, w: 0.42, top: 0.27, bottom: 0.3, z: -0.27, n: 2.1 },
  { x: 2.32, w: 0.66, top: 0.52, bottom: 0.46, z: -0.2, n: 2.3 },
  { x: 1.82, w: 0.8, top: 0.84, bottom: 0.56, z: -0.1, n: 2.5 },
  { x: 1.26, w: 0.85, top: 0.99, bottom: 0.68, z: -0.03, n: 2.7 },
  { x: 0.5, w: 0.87, top: 0.92, bottom: 0.8, z: 0.02, n: 3 },
  { x: -0.5, w: 0.86, top: 0.9, bottom: 0.8, z: 0.04, n: 3 },
  { x: -1.3, w: 0.74, top: 0.8, bottom: 0.66, z: 0.1, n: 2.7 },
  { x: -2.1, w: 0.5, top: 0.54, bottom: 0.38, z: 0.26, n: 2.3 },
  { x: -2.9, w: 0.3, top: 0.32, bottom: 0.24, z: 0.38, n: 2 },
  { x: -3.9, w: 0.2, top: 0.21, bottom: 0.18, z: 0.46, n: 2 },
  { x: -5.2, w: 0.145, top: 0.15, bottom: 0.14, z: 0.53, n: 2 },
  { x: -6.5, w: 0.1, top: 0.11, bottom: 0.1, z: 0.6, n: 2 },
  { x: -6.86, w: 0.05, top: 0.07, bottom: 0.06, z: 0.62, n: 2 },
  { x: -6.96, w: 0.008, top: 0.008, bottom: 0.008, z: 0.63, n: 2 },
];

/** The engines and gearbox under one long cowl, sloping into the boom's spine. */
const COWL: Station[] = [
  { x: 1.34, w: 0.012, top: 0.01, bottom: 0.1, z: 0.84, n: 2 },
  { x: 1.1, w: 0.26, top: 0.13, bottom: 0.2, z: 0.84, n: 2.2 },
  { x: 0.6, w: 0.5, top: 0.27, bottom: 0.3, z: 0.86, n: 2.5 },
  { x: 0, w: 0.57, top: 0.37, bottom: 0.34, z: 0.88, n: 2.8 },
  { x: -0.9, w: 0.57, top: 0.36, bottom: 0.34, z: 0.87, n: 2.8 },
  { x: -1.7, w: 0.44, top: 0.27, bottom: 0.3, z: 0.84, n: 2.4 },
  { x: -2.5, w: 0.22, top: 0.17, bottom: 0.22, z: 0.74, n: 2 },
  { x: -3.3, w: 0.08, top: 0.07, bottom: 0.16, z: 0.66, n: 2 },
  { x: -3.9, w: 0.01, top: 0.01, bottom: 0.02, z: 0.62, n: 2 },
];

/** A fairing along the cabin's lower side, which takes in the main wheels. */
const SPONSON: Station[] = [
  { x: 0.42, w: 0.01, top: 0.01, bottom: 0.01, z: -0.52, n: 2 },
  { x: 0.2, w: 0.15, top: 0.13, bottom: 0.16, z: -0.52, n: 2.2 },
  { x: -0.4, w: 0.27, top: 0.23, bottom: 0.27, z: -0.52, n: 2.6 },
  { x: -1, w: 0.28, top: 0.24, bottom: 0.27, z: -0.49, n: 2.6 },
  { x: -1.6, w: 0.15, top: 0.15, bottom: 0.17, z: -0.42, n: 2.2 },
  { x: -2, w: 0.01, top: 0.01, bottom: 0.01, z: -0.34, n: 2 },
];

const PAINT = /* glsl */ `
varying vec3 vBody;
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

/** Signed distance to a rounded box in the side view. */
float sideBox(vec2 p, vec2 centre, vec2 half_, float corner) {
  vec2 d = abs(p - centre) - half_ + corner;
  return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0) - corner;
}

/** Negative inside the glass, in metres of skin. */
float glassField(vec3 b) {
  vec2 p = b.xz;
  float side = 1e3;
  if (abs(b.y) > 0.3) {
    side = min(side, sideBox(p, vec2(0.86, 0.36), vec2(0.27, 0.3), 0.07));
    side = min(side, sideBox(p, vec2(-0.03, 0.36), vec2(0.5, 0.29), 0.08));
    side = min(side, sideBox(p, vec2(-1.02, 0.4), vec2(0.27, 0.22), 0.1));
  }
  // The windscreen wraps from the nose's shoulder to the roof, behind a raked pillar.
  float pillar = (1.2 + 0.5 * (0.92 - b.z)) - b.x;
  float sill = (-0.2 + 0.26 * (2.7 - b.x)) - b.z;
  float screen = max(pillar, sill);
  screen = max(screen, 0.022 - abs(b.y));
  // The chin windows, for looking down at the deck.
  float chin = (abs(b.y) > 0.08 && b.z < 0.0) ? sideBox(p, vec2(2.12, -0.36), vec2(0.38, 0.19), 0.1) : 1e3;
  return min(min(side, screen), chin);
}

/** 1 in the groove of a panel line. */
float panel(vec3 b, float width) {
  float across = abs(b.y) * 0.6 + b.z;
  vec2 size = vec2(0.92, 0.46);
  vec2 cells = vec2(b.x, across) / size;
  float row = floor(cells.y);
  cells.x += paintHash(vec2(row, 4.0)) * 0.8;
  vec2 id = floor(cells);
  vec2 edge = (0.5 - abs(fract(cells) - 0.5)) * size;
  vec2 aa = fwidth(cells) * size;
  // A short section of each seam is missing, so the grid never reads as brickwork.
  float lineX = (1.0 - smoothstep(width, width + aa.x, edge.x)) * step(0.3, paintHash(id + 3.0));
  float lineY = (1.0 - smoothstep(width, width + aa.y, edge.y)) * step(0.5, paintHash(id.yx + 9.0));
  return max(lineX, lineY) * smoothstep(0.07, 0.015, max(aa.x, aa.y));
}
`;

function paintMaterial(): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial({ color: 0xffffff, metalness: 0.05, roughness: 0.34, envMapIntensity: 0.5 });
  material.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vBody;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvBody = position;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", `#include <common>\n${PAINT}`)
      .replace(
        "#include <color_fragment>",
        /* glsl */ `#include <color_fragment>
        vec3 b = vBody;
        vec3 white = vec3(0.80, 0.81, 0.79);
        vec3 navy = vec3(0.022, 0.05, 0.095);
        vec3 signal = vec3(0.56, 0.042, 0.018);
        // The line of the belly colour: low along the cabin, rising up the boom.
        float aa = max(fwidth(b.z), 1e-4);
        float belly = mix(0.5, -0.32, smoothstep(-3.7, -0.5, b.x)) + 0.03 * sin(b.x * 0.9);
        float stripe = 0.15 * smoothstep(-5.2, -1.0, b.x) + 0.07;
        vec3 paint = white;
        paint = mix(paint, signal, 1.0 - smoothstep(belly + stripe - aa, belly + stripe + aa, b.z));
        paint = mix(paint, navy, 1.0 - smoothstep(belly - aa, belly + aa, b.z));
        // The tail is signal colour with a white band, so it reads from far off.
        paint = mix(signal, paint, smoothstep(-5.02, -5.0, b.x));
        paint = mix(paint, white, smoothstep(-5.92, -5.9, b.x) * (1.0 - smoothstep(-5.5, -5.48, b.x)));
        // A matt anti-glare panel ahead of the screen.
        paint = mix(paint, vec3(0.02, 0.022, 0.026), smoothstep(2.28, 2.32, b.x) * smoothstep(-0.2, -0.17, b.z) * step(b.z, 1.0));
        float grime = paintFbm(vec2(b.x * 1.6, b.z * 5.0 + b.y));
        paint *= 0.9 + 0.17 * grime;
        // Soot behind the exhausts.
        float soot = smoothstep(-1.5, -2.3, b.x) * smoothstep(-4.2, -2.6, b.x) * smoothstep(0.35, 0.72, b.z) * (0.55 + 0.45 * grime);
        paint *= 1.0 - 0.72 * soot;
        // The doors, as seams with a groove's shadow.
        float seam = 0.0;
        if (abs(b.y) > 0.3) {
          seam = max(seam, 1.0 - smoothstep(0.003, 0.003 + aa * 1.4, abs(sideBox(b.xz, vec2(-0.03, 0.0), vec2(0.6, 0.79), 0.12))));
          seam = max(seam, 1.0 - smoothstep(0.003, 0.003 + aa * 1.4, abs(sideBox(b.xz, vec2(0.86, 0.0), vec2(0.36, 0.79), 0.12))));
        }
        paint *= 1.0 - 0.75 * max(panel(b, 0.0024), seam);
        float glass = glassField(b);
        float glassAA = max(fwidth(glass), 1e-4);
        float inGlass = 1.0 - smoothstep(-glassAA, glassAA, glass);
        float frame = 1.0 - smoothstep(0.022, 0.022 + glassAA, abs(glass));
        paint = mix(paint, vec3(0.012, 0.014, 0.016), frame);
        paint = mix(paint, vec3(0.012, 0.022, 0.03), inGlass);
        diffuseColor.rgb = paint;
        `,
      )
      .replace(
        "#include <roughnessmap_fragment>",
        /* glsl */ `#include <roughnessmap_fragment>
        roughnessFactor = mix(clamp(roughnessFactor + (paintFbm(vBody.xy * 2.1) - 0.5) * 0.14, 0.15, 1.0), 0.06, inGlass);`,
      )
      .replace(
        "#include <metalnessmap_fragment>",
        /* glsl */ `#include <metalnessmap_fragment>
        metalnessFactor = mix(metalnessFactor, 0.0, inGlass);`,
      )
      .replace(
        "#include <lights_fragment_end>",
        /* glsl */ `// Glass shows the sky far more than a dielectric's four per cent would: it is what makes it glass.
        radiance *= 1.0 + 0.9 * inGlass;
        #include <lights_fragment_end>`,
      );
  };
  return material;
}

const DISC_VERTEX = /* glsl */ `
varying vec2 vPlace;
void main() {
  vPlace = position.xy;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

/**
 * A rotor as a camera sees one: the blades are a smear, darkest just behind each blade. The smear
 * turns with the blades' drawn speed, so the two agree.
 */
const DISC_FRAGMENT = /* glsl */ `
uniform float uAngle;
uniform float uRadius;
uniform float uBlades;
uniform float uRate;
uniform vec3 uTint;
varying vec2 vPlace;
void main() {
  float r = length(vPlace) / uRadius;
  float a = atan(vPlace.y, vPlace.x) - uAngle;
  float saw = fract(a * uBlades / 6.2831853);
  // The blade passes at saw = 1 going upward: behind it the smear thins out.
  float smear = exp(-(1.0 - saw) * 4.0);
  float body = smoothstep(0.1, 0.17, r) * (1.0 - smoothstep(0.985, 1.0, r));
  float banding = 0.86 + 0.14 * sin(r * 58.0);
  float alpha = (0.05 + 0.24 * smear * banding) * body;
  float tip = smoothstep(0.93, 0.945, r) * (1.0 - smoothstep(0.985, 1.0, r));
  vec3 color = mix(vec3(0.03, 0.032, 0.036), uTint, tip);
  gl_FragColor = vec4(color, min(alpha + tip * (0.03 + 0.13 * smear), 1.0) * uRate);
  #include <colorspace_fragment>
}
`;

export interface Helicopter {
  root: THREE.Group;
  /** What the cockpit view hides: all but the rotors. */
  airframe: THREE.Group;
  /** Tilts with the shaft and the flapping; the blades and the disc are inside. */
  rotor: THREE.Group;
  blades: THREE.Group;
  tailRotor: THREE.Group;
  discAngle: { value: number };
  tailAngle: { value: number };
  discRate: { value: number };
  noseGear: THREE.Group;
  leftGear: THREE.Group;
  rightGear: THREE.Group;
  /** The rotating beacon and the steady lights: the game sets their brightness. */
  beacon: THREE.MeshBasicMaterial;
}

function disc(radius: number, blades: number, tint: THREE.ColorRepresentation, angle: { value: number }, rate: { value: number }): THREE.Mesh {
  const mesh = new THREE.Mesh(
    new THREE.CircleGeometry(radius, 96),
    new THREE.ShaderMaterial({
      vertexShader: DISC_VERTEX,
      fragmentShader: DISC_FRAGMENT,
      uniforms: {
        uAngle: angle,
        uRate: rate,
        uRadius: { value: radius },
        uBlades: { value: blades },
        uTint: { value: new THREE.Color(tint) },
      },
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
    }),
  );
  mesh.renderOrder = 4;
  return mesh;
}

function zCylinder(radiusTop: number, radiusBottom: number, height: number, segments = 18): THREE.BufferGeometry {
  const geometry = new THREE.CylinderGeometry(radiusTop, radiusBottom, height, segments);
  geometry.rotateX(Math.PI / 2);
  return geometry;
}

function wheel(metal: THREE.Material, tyre: THREE.Material): THREE.Group {
  const group = new THREE.Group();
  const rubber = new THREE.TorusGeometry(0.15, 0.062, 12, 28);
  rubber.rotateX(Math.PI / 2);
  const hub = new THREE.CylinderGeometry(0.1, 0.1, 0.1, 18);
  group.add(new THREE.Mesh(rubber, tyre), new THREE.Mesh(hub, metal));
  return group;
}

export function buildHelicopter(): Helicopter {
  const paint = paintMaterial();
  const root = new THREE.Group();
  const airframe = new THREE.Group();
  root.add(airframe);

  const dark = new THREE.MeshStandardMaterial({ color: 0x0c0d0f, roughness: 0.85, metalness: 0.2 });
  const metal = new THREE.MeshStandardMaterial({ color: 0x565a5e, roughness: 0.34, metalness: 0.85, envMapIntensity: 0.8 });
  const hot = new THREE.MeshStandardMaterial({ color: 0x2a2523, roughness: 0.5, metalness: 0.7 });
  const tyre = new THREE.MeshStandardMaterial({ color: 0x08090a, roughness: 0.92 });

  const parts: THREE.BufferGeometry[] = [loft(FUSELAGE, 190, 84), loft(COWL, 90, 56)];
  for (const side of [1, -1]) {
    const pod = loft(SPONSON, 46, 36);
    pod.translate(0, side * 0.72, 0);
    parts.push(pod);
  }

  // The fin leans back with a swept tip, the ventral fin guards the tail rotor.
  parts.push(surface({
    root: { le: -5.46, te: -6.62, span: 0.56, up: 0 },
    tip: { le: -6.46, te: -7.02, span: 1.78, up: 0 },
    thickness: 0.2,
    vertical: true,
  }));
  parts.push(surface({
    root: { le: -5.72, te: -6.44, span: 0.5, up: 0 },
    tip: { le: -6.18, te: -6.56, span: -0.3, up: 0 },
    thickness: 0.2,
    vertical: true,
  }, 6, 10));
  for (const side of [1, -1] as const) {
    parts.push(surface({
      root: { le: -4.62, te: -5.32, span: 0.1, up: 0.51 },
      tip: { le: -4.86, te: -5.36, span: 1.26, up: 0.54 },
      thickness: 0.2,
      side,
    }));
    // End plates, trimming the tailplane.
    const plate = surface({
      root: { le: -4.84, te: -5.4, span: 0.28, up: 0 },
      tip: { le: -5.08, te: -5.5, span: 0.86, up: 0 },
      thickness: 0.12,
      vertical: true,
    }, 5, 8);
    plate.translate(0, side * 1.26, 0);
    parts.push(plate);
    const lower = surface({
      root: { le: -4.84, te: -5.4, span: 0.28, up: 0 },
      tip: { le: -5.02, te: -5.36, span: 0.08, up: 0 },
      thickness: 0.12,
      vertical: true,
    }, 3, 8);
    lower.translate(0, side * 1.26, 0);
    parts.push(lower);
  }

  const merged = mergeGeometries(parts.map((g) => {
    const clean = g.index ? g.toNonIndexed() : g;
    clean.deleteAttribute("uv");
    return clean;
  }));
  const body = new THREE.Mesh(merged, paint);
  body.castShadow = true;
  body.receiveShadow = true;
  airframe.add(body);

  // Two exhausts, angled out of the cowl's flanks.
  for (const side of [1, -1]) {
    const pipe = new THREE.Mesh(zCylinder(0.15, 0.17, 0.42, 22), hot);
    pipe.rotation.set(0, Math.PI / 2 - 0.12, 0);
    pipe.rotateX(side * 0.2);
    pipe.position.set(-1.74, side * 0.3, 0.94);
    pipe.scale.y = 0.72;
    airframe.add(pipe);
    const throat = new THREE.Mesh(new THREE.CircleGeometry(0.13, 22), dark);
    throat.rotation.y = -Math.PI / 2;
    throat.position.set(-1.96, side * 0.335, 0.92);
    airframe.add(throat);
    // The intakes, behind the screen's top corners.
    const intake = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.02, 0.09), dark);
    intake.position.set(0.42, side * 0.5, 0.88);
    intake.rotation.x = side * 0.3;
    airframe.add(intake);
    // Step and sill.
    const rail = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.05, 0.03), metal);
    rail.position.set(-0.02, side * 0.87, -0.42);
    airframe.add(rail);
    const handle = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.02, 0.025), metal);
    handle.position.set(0.72, side * 0.885, 0.02);
    airframe.add(handle);
  }

  // The pylon the mast comes out of, faired into the cowl.
  const pylon = new THREE.Mesh(zCylinder(0.15, 0.3, 0.36, 28), metal);
  pylon.position.set(0.04, 0, 1.28);
  pylon.rotation.y = SHAFT_TILT;
  airframe.add(pylon);

  // The pitot probes, the antennas and the lights.
  for (const side of [1, -1]) {
    const pitot = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.012, 0.3, 8), metal);
    pitot.rotation.z = Math.PI / 2;
    pitot.position.set(2.62, side * 0.36, 0.08);
    airframe.add(pitot);
  }
  const whip = new THREE.Mesh(new THREE.CylinderGeometry(0.003, 0.012, 0.8, 6), dark);
  whip.position.set(-2.8, 0, 1.04);
  whip.rotation.z = 0.7;
  airframe.add(whip);
  const blade = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.012, 0.24), dark);
  blade.position.set(-0.3, 0, -0.84);
  airframe.add(blade);

  const glow = (color: number, size: number, x: number, y: number, z: number): THREE.MeshBasicMaterial => {
    const material = new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(6), toneMapped: false });
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(size, 12, 10), material);
    mesh.position.set(x, y, z);
    airframe.add(mesh);
    return material;
  };
  glow(0xff2010, 0.03, -0.05, 1.27, -0.1);
  glow(0x20ff50, 0.03, -0.05, -1.27, -0.1);
  glow(0xffffff, 0.026, -6.98, 0, 0.72);
  const beacon = glow(0xff2510, 0.04, -6.6, 0, 1.82);
  const lamp = new THREE.Mesh(new THREE.CircleGeometry(0.07, 18), new THREE.MeshBasicMaterial({ color: new THREE.Color(5, 4.8, 4.2), toneMapped: false }));
  lamp.position.set(2.2, 0.1, -0.76);
  lamp.rotation.set(Math.PI, 0, 0);
  airframe.add(lamp);

  // The gear: fixed in the flight model, folded away in the picture at speed.
  const leg = (x: number, y: number, z: number): THREE.Group => {
    const hinge = new THREE.Group();
    hinge.position.set(x, y, z);
    airframe.add(hinge);
    return hinge;
  };
  const strut = (length: number): THREE.Mesh => {
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.045, length, 12), metal);
    mesh.rotation.x = Math.PI / 2;
    mesh.position.z = -length / 2;
    mesh.castShadow = true;
    return mesh;
  };
  const noseGear = leg(1.9, 0, -0.56);
  noseGear.add(strut(0.56));
  const nosePair = wheel(metal, tyre);
  nosePair.position.z = -0.56;
  noseGear.add(nosePair);
  const leftGear = leg(-0.8, 0.72, -0.6);
  const rightGear = leg(-0.8, -0.72, -0.6);
  for (const [gear, side] of [[leftGear, 1], [rightGear, -1]] as const) {
    const arm = strut(0.56);
    arm.rotation.x = Math.PI / 2 + side * 0.39;
    arm.position.set(0, side * 0.11, -0.26);
    gear.add(arm);
    const round = wheel(metal, tyre);
    round.position.set(0, side * 0.23, -0.52);
    gear.add(round);
  }
  for (const gear of [noseGear, leftGear, rightGear]) {
    gear.traverse((object) => {
      object.castShadow = true;
    });
  }

  // The main rotor, in the plane of its tips.
  const rotor = new THREE.Group();
  rotor.position.set(HUB.x, 0, HUB.z);
  root.add(rotor);
  const blades = new THREE.Group();
  rotor.add(blades);
  const hubParts = [
    zCylinder(0.09, 0.11, 0.42),
    zCylinder(0.27, 0.3, 0.14, 26),
    zCylinder(0.12, 0.2, 0.09),
  ];
  hubParts[0].translate(0, 0, -0.02);
  hubParts[1].translate(0, 0, 0.05);
  hubParts[2].translate(0, 0, 0.15);
  const hub = new THREE.Mesh(mergeGeometries(hubParts.map((g) => g.toNonIndexed())), metal);
  hub.castShadow = true;
  blades.add(hub);
  const bladePaint = new THREE.MeshStandardMaterial({ color: 0x17181b, roughness: 0.42, metalness: 0.15 });
  const tipPaint = new THREE.MeshStandardMaterial({ color: 0xd8a11c, roughness: 0.5 });
  const span = surface({
    root: { le: 0.17, te: -0.17, span: 0.44, up: 0 },
    tip: { le: 0.17, te: -0.17, span: ROTOR_RADIUS - 0.42, up: 0 },
    thickness: 0.2,
    open: true,
  }, 4, 10);
  const tip = surface({
    root: { le: 0.17, te: -0.17, span: ROTOR_RADIUS - 0.42, up: 0 },
    tip: { le: 0.1, te: -0.17, span: ROTOR_RADIUS, up: 0 },
    thickness: 0.2,
  }, 8, 10);
  const grip = zCylinder(0.05, 0.06, 0.44, 12);
  grip.rotateX(Math.PI / 2);
  grip.translate(0, 0.36, 0);
  for (let i = 0; i < 4; i += 1) {
    const arm = new THREE.Group();
    arm.rotation.z = (i * Math.PI) / 2;
    arm.position.z = 0.05;
    const inner = new THREE.Mesh(span, bladePaint);
    const outer = new THREE.Mesh(tip, tipPaint);
    inner.castShadow = true;
    arm.add(inner, outer, new THREE.Mesh(grip, metal));
    blades.add(arm);
  }
  const discAngle = { value: 0 };
  const discRate = { value: 1 };
  const main = disc(ROTOR_RADIUS, 4, 0xd8c070, discAngle, discRate);
  main.position.z = 0.05;
  rotor.add(main);

  // The tail rotor turns about y, on the left of the fin.
  const tailRotor = new THREE.Group();
  tailRotor.position.set(TAIL_HUB.x, TAIL_HUB.y, TAIL_HUB.z);
  root.add(tailRotor);
  const tailBlades = new THREE.Group();
  tailRotor.add(tailBlades);
  const tailHub = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.09, 0.2, 14), metal);
  tailHub.position.y = -0.06;
  tailBlades.add(tailHub);
  const tailSpan = new THREE.BoxGeometry(TAIL_RADIUS * 2, 0.02, 0.15);
  tailBlades.add(new THREE.Mesh(tailSpan, bladePaint));
  const tailAngle = { value: 0 };
  const tailDisc = disc(TAIL_RADIUS, 2, 0x8a8a8a, tailAngle, discRate);
  tailDisc.rotation.x = -Math.PI / 2;
  tailDisc.position.y = 0.012;
  tailRotor.add(tailDisc);
  const gearbox = new THREE.Mesh(new THREE.SphereGeometry(0.13, 16, 12), metal);
  gearbox.position.set(TAIL_HUB.x + 0.02, 0.06, TAIL_HUB.z);
  gearbox.scale.set(1.3, 0.8, 1);
  airframe.add(gearbox);

  return { root, airframe, rotor, blades, tailRotor, discAngle, tailAngle, discRate, noseGear, leftGear, rightGear, beacon };
}

const axisX = new THREE.Vector3(1, 0, 0);
const axisY = new THREE.Vector3(0, 1, 0);
const tiltPitch = new THREE.Quaternion();
const tiltRoll = new THREE.Quaternion();

/** The rotor's disc from the shaft and the FMU's flapping, in radians: a1 aft, b1 to the right. */
export function poseRotor(heli: Helicopter, a1: number, b1: number): void {
  tiltPitch.setFromAxisAngle(axisY, SHAFT_TILT - a1);
  tiltRoll.setFromAxisAngle(axisX, b1);
  heli.rotor.quaternion.copy(tiltRoll).multiply(tiltPitch);
}

/** Turns the blades: `azimuth` in radians. */
export function spinRotors(heli: Helicopter, azimuth: number, tailAzimuth: number): void {
  heli.blades.rotation.z = azimuth;
  heli.discAngle.value = azimuth;
  heli.tailRotor.children[0].rotation.y = tailAzimuth;
  heli.tailAngle.value = tailAzimuth;
}

/** Folds the gear: 0 down, 1 away. */
export function poseGear(heli: Helicopter, away: number): void {
  const a = away * away * (3 - 2 * away);
  heli.noseGear.rotation.y = -a * 1.55;
  heli.leftGear.rotation.x = a * 1.5;
  heli.rightGear.rotation.x = -a * 1.5;
}
