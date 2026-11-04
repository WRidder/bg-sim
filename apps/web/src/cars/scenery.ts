/**
 * What stands along a route: barriers, tyre walls, grandstands, the pits, the start gantry, boards
 * that say how far to the corner, trees; on a stage, stakes, rocks, bushes and the odd tent. All of
 * it is placed once, from the same arrays the tyres read, and joins the world scene so the air and
 * the clouds fall over it. No proper names but the game's own.
 */

import * as THREE from "three";
import { type AtmosphereUniforms, withAerial } from "../engine/atmosphere";
import { hash2 } from "../engine/noise";
import { roadHeight } from "./land";
import type { Line } from "./line";
import { box, merge, tube } from "./parts";
import { bends, structures, trees, type Structure } from "./placement";
import type { Side, Track } from "./track";
import type { Spot } from "./views";

type Aerial = <M extends THREE.Material>(material: M) => M;

export interface Scenery {
  group: THREE.Group;
  /** The trackside cameras. */
  spots: Spot[];
  /** Lamps of the start gantry, 0..5 lit, -1 all out. */
  setLights(count: number): void;
  dispose(): void;
}

const dummy = new THREE.Object3D();
const color = new THREE.Color();

function advert(words: string, paper: string, ink: string): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 64;
  const c = canvas.getContext("2d") as CanvasRenderingContext2D;
  c.fillStyle = paper;
  c.fillRect(0, 0, 512, 64);
  c.fillStyle = ink;
  c.font = 'italic 700 46px "Bahnschrift", "Arial Narrow", sans-serif';
  c.textAlign = "center";
  c.textBaseline = "middle";
  c.fillText(words, 256, 34);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}

function crowdTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 256;
  const c = canvas.getContext("2d") as CanvasRenderingContext2D;
  c.fillStyle = "#3a4048";
  c.fillRect(0, 0, 1024, 256);
  const tones = ["#d8d2c4", "#c23b22", "#2a4a7a", "#e0b23a", "#f2efe6", "#1f2428", "#3b7a5a", "#d97a3a", "#7a8896"];
  for (let i = 0; i < 9000; i += 1) {
    const x = (i % 170) * 6 + 2 + hash2(i, 1, 2) * 3;
    const y = Math.floor(i / 170) * 6 + 2 + hash2(i, 2, 2) * 3;
    if (hash2(i, 3, 2) > 0.14) {
      c.fillStyle = tones[Math.floor(hash2(i, 4, 2) * tones.length)];
      c.fillRect(x, y + 1, 4, 4);
      c.fillStyle = hash2(i, 5, 2) > 0.3 ? "#caa184" : "#6f4c3a";
      c.fillRect(x + 1, y - 1, 2, 2);
    }
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 8;
  return texture;
}

function fenceTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  const c = canvas.getContext("2d") as CanvasRenderingContext2D;
  c.fillStyle = "#000";
  c.fillRect(0, 0, 64, 64);
  c.strokeStyle = "#fff";
  c.lineWidth = 3;
  c.beginPath();
  c.moveTo(0, 0);
  c.lineTo(64, 64);
  c.moveTo(64, 0);
  c.lineTo(0, 64);
  c.stroke();
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 8;
  return texture;
}

