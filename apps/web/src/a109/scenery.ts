/**
 * What the pads look like: the decks with their painted H, the ship, the hospital, the ledge's rock,
 * the clearing, and the column of light over the next one. The numbers come from `pads.ts`, which
 * the physics shares. Decks join the near scene, where they catch the helicopter's real shadow on the
 * way down; what stands under them joins the world, so the air and the clouds fall over it.
 */

import * as THREE from "three";
import { type AtmosphereUniforms, withAerial } from "../engine/atmosphere";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { hash2 } from "../engine/noise";
import { type Pad, type PadKind, SHIP, TOWER } from "./pads";
import type { Ground, Surface } from "./surface";

const DEG = Math.PI / 180;

type DeckStyle = { ground: string; line: string; h: string; ring: string; grain: "concrete" | "steel" | "boards" | "tar" | "net" };

const DECKS: Record<PadKind, DeckStyle> = {
  apron: { ground: "#6d6d68", line: "#e9c33c", h: "#f1f1ea", ring: "#e9c33c", grain: "concrete" },
  ship: { ground: "#28342f", line: "#f1f1ea", h: "#f1f1ea", ring: "#e9c33c", grain: "net" },
  clearing: { ground: "#5f4c36", line: "#e8e2d2", h: "#efe9d8", ring: "#e8e2d2", grain: "boards" },
  roof: { ground: "#4a4e52", line: "#f1f1ea", h: "#e04232", ring: "#e04232", grain: "tar" },
  ledge: { ground: "#3b3f42", line: "#e9c33c", h: "#f1f1ea", ring: "#f08a2c", grain: "steel" },
};

function deckTexture(style: DeckStyle): THREE.CanvasTexture {
  const size = 1024;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const c = canvas.getContext("2d") as CanvasRenderingContext2D;
  c.fillStyle = style.ground;
  c.fillRect(0, 0, size, size);
  const speck = (count: number, light: number): void => {
    for (let i = 0; i < count; i += 1) {
      c.fillStyle = `rgba(${i % 2 ? "255,255,255" : "0,0,0"},${0.02 + Math.random() * light})`;
      c.fillRect(Math.random() * size, Math.random() * size, 2 + Math.random() * 14, 2 + Math.random() * 14);
    }
  };
  if (style.grain === "boards") {
    for (let y = 0; y < size; y += 58) {
      c.fillStyle = `rgba(0,0,0,${0.1 + Math.random() * 0.2})`;
      c.fillRect(0, y, size, 56);
      c.fillStyle = "rgba(0,0,0,0.65)";
      c.fillRect(0, y + 54, size, 4);
    }
    speck(1300, 0.05);
  } else if (style.grain === "steel" || style.grain === "net") {
    speck(800, 0.05);
    c.strokeStyle = style.grain === "steel" ? "rgba(0,0,0,0.4)" : "rgba(235,235,225,0.13)";
    c.lineWidth = style.grain === "steel" ? 3 : 2;
    const step = style.grain === "steel" ? 24 : 40;
    for (let i = -size; i < size * 2; i += step) {
      c.beginPath();
      c.moveTo(i, 0);
      c.lineTo(style.grain === "steel" ? i : i + size, size);
      c.moveTo(0, i);
      c.lineTo(size, style.grain === "steel" ? i : i - size);
      c.stroke();
    }
  } else {
    speck(2400, 0.05);
    for (let i = 0; i < 6; i += 1) {
      c.fillStyle = "rgba(0,0,0,0.16)";
      c.fillRect(0, i * 170 + 40, size, 2);
      c.fillRect(i * 170 + 40, 0, 2, size);
    }
  }
  const m = size / 2;
  c.lineWidth = 34;
  c.strokeStyle = style.ring;
  c.beginPath();
  c.arc(m, m, m * 0.74, 0, Math.PI * 2);
  c.stroke();
  // The rim: broken, as the deck markings on a real pad are.
  c.lineWidth = 20;
  c.strokeStyle = style.line;
  c.setLineDash([64, 42]);
  c.beginPath();
  c.arc(m, m, m * 0.94, 0, Math.PI * 2);
  c.stroke();
  c.setLineDash([]);
  c.fillStyle = style.h;
  const tall = size * 0.42;
  const stem = size * 0.075;
  const wide = size * 0.26;
  c.fillRect(m - wide / 2 - stem / 2, m - tall / 2, stem, tall);
  c.fillRect(m + wide / 2 - stem / 2, m - tall / 2, stem, tall);
  c.fillRect(m - wide / 2, m - stem / 2, wide, stem);
  // Tyre marks and wear over the paint.
  c.globalCompositeOperation = "multiply";
  for (let i = 0; i < 120; i += 1) {
    c.fillStyle = `rgba(90,90,90,${0.02 + Math.random() * 0.06})`;
    c.beginPath();
    c.ellipse(m + (Math.random() - 0.5) * size * 0.5, m + (Math.random() - 0.5) * size * 0.5, 6 + Math.random() * 60, 4 + Math.random() * 24, Math.random() * 3, 0, Math.PI * 2);
    c.fill();
  }
  c.globalCompositeOperation = "source-over";
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}

function facadeTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 256;
  const c = canvas.getContext("2d") as CanvasRenderingContext2D;
  c.fillStyle = "#c9ccc8";
  c.fillRect(0, 0, 256, 256);
  c.fillStyle = "#2c3f4a";
  c.fillRect(0, 56, 256, 120);
  for (let x = 0; x < 256; x += 64) {
    c.fillStyle = "#9fb2bb";
    c.fillRect(x, 56, 6, 120);
  }
  c.fillStyle = "rgba(160,200,215,0.28)";
  c.fillRect(10, 62, 110, 56);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 8;
  return texture;
}

function windowBand(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 32;
  const c = canvas.getContext("2d") as CanvasRenderingContext2D;
  c.fillStyle = "#e4e4dc";
  c.fillRect(0, 0, 64, 32);
  c.fillStyle = "#1a2830";
  c.fillRect(6, 6, 52, 20);
  c.fillStyle = "#5c7c8a";
  c.fillRect(8, 8, 26, 8);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = THREE.RepeatWrapping;
  texture.anisotropy = 4;
  return texture;
}

function sockTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 16;
  const c = canvas.getContext("2d") as CanvasRenderingContext2D;
  for (let i = 0; i < 5; i += 1) {
    c.fillStyle = i % 2 ? "#eeeeee" : "#ef5a1e";
    c.fillRect((i * 128) / 5, 0, 128 / 5, 16);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

const BEAM_FRAGMENT = /* glsl */ `
uniform float uStrength;
uniform float uTime;
varying vec2 vUv;
varying vec3 vNormalView;
varying vec3 vView;
void main() {
  float edge = pow(max(dot(normalize(vNormalView), normalize(vView)), 0.0), 2.0);
  float rise = (1.0 - vUv.y);
  float column = edge * (0.1 + 0.9 * exp(-(1.0 - rise) * 3.0)) * uStrength;
  float pulse = 0.9 + 0.1 * sin(uTime * 3.0 - vUv.y * 40.0);
  gl_FragColor = vec4(vec3(3.2, 2.0, 0.55) * pulse, column * 0.5);
  #include <colorspace_fragment>
}
`;

const BEAM_VERTEX = /* glsl */ `
varying vec2 vUv;
varying vec3 vNormalView;
varying vec3 vView;
void main() {
  vUv = uv;
  vec4 view = modelViewMatrix * vec4(position, 1.0);
  vView = -view.xyz;
  vNormalView = normalize(normalMatrix * normal);
  gl_Position = projectionMatrix * view;
}
`;

/** A tree the scenery redraws: its place and its colour, as the island's forest had them. */
export interface Tree {
  matrix: THREE.Matrix4;
  color: THREE.Color;
}

interface Sock {
  turn: THREE.Group;
  sag: THREE.Group;
}

export class Scenery {
  /** For the world scene and the near scene. */
  readonly world = new THREE.Group();
  readonly near = new THREE.Group();
  private readonly beam: THREE.Mesh;
  private readonly strength = { value: 0 };
  private readonly time = { value: 0 };
  private readonly ring: THREE.Mesh;
  private readonly socks: Sock[] = [];
  private readonly lights: THREE.MeshBasicMaterial;
  private target: Pad | null = null;
  private readonly at = new THREE.Vector3();
  private readonly aerial: <M extends THREE.Material>(material: M) => M;
  private readonly sock = sockTexture();

  constructor(
    pads: readonly Pad[],
    private readonly ground: Ground,
    uniforms: AtmosphereUniforms,
  ) {
    this.aerial = (material) => {
      withAerial(material, uniforms);
      return material;
    };
    this.lights = new THREE.MeshBasicMaterial({ color: new THREE.Color(0.5, 4, 1.4), toneMapped: false });
    for (const pad of pads) {
      this.deck(pad);
      this[pad.id](pad);
    }
    this.beam = new THREE.Mesh(
      new THREE.CylinderGeometry(9, 9, 900, 28, 1, true),
      new THREE.ShaderMaterial({
        vertexShader: BEAM_VERTEX,
        fragmentShader: BEAM_FRAGMENT,
        uniforms: { uStrength: this.strength, uTime: this.time },
        transparent: true,
        depthWrite: false,
        side: THREE.FrontSide,
      }),
    );
    this.beam.frustumCulled = false;
    this.beam.renderOrder = 6;
    this.beam.visible = false;
    this.ring = new THREE.Mesh(
      new THREE.RingGeometry(0.93, 1, 72),
      new THREE.MeshBasicMaterial({ color: new THREE.Color(3.4, 2.1, 0.5), transparent: true, opacity: 0.9, toneMapped: false, side: THREE.DoubleSide, depthWrite: false }),
    );
    this.ring.rotation.x = -Math.PI / 2;
    this.ring.visible = false;
    this.near.add(this.beam, this.ring);
  }

  private standard(color: number, roughness = 0.8, metalness = 0): THREE.MeshStandardMaterial {
    return this.aerial(new THREE.MeshStandardMaterial({ color, roughness, metalness }));
  }

  private deck(pad: Pad): void {
    const radius = pad.id === "roof" ? 13.5 : pad.id === "ledge" ? 15.5 : pad.id === "ship" ? 11.5 : pad.id === "clearing" ? 12 : 15;
    const style = DECKS[pad.id];
    const top = new THREE.Mesh(
      new THREE.CircleGeometry(radius, 72),
      this.aerial(new THREE.MeshStandardMaterial({ map: deckTexture(style), roughness: 0.82, metalness: style.grain === "steel" ? 0.4 : 0 })),
    );
    top.rotation.x = -Math.PI / 2;
    top.rotation.z = (pad.heading + 180) * -DEG;
    top.position.set(pad.east, pad.top, -pad.north);
    top.receiveShadow = true;
    this.near.add(top);
    const rim = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius + 0.3, 0.6, 72, 1, true), this.standard(0x3e4144, 0.7, 0.3));
    rim.position.set(pad.east, pad.top - 0.3, -pad.north);
    this.near.add(rim);
    // The edge lights, as small points that bloom.
    const bulb = new THREE.SphereGeometry(0.11, 8, 6);
    const lamps = new THREE.InstancedMesh(bulb, this.lights, 16);
    const matrix = new THREE.Matrix4();
    for (let i = 0; i < 16; i += 1) {
      const a = (i * Math.PI) / 8;
      matrix.setPosition(pad.east + Math.cos(a) * (radius - 0.1), pad.top + 0.1, -pad.north + Math.sin(a) * (radius - 0.1));
      lamps.setMatrixAt(i, matrix);
    }
    lamps.frustumCulled = false;
    this.near.add(lamps);
    this.windsock(pad, radius + 1.5);
  }

  private windsock(pad: Pad, reach: number): void {
    const a = (pad.heading + 130) * DEG;
    const pole = new THREE.Group();
    pole.position.set(pad.east + Math.sin(a) * reach, pad.top - 0.4, -pad.north - Math.cos(a) * reach);
    if (pad.id === "ship") {
      pole.position.y += 0.2;
    }
    const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.08, 6.5, 8), this.standard(0xcfcfca, 0.5, 0.4));
    mast.position.y = 3.25;
    pole.add(mast);
    const turn = new THREE.Group();
    turn.position.y = 6.4;
    pole.add(turn);
    const sag = new THREE.Group();
    turn.add(sag);
    const cone = new THREE.CylinderGeometry(0.34, 0.14, 2.6, 16, 1, true);
    cone.rotateZ(Math.PI / 2);
    cone.translate(1.3, 0, 0);
    sag.add(new THREE.Mesh(cone, this.aerial(new THREE.MeshStandardMaterial({ map: this.sock, side: THREE.DoubleSide, roughness: 0.9 }))));
    this.near.add(pole);
    this.socks.push({ turn, sag });
  }

  private person(east: number, north: number, up: number, color: number, facing: number): void {
    const figure = new THREE.Group();
    figure.position.set(east, up, -north);
    figure.rotation.y = facing;
    const trousers = this.standard(0x1d2228, 0.8);
    for (const side of [-0.1, 0.1]) {
      const leg = new THREE.Mesh(new THREE.CapsuleGeometry(0.085, 0.66, 3, 8), trousers);
      leg.position.set(side, 0.42, 0);
      figure.add(leg);
    }
    const vest = this.standard(color, 0.6);
    const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.17, 0.34, 3, 10), vest);
    torso.position.y = 1.14;
    torso.scale.z = 0.72;
    figure.add(torso);
    for (const side of [-1, 1]) {
      const arm = new THREE.Mesh(new THREE.CapsuleGeometry(0.055, 0.5, 3, 6), vest);
      arm.position.set(side * 0.25, 1.1, 0);
      arm.rotation.z = side * 0.14;
      figure.add(arm);
    }
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.1, 10, 8), this.standard(0xd8ae88, 0.6));
    head.position.y = 1.6;
    const helmet = new THREE.Mesh(new THREE.SphereGeometry(0.115, 10, 6, 0, Math.PI * 2, 0, Math.PI * 0.55), this.standard(0xf0f0ea, 0.4));
    helmet.position.y = 1.615;
    figure.add(head, helmet);
    this.near.add(figure);
  }

  private crew(pad: Pad, bearing: number, reach: number, color: number, count = 3): void {
    for (let i = 0; i < count; i += 1) {
      const a = (bearing + i * 5) * DEG;
      // They watch the deck, not each other.
      this.person(pad.east + Math.sin(a) * reach, pad.north + Math.cos(a) * reach, pad.top, color, Math.PI + a + i * 0.3);
    }
  }

  private apron(pad: Pad): void {
    const tanker = new THREE.Group();
    const a = (pad.heading + 200) * DEG;
    tanker.position.set(pad.east + Math.sin(a) * 26, pad.base + 0.2, -pad.north - Math.cos(a) * 26);
    tanker.rotation.y = -pad.heading * DEG;
    const paint = this.standard(0xd8d2c0, 0.5, 0.2);
    const cab = new THREE.Mesh(new THREE.BoxGeometry(2.3, 2, 1.8), this.standard(0xc23a24, 0.45, 0.2));
    cab.position.set(0, 1.4, -3.2);
    const tank = new THREE.Mesh(new THREE.CapsuleGeometry(1, 3.8, 6, 20), paint);
    tank.rotation.x = Math.PI / 2;
    tank.position.set(0, 1.7, 0.6);
    const chassis = new THREE.Mesh(new THREE.BoxGeometry(2.1, 0.5, 7.4), this.standard(0x1c1d1f, 0.8));
    chassis.position.set(0, 0.6, -0.6);
    const screen = new THREE.Mesh(new THREE.BoxGeometry(2.1, 0.8, 0.06), this.standard(0x10181e, 0.2));
    screen.position.set(0, 1.75, -4.12);
    tanker.add(cab, tank, chassis, screen);
    const tyre = this.standard(0x121315, 0.9);
    for (const z of [-3.2, 1.2, 2.6]) {
      for (const x of [-1.05, 1.05]) {
        const wheel = new THREE.Mesh(new THREE.CylinderGeometry(0.52, 0.52, 0.4, 16), tyre);
        wheel.rotation.z = Math.PI / 2;
        wheel.position.set(x, 0.32, z);
        tanker.add(wheel);
      }
    }
    this.near.add(tanker);
    this.crew(pad, pad.heading + 150, 18, 0xe8742c, 2);
  }

  private clearing(pad: Pad): void {
    const { ground } = this;
    const radius = 34;
    const rings = 14;
    const segments = 48;
    const positions: number[] = [];
    const uvs: number[] = [];
    const indices: number[] = [];
    for (let r = 0; r <= rings; r += 1) {
      for (let s = 0; s <= segments; s += 1) {
        const a = (s / segments) * Math.PI * 2;
        const reach = (r / rings) * radius * (1 + 0.14 * Math.sin(a * 5 + 1) * (r / rings));
        const east = pad.east + Math.sin(a) * reach;
        const north = pad.north + Math.cos(a) * reach;
        positions.push(east, ground(north, east) + 0.5, -north);
        uvs.push(r / rings, s / segments);
      }
    }
    const side = segments + 1;
    for (let r = 0; r < rings; r += 1) {
      for (let s = 0; s < segments; s += 1) {
        const a = r * side + s;
        indices.push(a, a + 1, a + side, a + 1, a + side + 1, a + side);
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 256;
    const c = canvas.getContext("2d") as CanvasRenderingContext2D;
    const fade = c.createLinearGradient(0, 0, 256, 0);
    fade.addColorStop(0, "rgba(120,98,70,1)");
    fade.addColorStop(0.55, "rgba(112,98,68,1)");
    fade.addColorStop(1, "rgba(80,88,52,0)");
    c.fillStyle = fade;
    c.fillRect(0, 0, 256, 256);
    for (let i = 0; i < 1600; i += 1) {
      c.fillStyle = `rgba(${i % 3 ? "40,30,18" : "150,140,100"},${0.05 + Math.random() * 0.1})`;
      c.fillRect(Math.random() * 256, Math.random() * 256, 2 + Math.random() * 10, 2 + Math.random() * 6);
    }
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    const dirt = new THREE.Mesh(geometry, this.aerial(new THREE.MeshStandardMaterial({ map: texture, transparent: true, roughness: 1, side: THREE.DoubleSide })));
    dirt.renderOrder = 1;
    this.world.add(dirt);
    // Logs stacked by the crew that cut it, and their truck.
    const bark = this.standard(0x4a3424, 0.95);
    for (let i = 0; i < 7; i += 1) {
      const log = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.3, 7 + (i % 3), 10), bark);
      const a = 2.3;
      const row = i < 4 ? i : i - 3.5;
      const layer = i < 4 ? 0 : 0.5;
      const east = pad.east + Math.sin(a) * 22 + Math.cos(a) * row * 0.62;
      const north = pad.north + Math.cos(a) * 22 - Math.sin(a) * row * 0.62;
      log.rotation.set(0, -a, Math.PI / 2, "YXZ");
      log.position.set(east, ground(north, east) + 0.8 + layer, -north);
      this.world.add(log);
    }
    this.crew(pad, 40, 19, 0xd8301c);
    const truck = new THREE.Mesh(new THREE.BoxGeometry(2.5, 2.4, 6.4), this.standard(0xb5261a, 0.45, 0.2));
    const east = pad.east - 20;
    const north = pad.north + 13;
    truck.position.set(east, ground(north, east) + 1.7, -north);
    truck.rotation.y = 0.5;
    this.near.add(truck);
  }

  private roof(pad: Pad): void {
    const wide = TOWER.wide;
    const facade = facadeTexture();
    facade.repeat.set(8, TOWER.tall / 4.2);
    const height = pad.top - pad.base;
    const wall = new THREE.Mesh(new THREE.BoxGeometry(wide * 2, height + 4, wide * 2), this.aerial(new THREE.MeshStandardMaterial({ map: facade, roughness: 0.55, metalness: 0.1 })));
    wall.position.set(pad.east, pad.base + height / 2 - 2.6, -pad.north);
    this.world.add(wall);
    const concrete = this.standard(0x8c8d88, 0.9);
    const slab = new THREE.Mesh(new THREE.BoxGeometry(wide * 2 + 0.6, 0.5, wide * 2 + 0.6), concrete);
    slab.position.set(pad.east, pad.top - 0.75, -pad.north);
    this.near.add(slab);
    for (const [x, z, w, d] of [[wide, 0, 0.5, wide * 2 + 0.6], [-wide, 0, 0.5, wide * 2 + 0.6], [0, wide, wide * 2 + 0.6, 0.5], [0, -wide, wide * 2 + 0.6, 0.5]] as const) {
      const parapet = new THREE.Mesh(new THREE.BoxGeometry(w, 1, d), concrete);
      parapet.position.set(pad.east + x, pad.top - 0.5, -pad.north + z);
      this.near.add(parapet);
    }
    const plant = this.standard(0x9fa2a3, 0.6, 0.3);
    for (const [x, z] of [[-15, -15], [15.5, -15], [15, 15.5]] as const) {
      const box = new THREE.Mesh(new THREE.BoxGeometry(5, 2.6, 4), plant);
      box.position.set(pad.east + x, pad.top + 0.6, -pad.north + z);
      this.near.add(box);
    }
    // The podium, wider than the tower, so it stands in the town rather than on it.
    const podium = new THREE.Mesh(new THREE.BoxGeometry(wide * 3, 18, wide * 3), this.standard(0xb6b8b2, 0.7));
    podium.position.set(pad.east, pad.base + 8, -pad.north);
    this.world.add(podium);
    this.crew(pad, 60, 15.6, 0xf2f2f0, 2);
  }

  private ledge(pad: Pad): void {
    const tall = pad.top - pad.base + 70;
    const rock = new THREE.CylinderGeometry(15.6, 48, tall, 36, 16, true);
    const place = rock.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < place.count; i += 1) {
      const y = place.getY(i);
      // The top ring stays round, for the deck; below it the stone breaks out in lumps and shelves.
      if (y < tall / 2 - 0.1) {
        const x = place.getX(i);
        const z = place.getZ(i);
        const a = Math.round(Math.atan2(z, x) * 11);
        const row = Math.round(y / 6);
        const k = 1 + 0.34 * (hash2(a, row, 3) - 0.5) + 0.3 * (hash2(Math.round(a / 3), Math.round(row / 3), 5) - 0.5);
        place.setXYZ(i, x * k, y, z * k);
      }
    }
    const stone = this.aerial(new THREE.MeshStandardMaterial({ color: 0x93806a, roughness: 1, flatShading: true }));
    const mesh = new THREE.Mesh(rock.toNonIndexed(), stone);
    mesh.geometry.computeVertexNormals();
    mesh.position.set(pad.east, pad.top - 0.5 - tall / 2, -pad.north);
    this.world.add(mesh);
    const steel = this.standard(0xc9cac6, 0.5, 0.5);
    const rail = new THREE.Mesh(new THREE.TorusGeometry(15.2, 0.035, 6, 72), steel);
    rail.rotation.x = Math.PI / 2;
    rail.position.set(pad.east, pad.top + 1.05, -pad.north);
    this.near.add(rail);
    for (let i = 0; i < 28; i += 1) {
      const a = (i * Math.PI) / 14;
      const post = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 1.05, 6), steel);
      post.position.set(pad.east + Math.cos(a) * 15.2, pad.top + 0.52, -pad.north + Math.sin(a) * 15.2);
      this.near.add(post);
    }
    this.crew(pad, 20, 14, 0xf0a020, 1);
  }

  private ship(pad: Pad): void {
    const { length, beam, deck, heading } = SHIP;
    const group = new THREE.Group();
    group.position.set(SHIP.east, 0, -SHIP.north);
    group.rotation.y = -heading * DEG;
    const half = length / 2;
    const b = beam / 2;
    const hull = (inset: number): THREE.Shape => {
      const shape = new THREE.Shape();
      shape.moveTo(-b + inset, -half + inset);
      shape.lineTo(-b + inset, half * 0.3);
      shape.quadraticCurveTo(-b + inset, half * 0.75, 0, half - inset);
      shape.quadraticCurveTo(b - inset, half * 0.75, b - inset, half * 0.3);
      shape.lineTo(b - inset, -half + inset);
      shape.closePath();
      return shape;
    };
    const slab = (inset: number, from: number, to: number, color: number): THREE.Mesh => {
      const geometry = new THREE.ExtrudeGeometry(hull(inset), { depth: to - from, bevelEnabled: false, curveSegments: 18 });
      geometry.rotateX(-Math.PI / 2);
      geometry.translate(0, from, 0);
      return new THREE.Mesh(geometry, this.standard(color, 0.55, 0.15));
    };
    group.add(slab(0.1, -3, 1.1, 0x7a2218), slab(0, 1.1, deck - 0.2, 0x10283e), slab(0, deck - 0.2, deck, 0xe8e8e2), slab(0.7, deck, deck + 0.06, 0x4f6b5f));
    const box = (w: number, h: number, l: number, along: number, up: number, color: number, across = 0): THREE.Mesh => {
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, l), this.standard(color, 0.6, 0.1));
      mesh.position.set(across, up + h / 2, -along);
      group.add(mesh);
      return mesh;
    };
    const white = 0xe4e4dc;
    box(16, 4.2, 26, 2, deck, white);
    box(15, 4.3, 22, 2, deck + 4.2, white);
    box(17.6, 3, 9, 6, deck + 8.5, white);
    box(17.8, 1.4, 9.1, 6, deck + 9.2, 0x162028);
    const ports = windowBand();
    ports.repeat.set(9, 1);
    for (const [w, l, up] of [[16.2, 26.2, 2], [15.2, 22.2, 6.2]] as const) {
      const band = box(w, 1, l, 2, deck + up, 0xffffff);
      band.material = this.aerial(new THREE.MeshStandardMaterial({ map: ports, roughness: 0.3 }));
    }
    const funnel = new THREE.Mesh(new THREE.CylinderGeometry(1.6, 1.9, 6, 16), this.standard(0xd14a24, 0.5, 0.2));
    funnel.position.set(0, deck + 11, 8);
    group.add(funnel);
    const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.3, 11, 8), this.standard(0xd8d8d2, 0.5, 0.4));
    mast.position.set(0, deck + 16, -6);
    group.add(mast);
    box(3.4, 0.2, 0.5, 6, deck + 19, 0x202428);
    // Survey gear on the foredeck: containers and an A-frame.
    box(5, 2.6, 12, 25, deck, 0xc8551e);
    box(5, 2.6, 6, 33, deck, 0x2a7f7a, 1);
    // An A-frame over the foredeck, for lowering the survey gear.
    const yellow = this.standard(0xe0b528, 0.5, 0.3);
    for (const side of [1, -1]) {
      const post = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.3, 9, 8), yellow);
      post.position.set(side * 3.6, deck + 4.2, -19.5);
      post.rotation.set(-0.3, 0, side * 0.12);
      group.add(post);
    }
    const beamTop = new THREE.Mesh(new THREE.BoxGeometry(6.6, 0.5, 0.5), yellow);
    beamTop.position.set(0, deck + 8.5, -20.8);
    group.add(beamTop);
    for (const side of [1, -1]) {
      const boat = new THREE.Mesh(new THREE.CapsuleGeometry(1, 4.5, 4, 14), this.standard(0xee6a1e, 0.5));
      boat.rotation.x = Math.PI / 2;
      boat.position.set(side * 8.6, deck + 5.2, 4);
      group.add(boat);
    }
    // The helideck's legs, down to the main deck.
    const steel = this.standard(0x70777a, 0.55, 0.5);
    for (let i = 0; i < 6; i += 1) {
      const a = (i * Math.PI) / 3 + 0.5;
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 2.7, 8), steel);
      leg.position.set(Math.cos(a) * 7, deck + 1.3, -SHIP.stern + Math.sin(a) * 7);
      group.add(leg);
    }
    const stair = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.1, 8), steel);
    stair.position.set(3, deck + 1.3, -SHIP.stern - 13);
    stair.rotation.x = 0.33;
    group.add(stair);
    this.world.add(group);
    // Where the hull cuts the water, thinning away from it.
    const foamTexture = (() => {
      const canvas = document.createElement("canvas");
      canvas.width = 128;
      canvas.height = 256;
      const c = canvas.getContext("2d") as CanvasRenderingContext2D;
      for (let i = 0; i < 2600; i += 1) {
        c.fillStyle = `rgba(235,242,244,${0.03 + Math.random() * 0.12})`;
        c.beginPath();
        c.arc(Math.random() * 128, Math.random() * 256, 0.5 + Math.random() * 2.5, 0, Math.PI * 2);
        c.fill();
      }
      const texture = new THREE.CanvasTexture(canvas);
      texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
      texture.repeat.set(0.09, 0.04);
      return texture;
    })();
    const foam = new THREE.Mesh(new THREE.ShapeGeometry(hull(-3), 18), new THREE.MeshBasicMaterial({ map: foamTexture, transparent: true, opacity: 0.8, depthWrite: false }));
    foam.rotation.set(-Math.PI / 2, 0, 0);
    foam.position.y = 0.2;
    const holder = new THREE.Group();
    holder.position.copy(group.position);
    holder.rotation.y = group.rotation.y;
    holder.add(foam);
    this.near.add(holder);
    this.crew(pad, SHIP.heading + 55, 12.7, 0xf0d020, 2);
  }

  /** Trees near the pads get boughs: from the deck, the forest's plain cones would show. */
  plant(trees: readonly Tree[]): void {
    const tiers: THREE.BufferGeometry[] = [];
    for (let i = 0; i < 5; i += 1) {
      const k = i / 4;
      const tier = new THREE.ConeGeometry(0.5 * (1 - 0.68 * k), 0.42 - 0.08 * k, 9, 1, true);
      tier.rotateY(i * 0.7);
      tier.translate(0, 0.21 + k * 0.58 - 0.5, 0);
      tiers.push(tier.index ? tier.toNonIndexed() : tier);
    }
    const stem = new THREE.CylinderGeometry(0.018, 0.03, 0.2, 5, 1, true);
    stem.translate(0, -0.45, 0);
    tiers.push(stem.toNonIndexed());
    const mesh = new THREE.InstancedMesh(mergeGeometries(tiers), this.aerial(new THREE.MeshStandardMaterial({ roughness: 1, side: THREE.DoubleSide })), trees.length);
    for (const [i, tree] of trees.entries()) {
      mesh.setMatrixAt(i, tree.matrix);
      mesh.setColorAt(i, tree.color);
    }
    mesh.frustumCulled = false;
    this.world.add(mesh);
  }

  /** The next pad gets the light; null for none. */
  setTarget(pad: Pad | null): void {
    this.target = pad;
    this.beam.visible = pad !== null;
    this.ring.visible = pad !== null;
    if (pad) {
      this.beam.position.set(pad.east, pad.top + 450, -pad.north);
      this.ring.position.set(pad.east, pad.top + 0.14, -pad.north);
      this.ring.scale.setScalar(pad.radius);
    }
  }

  update(time: number, eye: THREE.Vector3, windNorth: number, windEast: number): void {
    this.time.value = time;
    if (this.target) {
      const distance = this.at.set(this.target.east, this.target.top, -this.target.north).distanceTo(eye);
      this.strength.value = THREE.MathUtils.smoothstep(distance, 60, 500);
      (this.ring.material as THREE.MeshBasicMaterial).opacity = 0.55 + 0.35 * Math.sin(time * 4);
    }
    const speed = Math.hypot(windNorth, windEast);
    for (const { turn, sag } of this.socks) {
      // The sock streams with the air: at 3 m/s it hangs, at 13 it stands out.
      const flutter = Math.sin(time * 2.3 + turn.id) * 0.12 + Math.sin(time * 5.1) * 0.04;
      turn.rotation.y = (speed > 0.2 ? Math.atan2(windNorth, windEast) : 0.6) + flutter * 0.5;
      sag.rotation.z = -(1.35 - 1.3 * THREE.MathUtils.smoothstep(speed, 1, 12)) + flutter * 0.4;
    }
  }
}

