/**
 * Sky and aerial perspective. Single scattering is integrated once into a small panorama whenever
 * the sun moves. The sky dome, the reflections on water and the haze on distant land all read that
 * one texture, so the horizon, the sea and the mountains always agree in colour.
 */

import * as THREE from "three";

export const ATMOSPHERE_GLSL = /* glsl */ `
uniform sampler2D uSky;
uniform vec3 uSunDir;
uniform vec3 uSunColor;
uniform float uHaze;

vec3 skyRadiance(vec3 dir) {
  vec2 uv = vec2(atan(dir.x, -dir.z) / 6.2831853 + 0.5, 0.5 + 0.5 * sign(dir.y) * sqrt(abs(dir.y)));
  return textureLod(uSky, uv, 0.0).rgb;
}

/** How much of the light from a point survives the air between it and the eye, by height. */
float airTransmittance(float eyeHeight, float pointHeight, float distance) {
  float falloff = 1.0 / 2400.0;
  float a = exp(-max(eyeHeight, 0.0) * falloff);
  float delta = (pointHeight - eyeHeight) * falloff;
  float mean = abs(delta) < 1e-3 ? a : a * (1.0 - exp(-delta)) / delta;
  return exp(-distance * uHaze * mean);
}

/** The light of a surface as it reaches the eye: dimmed by the air and lit by the sky behind it. */
vec3 aerial(vec3 color, vec3 worldPos, vec3 eye) {
  vec3 ray = worldPos - eye;
  float distance = length(ray);
  vec3 dir = ray / distance;
  float t = airTransmittance(eye.y, worldPos.y, distance);
  vec3 horizon = skyRadiance(normalize(vec3(dir.x, max(dir.y, 0.015), dir.z)));
  float forward = pow(max(dot(dir, uSunDir), 0.0), 8.0);
  return mix(horizon + uSunColor * forward * 0.05, color, t);
}
`;

const PANORAMA_FRAGMENT = /* glsl */ `
precision highp float;
in vec2 vUv;
out vec4 fragColor;
uniform vec3 uSunDir;

const float R_EARTH = 6371e3;
const float R_TOP = 6471e3;
const vec3 BETA_R = vec3(5.8e-6, 13.5e-6, 33.1e-6);
const float BETA_M = 12e-6;
const float H_R = 8000.0;
const float H_M = 1300.0;
const float G = 0.78;

vec2 sphere(vec3 origin, vec3 dir, float radius) {
  float b = dot(origin, dir);
  float c = dot(origin, origin) - radius * radius;
  float d = b * b - c;
  if (d < 0.0) return vec2(1e9, -1e9);
  d = sqrt(d);
  return vec2(-b - d, -b + d);
}

vec3 transmittanceToSun(vec3 p) {
  vec2 ground = sphere(p, uSunDir, R_EARTH);
  if (ground.x > 0.0) return vec3(0.0);
  float top = sphere(p, uSunDir, R_TOP).y;
  float dt = top / 6.0;
  vec2 depth = vec2(0.0);
  for (int i = 0; i < 6; i++) {
    vec3 q = p + uSunDir * (float(i) + 0.5) * dt;
    float h = length(q) - R_EARTH;
    depth += vec2(exp(-h / H_R), exp(-h / H_M)) * dt;
  }
  return exp(-(BETA_R * depth.x + BETA_M * 1.1 * depth.y) * 0.8);
}

void main() {
  float azimuth = (vUv.x - 0.5) * 6.2831853;
  float s = vUv.y * 2.0 - 1.0;
  float y = sign(s) * s * s;
  float r = sqrt(max(1.0 - y * y, 0.0));
  vec3 dir = vec3(sin(azimuth) * r, y, -cos(azimuth) * r);
  // Below the horizon the panorama holds the haze a low observer sees towards the ground.
  dir.y = max(dir.y, 0.0);
  dir = normalize(dir + vec3(0.0, 1e-4, 0.0));

  vec3 origin = vec3(0.0, R_EARTH + 300.0, 0.0);
  float far = sphere(origin, dir, R_TOP).y;
  float dt = far / 16.0;
  vec3 sumR = vec3(0.0), sumM = vec3(0.0);
  vec2 depth = vec2(0.0);
  for (int i = 0; i < 16; i++) {
    vec3 p = origin + dir * (float(i) + 0.5) * dt;
    float h = length(p) - R_EARTH;
    vec2 density = vec2(exp(-h / H_R), exp(-h / H_M)) * dt;
    depth += density;
    // Multiple scattering, roughly: light knocked out of a long ray mostly comes back in further
    // along it, so the ray loses far less than single scattering says. This keeps the horizon white.
    vec3 t = exp(-(BETA_R * depth.x + BETA_M * 1.1 * depth.y) * 0.32) * transmittanceToSun(p);
    sumR += t * density.x;
    sumM += t * density.y;
  }
  float mu = dot(dir, uSunDir);
  float phaseR = 3.0 / (16.0 * 3.14159) * (1.0 + mu * mu);
  float phaseM = 3.0 / (8.0 * 3.14159) * ((1.0 - G * G) * (1.0 + mu * mu)) /
    ((2.0 + G * G) * pow(1.0 + G * G - 2.0 * G * mu, 1.5));
  fragColor = vec4(22.0 * (sumR * BETA_R * phaseR + sumM * BETA_M * phaseM), 1.0);
}
`;

const FULLSCREEN_VERTEX = /* glsl */ `
out vec2 vUv;
void main() {
  vUv = position.xy * 0.5 + 0.5;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

const SKY_VERTEX = /* glsl */ `
out vec3 vDir;
void main() {
  vDir = (modelMatrix * vec4(position, 0.0)).xyz;
  vec4 clip = projectionMatrix * mat4(mat3(viewMatrix)) * vec4(position, 1.0);
  gl_Position = clip.xyww;
}
`;

const SKY_FRAGMENT = /* glsl */ `
precision highp float;
${ATMOSPHERE_GLSL}
in vec3 vDir;
out vec4 fragColor;

