/**
 * What stands on the island: the runway, the airfield, the town and the forests, then the gates and
 * the aircraft's shadow. Things on the ground join the world scene, so clouds and aerial perspective
 * fall over them. Everything here is placed once, from the same heightfield the crash check reads.
 */

import * as THREE from "three";
import { type AtmosphereUniforms, withAerial } from "../engine/atmosphere";
import type { Heightfield } from "../engine/heightfield";
import { hash2 } from "../engine/noise";
import type { Gate } from "./flight";
import { AIRFIELD, TOWN } from "./island";

function runwayTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 4096;
  const c = canvas.getContext("2d") as CanvasRenderingContext2D;
  c.fillStyle = "#3a3b3d";
  c.fillRect(0, 0, 256, 4096);
  for (let i = 0; i < 2600; i += 1) {
    c.fillStyle = `rgba(${i % 2 ? "255,255,255" : "0,0,0"},${0.012 + Math.random() * 0.03})`;
    c.fillRect(Math.random() * 256, Math.random() * 4096, 2 + Math.random() * 30, 4 + Math.random() * 120);
  }
  // Rubber on the touchdown zones.
  for (const y of [260, 3400]) {
    for (let i = 0; i < 260; i += 1) {
      c.fillStyle = `rgba(10,10,12,${0.05 + Math.random() * 0.08})`;
      c.fillRect(96 + Math.random() * 62, y + Math.random() * 440, 3 + Math.random() * 6, 40 + Math.random() * 160);
    }
  }
  c.fillStyle = "#e9e9e4";
  c.fillRect(6, 0, 4, 4096);
  c.fillRect(246, 0, 4, 4096);
  for (let y = 240; y < 3840; y += 94) {
    c.fillRect(125, y, 6, 52);
  }
  for (const flip of [false, true]) {
    c.save();
    if (flip) {
      c.translate(256, 4096);
      c.rotate(Math.PI);
    }
    for (let x = 16; x < 240; x += 20) {
      if (Math.abs(x - 118) > 12) {
        c.fillRect(x, 16, 12, 90);
      }
    }
    c.font = "bold 62px sans-serif";
    c.textAlign = "center";
    c.fillText(flip ? "25" : "07", 128, 196);
    for (const y of [420, 620]) {
      c.fillRect(66, y, 26, 66);
      c.fillRect(164, y, 26, 66);
    }
    c.restore();
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}

/** A square in the ground's plane, `y` above the airfield, turned to the runway's heading. */
function apron(width: number, length: number, material: THREE.Material, across: number, along: number, y: number): THREE.Mesh {
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(width, length), material);
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.set(across, y, -along);
  return mesh;
}

function airfield(aerial: (m: THREE.Material) => THREE.Material): THREE.Group {
  const field = new THREE.Group();
  const a = (AIRFIELD.heading * Math.PI) / 180;
  field.position.set(AIRFIELD.east, AIRFIELD.elevation, -AIRFIELD.north);
  field.rotation.y = -a;
  const concrete = aerial(new THREE.MeshStandardMaterial({ color: 0x77776f, roughness: 0.95 }));
  const asphalt = aerial(new THREE.MeshStandardMaterial({ color: 0x45464a, roughness: 0.95 }));
  const runway = aerial(new THREE.MeshStandardMaterial({ map: runwayTexture(), roughness: 0.9 }));
  field.add(
    apron(AIRFIELD.width, AIRFIELD.length, runway, 0, 0, 1.2),
    apron(60, AIRFIELD.length + 240, asphalt, 0, 0, 1),
    apron(23, 1500, asphalt, -150, 0, 1.1),
    apron(300, 900, concrete, -280, 0, 1.15),
  );
  for (const along of [-650, 0, 650]) {
    field.add(apron(130, 23, asphalt, -80, along, 1.12));
  }

  const roof = aerial(new THREE.MeshStandardMaterial({ color: 0x8b8f92, roughness: 0.55, metalness: 0.4 }));
  const wall = aerial(new THREE.MeshStandardMaterial({ color: 0xc8c4b8, roughness: 0.8 }));
  const dark = aerial(new THREE.MeshStandardMaterial({ color: 0x24282c, roughness: 0.6 }));
  // Half-round hangars along the apron's far side, doors towards the runway.
  const door = new THREE.CircleGeometry(25, 18, 0, Math.PI);
  for (let i = 0; i < 7; i += 1) {
    const hangar = new THREE.Group();
    hangar.position.set(-452, 1, -390 + i * 130);
    const body = new THREE.Mesh(new THREE.CylinderGeometry(26, 26, 62, 18, 1, false, -Math.PI / 2, Math.PI), roof);
    body.rotation.z = Math.PI / 2;
    hangar.add(body);
    const front = new THREE.Mesh(door, dark);
    front.rotation.y = Math.PI / 2;
    front.position.x = 31.2;
    hangar.add(front);
    field.add(hangar);
  }
  const tower = new THREE.Mesh(new THREE.CylinderGeometry(5, 7, 34, 10), wall);
  tower.position.set(-430, 18, -560);
  const cab = new THREE.Mesh(new THREE.CylinderGeometry(9.5, 7.5, 6, 10), dark);
  cab.position.set(-430, 38, -560);
  const cap = new THREE.Mesh(new THREE.CylinderGeometry(10, 10, 1.2, 10), roof);
  cap.position.set(-430, 41.5, -560);
  const shed = new THREE.Mesh(new THREE.BoxGeometry(44, 11, 90), wall);
  shed.position.set(-440, 6.5, 560);
  field.add(tower, cab, cap, shed);
  return field;
}

