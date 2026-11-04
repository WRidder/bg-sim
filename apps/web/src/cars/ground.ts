/**
 * What is under the wheels. A flight game sees the ground from a kilometre up; this one sees it from
 * a metre, so the ground has real texture: one tiling detail map, mipmapped, at several scales, which
 * stays sharp at the bottom of the screen and calm at the horizon where per-pixel noise would
 * shimmer. Two meshes share one idea of the natural ground: the terrain, and a ribbon along the
 * route that adds the road, the paint, the kerbs, the gravel. The ribbon's far edge fades into the
 * terrain with no seam, because both draw the same grass.
 */

import * as THREE from "three";
import { ATMOSPHERE_GLSL, type AtmosphereUniforms } from "../engine/atmosphere";
import { CLOUD_MAP_GLSL } from "../engine/clouds";
import type { Heightfield } from "../engine/heightfield";
import { hash2 } from "../engine/noise";
import { roadHeight } from "./land";
import type { Line } from "./line";
import type { Track } from "./track";

/** Value noise on a lattice that wraps, so the map tiles. */
function periodic(x: number, y: number, period: number, seed: number): number {
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  const fx = x - ix;
  const fy = y - iy;
  const u = fx * fx * (3 - 2 * fx);
  const v = fy * fy * (3 - 2 * fy);
  const at = (i: number, j: number): number => hash2(((i % period) + period) % period, ((j % period) + period) % period, seed);
  const a = at(ix, iy);
  const b = at(ix + 1, iy);
  const c = at(ix, iy + 1);
  const d = at(ix + 1, iy + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}

/**
 * R: aggregate, a fine stipple. G: blotches over a wide range of scales. B: rounded stones.
 * A: blades, short strokes in all directions.
 */
export function detailTexture(renderer: THREE.WebGLRenderer): THREE.DataTexture {
  const size = 1024;
  const data = new Uint8Array(size * size * 4);
  const clump = new Float32Array(size * size);
  for (let j = 0; j < size; j += 1) {
    for (let i = 0; i < size; i += 1) {
      let sum = 0;
      let amplitude = 0.5;
      let period = 8;
      for (let octave = 0; octave < 6; octave += 1) {
        sum += amplitude * periodic((i / size) * period, (j / size) * period, period, 21 + octave);
        amplitude *= 0.55;
        period *= 2;
      }
      clump[j * size + i] = sum;
    }
  }
  // Stones: the distance to scattered points, on a grid that wraps.
  const cells = 72;
  const cellSize = size / cells;
  const centers = new Float32Array(cells * cells * 3);
  for (let c = 0; c < cells * cells; c += 1) {
    centers[c * 3] = hash2(c, 3, 31);
    centers[c * 3 + 1] = hash2(c, 4, 31);
    centers[c * 3 + 2] = 0.55 + 0.45 * hash2(c, 5, 31);
  }
  const stones = new Float32Array(size * size);
  for (let j = 0; j < size; j += 1) {
    for (let i = 0; i < size; i += 1) {
      const gx = i / cellSize;
      const gy = j / cellSize;
      const ix = Math.floor(gx);
      const iy = Math.floor(gy);
      let top = 0;
      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          const c = (((iy + dy + cells) % cells) * cells + ((ix + dx + cells) % cells)) * 3;
          const px = ix + dx + centers[c] - gx;
          const py = iy + dy + centers[c + 1] - gy;
          top = Math.max(top, centers[c + 2] * (1 - Math.min(1, (px * px + py * py) * 2.1)));
        }
      }
      stones[j * size + i] = top;
    }
  }
  const blades = new Float32Array(size * size);
  for (let stroke = 0; stroke < 90000; stroke += 1) {
    const x = hash2(stroke, 1, 41) * size;
    const y = hash2(stroke, 2, 41) * size;
    const angle = hash2(stroke, 3, 41) * Math.PI;
    const long = 5 + 12 * hash2(stroke, 4, 41);
    const value = 0.25 + 0.75 * hash2(stroke, 5, 41);
    for (let t = 0; t < long; t += 0.8) {
      const i = Math.floor(x + Math.cos(angle) * t + size) % size;
      const j = Math.floor(y + Math.sin(angle) * t + size) % size;
      blades[j * size + i] = Math.max(blades[j * size + i], value * (1 - (t / long) * 0.6));
    }
  }
  for (let at = 0; at < size * size; at += 1) {
    const fine = hash2(at % size, Math.floor(at / size), 51);
    const pip = fine > 0.86 ? 1 : fine * 0.62;
    data[at * 4] = Math.round(pip * 255);
    data[at * 4 + 1] = Math.round(Math.min(1, clump[at] * 1.05) * 255);
    data[at * 4 + 2] = Math.round(stones[at] * 255);
    data[at * 4 + 3] = Math.round(blades[at] * 255);
  }
  const texture = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.magFilter = THREE.LinearFilter;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.generateMipmaps = true;
  texture.anisotropy = Math.min(16, renderer.capabilities.getMaxAnisotropy());
  texture.needsUpdate = true;
  return texture;
}

