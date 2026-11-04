/**
 * The waves of the sea, the way film and flight simulators make them: a random spectrum of a real
 * wind sea, turned into a surface by an inverse FFT on the GPU every frame. Summed by hand, a few
 * sines or noise layers always show their lattice; thousands of waves with random phases do not.
 *
 * Two tiles, a large one for the sea you see from the air and a small one for the chop under your
 * wheels, each holding its own part of the spectrum. The surface comes out as slopes, height and
 * crest, and hardware mipmaps smooth away what a pixel cannot show; `unresolved` tells the shading
 * how much slope that took away, so that the sea turns rough rather than flat with distance.
 */

import * as THREE from "three";

const SIZE = 256;
/** Tile sizes in metres: no common multiple, so their repeats never line up. */
export const FAR_TILE = 2133;
export const NEAR_TILE = 197;
/** The wavelength at which the far tile hands over to the near one. */
const CROSSOVER = 20;
/** Wind that sets the longest waves, in m/s, and its heading in the sea's x, z plane. */
const WIND = 13;
const WIND_ANGLE = 0.64;
/** Ripples below this wavelength are too short for either tile. */
const SHORTEST = 0.5;
/** Mean square slope of the whole sea: a fresh breeze. */
export const SEA_SLOPE = 0.032;
/** One entry for each doubling of a pixel's width in metres, from `LOST_FROM`. */
export const LOST_STEPS = 16;
export const LOST_FROM = 0.5;

const TAU = Math.PI * 2;
const GRAVITY = 9.81;

/** Energy of the wave k, on the sea-state curve Phillips gave, with most of it running downwind. */
function spectrum(kx: number, kz: number): number {
  const k2 = kx * kx + kz * kz;
  if (k2 === 0) {
    return 0;
  }
  const longest = (WIND * WIND) / GRAVITY;
  const k = Math.sqrt(k2);
  const along = (kx * Math.cos(WIND_ANGLE) + kz * Math.sin(WIND_ANGLE)) / k;
  const spread = Math.max(along, 0) ** 4 + 0.015;
  return (Math.exp(-1 / (k2 * longest * longest)) / (k2 * k2)) * spread * Math.exp(-k2 * SHORTEST * SHORTEST * 0.02);
}

