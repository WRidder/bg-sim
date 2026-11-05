/**
 * What a landing is flown by. The island's airfield is the runway and its buildings; this adds the
 * things a pilot looks for on the way down: the four glide-slope lights beside the aiming point,
 * edge and approach lights, and a windsock that shows what the FMU's wind is doing.
 */

import * as THREE from "three";
import { type AtmosphereUniforms, withAerial } from "../engine/atmosphere";
import { AIM_POINT, DATUM, LANDING_HEADING, THRESHOLD, type Wind } from "./airfield";
import { AIRFIELD } from "./island";

const DEG = Math.PI / 180;
const HN = Math.cos(LANDING_HEADING * DEG);
const HE = Math.sin(LANDING_HEADING * DEG);

/** Scene position of a point `along` from the threshold, `across` right of the centre line. */
function spot(along: number, across: number, up: number, into: THREE.Vector3): THREE.Vector3 {
  const north = THRESHOLD.north + along * HN - across * HE;
  const east = THRESHOLD.east + along * HE + across * HN;
  return into.set(east, up, -north);
}

/** Lights that keep a fixed size on the screen, so they read from a long way out. */
function lights(count: number, size: number): { points: THREE.Points; position: THREE.BufferAttribute; color: THREE.BufferAttribute } {
  const geometry = new THREE.BufferGeometry();
  const position = new THREE.BufferAttribute(new Float32Array(count * 3), 3);
  const color = new THREE.BufferAttribute(new Float32Array(count * 3), 3);
  color.setUsage(THREE.DynamicDrawUsage);
  geometry.setAttribute("position", position);
  geometry.setAttribute("color", color);
  const points = new THREE.Points(
    geometry,
    new THREE.PointsMaterial({ size, sizeAttenuation: false, vertexColors: true, transparent: true, depthWrite: false, toneMapped: false }),
  );
  points.frustumCulled = false;
  return { points, position, color };
}

const scratch = new THREE.Vector3();

/**
 * The shared runway paints each number at the far end from the one it belongs to: a landing here
 * would read "07" upside down. Two patches of asphalt with the right numbers lie over them.
 */
export function runwayNumbers(uniforms: AtmosphereUniforms): THREE.Group {
  const group = new THREE.Group();
  for (const [text, along, turn] of [["25", 143, 0], ["07", AIRFIELD.length - 143, Math.PI]] as const) {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 256;
    const c = canvas.getContext("2d") as CanvasRenderingContext2D;
    c.fillStyle = "#3a3b3d";
    c.fillRect(0, 0, 256, 256);
    c.fillStyle = "#e9e9e4";
    c.font = "bold 150px sans-serif";
    c.textAlign = "center";
    c.textBaseline = "middle";
    c.setTransform(0.9, 0, 0, 1.5, 128, 128);
    c.fillText(text, 0, 0);
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = 8;
    const material = new THREE.MeshStandardMaterial({ map: texture, roughness: 0.9 });
    withAerial(material, uniforms);
    const patch = new THREE.Mesh(new THREE.PlaneGeometry(36, 50), material);
    // Lying flat, its top towards the far end of the runway, read by whoever is landing past it.
    patch.geometry.rotateX(-Math.PI / 2);
    patch.rotation.y = -LANDING_HEADING * DEG + turn;
    spot(along, 0, DATUM + 0.06, patch.position);
    group.add(patch);
  }
  return group;
}

export class FieldLights {
  readonly group = new THREE.Group();
  private readonly papi = lights(4, 7);
  private readonly approach = lights(18, 5);
  private readonly papiAt: THREE.Vector3[] = [];
  private readonly sock = new THREE.Group();
  private readonly sockRings: THREE.Mesh[] = [];