/** Natural ground and the light on it, in both the terrain and the ribbon. */
const SHARED = /* glsl */ `
${ATMOSPHERE_GLSL}
${CLOUD_MAP_GLSL}
uniform sampler2D uField;
uniform sampler2D uDetail;
uniform float uExtent;
uniform float uUvScale;
uniform float uTexel;
uniform float uStyle;

vec4 field(vec2 xz) { return textureLod(uField, vec2(xz.x, -xz.y) / uExtent * uUvScale + 0.5, 0.0); }

struct Layers { vec4 a; vec4 b; vec4 c; float near; };

Layers layers(vec2 xz, float eye) {
  Layers l;
  l.a = texture(uDetail, xz * 0.21);
  l.b = texture(uDetail, xz * 0.047 + 0.37);
  l.c = texture(uDetail, xz * 0.0062 + 0.11);
  l.near = smoothstep(70.0, 6.0, eye);
  return l;
}

/** The ground's own colour. wild is 1 far from the circuit, 0 on what is kept short. */
vec3 natural(vec2 xz, Layers l, float height, float slope, float wild, out float bump) {
  float blotch = l.c.g * 0.6 + l.b.g * 0.4;
  float blades = l.a.a * 0.7 + l.b.a * 0.3;
  vec3 color;
  if (uStyle < 0.5) {
    vec3 lush = mix(vec3(0.060, 0.105, 0.034), vec3(0.135, 0.175, 0.052), smoothstep(0.32, 0.66, blotch));
    vec3 dry = mix(vec3(0.200, 0.190, 0.085), vec3(0.300, 0.265, 0.135), l.b.g);
    vec3 grass = mix(lush, dry, smoothstep(0.50, 0.70, l.c.g * 0.7 + l.b.g * 0.42) * (0.25 + 0.75 * wild));
    grass *= 0.60 + 0.95 * blades * mix(0.55, 1.0, l.near);
    grass = mix(grass, grass * vec3(0.72, 0.62, 0.55), smoothstep(0.62, 0.45, l.a.g) * 0.5);
    vec3 rock = mix(vec3(0.16, 0.15, 0.135), vec3(0.34, 0.31, 0.27), smoothstep(0.3, 0.7, l.b.g * 0.6 + l.a.g * 0.4));
    vec3 sand = mix(vec3(0.46, 0.40, 0.28), vec3(0.60, 0.54, 0.41), l.a.g);
    color = mix(grass, rock, smoothstep(0.12, 0.26, slope + (l.b.g - 0.5) * 0.12));
    color = mix(color, sand, smoothstep(4.5, 1.8, height + (l.b.g - 0.5) * 3.0));
    bump = blades * 0.5;
  } else {
    vec3 dust = mix(vec3(0.335, 0.205, 0.115), vec3(0.50, 0.335, 0.20), smoothstep(0.3, 0.7, blotch));
    dust *= 0.82 + 0.3 * l.a.g + 0.3 * (l.a.r - 0.5) * l.near;
    // Stones show only in the patches where the fine soil has blown away.
    float pebbles = smoothstep(0.62, 0.8, l.a.b) * smoothstep(0.52, 0.66, l.b.g) * l.near;
    dust = mix(dust, vec3(0.20, 0.16, 0.13) * (0.5 + 0.9 * l.a.b), pebbles * 0.8);
    vec3 scrub = mix(vec3(0.115, 0.125, 0.060), vec3(0.205, 0.190, 0.095), l.a.a);
    float patches = smoothstep(0.52, 0.66, l.b.g * 0.65 + l.c.g * 0.4) * wild;
    vec3 strata = mix(vec3(0.42, 0.22, 0.12), vec3(0.60, 0.40, 0.25), 0.5 + 0.5 * sin(height * 0.62 + l.b.g * 3.0));
    color = mix(dust, scrub, patches * (0.45 + 0.55 * blades));
    color = mix(color, strata * (0.75 + 0.5 * l.a.g), smoothstep(0.13, 0.28, slope));
    bump = l.a.b * 0.6;
  }
  return color;
}

/** Sun, sky and cloud shadow on a surface, then the air between it and the eye. */
vec3 shade(vec3 color, vec3 normal, vec4 here, vec3 world, float gloss) {
  float clouds = 1.0 - 0.62 * cloudWeather(world.xz + uSunDir.xz / max(uSunDir.y, 0.15) * 2200.0);
  float light = here.g * clouds;
  float sunlight = max(dot(normal, uSunDir), 0.0) * light;
  vec3 ambient = skyRadiance(normalize(vec3(normal.x, 1.0, normal.z))) * 1.05 * (0.6 + 0.4 * here.g);
  // Shade is lit by the whole sky and the bright ground round it: never the black of a sharp print.
  vec3 lit = color * (uSunColor * sunlight * 0.62 + ambient * 0.8 + (1.0 - smoothstep(0.0, 0.4, sunlight)) * vec3(0.13, 0.14, 0.16));
  if (gloss > 0.0) {
    // A worn surface towards a low sun: broad, weak and only at a grazing view.
    vec3 view = normalize(cameraPosition - world);
    vec3 half_ = normalize(view + uSunDir);
    float sheen = pow(max(dot(normal, half_), 0.0), 26.0) * (0.04 + 0.96 * pow(1.0 - max(dot(view, half_), 0.0), 5.0));
    lit += uSunColor * sheen * light * gloss;
    vec3 sky = skyRadiance(normalize(reflect(-view, normal)));
    lit += sky * gloss * 0.1 * pow(1.0 - max(view.y, 0.0), 4.0);
  }
  return aerial(lit, world, cameraPosition);
}

vec3 groundNormal(vec2 xz, Layers l, float bump, out float slope) {
  float e = uTexel * uExtent;
  float hx = field(xz + vec2(e, 0.0)).r - field(xz - vec2(e, 0.0)).r;
  float hz = field(xz + vec2(0.0, e)).r - field(xz - vec2(0.0, e)).r;
  vec3 normal = normalize(vec3(-hx, 2.0 * e, -hz));
  slope = 1.0 - normal.y;
  float dx = l.a.g - texture(uDetail, xz * 0.21 + vec2(0.0015, 0.0)).g;
  float dz = l.a.g - texture(uDetail, xz * 0.21 + vec2(0.0, 0.0015)).g;
  return normalize(normal + vec3(dx, 0.0, dz) * (0.8 + bump) * l.near * 2.2);
}
`;

