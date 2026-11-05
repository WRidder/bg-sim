/**
 * Volumetric cumulus, raymarched through tiled 3D noise at half of the screen's resolution.
 * Each pixel starts its march at a different offset, so banding turns into fine grain that the
 * upsampling blurs away. Density comes from a large-scale weather map, eroded by the noise.
 */

import * as THREE from "three";
import { ATMOSPHERE_GLSL, type AtmosphereUniforms } from "./atmosphere";
import { hash2 } from "./noise";

/** Tiling inverted Worley noise: billowy at every octave, and it wraps at the edges. */
function makeNoiseVolume(size: number): THREE.Data3DTexture {
  const data = new Uint8Array(size * size * size);
  const octaves = [
    { cells: 4, weight: 0.625 },
    { cells: 9, weight: 0.25 },
    { cells: 19, weight: 0.125 },
  ];
  const points = octaves.map(({ cells }) => {
    const p = new Float32Array(cells * cells * cells * 3);
    for (let i = 0; i < p.length; i += 1) {
      p[i] = hash2(i, cells, 17);
    }
    return p;
  });
  for (let z = 0; z < size; z += 1) {
    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < size; x += 1) {
        let sum = 0;
        octaves.forEach(({ cells, weight }, o) => {
          const px = (x / size) * cells;
          const py = (y / size) * cells;
          const pz = (z / size) * cells;
          const ix = Math.floor(px);
          const iy = Math.floor(py);
          const iz = Math.floor(pz);
          let best = 9;
          for (let dz = -1; dz <= 1; dz += 1) {
            for (let dy = -1; dy <= 1; dy += 1) {
              for (let dx = -1; dx <= 1; dx += 1) {
                const cx = (ix + dx + cells) % cells;
                const cy = (iy + dy + cells) % cells;
                const cz = (iz + dz + cells) % cells;
                const at = (cz * cells * cells + cy * cells + cx) * 3;
                const qx = ix + dx + points[o][at] - px;
                const qy = iy + dy + points[o][at + 1] - py;
                const qz = iz + dz + points[o][at + 2] - pz;
                best = Math.min(best, qx * qx + qy * qy + qz * qz);
              }
            }
          }
          sum += weight * (1 - Math.min(1, Math.sqrt(best)));
        });
        data[z * size * size + y * size + x] = Math.round(255 * sum);
      }
    }
  }
  const texture = new THREE.Data3DTexture(data, size, size, size);
  texture.format = THREE.RedFormat;
  texture.magFilter = THREE.LinearFilter;
  texture.minFilter = THREE.LinearFilter;
  texture.wrapS = texture.wrapT = texture.wrapR = THREE.RepeatWrapping;
  texture.needsUpdate = true;
  return texture;
}

export const CLOUD_MAP_GLSL = /* glsl */ `
uniform float uCover;
uniform float uDrift;
float cloudHash(vec2 p) {
  vec3 q = fract(vec3(p.xyx) * 0.1031);
  q += dot(q, q.yzx + 33.33);
  return fract((q.x + q.y) * q.z);
}
float cloudNoise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(cloudHash(i), cloudHash(i + vec2(1, 0)), f.x), mix(cloudHash(i + vec2(0, 1)), cloudHash(i + vec2(1, 1)), f.x), f.y);
}
/** The weather map: how much cloud stands over a point, 0..1. */
float cloudWeather(vec2 xz) {
  vec2 p = (xz + vec2(uDrift, uDrift * 0.4)) * 0.00016;
  float n = cloudNoise(p) * 0.46 + cloudNoise(p * 2.7 + 3.1) * 0.32 + cloudNoise(p * 7.3 + 7.3) * 0.22;
  return smoothstep(1.0 - uCover, 1.0 - uCover + 0.16, n);
}
`;

const VERTEX = /* glsl */ `
precision highp float;
in vec3 position;
out vec2 vUv;
void main() {
  vUv = position.xy * 0.5 + 0.5;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

const FRAGMENT = /* glsl */ `
precision highp float;
precision highp sampler3D;
${ATMOSPHERE_GLSL}
${CLOUD_MAP_GLSL}
uniform sampler3D uNoise;
uniform sampler2D uDepth;
uniform mat4 uInverseView;
uniform mat4 uInverseProjection;
uniform vec3 uEye;
uniform vec2 uLayer;
uniform float uFrame;
uniform int uSteps;
in vec2 vUv;
out vec4 fragColor;

