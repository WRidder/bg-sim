/** What a car leaves behind: rubber on the road, smoke, dust, and stones in the air. */

import * as THREE from "three";

/** Dark strips laid behind the wheels; the oldest go first. */
export class SkidMarks {
  readonly mesh: THREE.Mesh;
  private readonly position: THREE.BufferAttribute;
  private readonly alpha: THREE.BufferAttribute;
  private head = 0;
  private readonly last: ({ a: THREE.Vector3; b: THREE.Vector3; strength: number } | null)[] = [null, null, null, null];
  private readonly left = new THREE.Vector3();
  private readonly right = new THREE.Vector3();

  constructor(private readonly quads = 6000) {
    const geometry = new THREE.BufferGeometry();
    this.position = new THREE.BufferAttribute(new Float32Array(quads * 4 * 3), 3);
    this.alpha = new THREE.BufferAttribute(new Float32Array(quads * 4), 1);
    this.position.setUsage(THREE.DynamicDrawUsage);
    this.alpha.setUsage(THREE.DynamicDrawUsage);
    geometry.setAttribute("position", this.position);
    geometry.setAttribute("aAlpha", this.alpha);
    const index = new Uint32Array(quads * 6);
    for (let i = 0; i < quads; i += 1) {
      index.set([i * 4, i * 4 + 1, i * 4 + 2, i * 4 + 1, i * 4 + 3, i * 4 + 2], i * 6);
    }
    geometry.setIndex(new THREE.BufferAttribute(index, 1));
    this.mesh = new THREE.Mesh(
      geometry,
      new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        side: THREE.DoubleSide,
        polygonOffset: true,
        polygonOffsetFactor: -3,
        polygonOffsetUnits: -12,
        uniforms: { uTint: { value: new THREE.Color(0.012, 0.012, 0.014) } },
        vertexShader: /* glsl */ `
          attribute float aAlpha;
          varying float vAlpha;
          void main() {
            vAlpha = aAlpha;
            gl_Position = projectionMatrix * viewMatrix * vec4(position, 1.0);
          }`,
        fragmentShader: /* glsl */ `
          uniform vec3 uTint;
          varying float vAlpha;
          void main() { gl_FragColor = vec4(uTint, vAlpha); }`,
      }),
    );
    this.mesh.frustumCulled = false;
  }

  set tint(color: THREE.Color) {
    ((this.mesh.material as THREE.ShaderMaterial).uniforms.uTint.value as THREE.Color).copy(color);
  }

  clear(): void {
    this.alpha.array.fill(0);
    this.alpha.needsUpdate = true;
    this.last.fill(null);
  }

  /** Extends the mark of a wheel: `side` is a unit across the wheel, `strength` 0 lifts the wheel off. */
  add(wheel: number, at: THREE.Vector3, side: THREE.Vector3, width: number, strength: number): void {
    const previous = this.last[wheel];
    if (strength <= 0.02) {
      this.last[wheel] = null;
      return;
    }
    this.left.copy(at).addScaledVector(side, width);
    this.right.copy(at).addScaledVector(side, -width);
    if (previous) {
      if (previous.a.distanceToSquared(this.left) < 0.16) {
        return;
      }
      const i = this.head;
      this.head = (i + 1) % this.quads;
      const p = this.position;
      p.setXYZ(i * 4, previous.a.x, previous.a.y, previous.a.z);
      p.setXYZ(i * 4 + 1, previous.b.x, previous.b.y, previous.b.z);
      p.setXYZ(i * 4 + 2, this.left.x, this.left.y, this.left.z);
      p.setXYZ(i * 4 + 3, this.right.x, this.right.y, this.right.z);
      this.alpha.setX(i * 4, previous.strength);
      this.alpha.setX(i * 4 + 1, previous.strength);
      this.alpha.setX(i * 4 + 2, strength);
      this.alpha.setX(i * 4 + 3, strength);
      p.needsUpdate = true;
      this.alpha.needsUpdate = true;
      previous.a.copy(this.left);
      previous.b.copy(this.right);
      previous.strength = strength;
    } else {
      this.last[wheel] = { a: this.left.clone(), b: this.right.clone(), strength };
    }
  }
}

/** Soft sprites that a shader moves along their own age, so a thousand cost one draw call. */
export class Puffs {
  readonly points: THREE.Points;
  private readonly time = { value: 0 };
  private readonly scale = { value: 720 };
  private readonly position: THREE.BufferAttribute;
  private readonly velocity: THREE.BufferAttribute;
  private readonly start: THREE.BufferAttribute;
  private readonly look: THREE.BufferAttribute;
  private head = 0;

