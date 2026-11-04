/** Things in the air that last a moment: vapour trails off the wingtips, and a fireball. */

import * as THREE from "three";

/** A ribbon laid along a moving point. It turns to face the camera and fades as it ages. */
export class Trail {
  readonly mesh: THREE.Mesh;
  private readonly points: THREE.Vector3[];
  private readonly strength: Float32Array;
  private readonly position: THREE.BufferAttribute;
  private readonly alpha: THREE.BufferAttribute;
  private head = 0;
  private readonly side = new THREE.Vector3();
  private readonly along = new THREE.Vector3();
  private readonly toEye = new THREE.Vector3();

  constructor(
    private readonly length = 90,
    private readonly width = 0.4,
    color = new THREE.Color(1.6, 1.65, 1.75),
  ) {
    this.points = Array.from({ length }, () => new THREE.Vector3());
    this.strength = new Float32Array(length);
    const geometry = new THREE.BufferGeometry();
    this.position = new THREE.BufferAttribute(new Float32Array(length * 6), 3);
    this.alpha = new THREE.BufferAttribute(new Float32Array(length * 2), 1);
    this.position.setUsage(THREE.DynamicDrawUsage);
    this.alpha.setUsage(THREE.DynamicDrawUsage);
    geometry.setAttribute("position", this.position);
    geometry.setAttribute("aAlpha", this.alpha);
    const index: number[] = [];
    for (let i = 0; i < length - 1; i += 1) {
      const a = i * 2;
      index.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
    geometry.setIndex(index);
    this.mesh = new THREE.Mesh(
      geometry,
      new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        side: THREE.DoubleSide,
        uniforms: { uColor: { value: color } },
        vertexShader: /* glsl */ `
          attribute float aAlpha;
          varying float vAlpha;
          void main() {
            vAlpha = aAlpha;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
          }`,
        fragmentShader: /* glsl */ `
          uniform vec3 uColor;
          varying float vAlpha;
          void main() { gl_FragColor = vec4(uColor, vAlpha); }`,
      }),
    );
    this.mesh.frustumCulled = false;
  }

  /** Adds a point; `strength` 0 leaves a gap in the ribbon. */
  add(point: THREE.Vector3, strength: number): void {
    this.head = (this.head + 1) % this.length;
    this.points[this.head].copy(point);
    this.strength[this.head] = strength;
  }

  clear(): void {
    this.strength.fill(0);
  }

  update(eye: THREE.Vector3): void {
    const { length, points, strength } = this;
    for (let i = 0; i < length; i += 1) {
      const at = (this.head - i + length) % length;
      const point = points[at];
      const older = points[(at - 1 + length) % length];
      const age = i / (length - 1);
      this.along.subVectors(older, point);
      this.toEye.subVectors(eye, point);
      this.side.crossVectors(this.along, this.toEye);
      const n = this.side.length();
      if (n > 1e-6) {
        this.side.multiplyScalar(((1 + 4 * age) * this.width) / n);
      }
      this.position.setXYZ(i * 2, point.x - this.side.x, point.y - this.side.y, point.z - this.side.z);
      this.position.setXYZ(i * 2 + 1, point.x + this.side.x, point.y + this.side.y, point.z + this.side.z);
      const fade = strength[at] * (1 - age) ** 1.6 * 0.5;
      this.alpha.setX(i * 2, fade);
      this.alpha.setX(i * 2 + 1, fade);
    }
    this.position.needsUpdate = true;
    this.alpha.needsUpdate = true;
  }
}

/** A fireball that rolls up into smoke, drawn as sprites that a shader moves along their own age. */
export class Burst {
  readonly points: THREE.Points;
  private readonly time = { value: 100 };

  constructor(count = 420) {
    const geometry = new THREE.BufferGeometry();
    const direction = new Float32Array(count * 3);
    const seed = new Float32Array(count * 2);
    for (let i = 0; i < count; i += 1) {
      const v = new THREE.Vector3().randomDirection();
      v.y = Math.abs(v.y) * 0.8 + 0.1;
      v.multiplyScalar(10 + 70 * Math.random() ** 2);
      direction.set([v.x, v.y, v.z], i * 3);
      seed.set([Math.random(), Math.random()], i * 2);
    }
    geometry.setAttribute("position", new THREE.BufferAttribute(direction, 3));
    geometry.setAttribute("aSeed", new THREE.BufferAttribute(seed, 2));
    this.points = new THREE.Points(
      geometry,
      new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        uniforms: { uTime: this.time, uScale: { value: 720 } },
        vertexShader: /* glsl */ `
          uniform float uTime;
          uniform float uScale;
          attribute vec2 aSeed;
          varying float vAge;
          void main() {
            float t = max(uTime - aSeed.y * 0.25, 0.0);
            vAge = t / (2.2 + 4.0 * aSeed.x);
            // Hurled out fast, stopped by the air, then rising.
            vec3 at = position * (1.0 - exp(-t * 2.2)) * 0.8 + vec3(0.0, 1.0, 0.0) * t * t * (0.6 + aSeed.x);
            vec4 view = modelViewMatrix * vec4(at, 1.0);
            gl_Position = projectionMatrix * view;
            gl_PointSize = uScale * (5.0 + 26.0 * sqrt(min(vAge, 1.0))) / max(-view.z, 1.0);
          }`,
        fragmentShader: /* glsl */ `
          varying float vAge;
          void main() {
            float r = length(gl_PointCoord - 0.5) * 2.0;
            if (vAge >= 1.0 || r > 1.0) discard;
            float soft = 1.0 - r * r;
            float fire = exp(-vAge * 9.0);
            vec3 smoke = vec3(0.05, 0.05, 0.055);
            vec3 color = mix(smoke, vec3(9.0, 3.6, 0.9), fire);
            gl_FragColor = vec4(color, soft * (1.0 - vAge) * (0.45 + 0.5 * fire));
          }`,
      }),
    );
    this.points.frustumCulled = false;
    this.points.visible = false;
  }

  fire(at: THREE.Vector3): void {
    this.points.position.copy(at);
    this.points.visible = true;
    this.time.value = 0;
  }

  clear(): void {
    this.points.visible = false;
  }

  update(dt: number, viewportHeight: number): void {
    this.time.value += dt;
    (this.points.material as THREE.ShaderMaterial).uniforms.uScale.value = viewportHeight;
    if (this.time.value > 8) {
      this.points.visible = false;
    }
  }
}