const TERRAIN_VERTEX = /* glsl */ `
uniform sampler2D uField;
uniform float uExtent;
uniform float uUvScale;
uniform vec3 uSnap;
uniform float uBaseCell;
in float aLevel;
out vec3 vWorld;

void main() {
  float cell = uBaseCell * pow(2.0, aLevel);
  vec2 snapped = floor(uSnap.xz / (cell * 2.0) + 0.5) * cell * 2.0;
  vec2 xz = position.xz + snapped;
  vec4 f = textureLod(uField, vec2(xz.x, -xz.y) / uExtent * uUvScale + 0.5, 0.0);
  vec2 uv = vec2(xz.x, -xz.y) / uExtent;
  float inside = step(abs(uv.x), 0.499) * step(abs(uv.y), 0.499);
  // Under the ribbon the mesh ducks away; its light comes from the field, which has no such step.
  float h = mix(-60.0, f.r - 0.4 * f.a, inside);
  vWorld = vec3(xz.x, h, xz.y);
  gl_Position = projectionMatrix * viewMatrix * vec4(vWorld, 1.0);
}
`;

const TERRAIN_FRAGMENT = /* glsl */ `
precision highp float;
${SHARED}
in vec3 vWorld;
out vec4 fragColor;

void main() {
  vec2 xz = vWorld.xz;
  float eye = length(vWorld - cameraPosition);
  vec4 here = field(xz);
  Layers l = layers(xz, eye);
  float bump = 0.0;
  float slope = 0.0;
  vec3 normal = groundNormal(xz, l, 0.3, slope);
  vec3 color = natural(xz, l, here.r, slope, here.b, bump);
  // Far away the mesh is too coarse to stay under the ribbon, so it wears the road's colour.
  vec3 road = uStyle < 0.5 ? vec3(0.10, 0.10, 0.105) : vec3(0.42, 0.29, 0.18);
  color = mix(color, road, (1.0 - here.b) * smoothstep(0.5, 0.9, here.a));
  fragColor = vec4(shade(color, normal, here, vWorld, 0.0), 1.0);
}
`;

