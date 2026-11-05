/**
 * The sea: a disc of rings that follows the camera to the horizon. The waves come from `Waves` and
 * live in the normal, never in the geometry, and as they grow too small for a pixel they turn into
 * roughness, so a far sea is a broad glitter and not a shimmer. The heightfield gives the depth, so
 * shallows turn turquoise and surf follows the coast by itself.
 */

import * as THREE from "three";
import { ATMOSPHERE_GLSL, type AtmosphereUniforms } from "./atmosphere";
import type { Heightfield } from "./heightfield";
import { FAR_TILE, LOST_FROM, LOST_STEPS, NEAR_TILE, Waves } from "./waves";

const VERTEX = /* glsl */ `
uniform vec3 uCenter;
out vec3 vWorld;
void main() {
  vWorld = vec3(position.x + uCenter.x, 0.0, position.z + uCenter.z);
  gl_Position = projectionMatrix * viewMatrix * vec4(vWorld, 1.0);
}
`;

const FRAGMENT = /* glsl */ `
precision highp float;
${ATMOSPHERE_GLSL}
uniform sampler2D uField;
uniform sampler2D uFarWaves;
uniform sampler2D uNearWaves;
uniform float uLost[${LOST_STEPS}];
uniform float uExtent;
uniform float uTime;
in vec3 vWorld;
out vec4 fragColor;

const float TAU = 6.2831853;
/** Mean square slope of the ripples too small for either tile. */
const float RIPPLES = 0.006;
/** One axis' slope variance that the sun's own width is worth. */
const float SUN_WIDTH = 0.0009;

float hash(vec2 p) {
  vec3 q = fract(vec3(p.xyx) * 0.1031);
  q += dot(q, q.yzx + 33.33);
  return fract((q.x + q.y) * q.z);
}
/** Value noise with a quintic blend: a cubic one leaves creases along its grid. */
float vnoise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  f = f * f * f * (f * (f * 6.0 - 15.0) + 10.0);
  return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}
/** Two turned layers, so that no grid lines up from one to the next. */
float cloudy(vec2 p) {
  return vnoise(p) * 0.65 + vnoise(mat2(0.8, 0.6, -0.6, 0.8) * p * 2.3 + 7.1) * 0.35;
}
float depthAt(vec2 uv) {
  return -textureLod(uField, uv, 0.0).r;
}
/** The slope variance that a pixel this wide has lost from the tiles' mipmaps. */
float lostTo(float pixel) {
  float at = clamp(log2(pixel / ${LOST_FROM.toFixed(2)}), 0.0, ${(LOST_STEPS - 1.001).toFixed(3)});
  int i = int(at);
  return mix(uLost[i], uLost[min(i + 1, ${LOST_STEPS - 1})], at - float(i));
}

void main() {
  // The sea stops at the coast, and the land at the sea. Drawn one over the other, a far shelf a
  // few metres down would fight the surface for the depth buffer and flicker through it.
  vec2 uv = vec2(vWorld.x, -vWorld.z) / uExtent + 0.5;
  float depth = depthAt(uv);
  if (depth <= 0.0) discard;

  vec3 view = cameraPosition - vWorld;
  float distanceToEye = length(view);
  view /= distanceToEye;
  vec2 p = vWorld.xz;
  // Anisotropic filtering keeps the detail along the short side of a stretched pixel.
  float pixel = sqrt(length(dFdx(p)) * length(dFdy(p)));

  // Cat's paws: wind that comes in patches, which is what gives a far sea its light and dark.
  float gust = cloudy(p * 0.00085 + vec2(uTime * 0.006, -uTime * 0.004));
  float chop = 0.6 + 0.9 * smoothstep(0.25, 0.75, gust);
  vec4 wave = texture(uFarWaves, p / ${FAR_TILE.toFixed(1)}) + texture(uNearWaves, p / ${NEAR_TILE.toFixed(1)}) * chop;
  // Waves lie down over the shallows.
  float calm = mix(0.3, 1.0, smoothstep(0.0, 9.0, depth));
  wave *= calm;
  vec3 normal = normalize(vec3(-wave.x, 1.0, -wave.y));

  // Light goes down, scatters and comes back the colour of the depth, and the sand shows through
  // the last few metres.
  float shallow = smoothstep(42.0, 1.0, depth);
  vec3 deep = vec3(0.004, 0.028, 0.060);
  vec3 reef = vec3(0.022, 0.21, 0.21);
  vec3 body = mix(deep, reef, shallow * shallow);
  body = mix(body, vec3(0.34, 0.37, 0.25), exp(-depth * 0.65) * 0.8);
  vec3 ambient = skyRadiance(vec3(0.0, 1.0, 0.0));
  vec3 color = body * (ambient * 1.3 + uSunColor * max(uSunDir.y, 0.0) * 0.3);
  // The thin top of a wave lets some through, most of all with the sun behind it.
  float behind = 0.4 + 0.6 * smoothstep(0.0, 0.9, -dot(normalize(view.xz + 1e-4), normalize(uSunDir.xz + 1e-4)));
  float rise = smoothstep(-0.2, 1.4, wave.z) * smoothstep(5.0, 0.8, pixel);
  color += vec3(0.004, 0.04, 0.036) * rise * (ambient * 0.7 + uSunColor * max(uSunDir.y, 0.0) * behind);

  // Everything finer than the pixel, as a rough mirror: Bruneton's mean Fresnel, and a reflection
  // that climbs off the white horizon, because the slopes that face you see higher up the sky.
  float mss = (RIPPLES * chop + lostTo(pixel)) * calm;
  float sigma = sqrt(mss * 0.5);
  float cosine = max(dot(normal, view), 0.0);
  float fresnel = 0.02 + 0.98 * pow(1.0 - cosine, 5.0 * exp(-2.69 * sigma)) / (1.0 + 22.7 * pow(sigma, 1.5));
  vec3 reflected = reflect(-view, normal);
  reflected.y = abs(reflected.y) + sigma * 1.4;
  color = mix(color, skyRadiance(normalize(reflected)), fresnel);

  // The sun: the chance that a facet out of that spread of slopes mirrors it to the eye.
  vec3 halfway = normalize(view + uSunDir);
  vec2 off = halfway.xz / max(halfway.y, 0.02) - normal.xz / normal.y;
  float spread = mss * 0.5 + SUN_WIDTH;
  float facets = exp(-dot(off, off) / (2.0 * spread)) / (TAU * spread);
  float mirror = 0.02 + 0.98 * pow(1.0 - max(dot(view, halfway), 0.0), 5.0);
  color += uSunColor * smoothstep(-0.02, 0.05, uSunDir.y) * min(facets * mirror / (1.0 + 7.0 * max(cosine, 0.05)), 6.0);

  vec3 white = ambient * 1.1 + uSunColor * (0.08 + 0.3 * max(uSunDir.y, 0.0));

  // Whitecaps: the crests that stand up steepest, torn by the wind, and only as long as a pixel can
  // show them.
  float seen = smoothstep(6.0, 1.2, pixel);
  if (seen > 0.0) {
    float tear = cloudy(p * 0.33 + wave.xy * 2.0 + uTime * 0.2);
    float breaking = smoothstep(0.5, 0.74, wave.w + (tear - 0.5) * 0.45 + (gust - 0.5) * 0.24);
    color = mix(color, white, breaking * seen * 0.75 * calm);
  }

  // Surf is measured from the waterline, not by depth, for a shelf can stay a metre deep for
  // hundreds of metres. The depth over its slope says how far away that line is.
  if (depth < 14.0) {
    vec2 texel = 1.0 / vec2(textureSize(uField, 0));
    vec2 rate = vec2(depthAt(uv + vec2(texel.x, 0.0)) - depthAt(uv - vec2(texel.x, 0.0)), depthAt(uv + vec2(0.0, texel.y)) - depthAt(uv - vec2(0.0, texel.y)));
    float slope = length(rate) / (2.0 * texel.x * uExtent);
    float shore = depth / max(slope, 0.012);
    float wander = cloudy(p * 0.006);
    float lace = cloudy(p * 0.17 + wave.xy * 4.0 - vec2(uTime * 0.1));
    // Rollers that come in, one behind the other, and fade as they spread up the beach.
    float roll = fract(shore * 0.016 + uTime * 0.09 + wander * 2.4);
    float line = smoothstep(0.0, 0.02, roll) * smoothstep(0.15, 0.03, roll);
    float rollers = line * smoothstep(100.0, 18.0, shore) * smoothstep(0.34, 0.6, lace + line * 0.2);
    // And the wash, which runs up to the sand and back.
    float reach = 9.0 + 5.0 * sin(uTime * 0.5 + wander * 9.0) + 14.0 * lace;
    float wash = smoothstep(reach, reach * 0.35, shore) * smoothstep(0.2, 0.5, lace + smoothstep(reach * 0.5, 0.0, shore));
    float detail = smoothstep(26.0, 7.0, pixel);
    // From far away all that remains is a thin bright edge.
    float edge = smoothstep(40.0 + pixel * 2.0, 0.0, shore);
    float foam = max(max(rollers * 0.5, wash * 0.85) * detail, edge * (1.0 - detail) * 0.55);
    color = mix(color, white, foam * smoothstep(0.0, 0.12, depth));
  }

  fragColor = vec4(aerial(color, vWorld, cameraPosition), 1.0);
}
`;