float density(vec3 p, bool cheap) {
  float base = (p.y - uLayer.x) / (uLayer.y - uLayer.x);
  if (base < 0.0 || base > 1.0) return 0.0;
  float weather = cloudWeather(p.xz);
  if (weather <= 0.0) return 0.0;
  // Flat bases, rounded tops: the profile narrows with height, more so where the cover is thin.
  float profile = smoothstep(0.0, 0.1, base) * smoothstep(1.0, 0.45 + 0.3 * (1.0 - weather), base);
  float shape = weather * profile;
  if (shape <= 0.0) return 0.0;
  vec3 q = (p + vec3(uDrift, 0.0, uDrift * 0.4)) * 0.00038;
  float n = texture(uNoise, q).r;
  // Erode from the outside: the noise cuts deep at the rim of a cloud and little at its heart.
  float d = shape - (1.0 - n * n * n) * 0.86;
  if (d <= 0.0 || cheap) return max(d, 0.0) * 3.0;
  float wisp = texture(uNoise, q * 6.1 + vec3(0.13)).r;
  d -= (1.0 - wisp) * 0.42 * smoothstep(0.42, 0.0, d);
  return max(d, 0.0) * 3.0;
}

float phase(float mu, float g) {
  float g2 = g * g;
  return (1.0 - g2) / (12.566 * pow(1.0 + g2 - 2.0 * g * mu, 1.5));
}

vec2 slab(vec3 o, vec3 d, float y0, float y1) {
  if (abs(d.y) < 1e-5) return (o.y > y0 && o.y < y1) ? vec2(0.0, 1e6) : vec2(1e6, -1.0);
  float a = (y0 - o.y) / d.y, b = (y1 - o.y) / d.y;
  float n = min(a, b), f = max(a, b);
  return vec2(max(n, 0.0), f);
}

