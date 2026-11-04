/**
 * The sea: a disc of rings that follows the camera to the horizon. Waves live in the normal, never
 * in the geometry, and fade with distance into the sky's own reflection. The heightfield gives the
 * depth, so shallows turn turquoise and a band of surf follows the coast by itself.
 */

import * as THREE from "three";
import { ATMOSPHERE_GLSL, type AtmosphereUniforms } from "./atmosphere";
import type { Heightfield } from "./heightfield";

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
uniform float uExtent;
uniform float uTime;
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

/** Directional waves: the sum of a few noise layers drifting downwind at their own speeds. */
float waves(vec2 p) {
  float h = 0.0, a = 1.0, s = 0.045;
  vec2 d = vec2(0.8, 0.6);
  for (int i = 0; i < 5; i++) {
    float t = uTime * (0.35 + 0.16 * float(i));
    h += a * vnoise(p * s + d * t);
    p = mat2(0.8, 0.6, -0.6, 0.8) * p;
    s *= 2.03;
    a *= 0.52;
  }
  return h;
}

void main() {
  vec3 view = cameraPosition - vWorld;
  float distanceToEye = length(view);
  view /= distanceToEye;

  float e = 0.8 + distanceToEye * 0.004;
  float near = smoothstep(26000.0, 300.0, distanceToEye);
  float w0 = waves(vWorld.xz);
  float wx = waves(vWorld.xz + vec2(e, 0.0));
  float wz = waves(vWorld.xz + vec2(0.0, e));
  vec3 normal = normalize(vec3((w0 - wx) * near * 1.6, e * 2.2, (w0 - wz) * near * 1.6));

  float depth = -textureLod(uField, vec2(vWorld.x, -vWorld.z) / uExtent + 0.5, 0.0).r;
  float shallow = smoothstep(42.0, 1.0, depth);
  vec3 deep = vec3(0.004, 0.028, 0.060);
  vec3 reef = vec3(0.025, 0.20, 0.21);
  vec3 body = mix(deep, reef, shallow * shallow);
  // Sand showing through the last metres, so a shoal has no hard edge.
  body = mix(body, vec3(0.30, 0.36, 0.30), smoothstep(3.5, 0.2, depth) * 0.8);

  float cosine = max(dot(normal, view), 0.0);
  float fresnel = 0.02 + 0.98 * pow(1.0 - cosine, 5.0);
  vec3 reflected = reflect(-view, normal);
  reflected.y = abs(reflected.y);
  vec3 sky = skyRadiance(normalize(reflected));
  vec3 ambient = skyRadiance(vec3(0.0, 1.0, 0.0));
  vec3 color = body * (ambient * 1.3 + uSunColor * max(uSunDir.y, 0.0) * 0.3);
  color = mix(color, sky, fresnel);

  float glint = pow(max(dot(reflect(-uSunDir, normal), view), 0.0), 340.0);
  color += uSunColor * glint * 1.8;

  // Surf: lace up close, a thin even line from far away, where lace would only sparkle.
  float close = smoothstep(2600.0, 700.0, distanceToEye);
  float band = smoothstep(mix(1.1, 4.0, close), 0.3, depth) * smoothstep(-0.1, 0.25, depth);
  float lace = smoothstep(0.5, 0.8, vnoise(vWorld.xz * 0.11 + uTime * 0.2) * 0.6 + vnoise(vWorld.xz * 0.37) * 0.4 + 0.25 * sin(depth * 2.6 - uTime * 0.7));
  color = mix(color, ambient * 1.1 + uSunColor * 0.16, band * mix(0.5, lace * 0.75, close));

  fragColor = vec4(aerial(color, vWorld, cameraPosition), 1.0);
}
`;

export class Ocean {
  readonly mesh: THREE.Mesh;
  private readonly center = new THREE.Vector3();
  private readonly time = { value: 0 };

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
          uExtent: { value: field.extent },
          uTime: this.time,
          uCenter: { value: this.center },
        },
        side: THREE.DoubleSide,
      }),
    );
    this.mesh.frustumCulled = false;
  }

  update(camera: THREE.Vector3, time: number): void {
    this.center.copy(camera);
    this.time.value = time;
  }
}