export class Ocean {
  readonly mesh: THREE.Mesh;
  private readonly center = new THREE.Vector3();
  private readonly time = { value: 0 };
  private readonly waves = new Waves();

  constructor(field: Heightfield, atmosphere: AtmosphereUniforms, radius = 180_000) {
    const geometry = new THREE.RingGeometry(0.1, radius, 96, 64);
    const position = geometry.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < position.count; i += 1) {
      // RingGeometry is uniform in radius: square it to crowd the rings at the camera.
      const x = position.getX(i);
      const y = position.getY(i);
      const r = Math.hypot(x, y);
      const scale = r / radius;
      position.setXYZ(i, x * scale, 0, -y * scale);
    }
    this.mesh = new THREE.Mesh(
      geometry,
      new THREE.ShaderMaterial({
        glslVersion: THREE.GLSL3,
        vertexShader: VERTEX,
        fragmentShader: FRAGMENT,
        uniforms: {
          ...atmosphere,
          uField: { value: field.texture },
          uFarWaves: { value: this.waves.far.surface.texture },
          uNearWaves: { value: this.waves.near.surface.texture },
          uLost: { value: this.waves.unresolved },
          uExtent: { value: field.extent },
          uTime: this.time,
          uCenter: { value: this.center },
        },
        side: THREE.DoubleSide,
      }),
    );
    this.mesh.frustumCulled = false;
  }

  update(camera: THREE.Vector3, time: number, renderer: THREE.WebGLRenderer): void {
    this.center.copy(camera);
    this.time.value = time;
    this.waves.update(renderer, time);
  }
}
