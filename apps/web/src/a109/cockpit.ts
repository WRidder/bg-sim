/**
 * The right seat: the glare shield, the instrument panel, the frames of the screen and the door, the
 * console and the stick. Built in the helicopter's mesh frame, so it flies along. The panel's displays
 * are one canvas, drawn a few times a second from the flight's numbers.
 */

import * as THREE from "three";
import { type Flight, POWER_LIMIT } from "./flight";
import { bodySpeeds } from "./pilot";

/** The pilot's eye, a little above the desktop app's so the panel clears the view of the deck. */
export const EYE = new THREE.Vector3(1.42, -0.38, 0.52);

const WIDE = 1024;
const TALL = 256;
const INK = "#d9f2e4";
const DIM = "#6f8a80";
const CYAN = "#58d8ff";
const AMBER = "#ffc34d";
const RED = "#ff5a4d";
const GREEN = "#7dffb0";
const FONT = 'ui-monospace, "Cascadia Mono", Consolas, monospace';

function bar(a: THREE.Vector3, b: THREE.Vector3, radius: number, material: THREE.Material): THREE.Mesh {
  const length = a.distanceTo(b);
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(radius * 2, length, radius * 2.6), material);
  mesh.position.copy(a).add(b).multiplyScalar(0.5);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
  return mesh;
}

const v = (x: number, y: number, z: number): THREE.Vector3 => new THREE.Vector3(x, y, z);

export class Cockpit {
  readonly group = new THREE.Group();
  private readonly canvas = document.createElement("canvas");
  private readonly c: CanvasRenderingContext2D;
  private readonly texture: THREE.CanvasTexture;
  private readonly stick = new THREE.Group();
  private since = 1;

  constructor() {
    this.canvas.width = WIDE;
    this.canvas.height = TALL;
    this.c = this.canvas.getContext("2d") as CanvasRenderingContext2D;
    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;
    this.texture.anisotropy = 8;
    this.build();
    this.group.visible = false;
  }

