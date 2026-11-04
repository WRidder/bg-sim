/**
 * From the scene to the screen. The world goes first, then the half-resolution clouds over it, and
 * only then what is near the camera: the aircraft and its effects stay sharp against a cloud,
 * because they never pass through the clouds' lower resolution. A bloom made by repeated
 * downsampling, filmic tone mapping and a last touch of grading finish it. Drawn by hand rather
 * than with EffectComposer, because the clouds need the world's depth and the bundle stays small.
 */

import * as THREE from "three";
import type { Clouds } from "./clouds";

const VERTEX = /* glsl */ `
precision highp float;
in vec3 position;
out vec2 vUv;
void main() {
  vUv = position.xy * 0.5 + 0.5;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

const DOWN = /* glsl */ `
precision highp float;
uniform sampler2D uSource;
uniform vec2 uTexel;
uniform float uThreshold;
in vec2 vUv;
out vec4 fragColor;
// One NaN, infinite or negative pixel must not grow through the chain into a block of wrong colour.
vec3 tap(vec2 uv) {
  vec3 c = texture(uSource, uv).rgb;
  return all(lessThan(abs(c), vec3(1000.0))) ? max(c, vec3(0.0)) : vec3(0.0);
}
void main() {
  vec3 c = tap(vUv) * 4.0;
  c += tap(vUv + uTexel * vec2(-1.0, -1.0));
  c += tap(vUv + uTexel * vec2(1.0, -1.0));
  c += tap(vUv + uTexel * vec2(-1.0, 1.0));
  c += tap(vUv + uTexel * vec2(1.0, 1.0));
  c /= 8.0;
  if (uThreshold > 0.0) {
    float brightness = max(c.r, max(c.g, c.b));
    c *= smoothstep(uThreshold, uThreshold * 2.5, brightness);
  }
  fragColor = vec4(min(c, vec3(40.0)), 1.0);
}
`;

const UP = /* glsl */ `
precision highp float;
uniform sampler2D uSource;
uniform vec2 uTexel;
in vec2 vUv;
out vec4 fragColor;
void main() {
  vec3 c = texture(uSource, vUv + uTexel * vec2(-1.0, 0.0)).rgb;
  c += texture(uSource, vUv + uTexel * vec2(1.0, 0.0)).rgb;
  c += texture(uSource, vUv + uTexel * vec2(0.0, -1.0)).rgb;
  c += texture(uSource, vUv + uTexel * vec2(0.0, 1.0)).rgb;
  c += (texture(uSource, vUv + uTexel * vec2(-0.7, 0.7)).rgb + texture(uSource, vUv + uTexel * vec2(0.7, 0.7)).rgb +
        texture(uSource, vUv + uTexel * vec2(-0.7, -0.7)).rgb + texture(uSource, vUv + uTexel * vec2(0.7, -0.7)).rgb) * 2.0;
  fragColor = vec4(c / 12.0, 1.0);
}
`;

const COMPOSE = /* glsl */ `
precision highp float;
uniform sampler2D uWorld;
uniform sampler2D uDepth;
uniform sampler2D uClouds;
in vec2 vUv;
out vec4 fragColor;
void main() {
  // A tent over the half-resolution pixels takes out the grain of the rays' jitter.
  vec2 texel = 1.0 / vec2(textureSize(uClouds, 0));
  vec4 clouds = texture(uClouds, vUv) * 0.28;
  clouds += texture(uClouds, vUv + texel * vec2(1.0, 0.5)) * 0.18;
  clouds += texture(uClouds, vUv + texel * vec2(-1.0, -0.5)) * 0.18;
  clouds += texture(uClouds, vUv + texel * vec2(-0.5, 1.0)) * 0.18;
  clouds += texture(uClouds, vUv + texel * vec2(0.5, -1.0)) * 0.18;
  fragColor = vec4(texture(uWorld, vUv).rgb * clouds.a + clouds.rgb, 1.0);
  // Near objects still go behind the land: the world's depth carries over.
  gl_FragDepth = texture(uDepth, vUv).r;
}
`;

const FINAL = /* glsl */ `
precision highp float;
uniform sampler2D uScene;
uniform sampler2D uBloom;
uniform float uBloomAmount;
uniform float uExposure;
uniform float uVignette;
uniform float uFlash;
uniform vec3 uFade;
uniform float uTime;
in vec2 vUv;
out vec4 fragColor;

// Narkowicz's ACES fit, with a little of the original's desaturation of hot colours kept by hand.
vec3 tonemap(vec3 x) {
  return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0);
}

