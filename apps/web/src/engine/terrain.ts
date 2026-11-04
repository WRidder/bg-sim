/**
 * Terrain: concentric rings of quads around the camera, displaced from the heightfield in the
 * vertex shader. The rings snap to their own grid, so the land does not swim as the camera moves.
 * All surface colour is computed per pixel from height, slope and noise, so it needs no textures
 * and stays sharp at any altitude.
 */

import * as THREE from "three";
import { ATMOSPHERE_GLSL, type AtmosphereUniforms } from "./atmosphere";
import { CLOUD_MAP_GLSL } from "./clouds";
import type { Heightfield } from "./heightfield";

const VERTEX = /* glsl */ `
uniform sampler2D uField;
uniform float uExtent;
uniform vec3 uSnap;
uniform float uBaseCell;
in float aLevel;
out vec3 vWorld;
out float vMorph;

vec4 field(vec2 xz) {
  // north = -z, east = x; the field's u runs east and v north
  vec2 uv = vec2(xz.x, -xz.y) / uExtent + 0.5;
  return textureLod(uField, uv, 0.0);
}

void main() {
  float cell = uBaseCell * pow(2.0, aLevel);
  vec2 snapped = floor(uSnap.xz / (cell * 2.0) + 0.5) * cell * 2.0;
  vec2 xz = position.xz + snapped;
  float h = field(xz).r;
  vec2 uv = vec2(xz.x, -xz.y) / uExtent;
  float inside = step(abs(uv.x), 0.499) * step(abs(uv.y), 0.499);
  h = mix(-60.0, h, inside);
  vWorld = vec3(xz.x, h, xz.y);
  gl_Position = projectionMatrix * viewMatrix * vec4(vWorld, 1.0);
}
`;

const FRAGMENT = /* glsl */ `
precision highp float;
${ATMOSPHERE_GLSL}
${CLOUD_MAP_GLSL}
uniform sampler2D uField;
uniform float uExtent;
uniform float uTexel;
in vec3 vWorld;
out vec4 fragColor;

float hash(vec2 p) {
  vec3 q = fract(vec3(p.xyx) * 0.1031);
  q += dot(q, q.yzx + 33.33);
  return fract((q.x + q.y) * q.z);
}
float vnoise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}
float fbm(vec2 p, int octaves) {
  float sum = 0.0, a = 0.5;
  for (int i = 0; i < octaves; i++) {
    sum += a * vnoise(p);
    p = mat2(1.6, 1.2, -1.2, 1.6) * p;
    a *= 0.5;
  }
  return sum;
}

vec4 field(vec2 xz) { return textureLod(uField, vec2(xz.x, -xz.y) / uExtent + 0.5, 0.0); }

void main() {
  vec2 xz = vWorld.xz;
  float distanceToEye = length(vWorld - cameraPosition);
  vec4 here = field(xz);
  float e = uTexel * uExtent;
  float hx = field(xz + vec2(e, 0.0)).r - field(xz - vec2(e, 0.0)).r;
  float hz = field(xz + vec2(0.0, e)).r - field(xz - vec2(0.0, e)).r;
  vec3 normal = normalize(vec3(-hx, 2.0 * e, -hz));

  // Fine relief that exists only in the light: it fades before it could shimmer.
  float detail = smoothstep(9000.0, 400.0, distanceToEye);
  if (detail > 0.0) {
    float s = 0.018;
    float n0 = fbm(xz * s, 5);
    float nx = fbm((xz + vec2(6.0, 0.0)) * s, 5);
    float nz = fbm((xz + vec2(0.0, 6.0)) * s, 5);
    normal = normalize(normal + detail * 0.9 * vec3(n0 - nx, 0.0, n0 - nz));
  }

  float height = here.r;
  float mask = here.b;
  float slope = 1.0 - normal.y;
  float wide = fbm(xz * 0.00035, 4);
  float mid = fbm(xz * 0.0031, 4);
  float fine = fbm(xz * 0.041, 3);

  vec3 sand = vec3(0.56, 0.50, 0.38);
  vec3 grass = mix(vec3(0.115, 0.15, 0.065), vec3(0.20, 0.205, 0.10), smoothstep(0.25, 0.65, wide * 0.6 + mid * 0.4));
  vec3 forest = mix(vec3(0.030, 0.055, 0.028), vec3(0.052, 0.078, 0.036), mid);
  vec3 rock = mix(vec3(0.17, 0.155, 0.14), vec3(0.33, 0.30, 0.26), clamp(mid * 1.3 * (0.6 + fine * 0.8), 0.0, 1.0));
  vec3 snow = vec3(0.86, 0.89, 0.93);

  float forestLine = 1100.0 + 300.0 * wide;
  float forestAmount = smoothstep(0.34, 0.74, mid * 0.7 + wide * 0.55 + (fine - 0.25) * 0.2) * smoothstep(forestLine, forestLine - 300.0, height);
  vec3 color = mix(grass, forest, forestAmount * smoothstep(0.34, 0.18, slope));
  // Fields near the coast: patches that follow no contour.
  float farmland = smoothstep(420.0, 120.0, height) * smoothstep(0.15, 0.05, slope) * smoothstep(0.42, 0.55, fbm(xz * 0.00022 + 9.0, 3));
  if (farmland > 0.0) {
    vec2 plot = floor(xz / 340.0 + vec2(fbm(xz * 0.002, 2) * 1.2));
    float tone = hash(plot);
    vec3 crop = mix(vec3(0.30, 0.28, 0.13), mix(vec3(0.15, 0.20, 0.08), vec3(0.34, 0.29, 0.19), step(0.6, tone)), step(0.3, tone));
    color = mix(color, crop, farmland * 0.6);
  }
  color = mix(color, rock, smoothstep(0.13, 0.30, slope + (mid - 0.5) * 0.12));
  float snowLine = 1320.0 + 220.0 * wide + (mid - 0.5) * 240.0;
  color = mix(color, snow, smoothstep(snowLine, snowLine + 140.0, height) * smoothstep(0.42, 0.22, slope));
  color = mix(color, sand, smoothstep(5.0, 1.5, height + (mid - 0.5) * 5.0));
  color = mix(color, mix(vec3(0.40, 0.40, 0.37), vec3(0.28, 0.27, 0.25), fine), mask);
  color *= 0.72 + 0.56 * fine * detail + 0.28 * (1.0 - detail);

  float clouds = 1.0 - 0.62 * cloudWeather(xz + uSunDir.xz / max(uSunDir.y, 0.15) * 2200.0);
  float sunlight = max(dot(normal, uSunDir), 0.0) * here.g * clouds;
  vec3 ambient = skyRadiance(normalize(vec3(normal.x, 1.0, normal.z))) * 1.05;
  ambient *= 0.55 + 0.45 * here.g;
  vec3 lit = color * (uSunColor * sunlight * 0.62 + ambient * 0.8);

  fragColor = vec4(aerial(lit, vWorld, cameraPosition), 1.0);
}
`;