function town(field: Heightfield, material: THREE.Material): THREE.InstancedMesh {
  const box = new THREE.BoxGeometry(1, 1, 1);
  box.translate(0, 0.5, 0);
  const count = 1600;
  const size = 1750;
  const mesh = new THREE.InstancedMesh(box, material, count);
  const matrix = new THREE.Matrix4();
  const quaternion = new THREE.Quaternion();
  const palette = [0xd8cfc0, 0xc4b6a4, 0xb9a48c, 0xa8a8a4, 0xc98f6c, 0x8e9499].map((hex) => new THREE.Color(hex));
  let placed = 0;
  for (let i = 0; placed < count && i < count * 6; i += 1) {
    const angle = hash2(i, 1, 4) * Math.PI * 2;
    const reach = size * hash2(i, 2, 4) ** 0.7;
    // On a street grid, thinning towards the edge.
    const north = TOWN.north + Math.round((reach * Math.cos(angle)) / 56) * 56;
    const east = TOWN.east + Math.round((reach * Math.sin(angle)) / 56) * 56;
    const core = 1 - reach / size;
    const width = 16 + 24 * hash2(i, 3, 4);
    const depth = 16 + 24 * hash2(i, 5, 4);
    const height = 7 + (core > 0.72 ? 74 : 26 * core + 5) * hash2(i, 6, 4) ** 2;
    quaternion.setFromAxisAngle(new THREE.Vector3(0, 1, 0), (Math.floor(hash2(i, 7, 4) * 2) * Math.PI) / 2);
    matrix.compose(new THREE.Vector3(east, field.at(north, east) - 1, -north), quaternion, new THREE.Vector3(width, height, depth));
    mesh.setMatrixAt(placed, matrix);
    mesh.setColorAt(placed, palette[Math.floor(hash2(i, 8, 4) * palette.length)]);
    placed += 1;
  }
  mesh.count = placed;
  mesh.frustumCulled = false;
  return mesh;
}

/** Conifers in stands on low, gentle ground. */
function forest(field: Heightfield, material: THREE.Material): THREE.InstancedMesh {
  const cone = new THREE.ConeGeometry(0.5, 1, 6, 1, true);
  cone.translate(0, 0.5, 0);
  const count = 42000;
  const mesh = new THREE.InstancedMesh(cone, material, count);
  const matrix = new THREE.Matrix4();
  const up = new THREE.Quaternion();
  const greens = [0x16281a, 0x1c301c, 0x142618, 0x24361e].map((hex) => new THREE.Color(hex));
  const color = new THREE.Color();
  const fits = (north: number, east: number): boolean => {
    const height = field.at(north, east);
    const steep = Math.abs(field.at(north + 60, east) - height) + Math.abs(field.at(north, east + 60) - height);
    return height > 8 && height < 1000 && steep < 55
      && Math.hypot(north - AIRFIELD.north, east - AIRFIELD.east) > 2200
      && Math.hypot(north - TOWN.north, east - TOWN.east) > 2000;
  };
  let placed = 0;
  for (let stand = 0; placed < count && stand < 9000; stand += 1) {
    const centreN = (hash2(stand, 11, 9) - 0.5) * 44000 - 1000;
    const centreE = (hash2(stand, 12, 9) - 0.5) * 40000 - 1000;
    if (!fits(centreN, centreE)) {
      continue;
    }
    const spread = 70 + 190 * hash2(stand, 13, 9);
    const trees = Math.floor(20 + 60 * hash2(stand, 14, 9));
    for (let i = 0; i < trees && placed < count; i += 1) {
      const angle = hash2(stand, i, 15) * Math.PI * 2;
      const reach = spread * Math.sqrt(-Math.log(1 - 0.98 * hash2(i, stand, 16)));
      const north = centreN + reach * Math.cos(angle);
      const east = centreE + reach * Math.sin(angle);
      if (!fits(north, east)) {
        continue;
      }
      const tall = 13 + 15 * hash2(i, stand, 17);
      matrix.compose(new THREE.Vector3(east, field.at(north, east) - 1, -north), up, new THREE.Vector3(tall * 0.44, tall, tall * 0.44));
      mesh.setMatrixAt(placed, matrix);
      mesh.setColorAt(placed, color.copy(greens[i % greens.length]).multiplyScalar(0.8 + 0.6 * hash2(i, stand, 18)));
      placed += 1;
    }
  }
  mesh.count = placed;
  mesh.frustumCulled = false;
  return mesh;
}

