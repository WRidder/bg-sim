/**
 * The view from the left seat. The airframe stays drawn: its skin faces outward, so from inside the
 * cabin it vanishes, while the cowling, the wing's underside and the strut stay in view. This group
 * adds what a passenger would touch: the panel with its dials, the glareshield, the doors and
 * pillars, the yoke and the throttle. It is in the body frame, like the aeroplane.
 */

import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import type { Flight } from "./flight";
import { Instruments, type Readings } from "./instruments";

/** The pilot's eye, from the CG: the left seat. */
export const EYE = new THREE.Vector3(0.25, 0.28, 0.33);
/** A pilot looks a little down, over the cowling: with this the panel fits under the horizon. */
export const SEAT_TILT = (9 * Math.PI) / 180;

const WIDTH = 1280;
const HEIGHT = 400;
/** The panel's plane: its top edge just under the glareshield. */
const PANEL = { x: 0.84, left: 0.58, right: -0.58, top: 0.1, bottom: -0.26 };

function beam(a: THREE.Vector3Like, b: THREE.Vector3Like, radius: number, flat = 1): THREE.BufferGeometry {
  const from = new THREE.Vector3().copy(a);
  const to = new THREE.Vector3().copy(b);
  const geometry = new THREE.CylinderGeometry(radius, radius, from.distanceTo(to), 12);
  geometry.scale(1, 1, flat);
  geometry.rotateX(Math.PI / 2);
  geometry.applyMatrix4(new THREE.Matrix4().lookAt(from, to, new THREE.Vector3(0.3, 0.2, 1)));
  geometry.translate((from.x + to.x) / 2, (from.y + to.y) / 2, (from.z + to.z) / 2);
  return geometry;
}

function plate(corners: [THREE.Vector3Like, THREE.Vector3Like, THREE.Vector3Like, THREE.Vector3Like]): THREE.BufferGeometry {
  const p = corners.flatMap((c) => [c.x, c.y, c.z]);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(p, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute([0, 1, 1, 1, 1, 0, 0, 0], 2));
  geometry.setIndex([0, 2, 1, 0, 3, 2]);
  geometry.computeVertexNormals();
  return geometry;
}

export class Cockpit {
  readonly group = new THREE.Group();
  private readonly canvas = document.createElement("canvas");
  private readonly c: CanvasRenderingContext2D;
  private readonly texture: THREE.CanvasTexture;
  private readonly dials = new Instruments();
  private readonly face: HTMLCanvasElement;
  private readonly yokes: THREE.Group[] = [];
  private readonly lever: THREE.Mesh;
  private lastDraw = -1;

  constructor() {
    this.canvas.width = WIDTH;
    this.canvas.height = HEIGHT;
    this.c = this.canvas.getContext("2d", { alpha: false }) as CanvasRenderingContext2D;
    this.face = this.paintFace();
    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;
    this.texture.generateMipmaps = false;
    this.texture.minFilter = THREE.LinearFilter;

    const trim = new THREE.MeshStandardMaterial({ color: 0x2b2e31, roughness: 0.7 });
    const pale = new THREE.MeshStandardMaterial({ color: 0x3f3e3a, roughness: 0.85, side: THREE.DoubleSide });
    const shadow = new THREE.MeshStandardMaterial({ color: 0x17191b, roughness: 0.65, side: THREE.DoubleSide });
    const chrome = new THREE.MeshStandardMaterial({ color: 0x9ea2a6, roughness: 0.3, metalness: 0.9 });
    const { x, left, right, top, bottom } = PANEL;
    const panel = new THREE.Mesh(
      plate([
        { x, y: left, z: top },
        { x, y: right, z: top },
        { x, y: right, z: bottom },
        { x, y: left, z: bottom },
      ]),
      new THREE.MeshBasicMaterial({ map: this.texture, color: new THREE.Color(0.86, 0.85, 0.82), side: THREE.DoubleSide }),
    );
    this.group.add(panel);

    // The glareshield: a padded hood over the panel.
    const hood = new THREE.Shape();
    hood.moveTo(-0.61, 0);
    hood.bezierCurveTo(-0.55, 0.075, 0.55, 0.075, 0.61, 0);
    hood.lineTo(0.61, -0.04);
    hood.lineTo(-0.61, -0.04);
    const geometry = new THREE.ExtrudeGeometry(hood, { depth: 0.24, bevelEnabled: false, curveSegments: 20 });
    // The shape's x is across the cabin, its y up, the depth forward.
    geometry.applyMatrix4(new THREE.Matrix4().makeBasis(new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, 0, 1), new THREE.Vector3(1, 0, 0)));
    geometry.translate(x, 0, top + 0.015);
    this.group.add(new THREE.Mesh(geometry, shadow));