/**
 * Makes room in the instanced town and forest for the pads, and tells the surface what is left. The
 * instances are read back rather than rebuilt: that way what the rotor hits is what is drawn.
 */
export function clearGround(group: THREE.Group, surface: Surface, pads: readonly Pad[]): Tree[] {
  const close: Tree[] = [];
  const matrix = new THREE.Matrix4();
  const nothing = new THREE.Matrix4().makeScale(0, 0, 0);
  const position = new THREE.Vector3();
  const rotation = new THREE.Quaternion();
  const size = new THREE.Vector3();
  const spot = (north: number, east: number, reach: number): boolean => pads.some((pad) => Math.hypot(north - pad.north, east - pad.east) < reach + (pad.id === "clearing" ? 22 : pad.id === "roof" ? 26 : 16));
  for (const child of group.children) {
    if (!(child instanceof THREE.InstancedMesh)) {
      continue;
    }
    const trees = child.geometry.type === "ConeGeometry";
    for (let i = 0; i < child.count; i += 1) {
      child.getMatrixAt(i, matrix);
      matrix.decompose(position, rotation, size);
      const north = -position.z;
      const east = position.x;
      if (spot(north, east, trees ? 4 : Math.max(size.x, size.z) / 2 + 2)) {
        child.setMatrixAt(i, nothing);
      } else if (trees) {
        surface.addTree(north, east, position.y, size.y);
        if (pads.some((pad) => Math.hypot(north - pad.north, east - pad.east) < 220)) {
          const color = new THREE.Color();
          child.getColorAt(i, color);
          close.push({ matrix: matrix.clone(), color });
          child.setMatrixAt(i, nothing);
        }
      } else {
        const quarter = Math.abs(rotation.y) > 0.3;
        surface.addBlock({ north, east, long: (quarter ? size.x : size.z) / 2, wide: (quarter ? size.z : size.x) / 2, heading: 0, top: position.y + size.y });
      }
    }
    child.instanceMatrix.needsUpdate = true;
    if (!trees) {
      windows(child.material as THREE.Material);
    }
  }
  thicken(close, surface, pads.find((pad) => pad.id === "clearing") as Pad);
  return close;
}