  constructor(
    private readonly count: number,
    sun: { value: THREE.Vector3 },
    sunColor: { value: THREE.Color },
  ) {
    const geometry = new THREE.BufferGeometry();
    this.position = new THREE.BufferAttribute(new Float32Array(count * 3), 3);
    this.velocity = new THREE.BufferAttribute(new Float32Array(count * 3), 3);
    // Birth time, lifetime, start size, end size.
    this.start = new THREE.BufferAttribute(new Float32Array(count * 4).fill(-100), 4);
    // Colour and opacity.
    this.look = new THREE.BufferAttribute(new Float32Array(count * 4), 4);
    for (const attribute of [this.position, this.velocity, this.start, this.look]) {
      attribute.setUsage(THREE.DynamicDrawUsage);
    }
    geometry.setAttribute("position", this.position);
    geometry.setAttribute("aVelocity", this.velocity);
    geometry.setAttribute("aStart", this.start);
    geometry.setAttribute("aLook", this.look);
    this.points = new THREE.Points(
      geometry,
      new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        uniforms: { uTime: this.time, uScale: this.scale, uSunDir: sun, uSunColor: sunColor },
        vertexShader: /* glsl */ `
          uniform float uTime;
          uniform float uScale;
          attribute vec3 aVelocity;
          attribute vec4 aStart;
          attribute vec4 aLook;
          varying float vAge;
          varying vec4 vLook;
          varying float vSpin;
          void main() {
            float t = uTime - aStart.x;
            vAge = t / aStart.y;
            vLook = aLook;
            vSpin = aStart.x * 37.0;
            // Thrown out, stopped by the air, then drifting up a little.
            float drag = (1.0 - exp(-t * 2.4)) / 2.4;
            vec3 at = position + aVelocity * drag + vec3(0.25, 0.42, 0.12) * t * sqrt(max(t, 0.0));
            vec4 view = viewMatrix * vec4(at, 1.0);
            gl_Position = projectionMatrix * view;
            float size = mix(aStart.z, aStart.w, 1.0 - pow(1.0 - clamp(vAge, 0.0, 1.0), 2.4));
            gl_PointSize = vAge < 0.0 || vAge >= 1.0 ? 0.0 : uScale * size / max(-view.z, 0.5);
          }`,
        fragmentShader: /* glsl */ `
          uniform vec3 uSunDir;
          uniform vec3 uSunColor;
          varying float vAge;
          varying vec4 vLook;
          varying float vSpin;
          void main() {
            vec2 p = (gl_PointCoord - 0.5) * 2.0;
            float r = dot(p, p);
            if (r > 1.0 || vAge >= 1.0) discard;
            // A lumpy edge and a lit side, so it reads as a volume rather than a disc.
            float a = atan(p.y, p.x) + vSpin;
            float lump = 0.82 + 0.18 * sin(a * 3.0) * sin(a * 5.0 + 1.0);
            float soft = 1.0 - smoothstep(0.15, lump, r);
            vec3 normal = normalize(vec3(p.x, -p.y, 0.8));
            float light = 0.55 + 0.45 * max(dot(normal, normalize(vec3(uSunDir.x, uSunDir.y + 0.3, 0.4))), 0.0);
            vec3 color = vLook.rgb * uSunColor * 0.32 * light;
            gl_FragColor = vec4(color, soft * vLook.a * pow(1.0 - vAge, 1.4) * smoothstep(0.0, 0.05, vAge));
          }`,
      }),
    );
    this.points.frustumCulled = false;
  }

  emit(at: THREE.Vector3, vx: number, vy: number, vz: number, life: number, from: number, to: number, color: THREE.Color, opacity: number): void {
    const i = this.head;
    this.head = (i + 1) % this.count;
    this.position.setXYZ(i, at.x, at.y, at.z);
    this.velocity.setXYZ(i, vx, vy, vz);
    this.start.setXYZW(i, this.time.value, life, from, to);
    this.look.setXYZW(i, color.r, color.g, color.b, opacity);
    this.position.needsUpdate = true;
    this.velocity.needsUpdate = true;
    this.start.needsUpdate = true;
    this.look.needsUpdate = true;
  }

  clear(): void {
    (this.start.array as Float32Array).fill(-100);
    this.start.needsUpdate = true;
  }

  update(dt: number, viewportHeight: number, fov: number): void {
    this.time.value += dt;
    this.scale.value = viewportHeight / (2 * Math.tan((fov * Math.PI) / 360));
  }
}