const RIBBON_VERTEX = /* glsl */ `
in vec2 aRoad;
in vec4 aSides;
in vec4 aMore;
in vec2 aEdge;
centroid out vec3 vWorld;
centroid out vec2 vRoad;
centroid out vec4 vSides;
centroid out vec4 vMore;
centroid out vec2 vEdge;

void main() {
  vRoad = aRoad;
  vSides = aSides;
  vMore = aMore;
  vEdge = aEdge;
  vWorld = position;
  gl_Position = projectionMatrix * viewMatrix * vec4(position, 1.0);
}
`;

const RIBBON_FRAGMENT = /* glsl */ `
precision highp float;
${SHARED}
uniform float uHalf;
uniform float uLength;
uniform float uStripe;
uniform float uGrid;
uniform float uLine;
centroid in vec3 vWorld;
centroid in vec2 vRoad;
centroid in vec4 vSides;
centroid in vec4 vMore;
centroid in vec2 vEdge;
out vec4 fragColor;

/** A band of width w from a, softened by the pixel. */
float band(float x, float a, float w, float aa) {
  return smoothstep(a - aa, a + aa, x) * (1.0 - smoothstep(a + w - aa, a + w + aa, x));
}

/** A square wave of the given period, its transitions softened by the pixel and gone to grey far off. */
float stripes(float x, float period, float aa) {
  float t = fract(x / period);
  float w = aa / period;
  if (w > 0.25) return 0.5;
  return smoothstep(0.0 - w, w, t) * (1.0 - smoothstep(0.5 - w, 0.5 + w, t)) + smoothstep(1.0 - w, 1.0 + w, t);
}

vec3 asphalt(vec2 xz, Layers l, float s, float d, float rubber, out float gloss) {
  float stones = l.a.r * 0.62 + texture(uDetail, xz * 0.83 + 0.2).r * 0.38;
  float wide = l.c.g * 0.6 + l.b.g * 0.4;
  vec3 color = mix(vec3(0.052, 0.052, 0.056), vec3(0.135, 0.132, 0.130), smoothstep(0.30, 0.70, wide));
  color *= 0.72 + 0.56 * mix(0.5, stones, l.near * 0.9 + 0.1);
  color += vec3(0.11, 0.105, 0.095) * pow(stones, 3.0) * l.near;
  // Laid in strips: the machine's width shows as faint seams and a change of tone.
  float lane = floor((d + uHalf) / 3.9);
  color *= 0.97 + 0.06 * fract(sin(lane * 12.9) * 43.7);
  // Sealed cracks run where the strips of a resurfacing meet: a thin wandering line, on and off.
  float wander = (texture(uDetail, vec2(s * 0.0071, lane * 0.37)).g - 0.5) * 0.9 + (texture(uDetail, vec2(s * 0.031, lane * 0.11)).g - 0.5) * 0.18;
  float seam = abs(fract((d + uHalf + wander) / 3.9 + 0.5) - 0.5) * 3.9;
  float aa = fwidth(d) + 0.002;
  float tar = (1.0 - smoothstep(0.02, 0.02 + aa, seam)) * smoothstep(0.56, 0.6, texture(uDetail, vec2(s * 0.0043, lane * 0.21 + 0.3)).g);
  tar *= 1.0 - smoothstep(0.03, 0.09, aa);
  color = mix(color, vec3(0.02), tar * 0.75);
  // Repair patches: squares of newer, darker surface.
  float bin = floor(s / 43.0);
  float which = fract(sin(bin * 91.7) * 311.3);
  if (which > 0.62) {
    float centre = (fract(which * 7.1) - 0.5) * uHalf * 1.2;
    float half_ = 1.6 + 2.4 * fract(which * 13.0);
    float inside = (1.0 - smoothstep(half_ - 0.03, half_ + 0.03, abs(d - centre))) * (1.0 - smoothstep(4.0 + 7.0 * which - 0.03, 4.0 + 7.0 * which + 0.03, abs(s - (bin + 0.5) * 43.0)));
    color = mix(color, color * 0.68, inside);
  }
  // Rubber: dark grooves along the line, drawn out by the texture's stretch along the road.
  float streak = texture(uDetail, vec2(d * 0.4, s * 0.011)).g;
  float fine = texture(uDetail, vec2(d * 1.4, s * 0.024)).g;
  float marks = smoothstep(0.42, 0.62, streak * 0.6 + fine * 0.4);
  color *= 1.0 - rubber * (0.26 + 0.42 * marks);
  gloss = 0.32 + 0.3 * rubber;
  return color;
}

void main() {
  vec2 xz = vWorld.xz;
  float eye = length(vWorld - cameraPosition);
  vec4 here = field(xz);
  Layers l = layers(xz, eye);
  float s = vRoad.x;
  float d = vRoad.y;
  float a = abs(d);
  float aa = max(fwidth(d), 0.002) * 0.75;
  float aas = max(fwidth(s), 0.002) * 0.75;
  float left = d > 0.0 ? 1.0 : 0.0;
  float kerb = mix(vSides.y, vSides.x, left);
  float paved = mix(vSides.w, vSides.z, left);
  float gravel = mix(vMore.y, vMore.x, left);
  float line = vMore.z;
  float brake = vMore.w;

  float slope = 0.0;
  vec3 normal = groundNormal(xz, l, 0.4, slope);
  float bump = 0.0;
  vec3 color = natural(xz, l, here.r, slope, here.b, bump);
  float gloss = 0.0;
  float edge = a - uHalf;

  if (uStyle < 0.5) {
    // Mown bands along the circuit, as a groundsman leaves them.
    float mown = stripes(a + 0.5 * sin(s * 0.004) , 9.0, aa + eye * 0.004);
    color *= mix(1.0, 0.88 + 0.26 * mown, 0.9 * smoothstep(38.0, 8.0, edge));

    float rubber = exp(-pow((d - line) / 2.6, 2.0)) * (0.55 + 0.45 * brake) + 0.20 * smoothstep(uHalf, uHalf * 0.5, a);
    float tar = 0.0;
    vec3 road = asphalt(xz, l, s, d, rubber, tar);

    if (gravel > 0.05) {
      float from = kerb + paved;
      float inTrap = band(edge, from, gravel, aa * 2.0 + 0.04);
      float raked = 0.92 + 0.14 * sin(a * 7.0 + l.b.g * 5.0) * l.near;
      vec3 stones = mix(vec3(0.33, 0.28, 0.20), vec3(0.62, 0.55, 0.43), smoothstep(0.25, 0.8, l.a.b * 0.75 + l.b.b * 0.25)) * raked;
      stones *= 0.72 + 0.5 * l.a.g;
      float scatter = smoothstep(0.42, 0.9, l.b.g + 1.6 * (1.0 - smoothstep(0.0, 2.8, edge - from)) * l.a.g);
      color = mix(color, stones, inTrap);
      color = mix(color, stones, scatter * (1.0 - smoothstep(0.0, 1.2, edge - from - gravel)) * smoothstep(-0.3, 0.3, edge - from - gravel) * 0.7);
    }

    // Paved run-off: the same road, older, with the painted warning bands of a modern circuit.
    float runoff = band(edge, 0.0, kerb + paved, aa);
    vec3 apron = road * 1.08 + 0.012;
    float warn = stripes(s + a, 8.0, aas + aa);
    float bandEdge = smoothstep(kerb + 1.4 + aa, kerb + 1.4 - aa, edge) * smoothstep(kerb - aa, kerb + aa, edge);
    apron = mix(apron, mix(vec3(0.34), vec3(0.03, 0.14, 0.34), warn) * (0.82 + 0.3 * l.a.r), bandEdge * step(0.4, paved));
    color = mix(color, apron, runoff);
    gloss = mix(gloss, tar * 0.6, runoff);

    float onRoad = 1.0 - smoothstep(uHalf - aa, uHalf + aa, a);
    color = mix(color, road, onRoad);
    gloss = mix(gloss, tar, onRoad);

    // The white lines, worn at the edges and where cars cross them.
    float paint = band(a, uHalf - 0.32, 0.22, aa) * (0.78 + 0.22 * smoothstep(0.28, 0.5, l.a.g));
    color = mix(color, vec3(0.70, 0.70, 0.67) * (0.74 + 0.3 * l.a.r), paint);

    // The kerbs: red and white blocks, with a rib you can read at a metre.
    if (kerb > 0.05) {
      float inKerb = band(edge, -0.02, kerb, aa);
      float block = stripes(s, uStripe, aas);
      vec3 paintKerb = mix(vec3(0.60, 0.035, 0.03), vec3(0.74, 0.74, 0.71), block);
      float rib = fract(s / 0.42);
      float ribbed = 0.84 + 0.3 * smoothstep(0.1, 0.5, rib) * smoothstep(0.9, 0.5, rib) * l.near + 0.08 * (1.0 - l.near);
      paintKerb *= ribbed * (0.8 + 0.25 * l.a.g) * (1.0 - 0.25 * smoothstep(0.55, 0.3, l.a.r) * l.near);
      paintKerb *= 1.0 - 0.45 * smoothstep(0.0, 1.0, exp(-pow(edge / 0.55, 2.0))) * exp(-pow((d - line) / 3.0, 2.0));
      color = mix(color, paintKerb, inKerb);
      gloss = mix(gloss, 0.45, inKerb);
    }

    // The line, the grid and the box round it.
    float start = fract(s / uLength + 0.5) - 0.5;
    float metres = start * uLength;
    float checks = stripes(d + 200.0, 1.6, aa) ;
    float checks2 = stripes(s + 400.0, 1.6, aas);
    float flag = abs(checks - checks2);
    float onLine = band(metres, 0.0, 3.2, aas) * onRoad;
    color = mix(color, mix(vec3(0.015), vec3(0.72), flag), onLine);
    if (metres < 0.0 && metres > -130.0) {
      for (int row = 0; row < 6; row++) {
        float place = -uGrid - 8.0 * float(row);
        float across = (mod(float(row), 2.0) < 0.5 ? 1.0 : -1.0) * uHalf * 0.36;
        float u = abs(d - across);
        float v = metres - place;
        float inside = band(v, -2.6, 3.4, aas) * (1.0 - smoothstep(1.3 - aa, 1.3 + aa, u));
        float frame = inside * (1.0 - band(v, -2.5, 3.3, aas) * (1.0 - smoothstep(1.2 - aa, 1.2 + aa, u)) * (1.0 - band(v, 0.7, 0.1, aas)));
        color = mix(color, vec3(0.68), frame * 0.9);
      }
    }
    if (uLine > 0.5) {
      float width = 0.62;
      float along = fract((s + (d - line) * 0.0) / 7.0);
      float chevron = fract(along + abs(d - line) / 2.4);
      float dash = smoothstep(0.0, 0.03, chevron) * (1.0 - smoothstep(0.5, 0.53, chevron));
      vec3 hint = mix(vec3(0.05, 0.75, 0.25), vec3(0.95, 0.10, 0.05), smoothstep(0.03, 0.5, brake));
      hint = mix(hint, vec3(0.95, 0.65, 0.05), smoothstep(0.03, 0.2, brake) * (1.0 - smoothstep(0.2, 0.5, brake)));
      float on = (1.0 - smoothstep(width - aa, width + aa, abs(d - line))) * dash * onRoad;
      color = mix(color, hint, on * 0.7);
    }
  } else {
    // A road only by use: packed where the wheels go, loose everywhere else.
    float rutA = exp(-pow((d - line - 0.87) / 0.46, 2.0));
    float rutB = exp(-pow((d - line + 0.87) / 0.46, 2.0));
    float ruts = max(rutA, rutB);
    float onDirt = 1.0 - smoothstep(uHalf - 0.5 + (l.b.g - 0.5) * 2.5, uHalf + 0.9 + (l.b.g - 0.5) * 2.5, a);
    vec3 packed_ = mix(vec3(0.335, 0.235, 0.150), vec3(0.47, 0.345, 0.225), smoothstep(0.32, 0.68, l.b.g * 0.65 + l.c.g * 0.35));
    packed_ *= 0.74 + 0.52 * l.a.g;
    float washboard = sin(s * 3.1 + l.b.g * 4.0) * smoothstep(0.35, 0.6, l.c.g);
    packed_ *= 1.0 + 0.09 * washboard * l.near;
    float pebbles = smoothstep(0.64, 0.8, l.a.b) * smoothstep(0.46, 0.62, l.b.g + (1.0 - ruts) * 0.2) * l.near;
    packed_ = mix(packed_, vec3(0.21, 0.17, 0.14) * (0.5 + 0.9 * l.a.b), pebbles * 0.8);
    packed_ *= 1.0 - 0.32 * ruts * (0.6 + 0.4 * l.a.g);
    color = mix(color, packed_, onDirt);
    // Thrown up by the wheels: a low bank of loose stuff along the edge.
    float berm = band(edge, -0.2 + (l.a.g - 0.5) * 1.0, kerb + 0.8, aa + 0.25);
    vec3 loose = mix(vec3(0.27, 0.185, 0.115), vec3(0.45, 0.33, 0.21), l.a.b);
    color = mix(color, loose * (0.7 + 0.6 * l.a.g), berm * 0.8);
    normal = normalize(normal + vec3(sign(d) * berm * 0.22 * (1.0 - 2.0 * smoothstep(0.0, kerb + 0.8, edge)), 0.0, 0.0) + vec3(0.0, 0.0, 0.0) + vec3(sin(s * 3.1) * 0.05 * l.near, 0.0, 0.0));
    gloss = 0.05 * onDirt;
    float start = fract(s / uLength + 0.5) - 0.5;
    float metres = start * uLength;
    float chalk = band(metres, 0.0, 0.5, aas) * onDirt * (0.5 + 0.5 * smoothstep(0.3, 0.6, l.a.g));
    color = mix(color, vec3(0.70, 0.68, 0.62), chalk);
    if (uLine > 0.5) {
      float along = fract(s / 8.0);
      float dash = smoothstep(0.0, 0.03, along) * (1.0 - smoothstep(0.42, 0.45, along));
      vec3 hint = mix(vec3(0.15, 0.85, 0.35), vec3(0.95, 0.12, 0.06), smoothstep(0.03, 0.4, brake));
      color = mix(color, hint, (1.0 - smoothstep(0.34, 0.36, abs(d - line))) * dash * 0.6 * onDirt);
    }
  }

  // A float target clamps nothing: an alpha outside 0..1 would blend to huge or negative colours.
  fragColor = vec4(shade(color, normal, here, vWorld, gloss), clamp(vEdge.x, 0.0, 1.0));
}
`;

