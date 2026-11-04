/**
 * What the rotor does to the ground: spray off the water, dust off the land, a pale haze off a deck.
 * Sprites leave a ring under the disc, race out along the surface and rise as they slow, each moved by
 * a shader along its own age. A ring of ripples sits on the surface under them. This one effect is
 * most of what tells the eye that a machine is holding itself up on moving air.
 */

import * as THREE from "three";

export type Wash = "water" | "dust" | "rock" | "deck";

const COLORS: Record<Wash, THREE.Color> = {
  water: new THREE.Color(1.5, 1.6, 1.65),
  dust: new THREE.Color(0.62, 0.5, 0.36),
  rock: new THREE.Color(0.52, 0.5, 0.47),
  deck: new THREE.Color(0.7, 0.7, 0.72),
};

const SPRITE_VERTEX = /* glsl */ `
uniform float uTime;
uniform float uScale;
attribute vec3 aFrom;
attribute vec3 aDrive;
attribute vec3 aTone;
attribute vec3 aLife;
varying float vFade;
varying vec3 vTone;
void main() {
  float t = uTime - aLife.x;
  float age = clamp(t / aLife.y, 0.0, 1.0);
  // Thrown out fast, stopped by the air, and lifted by what is left of the flow.
  float run = (1.0 - exp(-t * 1.5)) / 1.5;
  vec3 at = aFrom + vec3(aDrive.x, 0.0, aDrive.z) * run;
  at.y += aDrive.y * run + 0.5 * t * t * 0.25;
  vec4 view = modelViewMatrix * vec4(at, 1.0);
  gl_Position = projectionMatrix * view;
  gl_PointSize = uScale * (aLife.z * (1.0 + 3.2 * sqrt(age))) / max(-view.z, 1.0);
  vFade = age >= 1.0 || t < 0.0 ? 0.0 : smoothstep(0.0, 0.08, age) * (1.0 - age) * (1.0 - age);
  vTone = aTone;
}
`;

const SPRITE_FRAGMENT = /* glsl */ `
varying float vFade;
varying vec3 vTone;
void main() {
  if (vFade <= 0.003) discard;
  vec2 p = gl_PointCoord - 0.5;
  float r = length(p) * 2.0;
  if (r > 1.0) discard;
  float soft = (1.0 - r * r);
  gl_FragColor = vec4(vTone, soft * soft * vFade * 0.34);
  #include <colorspace_fragment>
}
`;

const RING_VERTEX = /* glsl */ `
varying vec2 vPlace;
void main() {
  vPlace = position.xy;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const RING_FRAGMENT = /* glsl */ `