void main() {
  vec3 color = texture(uScene, vUv).rgb;
  color += texture(uBloom, vUv).rgb * uBloomAmount;
  color *= uExposure;
  color = tonemap(color);
  vec2 c = vUv - 0.5;
  color *= 1.0 - uVignette * smoothstep(0.25, 0.85, dot(c, c) * 2.4);
  color = pow(color, vec3(1.0 / 2.2));
  float luma = dot(color, vec3(0.2126, 0.7152, 0.0722));
  color = mix(vec3(luma), color, 1.08);
  // Dither to hide the banding of 8 bits across a big, smooth sky.
  float n = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))) + uTime);
  color += (n - 0.5) / 255.0;
  color = mix(color, uFade, uFlash);
  fragColor = vec4(color, 1.0);
}
`;

const CHAIN = 5;

export class Pipeline {
  readonly world: THREE.WebGLRenderTarget;
  readonly scene: THREE.WebGLRenderTarget;
  /** Clear to an effect: 0 nothing, 1 entirely `fadeColor`. */
  flash = 0;
  fadeColor = new THREE.Color(0, 0, 0);
  exposure = 0.62;
  private readonly quad = new THREE.Scene();
  private readonly camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  private readonly mesh: THREE.Mesh;
  private readonly down: THREE.RawShaderMaterial;
  private readonly up: THREE.RawShaderMaterial;
  private readonly final: THREE.RawShaderMaterial;
  private readonly compose: THREE.RawShaderMaterial;
  private readonly chain: THREE.WebGLRenderTarget[] = [];

  constructor(
    private readonly renderer: THREE.WebGLRenderer,
    private readonly clouds: Clouds,
    samples = 4,
  ) {
    this.world = new THREE.WebGLRenderTarget(4, 4, {
      type: THREE.HalfFloatType,
      format: THREE.RGBAFormat,
      samples,
      depthBuffer: true,
      depthTexture: new THREE.DepthTexture(4, 4, THREE.FloatType),
    });
    this.scene = new THREE.WebGLRenderTarget(4, 4, {
      type: THREE.HalfFloatType,
      format: THREE.RGBAFormat,
      samples,
      depthBuffer: true,
    });
    for (let i = 0; i < CHAIN; i += 1) {
      this.chain.push(
        new THREE.WebGLRenderTarget(4, 4, {
          type: THREE.HalfFloatType,
          format: THREE.RGBAFormat,
          depthBuffer: false,
          magFilter: THREE.LinearFilter,
          minFilter: THREE.LinearFilter,
        }),
      );
    }
    const raw = (fragmentShader: string, uniforms: Record<string, THREE.IUniform>) =>
      new THREE.RawShaderMaterial({
        glslVersion: THREE.GLSL3,
        vertexShader: VERTEX,
        fragmentShader,
        uniforms,
        depthTest: false,
        depthWrite: false,
      });
    this.down = raw(DOWN, { uSource: { value: null }, uTexel: { value: new THREE.Vector2() }, uThreshold: { value: 0 } });
    this.up = raw(UP, { uSource: { value: null }, uTexel: { value: new THREE.Vector2() } });
    this.up.blending = THREE.AdditiveBlending;
    this.up.transparent = true;
    this.compose = raw(COMPOSE, {
      uWorld: { value: this.world.texture },
      uDepth: { value: this.world.depthTexture },
      uClouds: { value: clouds.target.texture },
    });
    this.compose.depthTest = true;
    this.compose.depthFunc = THREE.AlwaysDepth;
    this.compose.depthWrite = true;
    this.final = raw(FINAL, {
      uScene: { value: this.scene.texture },
      uBloom: { value: this.chain[0].texture },
      uBloomAmount: { value: 0.32 },
      uExposure: { value: this.exposure },
      uVignette: { value: 0.28 },
      uFlash: { value: 0 },
      uFade: { value: this.fadeColor },
      uTime: { value: 0 },
    });
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), this.final);
    this.mesh.frustumCulled = false;
    this.quad.add(this.mesh);
  }

  resize(width: number, height: number): void {
    this.world.setSize(width, height);
    this.scene.setSize(width, height);
    this.clouds.resize(width, height);
    this.chain.forEach((target, i) => {
      target.setSize(Math.max(2, width >> (i + 1)), Math.max(2, height >> (i + 1)));
    });
  }

  private blit(material: THREE.RawShaderMaterial, target: THREE.WebGLRenderTarget | null): void {
    this.mesh.material = material;
    this.renderer.setRenderTarget(target);
    this.renderer.render(this.quad, this.camera);
  }

  render(world: THREE.Scene, near: THREE.Scene, camera: THREE.PerspectiveCamera, time: number): void {
    const { renderer } = this;
    renderer.setRenderTarget(this.world);
    renderer.clear();
    renderer.render(world, camera);
    this.clouds.render(renderer, camera, this.world.depthTexture as THREE.Texture, time);
    this.blit(this.compose, this.scene);
    renderer.autoClear = false;
    renderer.setRenderTarget(this.scene);
    renderer.render(near, camera);
    renderer.autoClear = true;

    let source: THREE.WebGLRenderTarget = this.scene;
    this.down.uniforms.uThreshold.value = 2.2;
    for (const target of this.chain) {
      this.down.uniforms.uSource.value = source.texture;
      this.down.uniforms.uTexel.value.set(1 / source.width, 1 / source.height);
      this.blit(this.down, target);
      this.down.uniforms.uThreshold.value = 0;
      source = target;
    }
    renderer.autoClear = false;
    for (let i = CHAIN - 1; i > 0; i -= 1) {
      this.up.uniforms.uSource.value = this.chain[i].texture;
      this.up.uniforms.uTexel.value.set(1 / this.chain[i].width, 1 / this.chain[i].height);
      this.blit(this.up, this.chain[i - 1]);
    }
    renderer.autoClear = true;

    const u = this.final.uniforms;
    u.uExposure.value = this.exposure;
    u.uFlash.value = this.flash;
    u.uTime.value = time % 1;
    this.blit(this.final, null);
  }
}