export interface GroundUniforms {
  uDetail: { value: THREE.Texture };
  uStyle: { value: number };
  uLine: { value: number };
  [key: string]: THREE.IUniform;
}

/** The stage's terrain mesh keeps its rings and takes this material. */
export function groundMaterial(
  field: Heightfield,
  atmosphere: AtmosphereUniforms,
  clouds: Record<"uCover" | "uDrift", THREE.IUniform>,
  shared: GroundUniforms,
  base: THREE.ShaderMaterial,
): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: TERRAIN_VERTEX,
    fragmentShader: TERRAIN_FRAGMENT,
    uniforms: {
      ...atmosphere,
      ...clouds,
      ...shared,
      uField: { value: field.texture },
      uExtent: { value: field.extent },
      uUvScale: { value: (field.size - 1) / field.size },
      uTexel: { value: 1 / field.size },
      uSnap: base.uniforms.uSnap,
      uBaseCell: base.uniforms.uBaseCell,
    },
  });
}

/** The strip of worked ground along a route. */
export function roadRibbon(
  track: Track,
  line: Line,
  field: Heightfield,
  atmosphere: AtmosphereUniforms,
  clouds: Record<"uCover" | "uDrift", THREE.IUniform>,
  shared: GroundUniforms,
): THREE.Mesh {
  const { n, definition } = track;
  const kind = definition.car;
  const every = 2;
  const sections = Math.floor(n / every);
  const columns = kind === "racecar" ? 11 : 15;
  const across = columns * 2 + 1;
  const count = (sections + 1) * across;
  const position = new Float32Array(count * 3);
  const road = new Float32Array(count * 2);
  const sides = new Float32Array(count * 4);
  const more = new Float32Array(count * 4);
  const edge = new Float32Array(count * 2);
  const { left, right } = track;
  let at = 0;
  for (let k = 0; k <= sections; k += 1) {
    const i = (k * every) % n;
    const s = k === sections ? track.length : (i / n) * track.length;
    const nx = -track.ty[i];
    const ny = track.tx[i];
    for (let c = -columns; c <= columns; c += 1) {
      const side = c >= 0 ? left : right;
      const u = Math.abs(c) / columns;
      // Crowded over the road surface, which is where the shape of the ground matters most.
      const d = Math.sign(c) * side.reach[i] * (0.65 * u * u + 0.35 * u);
      const x = track.x[i] + nx * d;
      const y = track.y[i] + ny * d;
      position.set([x, roadHeight(kind, x, y), -y], at * 3);
      road.set([s, d], at * 2);
      sides.set([left.kerb[i], right.kerb[i], left.paved[i], right.paved[i]], at * 4);
      more.set([left.gravel[i], right.gravel[i], line.offset[i], line.braking[i]], at * 4);
      edge.set([1 - THREE.MathUtils.smoothstep(u, 0.86, 0.985), 0], at * 2);
      at += 1;
    }
  }
  const index: number[] = [];
  for (let k = 0; k < sections; k += 1) {
    for (let c = 0; c < across - 1; c += 1) {
      const a = k * across + c;
      const b = a + 1;
      const e = a + across;
      const f = e + 1;
      index.push(a, b, e, b, f, e);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(position, 3));
  geometry.setAttribute("aRoad", new THREE.BufferAttribute(road, 2));
  geometry.setAttribute("aSides", new THREE.BufferAttribute(sides, 4));
  geometry.setAttribute("aMore", new THREE.BufferAttribute(more, 4));
  geometry.setAttribute("aEdge", new THREE.BufferAttribute(edge, 2));
  geometry.setIndex(index);
  const stripe = track.length / Math.round(track.length / 5.2);
  const material = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: RIBBON_VERTEX,
    fragmentShader: RIBBON_FRAGMENT,
    transparent: true,
    side: THREE.DoubleSide,
    polygonOffset: true,
    polygonOffsetFactor: -2,
    polygonOffsetUnits: -8,
    uniforms: {
      ...atmosphere,
      ...clouds,
      ...shared,
      uField: { value: field.texture },
      uExtent: { value: field.extent },
      uUvScale: { value: (field.size - 1) / field.size },
      uTexel: { value: 1 / field.size },
      uHalf: { value: track.width },
      uLength: { value: track.length },
      uStripe: { value: stripe },
      uGrid: { value: definition.gridBack },
    },
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.frustumCulled = false;
  mesh.renderOrder = 1;
  return mesh;
}