/** A band hung along a side of the road between two heights, with u running along it in metres. */
function strip(track: Track, side: Side, sign: 1 | -1, offset: number, low: number, high: number, every = 4, keep?: (i: number) => boolean): THREE.BufferGeometry {
  const kind = track.definition.car;
  const positions: number[] = [];
  const uvs: number[] = [];
  const normals: number[] = [];
  const indices: number[] = [];
  let previous = false;
  for (let k = 0; k <= track.n; k += every) {
    const i = k % track.n;
    const on = keep ? keep(i) : true;
    if (on) {
      const d = sign * (side.wall[i] + offset);
      const x = track.x[i] - track.ty[i] * d;
      const y = track.y[i] + track.tx[i] * d;
      const h = roadHeight(kind, x, y);
      const base = positions.length / 3;
      positions.push(x, h + low, -y, x, h + high, -y);
      const u = k;
      uvs.push(u / 2, 0, u / 2, (high - low) / 2);
      const nx = track.ty[i] * sign;
      const ny = -track.tx[i] * sign;
      normals.push(nx, 0, -ny, nx, 0, -ny);
      if (previous) {
        indices.push(base - 2, base, base - 1, base - 1, base, base + 1);
      }
    }
    previous = on;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  return geometry;
}

function instances(geometry: THREE.BufferGeometry, material: THREE.Material, count: number): THREE.InstancedMesh {
  const mesh = new THREE.InstancedMesh(geometry, material, count);
  mesh.count = 0;
  mesh.frustumCulled = false;
  return mesh;
}

function put(mesh: THREE.InstancedMesh, tone?: THREE.Color): void {
  dummy.updateMatrix();
  mesh.setMatrixAt(mesh.count, dummy.matrix);
  if (tone) {
    mesh.setColorAt(mesh.count, tone);
  }
  mesh.count += 1;
}

/** A local frame on the road: x along it, y up, z towards the outside of `side`. */
function frameAt(track: Track, s: number, d: number): { x: number; y: number; z: number; angle: number } {
  const p = track.pose(s, d);
  return { x: p.x, y: roadHeight(track.definition.car, p.x, p.y), z: -p.y, angle: p.yaw };
}

function grandstand(block: Structure, track: Track, aerial: Aerial, crowd: THREE.Texture): THREE.Group {
  const stand = new THREE.Group();
  const f = frameAt(track, block.s, block.side * (block.d + block.depth / 2));
  stand.position.set(f.x, f.y, f.z);
  stand.rotation.y = f.angle + (block.side > 0 ? 0 : Math.PI);
  const rows = Math.round(block.depth / 1.1);
  const rise = (block.height * 0.8) / rows;
  const seats: THREE.BufferGeometry[] = [];
  const steps = new THREE.MeshStandardMaterial({ map: crowd, roughness: 0.9 });
  const concrete = aerial(new THREE.MeshStandardMaterial({ color: 0x8c8c86, roughness: 0.9 }));
  for (let r = 0; r < rows; r += 1) {
    const z = block.depth / 2 - 1 - r * 1.1;
    const y = 1.6 + r * rise;
    seats.push(box(-block.length / 2, y, z - 0.55, block.length / 2, y + rise, z + 0.55));
  }
  const body = new THREE.BufferGeometry().copy(merge(seats));
  const uv: number[] = [];
  const at = body.attributes.position as THREE.BufferAttribute;
  for (let i = 0; i < at.count; i += 1) {
    uv.push(at.getX(i) / 42, (at.getY(i) + at.getZ(i)) / 10.5);
  }
  body.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
  stand.add(new THREE.Mesh(body, aerial(steps)));
  stand.add(new THREE.Mesh(box(-block.length / 2, 0, -block.depth / 2, block.length / 2, 1.7, block.depth / 2), concrete));
  stand.add(new THREE.Mesh(box(-block.length / 2, 0, -block.depth / 2 - 0.3, block.length / 2, block.height, -block.depth / 2), concrete));
  // A roof on thin columns, so the shade falls on the back rows only.
  const roof = aerial(new THREE.MeshStandardMaterial({ color: 0xd9d6cc, roughness: 0.55, metalness: 0.2 }));
  const canopy = new THREE.Mesh(box(-block.length / 2 - 1, 0, -block.depth / 2 - 1, block.length / 2 + 1, 0.3, block.depth / 2 - 4), roof);
  canopy.position.y = block.height + 1.6;
  canopy.rotation.x = -0.07;
  stand.add(canopy);
  const columns: THREE.BufferGeometry[] = [];
  for (let x = -block.length / 2; x <= block.length / 2; x += 14) {
    columns.push(tube(x, 0, -block.depth / 2 + 0.2, x, block.height + 1.7, -block.depth / 2 + 0.2, 0.22, 6));
    columns.push(tube(x, block.height * 0.6, 2, x, block.height + 1.5, -block.depth / 2 + 0.2, 0.12, 6));
  }
  stand.add(new THREE.Mesh(merge(columns), concrete));
  // Flags on the roof line.
  const hues = [0xc23b22, 0xe9e4d8, 0x2a4a7a];
  for (let x = -block.length / 2 + 6; x < block.length / 2; x += 18) {
    const pole = new THREE.Mesh(tube(x, block.height, -block.depth / 2, x, block.height + 6, -block.depth / 2, 0.05, 5), concrete);
    const flag = new THREE.Mesh(box(x + 0.05, block.height + 4.8, -block.depth / 2 - 0.02, x + 2.2, block.height + 6, -block.depth / 2 + 0.02), aerial(new THREE.MeshStandardMaterial({ color: hues[Math.round(x) % 3 < 0 ? 0 : Math.abs(Math.round(x)) % 3], roughness: 0.8 })));
    stand.add(pole, flag);
  }
  return stand;
}

function pits(block: Structure, track: Track, aerial: Aerial): THREE.Group {
  const group = new THREE.Group();
  const f = frameAt(track, block.s, block.side * (block.d + block.depth / 2));
  group.position.set(f.x, f.y, f.z);
  group.rotation.y = f.angle + (block.side > 0 ? 0 : Math.PI);
  const wall = aerial(new THREE.MeshStandardMaterial({ color: 0xdedbd2, roughness: 0.75 }));
  const glass = aerial(new THREE.MeshStandardMaterial({ color: 0x1b2a33, roughness: 0.08, metalness: 0.7 }));
  const dark = aerial(new THREE.MeshStandardMaterial({ color: 0x15181b, roughness: 0.7 }));
  const metal = aerial(new THREE.MeshStandardMaterial({ color: 0x6f7c84, roughness: 0.5, metalness: 0.5 }));
  const { length: L, depth: D, height: H } = block;
  const front = D / 2;
  group.add(new THREE.Mesh(box(-L / 2, 0, -D / 2, L / 2, H * 0.5, D / 2 - 0.4), wall));
  group.add(new THREE.Mesh(box(-L / 2 - 1, H * 0.5, -D / 2 - 1, L / 2 + 1, H * 0.54, front + 1.5), metal));
  group.add(new THREE.Mesh(box(-L / 2, H * 0.54, -D / 2, L / 2, H, D / 2 - 3), glass));
  group.add(new THREE.Mesh(box(-L / 2 - 1.5, H, -D / 2 - 1, L / 2 + 1.5, H + 0.5, front - 1), wall));
  // Garage doors, one bay after another.
  const doors: THREE.BufferGeometry[] = [];
  const lights: THREE.BufferGeometry[] = [];
  for (let x = -L / 2 + 6; x < L / 2 - 4; x += 12.5) {
    doors.push(box(x - 5, 0, front - 0.45, x + 5, H * 0.44, front - 0.38));
    lights.push(box(x - 4.4, H * 0.41, front - 0.37, x + 4.4, H * 0.425, front - 0.36));
  }
  group.add(new THREE.Mesh(merge(doors), dark));
  group.add(new THREE.Mesh(merge(lights), new THREE.MeshBasicMaterial({ color: new THREE.Color(2.2, 2.1, 1.9) })));
  // The race control tower at the middle of the block.
  group.add(new THREE.Mesh(box(-7, 0, -D / 2 + 3, 7, H + 9, D / 2 - 6), wall));
  group.add(new THREE.Mesh(box(-8.5, H + 4.4, -D / 2 + 2, 8.5, H + 8.4, D / 2 - 4), glass));
  group.add(new THREE.Mesh(box(-9, H + 8.4, -D / 2 + 1.5, 9, H + 8.9, D / 2 - 3.5), metal));
  return group;
}

/** The gantry over the line: a truss on two legs, with five lamps per side facing the grid. */
function gantry(track: Track, aerial: Aerial, stage: boolean): { group: THREE.Group; lamps: THREE.MeshBasicMaterial[]; go: THREE.MeshBasicMaterial } {
  const group = new THREE.Group();
  const f = frameAt(track, 3, 0);
  group.position.set(f.x, f.y, f.z);
  group.rotation.y = f.angle;
  const steel = aerial(new THREE.MeshStandardMaterial({ color: stage ? 0x7a6a55 : 0x1f2428, roughness: 0.55, metalness: 0.5 }));
  const half = track.width + 3.4;
  const top = stage ? 6.2 : 7.4;
  const bars: THREE.BufferGeometry[] = [];
  for (const side of [-1, 1]) {
    bars.push(box(-0.25, 0, side * half - 0.25, 0.25, top + 0.9, side * half + 0.25));
  }
  bars.push(box(-0.08, top + 0.8, -half, 0.08, top + 0.95, half));
  bars.push(box(-0.08, top - 0.05, -half, 0.08, top + 0.1, half));
  for (let z = -half; z < half; z += 1.4) {
    bars.push(tube(0, top, z, 0, top + 0.86, z + 0.7, 0.04, 5));
    bars.push(tube(0, top + 0.86, z + 0.7, 0, top, z + 1.4, 0.04, 5));
  }
  group.add(new THREE.Mesh(merge(bars), steel));
  const face = new THREE.Mesh(box(-0.14, top + 0.08, -3.2, 0.14, top + 0.85, 3.2), aerial(new THREE.MeshStandardMaterial({ color: 0x0a0b0c, roughness: 0.6 })));
  group.add(face);
  const lamps: THREE.MeshBasicMaterial[] = [];
  const disc = new THREE.CircleGeometry(0.21, 20);
  for (let i = 0; i < 5; i += 1) {
    const material = new THREE.MeshBasicMaterial({ color: new THREE.Color(0.06, 0.01, 0.01) });
    lamps.push(material);
    for (const z of [-1, 1]) {
      const lamp = new THREE.Mesh(disc, material);
      lamp.position.set(-0.15 * z, top + 0.46, (i - 2) * 1.2);
      lamp.rotation.y = -z * Math.PI / 2;
      group.add(lamp);
    }
  }
  const go = new THREE.MeshBasicMaterial({ color: new THREE.Color(0.02, 0.06, 0.03) });
  const greens = new THREE.Mesh(box(-0.16, top + 0.8, -3, -0.15, top + 0.84, 3), go);
  group.add(greens);
  return { group, lamps, go };
}

function pine(): THREE.BufferGeometry {
  const parts: THREE.BufferGeometry[] = [];
  const lobes = [[0, 0.82, 0, 0.5], [0.3, 0.76, 0.1, 0.32], [-0.26, 0.78, -0.16, 0.34], [0.05, 0.74, 0.32, 0.3], [-0.1, 0.92, -0.08, 0.32]];
  for (const [x, y, z, r] of lobes) {
    const crown = new THREE.IcosahedronGeometry(r, 1);
    crown.scale(1, 0.46, 1);
    crown.translate(x, y, z);
    parts.push(crown);
  }
  const merged = merge(parts);
  // Rough the outline up so the crowns do not read as spheres.
  const at = merged.attributes.position as THREE.BufferAttribute;
  for (let i = 0; i < at.count; i += 1) {
    const [x, y, z] = [at.getX(i), at.getY(i), at.getZ(i)];
    if (y > 0.6) {
      const n = hash2(Math.round(x * 13), Math.round(z * 13), 3) - 0.5;
      at.setXYZ(i, x * (1 + n * 0.3), y + n * 0.05, z * (1 + n * 0.3));
    }
  }
  merged.computeVertexNormals();
  return merged;
}

function cypress(): THREE.BufferGeometry {
  const cone = new THREE.ConeGeometry(0.17, 1, 8, 4);
  cone.translate(0, 0.5, 0);
  return cone;
}

function bush(): THREE.BufferGeometry {
  const parts: THREE.BufferGeometry[] = [];
  for (let i = 0; i < 5; i += 1) {
    const blob = new THREE.IcosahedronGeometry(0.42 + 0.2 * hash2(i, 1, 1), 1);
    blob.scale(1, 0.72, 1);
    blob.translate(Math.cos(i * 2.4) * 0.34, 0.3 + 0.12 * hash2(i, 2, 1), Math.sin(i * 2.4) * 0.34);
    parts.push(blob);
  }
  return merge(parts);
}

function rock(): THREE.BufferGeometry {
  const stone = new THREE.IcosahedronGeometry(1, 1);
  const at = stone.attributes.position as THREE.BufferAttribute;
  for (let i = 0; i < at.count; i += 1) {
    const n = 0.72 + 0.5 * hash2(Math.round(at.getX(i) * 9), Math.round((at.getY(i) + at.getZ(i)) * 9), 7);
    at.setXYZ(i, at.getX(i) * n, at.getY(i) * n * 0.72, at.getZ(i) * n);
  }
  stone.computeVertexNormals();
  return stone;
}

function tufts(track: Track, parent: THREE.Group, aerial: Aerial, racing: boolean): void {
  // Rocks and bushes are on the map; what follows is stuff at the roadside.
  const stoneTone = racing ? [0x8d8b84, 0x6f6c66] : [0x8b5a3a, 0x6a4a36, 0xa8744a];
  const stones = instances(rock(), aerial(new THREE.MeshStandardMaterial({ roughness: 0.95 })), racing ? 240 : 1500);
  const { seed } = track.definition;
  for (let i = 0; i < stones.instanceMatrix.count; i += 1) {
    let x: number;
    let y: number;
    if (racing) {
      // A rocky shore south of the circuit.
      x = -1400 + 2800 * hash2(i, 1, seed);
      y = -320 + 90 * (hash2(i, 2, seed) - 0.5) - 70 * hash2(i, 3, seed);
    } else {
      const s = hash2(i, 1, seed) * track.length;
      const side = hash2(i, 2, seed) > 0.5 ? 1 : -1;
      const row = side > 0 ? track.left.wall : track.right.wall;
      const k = Math.floor((s / track.length) * track.n);
      const spread = 1 + (hash2(i, 3, seed) ** 2) * 70;
      const place = track.pose(s, side * (row[k] + spread));
      x = place.x;
      y = place.y;
    }
    const size = (racing ? 0.8 : 0.35) + hash2(i, 4, seed) ** 3 * (racing ? 2.6 : 3);
    dummy.position.set(x, roadHeight(track.definition.car, x, y) - size * 0.25, -y);
    dummy.scale.setScalar(size);
    dummy.rotation.set(hash2(i, 5, seed) * 6, hash2(i, 6, seed) * 6, 0);
    put(stones, color.set(stoneTone[i % stoneTone.length]).multiplyScalar(0.7 + 0.6 * hash2(i, 7, seed)));
  }
  parent.add(stones);
}

function raceDressing(track: Track, line: Line, group: THREE.Group, aerial: Aerial, spots: Spot[]): void {
  const rail = aerial(new THREE.MeshStandardMaterial({ color: 0xa8a8a4, roughness: 0.42, metalness: 0.45, side: THREE.DoubleSide }));
  const post = aerial(new THREE.MeshStandardMaterial({ color: 0x74787c, roughness: 0.5, metalness: 0.7 }));
  const posts = instances(new THREE.BoxGeometry(0.12, 1.2, 0.12).translate(0, 0.6, 0), post, 3000);
  const tyre = new THREE.TorusGeometry(0.31, 0.17, 6, 10).rotateX(Math.PI / 2);
  const tyres = instances(tyre, aerial(new THREE.MeshStandardMaterial({ roughness: 0.75 })), 9000);
  const red = new THREE.Color(0xb12418);
  const white = new THREE.Color(0xd8d6cf);
  const fenceMap = fenceTexture();
  const fence = aerial(new THREE.MeshStandardMaterial({ color: 0x5a6066, alphaMap: fenceMap, transparent: true, depthWrite: false, side: THREE.DoubleSide, roughness: 0.7 }));
  for (const [side, sign] of [[track.left, 1], [track.right, -1]] as const) {
    const armco = (i: number): boolean => side.gravel[i] < 2;
    const walled = (i: number): boolean => side.gravel[i] >= 2;
    group.add(new THREE.Mesh(strip(track, side, sign, 0, 0.42, 0.74, 3, armco), rail));
    group.add(new THREE.Mesh(strip(track, side, sign, 0, 0.82, 1.1, 3, armco), rail));
    group.add(new THREE.Mesh(strip(track, side, sign, 0.3, 1.0, 4.4, 3, walled), fence));
    for (let i = 0; i < track.n; i += 4) {
      const d = sign * side.wall[i];
      const p = track.pose((i / track.n) * track.length, d);
      const h = roadHeight("racecar", p.x, p.y);
      if (armco(i)) {
        dummy.position.set(p.x, h, -p.y);
        dummy.rotation.set(0, 0, 0);
        dummy.scale.setScalar(1);
        put(posts);
      } else {
        dummy.rotation.set(0, 0, 0);
        dummy.scale.setScalar(1);
        // Stacks three high, bolted in runs of alternating colour.
        for (let along = 0; along < 3; along += 1) {
          const q = track.pose((i / track.n) * track.length + along * 1.34, d);
          for (let row = 0; row < 3; row += 1) {
            dummy.position.set(q.x, h + 0.14 + row * 0.33, -q.y);
            put(tyres, Math.floor(i / 12) % 2 === 0 ? red : white);
          }
        }
      }
    }
    // Tall posts for the debris fence, where it stands.
    for (let i = 0; i < track.n; i += 12) {
      if (walled(i)) {
        const p = track.pose((i / track.n) * track.length, sign * (side.wall[i] + 0.3));
        dummy.position.set(p.x, roadHeight("racecar", p.x, p.y), -p.y);
        dummy.scale.set(0.8, 3.7, 0.8);
        put(posts);
      }
    }
  }
  group.add(posts, tyres);

  const names: [string, string, string][] = [
    ["CAPE MERROW RACEWAY", "#10222c", "#f2efe6"], ["FLAT OUT", "#e8e4d8", "#c23b22"], ["APEX & DUST", "#c23b22", "#f2efe6"],
    ["LATE BRAKE COFFEE", "#f2efe6", "#10222c"], ["MERROW TIDE TABLES", "#2a4a7a", "#f2efe6"], ["SECTOR ONE", "#10222c", "#e0b23a"],
  ];
  const boards = names.map(([words, paper, ink]) => aerial(new THREE.MeshStandardMaterial({ map: advert(words, paper, ink), roughness: 0.7 })));
  const hoarding = new THREE.BoxGeometry(12, 1.5, 0.08);
  const frame = aerial(new THREE.MeshStandardMaterial({ color: 0x20262c, roughness: 0.7 }));
  let which = 0;
  for (let s = 60; s < track.length; s += 72) {
    const i = Math.floor((s / track.length) * track.n);
    const k = Math.abs(track.curvature[i]);
    if (k > 1 / 300) {
      continue;
    }
    for (const sign of [1, -1] as const) {
      const row = sign > 0 ? track.left : track.right;
      const f = frameAt(track, s, sign * (row.wall[i] + 0.55));
      const panel = new THREE.Mesh(hoarding, boards[which % boards.length]);
      panel.position.set(f.x, f.y + 1.75, f.z);
      panel.rotation.y = f.angle + (sign > 0 ? Math.PI : 0);
      const back = new THREE.Mesh(box(-6.1, -0.85, 0.05, 6.1, 0.85, 0.1), frame);
      panel.add(back);
      group.add(panel);
      which += 1;
    }
  }

  // Before each stop: boards counting down the metres on the outside of the road.
  const marker = aerial(new THREE.MeshStandardMaterial({ color: 0xece9e0, roughness: 0.6 }));
  const countdown = (metres: number): THREE.Material => {
    const canvas = document.createElement("canvas");
    canvas.width = 128;
    canvas.height = 128;
    const c = canvas.getContext("2d") as CanvasRenderingContext2D;
    c.fillStyle = "#f2efe6";
    c.fillRect(0, 0, 128, 128);
    c.fillStyle = "#14181c";
    c.font = '700 66px "Bahnschrift", "Arial Narrow", sans-serif';
    c.textAlign = "center";
    c.textBaseline = "middle";
    c.fillText(String(metres), 64, 68);
    const map = new THREE.CanvasTexture(canvas);
    map.colorSpace = THREE.SRGBColorSpace;
    map.anisotropy = 8;
    return aerial(new THREE.MeshStandardMaterial({ map, roughness: 0.6 }));
  };
  const faces = [150, 100, 50].map((metres) => [metres, countdown(metres)] as const);
  const metre = track.length / track.n;
  for (let i = 0; i < track.n; i += 1) {
    if (line.braking[i] <= 0.5 || line.braking[(i + track.n - 1) % track.n] > 0.5) {
      continue;
    }
    let end = i;
    while (line.braking[end % track.n] > 0.5 && end < i + track.n) {
      end += 1;
    }
    const stop = (end - i) * metre;
    if (stop < 45) {
      continue;
    }
    // Counted back from where the braking ends, on the outside of the bend to come.
    let sign: 1 | -1 = 1;
    for (let k = 0; k < 120; k += 1) {
      const c = track.curvature[(end + k) % track.n];
      if (Math.abs(c) > 1 / 200) {
        sign = c > 0 ? -1 : 1;
        break;
      }
    }
    const row = sign > 0 ? track.left : track.right;
    for (const [metres, face] of faces) {
      const k = (end - Math.round(metres / metre) + track.n) % track.n;
      const f = frameAt(track, (k / track.n) * track.length, sign * Math.min(track.width + 5.5, row.wall[k] - 1));
      const board = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 1.5), face);
      board.position.set(f.x, f.y + 2.2, f.z);
      board.rotation.y = f.angle - Math.PI / 2;
      board.add(new THREE.Mesh(box(-0.06, -2.2, -0.06, 0.06, -0.7, 0.06), marker));
      group.add(board);
    }
  }

  // A scaffold tower at the outside of each main bend, for the cameras and the marshals.
  const scaffold = aerial(new THREE.MeshStandardMaterial({ color: 0x8b8f92, roughness: 0.5, metalness: 0.6 }));
  const tent = aerial(new THREE.MeshStandardMaterial({ color: 0xe0752a, roughness: 0.7 }));
  const tower: THREE.BufferGeometry[] = [];
  for (const [x, z] of [[-1, -1], [1, -1], [1, 1], [-1, 1]] as const) {
    tower.push(tube(x, 0, z, x * 0.9, 7, z * 0.9, 0.06, 5));
  }
  for (const y of [2.3, 4.6, 7]) {
    tower.push(box(-1.1, y, -1.1, 1.1, y + 0.08, 1.1));
  }
  const towerGeometry = merge(tower);
  for (const bend of bends(track, 12)) {
    const outside = -bend.side as 1 | -1;
    const i = Math.floor((bend.s / track.length) * track.n);
    const row = outside > 0 ? track.left : track.right;
    const f = frameAt(track, bend.s + 26, outside * (row.wall[(i + 26) % track.n] + 4));
    const mesh = new THREE.Mesh(towerGeometry, scaffold);
    mesh.position.set(f.x, f.y, f.z);
    const top = new THREE.Mesh(box(-1.3, 8.8, -1.3, 1.3, 9.1, 1.3), tent);
    mesh.add(top);
    group.add(mesh);
    spots.push({ position: new THREE.Vector3(f.x, f.y + 8.6, f.z) });
  }
}