void main() {
  vec3 dir = normalize(vDir);
  vec3 color = skyRadiance(dir);
  float mu = dot(dir, uSunDir);
  float disc = smoothstep(0.99996, 0.99999, mu);
  color += uSunColor * disc * 60.0;
  color += uSunColor * pow(max(mu, 0.0), 900.0) * 1.4;
  fragColor = vec4(color, 1.0);
}
`;

export interface Sun {
  /** Degrees above the horizon. */
  elevation: number;
  /** Degrees clockwise from north. */
  azimuth: number;
}

export function sunDirection(sun: Sun): THREE.Vector3 {
  const e = THREE.MathUtils.degToRad(sun.elevation);
  const a = THREE.MathUtils.degToRad(sun.azimuth);
  return new THREE.Vector3(Math.sin(a) * Math.cos(e), Math.sin(e), -Math.cos(a) * Math.cos(e));
}

/** The sunlight left after the air above: white high up, gold and red towards the horizon. */
export function sunColor(direction: THREE.Vector3): THREE.Color {
  const mass = 1 / Math.max(direction.y + 0.15 * Math.pow(Math.max(direction.y, 0) + 0.06, -1.25) * 0.1, 0.02);
  const fade = THREE.MathUtils.smoothstep(direction.y, -0.03, 0.05);
  return new THREE.Color(
    4.2 * Math.exp(-0.05 * mass) * fade,
    4.0 * Math.exp(-0.115 * mass) * fade,
    3.8 * Math.exp(-0.26 * mass) * fade,
  );
}

/** Shared by every material that shows the sky or stands in the air. */
export interface AtmosphereUniforms {
  uSky: { value: THREE.Texture };
  uSunDir: { value: THREE.Vector3 };
  uSunColor: { value: THREE.Color };
  uHaze: { value: number };
  [key: string]: THREE.IUniform;
}

export class Atmosphere {
  readonly uniforms: AtmosphereUniforms;
  readonly dome: THREE.Mesh;
  /** Image-based light for ordinary materials, rebuilt with the sun. */
  environment: THREE.Texture | null = null;
  private readonly target = new THREE.WebGLRenderTarget(384, 192, {
    type: THREE.HalfFloatType,
    format: THREE.RGBAFormat,
    magFilter: THREE.LinearFilter,
    minFilter: THREE.LinearFilter,
    wrapS: THREE.RepeatWrapping,
    depthBuffer: false,
  });
  private readonly panorama: THREE.Mesh;
  private readonly camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  private readonly pmrem: THREE.PMREMGenerator;

  constructor(private readonly renderer: THREE.WebGLRenderer) {
    this.uniforms = {
      uSky: { value: this.target.texture },
      uSunDir: { value: new THREE.Vector3(0, 1, 0) },
      uSunColor: { value: new THREE.Color() },
      uHaze: { value: 1 / 130_000 },
    };
    this.panorama = new THREE.Mesh(
      new THREE.PlaneGeometry(2, 2),
      new THREE.RawShaderMaterial({
        glslVersion: THREE.GLSL3,
        vertexShader: `precision highp float; in vec3 position; ${FULLSCREEN_VERTEX}`,
        fragmentShader: PANORAMA_FRAGMENT,
        uniforms: { uSunDir: this.uniforms.uSunDir },
        depthTest: false,
        depthWrite: false,
      }),
    );
    this.panorama.frustumCulled = false;
    this.dome = new THREE.Mesh(
      new THREE.BoxGeometry(2, 2, 2),
      new THREE.ShaderMaterial({
        glslVersion: THREE.GLSL3,
        vertexShader: SKY_VERTEX,
        fragmentShader: SKY_FRAGMENT,
        uniforms: this.uniforms,
        side: THREE.BackSide,
        depthWrite: false,
        depthTest: true,
      }),
    );
    this.dome.frustumCulled = false;
    this.dome.renderOrder = -10;
    this.pmrem = new THREE.PMREMGenerator(renderer);
  }

  setSun(sun: Sun): void {
    const direction = sunDirection(sun);
    this.uniforms.uSunDir.value.copy(direction);
    this.uniforms.uSunColor.value.copy(sunColor(direction));
    const previous = this.renderer.getRenderTarget();
    this.renderer.setRenderTarget(this.target);
    this.renderer.render(this.panorama, this.camera);
    this.renderer.setRenderTarget(previous);

    const scene = new THREE.Scene();
    scene.add(this.dome.clone());
    const old = this.environment;
    this.environment = this.pmrem.fromScene(scene, 0, 1, 100_000).texture;
    old?.dispose();
  }
}

/**
 * Gives a standard material the same aerial perspective as the terrain, for anything standing in
 * the world. The aircraft does not need it; buildings kilometres away do.
 */
export function withAerial(material: THREE.Material, uniforms: AtmosphereUniforms): void {
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vWorld;")
      .replace(
        "#include <project_vertex>",
        `#include <project_vertex>
        #ifdef USE_INSTANCING
        vWorld = (modelMatrix * instanceMatrix * vec4(transformed, 1.0)).xyz;
        #else
        vWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;
        #endif`,
      );
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", `#include <common>\nvarying vec3 vWorld;\n${ATMOSPHERE_GLSL}`)
      .replace(
        "#include <opaque_fragment>",
        "#include <opaque_fragment>\ngl_FragColor.rgb = aerial(gl_FragColor.rgb, vWorld, cameraPosition);",
      );
  };
}