  constructor(ground: (north: number, east: number) => number) {
    // Left of the runway, abeam the aiming point, as on any real runway.
    for (let i = 0; i < 4; i += 1) {
      const at = spot(AIM_POINT, -AIRFIELD.width / 2 - 14 - i * 9, DATUM + 1.2, new THREE.Vector3());
      this.papiAt.push(at);
      this.papi.position.setXYZ(i, at.x, at.y, at.z);
    }
    this.group.add(this.papi.points);

    const edges = lights(200, 2.6);
    const c = new THREE.Color();
    let n = 0;
    for (let along = 0; along <= AIRFIELD.length; along += 80) {
      for (const side of [-1, 1]) {
        spot(along, side * (AIRFIELD.width / 2 + 2), DATUM + 0.5, scratch);
        edges.position.setXYZ(n, scratch.x, scratch.y, scratch.z);
        const near = along > AIRFIELD.length - 600;
        c.setRGB(near ? 1.6 : 1.7, near ? 1.0 : 1.6, near ? 0.3 : 1.3);
        edges.color.setXYZ(n, c.r, c.g, c.b);
        n += 1;
      }
    }
    // The threshold's green bar.
    for (let across = -22; across <= 22; across += 5) {
      spot(-1, across, DATUM + 0.4, scratch);
      edges.position.setXYZ(n, scratch.x, scratch.y, scratch.z);
      edges.color.setXYZ(n, 0.2, 2, 0.5);
      n += 1;
    }
    edges.points.geometry.setDrawRange(0, n);
    this.group.add(edges.points);

    // A line of poles out over the water, each flashing in turn towards the runway.
    for (let i = 0; i < 18; i += 1) {
      const along = -60 - i * 50;
      const north = THRESHOLD.north + along * HN;
      const east = THRESHOLD.east + along * HE;
      const up = Math.max(ground(north, east), 0) + 5;
      this.approach.position.setXYZ(i, east, up, -north);
    }
    this.group.add(this.approach.points);
    const pole = new THREE.Mesh(
      new THREE.CylinderGeometry(0.1, 0.13, 9, 8),
      new THREE.MeshStandardMaterial({ color: 0xc8c8c0, roughness: 0.6 }),
    );
    pole.geometry.translate(0, 4.5, 0);
    spot(170, 62, DATUM - 1.2, this.sock.position);
    pole.position.copy(this.sock.position);
    this.group.add(pole);

    // The sock: five hoops of orange and white, tapering, each hanging from the one before.
    this.sock.position.y += 8.7;
    const orange = new THREE.MeshStandardMaterial({ color: 0xff5a1a, roughness: 0.75, side: THREE.DoubleSide });
    const white = new THREE.MeshStandardMaterial({ color: 0xf0ece0, roughness: 0.75, side: THREE.DoubleSide });
    let parent: THREE.Object3D = this.sock;
    for (let i = 0; i < 5; i += 1) {
      const hoop = new THREE.Mesh(
        new THREE.CylinderGeometry(0.42 - i * 0.05, 0.37 - i * 0.05, 0.8, 16, 1, true),
        i % 2 ? white : orange,
      );
      hoop.geometry.rotateZ(Math.PI / 2);
      hoop.geometry.translate(0.4, 0, 0);
      hoop.position.x = i === 0 ? 0 : 0.78;
      parent.add(hoop);
      parent = hoop;
      this.sockRings.push(hoop);
    }
    this.group.add(this.sock);
  }

  /** `from` is the point that looks at the lights: the pilot. */
  update(from: THREE.Vector3, wind: Wind, time: number): void {
    // Each light turns from red to white at its own angle: two of each is on the path.
    for (let i = 0; i < 4; i += 1) {
      const at = this.papiAt[i];
      const range = Math.hypot(from.x - at.x, from.z - at.z);
      const angle = Math.atan2(from.y - at.y, range) / DEG;
      const white = angle > 2.5 + i * 0.33;
      if (white) {
        this.papi.color.setXYZ(i, 2.4, 2.4, 2.2);
      } else {
        this.papi.color.setXYZ(i, 2.6, 0.12, 0.08);
      }
    }
    this.papi.color.needsUpdate = true;

    const running = time % 1.8;
    for (let i = 0; i < 18; i += 1) {
      const flash = Math.exp(-((running - (17 - i) * 0.05) ** 2) / 0.0012) * 3;
      this.approach.color.setXYZ(i, 0.5 + flash, 0.5 + flash, 0.48 + flash);
    }
    this.approach.color.needsUpdate = true;

    // Wind in the runway's terms to a heading for the sock: it streams away from where it blows.
    const speed = Math.hypot(wind.head, wind.cross);
    const to = LANDING_HEADING * DEG + Math.atan2(wind.cross, wind.head) + Math.PI;
    const flutter = Math.sin(time * 3.1) * 0.04 + Math.sin(time * 5.3 + 1) * 0.03;
    this.sock.rotation.y = speed > 0.05 ? Math.PI / 2 - to + flutter : 0.4;
    const lift = Math.min(speed / 9, 1);
    this.sockRings.forEach((ring, i) => {
      ring.rotation.z = -(1.2 * (1 - lift)) / (i === 0 ? 1 : 3) + flutter * i * 0.3;
    });
  }
}