    const frames: THREE.BufferGeometry[] = [];
    for (const side of [1, -1]) {
      // The windshield's pillar, the door's front edge and the sill.
      frames.push(beam({ x: 0.93, y: side * 0.56, z: 0.11 }, { x: 0.47, y: side * 0.56, z: 0.63 }, 0.03, 0.8));
      frames.push(beam({ x: 0.93, y: side * 0.585, z: 0.08 }, { x: -0.42, y: side * 0.585, z: 0.08 }, 0.03, 0.7));
      frames.push(beam({ x: -0.42, y: side * 0.585, z: 0.08 }, { x: -0.42, y: side * 0.585, z: 0.63 }, 0.035, 0.7));
    }
    frames.push(beam({ x: 0.47, y: 0.58, z: 0.63 }, { x: 0.47, y: -0.58, z: 0.63 }, 0.035, 0.8));
    frames.push(beam({ x: 0.93, y: 0, z: 0.12 }, { x: 0.47, y: 0, z: 0.62 }, 0.008));
    this.group.add(new THREE.Mesh(mergeGeometries(frames.map((g) => g.toNonIndexed())), trim));

    // The headliner, the door panels below the sill and the walls behind the seats.
    const liner: THREE.BufferGeometry[] = [
      plate([{ x: 0.5, y: 0.6, z: 0.64 }, { x: 0.5, y: -0.6, z: 0.64 }, { x: -1.2, y: -0.6, z: 0.62 }, { x: -1.2, y: 0.6, z: 0.62 }]),
      plate([{ x: -0.42, y: 0.59, z: 0.64 }, { x: -1.5, y: 0.59, z: 0.62 }, { x: -1.5, y: 0.59, z: -0.7 }, { x: -0.42, y: 0.59, z: -0.7 }]),
      plate([{ x: -0.42, y: -0.59, z: 0.64 }, { x: -1.5, y: -0.59, z: 0.62 }, { x: -1.5, y: -0.59, z: -0.7 }, { x: -0.42, y: -0.59, z: -0.7 }]),
    ];
    for (const side of [1, -1]) {
      liner.push(plate([{ x: 0.9, y: side * 0.6, z: 0.07 }, { x: -0.42, y: side * 0.6, z: 0.07 }, { x: -0.42, y: side * 0.6, z: -0.7 }, { x: 0.9, y: side * 0.6, z: -0.7 }]));
    }
    this.group.add(new THREE.Mesh(mergeGeometries(liner), pale));

    // The floor and the fire wall below the panel: dark, and most of it hidden by the yoke.
    this.group.add(new THREE.Mesh(
      plate([{ x: 0.86, y: 0.6, z: -0.26 }, { x: 0.86, y: -0.6, z: -0.26 }, { x: 0.4, y: -0.6, z: -0.7 }, { x: 0.4, y: 0.6, z: -0.7 }]),
      shadow,
    ));

    for (const seat of [0.28]) {
      const yoke = new THREE.Group();
      yoke.position.set(0.5, seat, 0.02);
      const shaft = new THREE.Mesh(beam({ x: 0, y: 0, z: 0 }, { x: 0.36, y: 0, z: -0.26 }, 0.014), chrome);
      yoke.add(shaft);
      const wheel: THREE.BufferGeometry[] = [
        beam({ x: 0, y: -0.1, z: 0.0 }, { x: 0, y: 0.1, z: 0.0 }, 0.016),
        beam({ x: 0, y: -0.1, z: 0.0 }, { x: 0, y: -0.125, z: 0.075 }, 0.018),
        beam({ x: 0, y: 0.1, z: 0.0 }, { x: 0, y: 0.125, z: 0.075 }, 0.018),
        new THREE.BoxGeometry(0.02, 0.06, 0.07),
      ];
      const grip = new THREE.Mesh(mergeGeometries(wheel.map((g) => (g.index ? g.toNonIndexed() : g)).map((g) => {
        g.deleteAttribute("uv");
        return g;
      })), shadow);
      yoke.add(grip);
      this.group.add(yoke);
      this.yokes.push(yoke);
    }