uniform float uTime;
uniform float uPower;
uniform vec3 uTone;
varying vec2 vPlace;
void main() {
  float r = length(vPlace);
  float a = atan(vPlace.y, vPlace.x);
  // Rings running outward, broken up so they read as cat's paws rather than a target.
  float wave = 0.5 + 0.5 * sin(r * 1.5 - uTime * 11.0 + 1.4 * sin(a * 7.0 + r * 0.2));
  float grain = 0.5 + 0.5 * sin(a * 23.0 + r * 3.0 - uTime * 7.0);
  float reach = smoothstep(1.0, 0.5, r / 15.0) * smoothstep(0.1, 0.34, r / 15.0);
  float alpha = (0.2 * wave * wave + 0.1 * grain * wave) * reach * uPower;
  gl_FragColor = vec4(uTone, alpha);
  #include <colorspace_fragment>
}
`;

export class Downwash {
  readonly group = new THREE.Group();
  private readonly points: THREE.Points;
  private readonly ring: THREE.Mesh;
  private readonly from: THREE.BufferAttribute;
  private readonly drive: THREE.BufferAttribute;
  private readonly tone: THREE.BufferAttribute;
  private readonly life: THREE.BufferAttribute;
  private readonly time = { value: 0 };
  private readonly scale = { value: 720 };
  private readonly ringPower = { value: 0 };
  private readonly ringTone = { value: new THREE.Color() };
  private head = 0;
  private debt = 0;
  private readonly count: number;

  constructor(count = 1800) {
    this.count = count;
    const geometry = new THREE.BufferGeometry();
    const attribute = (size: number): THREE.BufferAttribute => {
      const a = new THREE.BufferAttribute(new Float32Array(count * size), size);
      a.setUsage(THREE.DynamicDrawUsage);
      return a;
    };
    this.from = attribute(3);
    this.drive = attribute(3);
    this.tone = attribute(3);
    this.life = attribute(3);
    this.life.array.fill(-100);
    geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(count * 3), 3));
    geometry.setAttribute("aFrom", this.from);
    geometry.setAttribute("aDrive", this.drive);
    geometry.setAttribute("aTone", this.tone);
    geometry.setAttribute("aLife", this.life);
    this.points = new THREE.Points(
      geometry,
      new THREE.ShaderMaterial({
        vertexShader: SPRITE_VERTEX,
        fragmentShader: SPRITE_FRAGMENT,
        uniforms: { uTime: this.time, uScale: this.scale },
        transparent: true,
        depthWrite: false,
      }),
    );
    this.points.frustumCulled = false;
    this.points.renderOrder = 5;
    this.ring = new THREE.Mesh(
      new THREE.CircleGeometry(15, 72),
      new THREE.ShaderMaterial({
        vertexShader: RING_VERTEX,
        fragmentShader: RING_FRAGMENT,
        uniforms: { uTime: this.time, uPower: this.ringPower, uTone: this.ringTone },
        transparent: true,
        depthWrite: false,
      }),
    );
    this.ring.rotation.x = -Math.PI / 2;
    this.ring.visible = false;
    this.ring.renderOrder = 2;
    this.group.add(this.ring, this.points);
  }

  clear(): void {
    this.life.array.fill(-100);
    this.life.needsUpdate = true;
    this.ring.visible = false;
    this.ringPower.value = 0;
  }

  /**
   * `power` 0..1 is how hard the air hits; `centre` the point on the surface under the rotor.
   * `driftX`, `driftZ` are carried by whatever moves the air above it.
   */
  blow(dt: number, centre: THREE.Vector3, power: number, wash: Wash, driftX: number, driftZ: number): void {
    this.ring.visible = power > 0.02;
    if (this.ring.visible) {
      this.ring.position.set(centre.x, centre.y + 0.12, centre.z);
      this.ringPower.value = Math.min(power * (wash === "water" ? 1.6 : 0.7), 1);
      this.ringTone.value.copy(COLORS[wash]);
    }
    const rate = (wash === "water" ? 330 : wash === "deck" ? 22 : 190) * power;
    this.debt += rate * dt;
    const emit = Math.min(Math.floor(this.debt), 60);
    this.debt -= emit;
    const now = this.time.value;
    for (let i = 0; i < emit; i += 1) {
      const at = this.head;
      this.head = (this.head + 1) % this.count;
      const angle = Math.random() * Math.PI * 2;
      const c = Math.cos(angle);
      const s = Math.sin(angle);
      const r = 2.5 + Math.random() * 5;
      const speed = 12 + Math.random() * 14;
      const rise = wash === "water" ? 1.2 + Math.random() * 4.5 : 0.6 + Math.random() * 2.4;
      this.from.setXYZ(at, centre.x + c * r, centre.y + 0.3, centre.z + s * r);
      this.drive.setXYZ(at, c * speed + driftX, rise, s * speed + driftZ);
      const tint = COLORS[wash];
      const shade = 0.82 + Math.random() * 0.25;
      this.tone.setXYZ(at, tint.r * shade, tint.g * shade, tint.b * shade);
      this.life.setXYZ(at, now, 1.2 + Math.random() * 2.2, wash === "water" ? 1.1 + Math.random() * 0.9 : 1.6 + Math.random() * 1.6);
    }
    if (emit > 0) {
      this.from.needsUpdate = true;
      this.drive.needsUpdate = true;
      this.tone.needsUpdate = true;
      this.life.needsUpdate = true;
    }
  }

  update(dt: number, viewportHeight: number): void {
    this.time.value += dt;
    this.scale.value = viewportHeight;
  }
}