/** One level of rings: a square of quads with a hole for the finer level inside it. */
function ring(positions: number[], levels: number[], indices: number[], level: number, half: number, cell: number): void {
  const side = half * 2 + 1;
  const first = positions.length / 3;
  for (let z = -half; z <= half; z += 1) {
    for (let x = -half; x <= half; x += 1) {
      positions.push(x * cell, 0, z * cell);
      levels.push(level);
    }
  }
  // The rings overlap: each snaps to its own grid, so a tight fit would leave gaps at the seams.
  const hole = level === 0 ? -1 : half / 2 - 2;
  for (let z = 0; z < side - 1; z += 1) {
    for (let x = 0; x < side - 1; x += 1) {
      const gx = x - half;
      const gz = z - half;
      if (gx >= -hole && gx < hole && gz >= -hole && gz < hole) {
        continue;
      }
      const a = first + z * side + x;
      const b = a + 1;
      const c = a + side;
      const d = c + 1;
      indices.push(a, c, b, b, c, d);
    }
  }
}

export interface TerrainOptions {
  baseCell?: number;
  half?: number;
  levels?: number;
}

export class Terrain {
  readonly mesh: THREE.Mesh;
  private readonly snap = new THREE.Vector3();

  constructor(
    field: Heightfield,
    atmosphere: AtmosphereUniforms,
    clouds: Record<"uCover" | "uDrift", THREE.IUniform>,
    options: TerrainOptions = {},
  ) {
    const baseCell = options.baseCell ?? 12;
    const half = options.half ?? 64;
    const levels = options.levels ?? 8;
    const positions: number[] = [];
    const level: number[] = [];
    const indices: number[] = [];
    for (let i = 0; i < levels; i += 1) {
      ring(positions, level, indices, i, half, baseCell * 2 ** i);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute("aLevel", new THREE.Float32BufferAttribute(level, 1));
    geometry.setIndex(indices);
    const material = new THREE.ShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: VERTEX,
      fragmentShader: FRAGMENT,
      uniforms: {
        ...atmosphere,
        ...clouds,
        uField: { value: field.texture },
        uExtent: { value: field.extent },
        uTexel: { value: 1 / field.size },
        uSnap: { value: this.snap },
        uBaseCell: { value: baseCell },
      },
    });
    this.mesh = new THREE.Mesh(geometry, material);
    this.mesh.frustumCulled = false;
  }

  follow(camera: THREE.Vector3): void {
    this.snap.copy(camera);
  }
}