    this.lever = new THREE.Mesh(new THREE.SphereGeometry(0.018, 12, 10), new THREE.MeshStandardMaterial({ color: 0x0b0b0c, roughness: 0.4 }));
    this.lever.add(new THREE.Mesh(beam({ x: 0, y: 0, z: 0 }, { x: 0.09, y: 0, z: 0 }, 0.004), chrome));
    this.group.add(this.lever);
    this.group.visible = false;
  }

  /** The panel behind the dials: painted once, then laid under each update. */
  private paintFace(): HTMLCanvasElement {
    const canvas = document.createElement("canvas");
    canvas.width = WIDTH;
    canvas.height = HEIGHT;
    const c = canvas.getContext("2d") as CanvasRenderingContext2D;
    const metal = c.createLinearGradient(0, 0, 0, HEIGHT);
    metal.addColorStop(0, "#26292c");
    metal.addColorStop(1, "#1a1c1f");
    c.fillStyle = metal;
    c.fillRect(0, 0, WIDTH, HEIGHT);
    // Fine vertical brushing keeps the panel from looking like flat paint.
    for (let i = 0; i < 1400; i += 1) {
      c.fillStyle = `rgba(255,255,255,${0.008 + Math.random() * 0.012})`;
      c.fillRect(Math.random() * WIDTH, Math.random() * HEIGHT, 1, 14 + Math.random() * 60);
    }
    c.strokeStyle = "rgba(0,0,0,0.5)";
    c.lineWidth = 3;
    c.strokeRect(56, 8, 540, 382);
    c.fillStyle = "#c9c6ba";
    c.font = '600 15px "Bahnschrift", "Arial Narrow", sans-serif';
    c.textAlign = "center";
    for (const [text, x, y] of [["FLAPS", 716, 182], ["TRIM", 800, 182], ["BRAKE", 884, 182]] as const) {
      c.fillText(text, x, y + 186);
    }
    // Radio stack.
    c.fillStyle = "#0b0c0d";
    c.fillRect(960, 36, 268, 130);
    c.fillRect(960, 180, 268, 96);
    c.strokeStyle = "#3a3e42";
    c.strokeRect(960, 36, 268, 130);
    c.strokeRect(960, 180, 268, 96);
    for (let i = 0; i < 4; i += 1) {
      for (const y of [146, 262]) {
        c.fillStyle = "#3a3e42";
        c.beginPath();
        c.arc(990 + i * 70, y, 7, 0, Math.PI * 2);
        c.fill();
      }
    }
    return canvas;
  }

  /** The dials, at most twenty times a second: a texture upload per frame buys nothing here. */
  update(f: Flight, readings: Readings, bug: number | null, wind: string, time: number): void {
    const pitch = f.u[0];
    const roll = f.u[1];
    for (const yoke of this.yokes) {
      yoke.position.x = 0.5 - pitch * 0.07;
      yoke.rotation.x = roll * 0.9;
    }
    this.lever.position.set(0.74 + f.throttle * 0.07, 0.0, -0.2);
    if (time - this.lastDraw < 0.05 && time >= this.lastDraw) {
      return;
    }
    this.lastDraw = time;
    const c = this.c;
    c.drawImage(this.face, 0, 0);
    const r = 84;
    const { dials } = this;
    dials.speed(c, 142, 104, r, readings.kias);
    dials.attitude(c, 326, 104, r, readings.pitch, readings.bank);
    dials.altitude(c, 510, 104, r, readings.feet);
    dials.turn(c, 142, 288, r, readings.turn, readings.slip);
    dials.compass(c, 326, 288, r, readings.heading, bug);
    dials.climb(c, 510, 288, r, readings.fpm);
    dials.revs(c, 716, 104, 70, readings.rpm);
    this.bars(c, f);
    this.radio(c, readings, wind);
    this.texture.needsUpdate = true;
  }

  private bars(c: CanvasRenderingContext2D, f: Flight): void {
    const bar = (x: number, value: number, marks: number): void => {
      c.fillStyle = "#0b0c0d";
      c.fillRect(x - 12, 196, 24, 150);
      c.strokeStyle = "#3a3e42";
      c.lineWidth = 1;
      c.strokeRect(x - 12, 196, 24, 150);
      c.fillStyle = "#6b6f73";
      for (let i = 0; i <= marks; i += 1) {
        c.fillRect(x + 14, 196 + (150 * i) / marks - 1, 8, 2);
      }
      c.fillStyle = "#ffb43a";
      c.fillRect(x - 12, 196 + 150 * value - 3, 24, 6);
    };
    bar(716, f.get("flap_deg") / 30, 3);
    bar(800, 0.5 - f.trim / 2, 4);
    bar(884, f.brakes, 1);
  }

  private radio(c: CanvasRenderingContext2D, r: Readings, wind: string): void {
    c.fillStyle = "#0b0c0d";
    c.fillRect(976, 50, 236, 72);
    c.fillRect(976, 194, 236, 46);
    c.font = '600 44px ui-monospace, "Cascadia Mono", Consolas, monospace';
    c.textAlign = "left";
    c.fillStyle = "#ffae42";
    c.fillText(`${String(Math.round(r.heading) % 360).padStart(3, "0")}`, 984, 104);
    c.font = '600 20px ui-monospace, "Cascadia Mono", Consolas, monospace';
    c.fillStyle = "#7dffb0";
    c.textAlign = "right";
    c.fillText(`${Math.round(r.kias)} KT`, 1204, 78);
    c.fillText(`${Math.round(r.feet)} FT`, 1204, 106);
    c.textAlign = "left";
    c.fillText(wind, 984, 224);
  }
}