void main() {
  vec4 clip = vec4(vUv * 2.0 - 1.0, 1.0, 1.0);
  vec4 view = uInverseProjection * clip;
  vec3 dir = normalize((uInverseView * vec4(view.xyz / view.w, 0.0)).xyz);

  float sceneDepth = texture(uDepth, vUv).r;
  vec4 hit = uInverseProjection * vec4(vUv * 2.0 - 1.0, sceneDepth * 2.0 - 1.0, 1.0);
  float limit = sceneDepth >= 1.0 ? 1e9 : length(hit.xyz / hit.w);

  vec2 span = slab(uEye, dir, uLayer.x, uLayer.y);
  span.y = min(span.y, min(limit, 90000.0));
  if (span.x >= span.y) {
    fragColor = vec4(0.0, 0.0, 0.0, 1.0);
    return;
  }
  float jitter = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))) + uFrame * 0.618034);
  int steps = uSteps;
  float t = span.x + jitter * clamp(span.x * 0.02, 50.0, 300.0);

  float mu = dot(dir, uSunDir);
  float forward = phase(mu, 0.72) * 0.75 + phase(mu, -0.22) * 0.25;
  vec3 ambientTop = skyRadiance(vec3(0.0, 1.0, 0.0));
  vec3 scattered = vec3(0.0);
  float transmittance = 1.0;
  float firstHit = -1.0;
  bool inside = false;
  for (int i = 0; i < steps && t < span.y; i++) {
    // Steps grow with distance, where a cloud covers fewer pixels; empty air is crossed faster.
    float dt = clamp(t * 0.02, 50.0, 300.0);
    vec3 p = uEye + dir * t;
    if (!inside) {
      if (density(p, true) <= 0.0) {
        t += dt * 2.5;
        continue;
      }
      inside = true;
      t = max(t - dt * 1.5, span.x);
      p = uEye + dir * t;
    }
    float d = density(p, false);
    if (d > 0.001) {
      if (firstHit < 0.0) firstHit = t;
      float shade = 0.0;
      float lightStep = 90.0;
      for (int j = 1; j <= 5; j++) {
        shade += density(p + uSunDir * lightStep * float(j) * float(j) * 0.5, true);
      }
      // Two lobes of light through the cloud: the direct beam, and a softer one that stands in
      // for the many scatterings which keep the inside of a cumulus bright.
      float toSun = exp(-shade * lightStep * 0.0066) * 0.72 + exp(-shade * lightStep * 0.0014) * 0.28;
      float powder = 1.0 - exp(-d * dt * 0.012);
      float height = clamp((p.y - uLayer.x) / (uLayer.y - uLayer.x), 0.0, 1.0);
      vec3 light = uSunColor * toSun * mix(0.5, 1.0, powder) * (forward * 4.0 + 0.5) + ambientTop * (0.17 + 0.5 * height);
      float opticalDepth = d * dt * 0.026;
      float through = exp(-opticalDepth);
      scattered += transmittance * (1.0 - through) * light;
      transmittance *= through;
      if (transmittance < 0.015) break;
    }
    t += dt;
  }
  if (firstHit > 0.0) {
    // The same aerial perspective as the land, so far clouds melt into the horizon.
    float fade = airTransmittance(uEye.y, mix(uLayer.x, uLayer.y, 0.4), firstHit);
    vec3 haze = skyRadiance(normalize(vec3(dir.x, max(dir.y, 0.015), dir.z)));
    scattered = mix(haze * (1.0 - transmittance), scattered, fade);
  }
  fragColor = vec4(scattered, transmittance);
}
`;

export interface CloudOptions {
  /** Metres: the bottom and the top of the layer. */
  layer?: [number, number];
  cover?: number;
  steps?: number;
}

export class Clouds {
  readonly target: THREE.WebGLRenderTarget;
  private readonly mesh: THREE.Mesh;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  private readonly material: THREE.RawShaderMaterial;
  readonly shared = { uCover: { value: 0.42 }, uDrift: { value: 0 } };
  private frame = 0;

  constructor(atmosphere: AtmosphereUniforms, options: CloudOptions = {}) {
    this.target = new THREE.WebGLRenderTarget(4, 4, {
      type: THREE.HalfFloatType,
      format: THREE.RGBAFormat,
      depthBuffer: false,
      magFilter: THREE.LinearFilter,
      minFilter: THREE.LinearFilter,
    });
    this.shared.uCover.value = options.cover ?? 0.3;
    this.material = new THREE.RawShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: VERTEX,
      fragmentShader: FRAGMENT,
      uniforms: {
        ...atmosphere,
        ...this.shared,
        uNoise: { value: makeNoiseVolume(64) },
        uDepth: { value: null },
        uInverseView: { value: new THREE.Matrix4() },
        uInverseProjection: { value: new THREE.Matrix4() },
        uEye: { value: new THREE.Vector3() },
        uLayer: { value: new THREE.Vector2(...(options.layer ?? [1500, 3000])) },
        uFrame: { value: 0 },
        uSteps: { value: options.steps ?? 72 },
      },
      depthTest: false,
      depthWrite: false,
    });
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.material);
    this.mesh.frustumCulled = false;
    this.scene.add(this.mesh);
  }

  set steps(value: number) {
    this.material.uniforms.uSteps.value = value;
  }

  resize(width: number, height: number): void {
    this.target.setSize(Math.max(2, Math.ceil(width / 2)), Math.max(2, Math.ceil(height / 2)));
  }

  render(renderer: THREE.WebGLRenderer, camera: THREE.PerspectiveCamera, depth: THREE.Texture, time: number): void {
    const u = this.material.uniforms;
    u.uDepth.value = depth;
    u.uInverseView.value.copy(camera.matrixWorld);
    u.uInverseProjection.value.copy(camera.projectionMatrixInverse);
    u.uEye.value.copy(camera.position);
    u.uFrame.value = this.frame++ % 64;
    this.shared.uDrift.value = time * 6;
    renderer.setRenderTarget(this.target);
    renderer.render(this.scene, this.camera);
  }
}