/** Cameras down the long sides too, so none has to film the car from half a kilometre. */
function outerSpots(track: Track, spots: Spot[], every: number): void {
  for (let s = every / 2; s < track.length; s += every) {
    const i = Math.floor((s / track.length) * track.n);
    const outside = track.curvature[i] > 0 ? -1 : 1;
    const row = outside > 0 ? track.left : track.right;
    const f = frameAt(track, s, outside * (row.wall[i] + 3));
    spots.push({ position: new THREE.Vector3(f.x, f.y + 4.5, f.z) });
  }
}

function stageDressing(track: Track, group: THREE.Group, aerial: Aerial, spots: Spot[]): void {
  const { seed } = track.definition;
  const wood = aerial(new THREE.MeshStandardMaterial({ color: 0x6d5236, roughness: 0.9 }));
  const orange = aerial(new THREE.MeshStandardMaterial({ color: 0xe4641c, roughness: 0.6 }));
  const white = aerial(new THREE.MeshStandardMaterial({ color: 0xdedacc, roughness: 0.7 }));
  const stake = instances(new THREE.CylinderGeometry(0.035, 0.05, 1.4, 5).translate(0, 0.7, 0), wood, 2000);
  const flag = instances(new THREE.PlaneGeometry(0.42, 0.26).translate(0.21, 1.25, 0), orange, 800);
  const tape = new THREE.MeshStandardMaterial({ color: 0xe8e4d6, roughness: 0.6, side: THREE.DoubleSide });
  for (const [side, sign] of [[track.left, 1], [track.right, -1]] as const) {
    group.add(new THREE.Mesh(strip(track, side, sign, 0, 0.92, 0.98, 2), aerial(tape)));
    for (let i = 0; i < track.n; i += 14) {
      const p = track.pose((i / track.n) * track.length, sign * side.wall[i]);
      dummy.position.set(p.x, roadHeight("buggy", p.x, p.y), -p.y);
      dummy.rotation.set(0, hash2(i, 1, seed) * 6, 0);
      dummy.scale.setScalar(1);
      put(stake);
      if (i % 42 === 0) {
        put(flag);
      }
    }
  }
  group.add(stake, flag);

  // A straw bale or a stack of tyres on the outside of each bend.
  const bale = instances(new THREE.CylinderGeometry(0.62, 0.62, 1.15, 14).rotateX(Math.PI / 2), aerial(new THREE.MeshStandardMaterial({ color: 0x9c7f55, roughness: 1 })), 300);
  for (const bend of bends(track, 14)) {
    const outside = -bend.side as 1 | -1;
    const i = Math.floor((bend.s / track.length) * track.n);
    const row = outside > 0 ? track.left : track.right;
    for (let k = -21; k <= 21; k += 7) {
      const at = bend.s + k + 3 * hash2(k, i, seed);
      const f = frameAt(track, at, outside * (track.width + row.kerb[(i + k + track.n) % track.n] + 3.2 + 1.2 * hash2(k, i, seed + 1)));
      dummy.position.set(f.x, f.y + 0.56, f.z);
      dummy.rotation.set(0, f.angle + 1.2 * (hash2(k, i, seed + 2) - 0.5), 0);
      dummy.scale.setScalar(1);
      put(bale);
    }
    const spot = frameAt(track, bend.s + 18, outside * (row.wall[(i + 18) % track.n] + 8));
    spots.push({ position: new THREE.Vector3(spot.x, spot.y + 5, spot.z) });
  }
  group.add(bale);

  for (const block of structures(track)) {
    if (block.kind !== "tent") {
      continue;
    }
    const f = frameAt(track, block.s, block.side * (block.d + block.depth / 2));
    const tent = new THREE.Group();
    tent.position.set(f.x, f.y, f.z);
    tent.rotation.y = f.angle;
    const legs: THREE.BufferGeometry[] = [];
    for (const [x, z] of [[-1, -1], [1, -1], [1, 1], [-1, 1]] as const) {
      legs.push(tube(x * block.length * 0.5, 0, z * block.depth * 0.5, x * block.length * 0.5, block.height - 0.4, z * block.depth * 0.5, 0.05, 5));
    }
    tent.add(new THREE.Mesh(merge(legs), wood));
    const top = new THREE.Mesh(new THREE.ConeGeometry(block.depth * 0.82, 1.1, 4).rotateY(Math.PI / 4).scale(block.length / block.depth, 1, 1).translate(0, block.height, 0), Math.round(block.s) % 2 ? orange : white);
    tent.add(top);
    group.add(tent);
  }
}