  private build(): void {
    const { group } = this;
    const dark = new THREE.MeshStandardMaterial({ color: 0x121315, roughness: 0.82 });
    const shell = new THREE.MeshStandardMaterial({ color: 0x2a2d31, roughness: 0.72 });
    const pale = new THREE.MeshStandardMaterial({ color: 0x8d9094, roughness: 0.6 });
    const fabric = new THREE.MeshStandardMaterial({ color: 0x2f3338, roughness: 0.95 });

    // The panel faces the crew from under the shield.
    const face = new THREE.Mesh(new THREE.PlaneGeometry(1.44, 0.36), new THREE.MeshBasicMaterial({ map: this.texture, color: new THREE.Color(0.86, 0.86, 0.86) }));
    face.up.set(0, 0, 1);
    face.lookAt(-1, 0, 0);
    face.position.set(2.19, 0, 0.0);
    group.add(face);
    const backing = new THREE.Mesh(new THREE.BoxGeometry(0.04, 1.56, 0.5), dark);
    backing.position.set(2.215, 0, 0);
    group.add(backing);

    const shieldShape = new THREE.Shape();
    shieldShape.moveTo(-0.8, 0);
    shieldShape.quadraticCurveTo(-0.72, 0.1, -0.2, 0.12);
    shieldShape.quadraticCurveTo(0, 0.13, 0.2, 0.12);
    shieldShape.quadraticCurveTo(0.72, 0.1, 0.8, 0);
    shieldShape.lineTo(-0.8, 0);
    const shieldGeometry = new THREE.ExtrudeGeometry(shieldShape, { depth: 0.42, bevelEnabled: false, curveSegments: 16 });
    shieldGeometry.applyMatrix4(new THREE.Matrix4().makeBasis(v(0, 1, 0), v(0, 0, 1), v(1, 0, 0)));
    const shield = new THREE.Mesh(shieldGeometry, dark);
    shield.position.set(2.1, 0, 0.17);
    group.add(shield);

    // The screen's posts, and the roof with its frame over the crew.
    group.add(bar(v(2.42, 0, 0.26), v(1.42, 0, 1.0), 0.012, shell));
    for (const side of [1, -1]) {
      group.add(bar(v(2.42, side * 0.72, 0.14), v(1.34, side * 0.66, 0.98), 0.024, shell));
      group.add(bar(v(1.34, side * 0.66, 0.98), v(0.8, side * 0.7, 1.02), 0.05, shell));
      group.add(bar(v(1.34, side * 0.66, 0.98), v(1.34, side * 0.86, 0.1), 0.028, shell));
      group.add(bar(v(0.62, side * 0.88, 1.0), v(0.62, side * 0.9, -0.2), 0.05, shell));
      group.add(bar(v(2.5, side * 0.74, 0.08), v(0.5, side * 0.9, 0.02), 0.022, shell));
      const sill = new THREE.Mesh(new THREE.BoxGeometry(2, 0.05, 0.75), shell);
      sill.position.set(1.5, side * 0.89, -0.36);
      sill.rotation.z = side * -0.07;
      group.add(sill);
      const seat = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.52, 0.86), fabric);
      seat.position.set(0.86, side * 0.38, 0.28);
      seat.rotation.y = -0.16;
      group.add(seat);
      const cushion = new THREE.Mesh(new THREE.BoxGeometry(0.56, 0.52, 0.13), fabric);
      cushion.position.set(1.14, side * 0.38, -0.2);
      group.add(cushion);
      const pedal = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.12, 0.22), pale);
      pedal.position.set(2.05, side * 0.2 - 0.38, -0.46);
      pedal.rotation.y = -0.5;
      group.add(pedal);
    }
    const roof = new THREE.Mesh(new THREE.BoxGeometry(0.54, 1.4, 0.05), shell);
    roof.position.set(1.06, 0, 1.03);
    group.add(roof);
    const overhead = new THREE.Mesh(new THREE.BoxGeometry(0.46, 0.46, 0.08), dark);
    overhead.position.set(1.08, 0, 0.98);
    overhead.rotation.y = 0.2;
    group.add(overhead);
    const floor = new THREE.Mesh(new THREE.BoxGeometry(1.5, 1.76, 0.05), dark);
    floor.position.set(1.05, 0, -0.62);
    group.add(floor);

    const console_ = new THREE.Mesh(new THREE.BoxGeometry(1.02, 0.26, 0.3), dark);
    console_.position.set(1.66, 0, -0.42);
    console_.rotation.y = 0.32;
    group.add(console_);
    for (let i = 0; i < 18; i += 1) {
      const key = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.03, 0.01), i % 5 === 0 ? pale : shell);
      key.position.set(1.32 + (i % 6) * 0.11, -0.07 + Math.floor(i / 6) * 0.07, -0.25 - (i % 6) * 0.035);
      key.rotation.y = 0.32;
      group.add(key);
    }

    // The stick, pivoting at the floor between the knees.
    this.stick.position.set(1.62, -0.38, -0.6);
    const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.018, 0.62, 12), dark);
    shaft.rotation.x = Math.PI / 2;
    shaft.position.z = 0.31;
    const head = new THREE.Mesh(new THREE.CapsuleGeometry(0.026, 0.08, 6, 12), fabric);
    head.rotation.x = Math.PI / 2;
    head.position.z = 0.64;
    this.stick.add(shaft, head);
    group.add(this.stick);

    // Wiper, and the compass on the post.
    group.add(bar(v(2.34, -0.42, 0.3), v(1.98, -0.32, 0.63), 0.006, dark));
    const compass = new THREE.Mesh(new THREE.SphereGeometry(0.03, 12, 10), dark);
    compass.position.set(2.18, 0.02, 0.36);
    group.add(compass);
  }

  /** The stick's lean follows the cyclic, the displays a few times a second. */
  update(dt: number, f: Flight, next: { north: number; east: number; top: number } | undefined): void {
    this.stick.rotation.set(f.u[2] * 0.2, f.u[1] * 0.2, 0, "YXZ");
    this.since += dt;
    if (this.group.visible && this.since > 0.08) {
      this.since = 0;
      this.draw(f, next);
      this.texture.needsUpdate = true;
    }
  }

  private label(s: string, x: number, y: number, size: number, color = INK, align: CanvasTextAlign = "left"): void {
    const c = this.c;
    c.font = `600 ${size}px ${FONT}`;
    c.fillStyle = color;
    c.textAlign = align;
    c.fillText(s, x, y);
  }

  private draw(f: Flight, next: { north: number; east: number; top: number } | undefined): void {
    const c = this.c;
    c.fillStyle = "#181a1c";
    c.fillRect(0, 0, WIDE, TALL);
    this.screen(14, 12, 282, 232, () => this.attitude(f));
    this.screen(308, 12, 232, 232, () => this.hover(f));
    this.screen(552, 12, 262, 232, () => this.navigation(f, next));
    this.screen(826, 12, 184, 232, () => this.engines(f));
  }

  private screen(x: number, y: number, w: number, h: number, content: () => void): void {
    const c = this.c;
    c.save();
    c.translate(x, y);
    c.beginPath();
    c.roundRect(0, 0, w, h, 8);
    c.fillStyle = "#050a0a";
    c.fill();
    c.clip();
    content();
    c.restore();
    c.strokeStyle = "#34383c";
    c.lineWidth = 3;
    c.beginPath();
    c.roundRect(x, y, w, h, 8);
    c.stroke();
  }

  private attitude(f: Flight): void {
    const c = this.c;
    const w = 282;
    const h = 232;
    const perDeg = 4.2;
    c.save();
    c.beginPath();
    c.rect(52, 22, 178, 188);
    c.clip();
    c.translate(141, 116);
    c.rotate((-f.get("phi_deg") * Math.PI) / 180);
    c.translate(0, f.get("theta_deg") * perDeg);
    c.fillStyle = "#1f6fb0";
    c.fillRect(-300, -600, 600, 600);
    c.fillStyle = "#7a5230";
    c.fillRect(-300, 0, 600, 600);
    c.strokeStyle = "#ffffff";
    c.lineWidth = 2;
    c.beginPath();
    c.moveTo(-300, 0);
    c.lineTo(300, 0);
    c.stroke();
    for (let p = -30; p <= 30; p += 10) {
      if (p !== 0) {
        const y = -p * perDeg;
        c.beginPath();
        c.moveTo(-26, y);
        c.lineTo(26, y);
        c.stroke();
      }
    }
    c.restore();
    c.strokeStyle = AMBER;
    c.lineWidth = 4;
    c.beginPath();
    c.moveTo(96, 116);
    c.lineTo(128, 116);
    c.moveTo(154, 116);
    c.lineTo(186, 116);
    c.stroke();
    c.fillStyle = AMBER;
    c.fillRect(138, 113, 6, 6);
    this.label(`${Math.round(f.get("kts"))}`, 6, 122, 26);
    this.label("KT", 6, 142, 13, DIM);
    this.label(`${Math.round(f.altitude() * 3.28084)}`, w - 4, 122, 22, INK, "right");
    this.label("FT", w - 4, 142, 13, DIM, "right");
    const radar = Math.max(f.radar(), 0);
    this.label(radar < 300 ? `R ${radar.toFixed(radar < 30 ? 1 : 0)}` : "", 141, h - 6, 20, radar < 12 ? AMBER : GREEN, "center");
    const vs = f.get("vs_mps");
    this.label(`${vs >= 0 ? "+" : ""}${vs.toFixed(1)}`, w - 4, 180, 18, Math.abs(vs) > 2.5 ? AMBER : INK, "right");
    this.label("M/S", w - 4, 198, 12, DIM, "right");
    this.label(`${((f.get("psi_deg") + 360) % 360).toFixed(0).padStart(3, "0")}`, 141, 18, 18, INK, "center");
  }

  /** The drift over the ground, nose up, with 10 knots at the rim. */
  private hover(f: Flight): void {
    const c = this.c;
    const x = 116;
    const y = 112;
    const r = 96;
    c.strokeStyle = "#2c5a48";
    c.lineWidth = 2;
    for (const ring of [r, r / 2]) {
      c.beginPath();
      c.arc(x, y, ring, 0, Math.PI * 2);
      c.stroke();
    }
    c.beginPath();
    c.moveTo(x - r, y);
    c.lineTo(x + r, y);
    c.moveTo(x, y - r);
    c.lineTo(x, y + r);
    c.stroke();
    const [along, across] = bodySpeeds(f);
    const knots = 1.94384;
    const px = Math.max(-1, Math.min(1, (across * knots) / 10));
    const py = Math.max(-1, Math.min(1, (along * knots) / 10));
    const slow = f.groundSpeed() * knots < 1;
    c.strokeStyle = slow ? GREEN : CYAN;
    c.lineWidth = 4;
    c.beginPath();
    c.moveTo(x, y);
    c.lineTo(x + px * r, y - py * r);
    c.stroke();
    c.fillStyle = slow ? GREEN : CYAN;
    c.beginPath();
    c.arc(x + px * r, y - py * r, 8, 0, Math.PI * 2);
    c.fill();
    this.label(`${(f.groundSpeed() * knots).toFixed(1)} KT`, x, 228, 15, slow ? GREEN : INK, "center");
    this.label("HOVER", 6, 18, 13, DIM);
  }

  private navigation(f: Flight, next: { north: number; east: number; top: number } | undefined): void {
    this.label("NEXT PAD", 12, 26, 14, DIM);
    if (!next) {
      this.label("----", 12, 62, 28, DIM);
      return;
    }
    const dn = next.north - f.north();
    const de = next.east - f.east();
    const bearing = ((Math.atan2(de, dn) * 180) / Math.PI + 360) % 360;
    const off = (((bearing - f.get("psi_deg")) + 540) % 360) - 180;
    const km = Math.hypot(dn, de) / 1000;
    this.label(`${km.toFixed(km < 10 ? 2 : 1)} KM`, 12, 62, 28, GREEN);
    this.label(`BRG ${bearing.toFixed(0).padStart(3, "0")}`, 12, 92, 18, INK);
    const above = next.top - f.altitude();
    this.label(`DECK ${above >= 0 ? "+" : ""}${above.toFixed(0)} M`, 12, 118, 18, above > 0 ? AMBER : INK);
    const c = this.c;
    c.save();
    c.translate(190, 150);
    c.strokeStyle = "#2c5a48";
    c.lineWidth = 2;
    c.beginPath();
    c.arc(0, 0, 58, 0, Math.PI * 2);
    c.stroke();
    c.rotate((off * Math.PI) / 180);
    c.fillStyle = AMBER;
    c.beginPath();
    c.moveTo(0, -54);
    c.lineTo(-11, -30);
    c.lineTo(11, -30);
    c.fill();
    c.restore();
  }

  private engines(f: Flight): void {
    const c = this.c;
    const meter = (x: number, name: string, value: number, top: number, green: number, red: number): void => {
      const y0 = 196;
      const tall = 160;
      const at = (t: number): number => y0 - (tall * Math.max(0, Math.min(top, t))) / top;
      c.fillStyle = "#10201a";
      c.fillRect(x, y0 - tall, 42, tall);
      c.fillStyle = value >= red ? RED : value >= green ? AMBER : GREEN;
      c.fillRect(x + 3, at(value), 36, y0 - at(value));
      c.fillStyle = RED;
      c.fillRect(x - 4, at(red) - 1, 50, 3);
      this.label(name, x + 21, 18, 15, DIM, "center");
      this.label(`${Math.round(value)}`, x + 21, 220, 20, INK, "center");
    };
    meter(20, "TQ", (f.get("power_hp") / POWER_LIMIT) * 100, 110, 90, 100);
    meter(116, "NR", f.get("rotor_pct"), 115, 106, 110);
  }
}