/** A seeded generator: the same sea every time. */
function random(seed: number): () => number {
  let s = seed;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const FLOAT_TARGET: THREE.RenderTargetOptions = {
  type: THREE.FloatType,
  format: THREE.RGBAFormat,
  minFilter: THREE.NearestFilter,
  magFilter: THREE.NearestFilter,
  depthBuffer: false,
  generateMipmaps: false,
};

const QUAD = /* glsl */ `
void main() {
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

/** The spectrum, at this moment: each wave has only turned its phase by its own speed. */
const EVOLVE = /* glsl */ `
precision highp float;
uniform sampler2D uStart;
uniform float uTile;
uniform float uTime;
out vec4 fragColor;
vec2 times(vec2 a, vec2 b) {
  return vec2(a.x * b.x - a.y * b.y, a.x * b.y + a.y * b.x);
}
void main() {
  ivec2 at = ivec2(gl_FragCoord.xy);
  vec4 start = texelFetch(uStart, at, 0);
  vec2 n = vec2(at);
  n -= ${SIZE.toFixed(1)} * step(${(SIZE / 2).toFixed(1)}, n);
  vec2 k = ${TAU.toFixed(7)} * n / uTile;
  float size = length(k);
  float turn = mod(sqrt(${GRAVITY.toFixed(2)} * size) * uTime, ${TAU.toFixed(7)});
  vec2 spin = vec2(cos(turn), sin(turn));
  vec2 h = times(start.xy, vec2(spin.x, -spin.y)) + times(start.zw, spin);
  // Two real fields travel in each complex one: the slopes in x and z, and the height and the
  // crest, which is the height with short waves weighted up, and picks out what is about to break.
  vec2 slopes = k.x * vec2(-h.y, h.x) - k.y * h;
  vec2 rest = h + size * vec2(-h.y, h.x);
  fragColor = vec4(slopes, rest);
}
`;

/** One stage of a Stockham FFT, along one axis, for the two complex numbers in a texel. */
const fft = (axis: "x" | "y"): string => /* glsl */ `
precision highp float;
uniform sampler2D uInput;
uniform float uSpan;
out vec4 fragColor;
vec2 times(vec2 a, vec2 b) {
  return vec2(a.x * b.x - a.y * b.y, a.x * b.y + a.y * b.x);
}
void main() {
  ivec2 at = ivec2(gl_FragCoord.xy);
  float index = float(at.${axis});
  float half_ = uSpan * 0.5;
  int even = int(floor(index / uSpan) * half_ + mod(index, half_));
  int odd = even + ${SIZE / 2};
  ivec2 a = at;
  ivec2 b = at;
  a.${axis} = even;
  b.${axis} = odd;
  vec4 p = texelFetch(uInput, a, 0);
  vec4 q = texelFetch(uInput, b, 0);
  float angle = ${TAU.toFixed(7)} * index / uSpan;
  vec2 twiddle = vec2(cos(angle), sin(angle));
  fragColor = vec4(p.xy + times(twiddle, q.xy), p.zw + times(twiddle, q.zw));
}
`;

const COPY = /* glsl */ `
precision highp float;
uniform sampler2D uInput;
out vec4 fragColor;
void main() {
  fragColor = texelFetch(uInput, ivec2(gl_FragCoord.xy), 0);
}
`;

class Tile {
  readonly start: THREE.DataTexture;
  /** Slopes in x and z, height, crest. */
  readonly surface: THREE.WebGLRenderTarget;
  readonly a = new THREE.WebGLRenderTarget(SIZE, SIZE, FLOAT_TARGET);
  readonly b = new THREE.WebGLRenderTarget(SIZE, SIZE, FLOAT_TARGET);

  constructor(
    readonly size: number,
    from: number,
    to: number,
    scale: number,
    seed: number,
  ) {
    const next = random(seed);
    const cell = (TAU / size) ** 2;
    const gauss = (): number => Math.sqrt(-2 * Math.log(1 - next())) * Math.cos(TAU * next());
    const h = new Float32Array(SIZE * SIZE * 2);
    const wrap = (n: number): number => (n < SIZE / 2 ? n : n - SIZE);
    for (let j = 0; j < SIZE; j += 1) {
      for (let i = 0; i < SIZE; i += 1) {
        const kx = (TAU * wrap(i)) / size;
        const kz = (TAU * wrap(j)) / size;
        const k = Math.hypot(kx, kz);
        const a = gauss();
        const b = gauss();
        if (k >= from && k < to && i !== SIZE / 2 && j !== SIZE / 2) {
          const amplitude = Math.sqrt(spectrum(kx, kz) * cell * scale * 0.5);
          h[(j * SIZE + i) * 2] = a * amplitude;
          h[(j * SIZE + i) * 2 + 1] = b * amplitude;
        }
      }
    }
    const data = new Float32Array(SIZE * SIZE * 4);
    for (let j = 0; j < SIZE; j += 1) {
      for (let i = 0; i < SIZE; i += 1) {
        const at = (j * SIZE + i) * 2;
        const mirror = (((SIZE - j) % SIZE) * SIZE + ((SIZE - i) % SIZE)) * 2;
        data[at * 2] = h[at];
        data[at * 2 + 1] = h[at + 1];
        data[at * 2 + 2] = h[mirror];
        data[at * 2 + 3] = -h[mirror + 1];
      }
    }
    this.start = new THREE.DataTexture(data, SIZE, SIZE, THREE.RGBAFormat, THREE.FloatType);
    this.start.needsUpdate = true;
    this.surface = new THREE.WebGLRenderTarget(SIZE, SIZE, {
      type: THREE.HalfFloatType,
      format: THREE.RGBAFormat,
      minFilter: THREE.LinearMipmapLinearFilter,
      magFilter: THREE.LinearFilter,
      wrapS: THREE.RepeatWrapping,
      wrapT: THREE.RepeatWrapping,
      generateMipmaps: true,
      anisotropy: 8,
      depthBuffer: false,
    });
  }
}

export class Waves {
  readonly far: Tile;
  readonly near: Tile;
  /** Slope variance lost to a pixel of each width: see LOST_FROM. */
  readonly unresolved: number[] = [];
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  private readonly quad: THREE.Mesh;
  private readonly evolve = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: QUAD,
    fragmentShader: EVOLVE,
    uniforms: { uStart: { value: null }, uTile: { value: 0 }, uTime: { value: 0 } },
    depthTest: false,
    depthWrite: false,
  });
  private readonly passes = (["x", "y"] as const).map(
    (axis) =>
      new THREE.ShaderMaterial({
        glslVersion: THREE.GLSL3,
        vertexShader: QUAD,
        fragmentShader: fft(axis),
        uniforms: { uInput: { value: null }, uSpan: { value: 0 } },
        depthTest: false,
        depthWrite: false,
      }),
  );
  private readonly copy = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3,
    vertexShader: QUAD,
    fragmentShader: COPY,
    uniforms: { uInput: { value: null } },
    depthTest: false,
    depthWrite: false,
  });

  constructor() {
    // The size of the energy is fixed by the slope it should add up to, not by a constant.
    const cross = TAU / CROSSOVER;
    let total = 0;
    const bands = new Array<number>(LOST_STEPS).fill(0);
    const measure = (tile: number, from: number, to: number): void => {
      for (let j = -SIZE / 2 + 1; j < SIZE / 2; j += 1) {
        for (let i = -SIZE / 2 + 1; i < SIZE / 2; i += 1) {
          const kx = (TAU * i) / tile;
          const kz = (TAU * j) / tile;
          const k = Math.hypot(kx, kz);
          if (k >= from && k < to) {
            // The spectrum is a density: a finer lattice of waves shares the energy among more.
            const slope = k * k * spectrum(kx, kz) * (TAU / tile) ** 2;
            total += slope * 2;
            // A pixel of width w can show waves down to twice that.
            const band = Math.ceil(Math.log2(Math.PI / k / LOST_FROM));
            for (let b = Math.max(band, 0); b < LOST_STEPS; b += 1) {
              bands[b] += slope * 2;
            }
          }
        }
      }
    };
    measure(FAR_TILE, 0, cross);
    measure(NEAR_TILE, cross, Infinity);
    const scale = SEA_SLOPE / total;
    this.unresolved = bands.map((b) => b * scale);
    this.far = new Tile(FAR_TILE, 0, cross, scale * 2, 7);
    this.near = new Tile(NEAR_TILE, cross, Infinity, scale * 2, 19);
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.evolve);
    this.quad.frustumCulled = false;
    this.scene.add(this.quad);
  }

  private draw(renderer: THREE.WebGLRenderer, material: THREE.ShaderMaterial, target: THREE.WebGLRenderTarget): void {
    this.quad.material = material;
    material.uniformsNeedUpdate = true;
    renderer.setRenderTarget(target);
    renderer.render(this.scene, this.camera);
  }

  private solve(renderer: THREE.WebGLRenderer, tile: Tile, time: number): void {
    this.evolve.uniforms.uStart.value = tile.start;
    this.evolve.uniforms.uTile.value = tile.size;
    this.evolve.uniforms.uTime.value = time;
    this.draw(renderer, this.evolve, tile.a);
    let from = tile.a;
    let to = tile.b;
    for (const pass of this.passes) {
      for (let span = 2; span <= SIZE; span *= 2) {
        pass.uniforms.uInput.value = from.texture;
        pass.uniforms.uSpan.value = span;
        this.draw(renderer, pass, to);
        [from, to] = [to, from];
      }
    }
    this.copy.uniforms.uInput.value = from.texture;
    this.draw(renderer, this.copy, tile.surface);
  }

  update(renderer: THREE.WebGLRenderer, time: number): void {
    // Without float targets the tiles stay empty and the sea is a rough mirror, which still works.
    if (!renderer.extensions.has("EXT_color_buffer_float")) {
      return;
    }
    const target = renderer.getRenderTarget();
    this.solve(renderer, this.far, time);
    this.solve(renderer, this.near, time);
    renderer.setRenderTarget(target);
  }
}