export function buildScenery(track: Track, line: Line, atmosphere: AtmosphereUniforms): Scenery {
  const group = new THREE.Group();
  const racing = track.definition.car === "racecar";
  const spots: Spot[] = [];
  const aerial: Aerial = (material) => {
    withAerial(material, atmosphere);
    return material;
  };
  const crowd = crowdTexture();
  for (const block of structures(track)) {
    if (block.kind === "stand") {
      group.add(grandstand(block, track, aerial, crowd));
    } else if (block.kind === "pits") {
      group.add(pits(block, track, aerial));
    }
  }
  const { group: arch, lamps, go } = gantry(track, aerial, !racing);
  group.add(arch);
  if (racing) {
    raceDressing(track, line, group, aerial, spots);
  } else {
    stageDressing(track, group, aerial, spots);
  }
  outerSpots(track, spots, 220);
  tufts(track, group, aerial, racing);

  const standing = trees(track);
  const foliage = aerial(new THREE.MeshStandardMaterial({ roughness: 0.95, flatShading: false }));
  const crowns = instances(racing ? pine() : bush(), foliage, standing.length);
  const trunks = instances(new THREE.CylinderGeometry(0.035, 0.07, 0.8, 6).translate(0, 0.4, 0), aerial(new THREE.MeshStandardMaterial({ color: 0x3d2e22, roughness: 0.95 })), racing ? standing.length : 0);
  const tall = racing ? instances(cypress(), foliage, standing.length) : null;
  for (const tree of standing) {
    const i = crowns.count + (tall?.count ?? 0);
    dummy.position.set(tree.x, roadHeight(track.definition.car, tree.x, tree.y), -tree.y);
    dummy.rotation.set(0, hash2(i, 1, 3) * 6, 0);
    if (racing && tree.variant === 2) {
      dummy.scale.set(tree.height * 0.9, tree.height * 1.05, tree.height * 0.9);
      put(tall as THREE.InstancedMesh, color.setRGB(0.05, 0.1, 0.055).multiplyScalar(0.8 + 0.7 * hash2(i, 2, 3)));
    } else if (racing) {
      dummy.scale.set(tree.height * 0.82, tree.height, tree.height * 0.82);
      put(crowns, color.setRGB(0.075, 0.125, 0.05).multiplyScalar(0.75 + 0.8 * hash2(i, 2, 3)));
      put(trunks);
    } else {
      dummy.scale.setScalar(tree.radius * 0.85);
      put(crowns, color.setRGB(0.17, 0.17, 0.085).multiplyScalar(0.7 + 0.7 * hash2(i, 2, 3)));
    }
  }
  group.add(crowns, trunks);
  if (tall) {
    group.add(tall);
  }
  if (racing) {
    // A lighthouse on the shore, so the coast has a landmark from anywhere on the circuit.
    const stone = aerial(new THREE.MeshStandardMaterial({ color: 0xe9e4d8, roughness: 0.7 }));
    const band = aerial(new THREE.MeshStandardMaterial({ color: 0xb12418, roughness: 0.7 }));
    const dark = aerial(new THREE.MeshStandardMaterial({ color: 0x20262c, roughness: 0.5 }));
    const light = new THREE.Group();
    const at = frameAt(track, 300, -210);
    light.position.set(at.x, 6, at.z);
    light.add(new THREE.Mesh(new THREE.CylinderGeometry(3.4, 5, 30, 18).translate(0, 15, 0), stone));
    light.add(new THREE.Mesh(new THREE.CylinderGeometry(3.95, 4.2, 6, 18).translate(0, 16, 0), band));
    light.add(new THREE.Mesh(new THREE.CylinderGeometry(3.2, 3.2, 4, 12).translate(0, 32, 0), dark));
    light.add(new THREE.Mesh(new THREE.ConeGeometry(3.6, 2.4, 12).translate(0, 35.2, 0), band));
    group.add(light);
  }

  return {
    group,
    spots,
    setLights(count: number): void {
      lamps.forEach((lamp, i) => lamp.color.setRGB(count >= 0 && i < count ? 12 : 0.06, count >= 0 && i < count ? 0.5 : 0.01, 0.01));
      go.color.setRGB(count < 0 ? 0.2 : 0.02, count < 0 ? 8 : 0.06, count < 0 ? 1.8 : 0.03);
    },
    dispose(): void {
      group.traverse((part) => {
        const mesh = part as THREE.Mesh;
        if (mesh.isMesh) {
          mesh.geometry.dispose();
        }
      });
    },
  };
}