export function buildGround(field: Heightfield, uniforms: AtmosphereUniforms): THREE.Group {
  const aerial = <M extends THREE.Material>(material: M): M => {
    withAerial(material, uniforms);
    return material;
  };
  const group = new THREE.Group();
  group.add(airfield(aerial));
  group.add(town(field, aerial(new THREE.MeshStandardMaterial({ roughness: 0.85 }))));
  group.add(forest(field, aerial(new THREE.MeshStandardMaterial({ roughness: 1 }))));
  return group;
}

const NEXT = new THREE.Color(3.2, 2.1, 0.5);
const LATER = new THREE.Color(0.9, 0.95, 1.05);
const DONE = new THREE.Color(0.25, 2.2, 0.8);

/** One glowing ring per gate; the next is the bright one, and the one after it shows the way on. */
export class GateRings {
  readonly group = new THREE.Group();
  private readonly rings: THREE.Mesh[] = [];

  show(gates: Gate[]): void {
    this.group.clear();
    this.rings.length = 0;
    const ring = new THREE.TorusGeometry(1, 0.035, 8, 48);
    for (const gate of gates) {
      const mesh = new THREE.Mesh(
        ring,
        new THREE.MeshBasicMaterial({ color: LATER.clone(), transparent: true, opacity: 0.9, toneMapped: false }),
      );
      mesh.position.set(gate.east, gate.alt, -gate.north);
      mesh.rotation.y = -(gate.heading * Math.PI) / 180;
      mesh.scale.setScalar(gate.radius);
      this.group.add(mesh);
      this.rings.push(mesh);
    }
  }

  update(gates: Gate[], time: number): void {
    const next = gates.findIndex((gate) => !gate.passed);
    this.rings.forEach((mesh, i) => {
      const gate = gates[i];
      const material = mesh.material as THREE.MeshBasicMaterial;
      mesh.visible = !gate.passed || i === next - 1;
      if (gate.passed) {
        material.color.copy(gate.hit ? DONE : LATER);
        material.opacity = 0.5;
      } else if (i === next) {
        material.color.copy(NEXT).multiplyScalar(1 + 0.35 * Math.sin(time * 6));
        material.opacity = 1;
      } else {
        material.color.copy(LATER);
        material.opacity = i === next + 1 ? 0.75 : 0.25;
      }
    });
  }
}

/** The aircraft's shadow on the ground: a silhouette, near enough for low flying to read. */
export function groundShadow(): THREE.Mesh {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 128;
  const c = canvas.getContext("2d") as CanvasRenderingContext2D;
  c.filter = "blur(3px)";
  c.fillStyle = "#000";
  c.beginPath();
  // Seen from above, nose up: fuselage, wings, tailplanes.
  for (const [x, y] of [[64, 6], [69, 40], [116, 80], [116, 86], [70, 80], [70, 100], [92, 118], [92, 122], [64, 116], [36, 122], [36, 118], [58, 100], [58, 80], [12, 86], [12, 80], [59, 40]]) {
    c.lineTo(x, y);
  }
  c.closePath();
  c.fill();
  const texture = new THREE.CanvasTexture(canvas);
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.MeshBasicMaterial({ map: texture, transparent: true, opacity: 0.55, depthWrite: false }),
  );
  mesh.geometry.rotateX(-Math.PI / 2);
  mesh.visible = false;
  return mesh;
}