/** A clearing wants a wall of forest round it, which is why you need a helicopter to get there. */
function thicken(trees: Tree[], surface: Surface, pad: Pad): void {
  const greens = [0x1c3a22, 0x24452a, 0x18331f, 0x2c4c2c];
  const position = new THREE.Vector3();
  const rotation = new THREE.Quaternion();
  const size = new THREE.Vector3();
  for (let i = 0; i < 620; i += 1) {
    const a = hash2(i, 41, 7) * Math.PI * 2;
    const reach = 50 + 170 * Math.sqrt(hash2(i, 43, 9));
    const north = pad.north + Math.cos(a) * reach;
    const east = pad.east + Math.sin(a) * reach;
    const base = surface.at(north, east);
    const tall = 15 + 15 * hash2(i, 47, 2);
    position.set(east, base + tall * 0.47, -north);
    size.set(tall * 0.42, tall, tall * 0.42);
    surface.addTree(north, east, base, tall);
    trees.push({ matrix: new THREE.Matrix4().compose(position, rotation, size), color: new THREE.Color(greens[i % 4]).multiplyScalar(0.8 + 0.6 * hash2(i, 53, 3)) });
  }
}

/** Floors and windows on the town's walls, in world metres, so every box gets them for nothing. */
function windows(material: THREE.Material): void {
  const earlier = material.onBeforeCompile.bind(material);
  material.onBeforeCompile = (shader, renderer) => {
    earlier(shader, renderer);
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vWall;\nvarying float vSide;")
      .replace(
        "#include <begin_vertex>",
        /* glsl */ `#include <begin_vertex>
        vWall = (modelMatrix * instanceMatrix * vec4(position, 1.0)).xyz;
        vSide = abs(normal.x) > 0.5 ? 1.0 : abs(normal.z) > 0.5 ? 2.0 : 0.0;`,
      );
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vWall;\nvarying float vSide;")
      .replace(
        "#include <color_fragment>",
        /* glsl */ `#include <color_fragment>
        if (vSide > 0.5) {
          float along = (vSide < 1.5 ? vWall.z : vWall.x) / 3.1;
          float storey = vWall.y / 3.3;
          vec2 cell = abs(fract(vec2(along, storey)) - 0.5);
          float blur = max(fwidth(along), fwidth(storey));
          float pane = (1.0 - smoothstep(0.3 - blur, 0.3 + blur, cell.x)) * (1.0 - smoothstep(0.27 - blur, 0.27 + blur, cell.y));
          // Further off the windows melt into an even, darker wall rather than shimmer.
          pane = mix(pane, 0.33, smoothstep(0.2, 0.55, blur));
          diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.05, 0.08, 0.1), pane * 0.85);
        }`,
      );
  };
  material.customProgramCacheKey = () => "town-windows";
}

/** The helicopter's shadow from above: the disc faint, the body solid. */
export function shadowTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 256;
  const c = canvas.getContext("2d") as CanvasRenderingContext2D;
  c.filter = "blur(3px)";
  c.fillStyle = "rgba(0,0,0,0.3)";
  c.beginPath();
  c.arc(128, 90, 78, 0, Math.PI * 2);
  c.fill();
  c.fillStyle = "#000";
  c.beginPath();
  c.ellipse(128, 86, 15, 40, 0, 0, Math.PI * 2);
  c.fill();
  c.fillRect(125, 110, 6, 124);
  c.fillRect(106, 196, 44, 6);
  return new THREE.CanvasTexture(canvas);
}
