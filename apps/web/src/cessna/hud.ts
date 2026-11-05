/**
 * What sits over the world. Outside, a row of real round dials along the bottom, a heading tape, the
 * moving map and a line from the instructor. In the cabin the dials are on the panel, so only the
 * words and the marker for the next ring stay over the view.
 */

import { AMBER, FONT, GREEN, Overlay, type ScreenPoint } from "../engine/overlay";
import { AIRFIELD, EXTENT } from "../island/island";
import { AIM_POINT, type Flight, type Touchdown } from "./flight";
import { Instruments, type Readings } from "./instruments";

const CREAM = "#f2ecd8";

export function readings(f: Flight): Readings {
  return {
    kias: f.get("kias"),
    feet: Math.max((f.get("alt_m") - 1.25) * 3.28084, 0),
    fpm: f.get("vs_fpm"),
    pitch: f.get("theta_deg"),
    bank: f.get("phi_deg"),
    heading: f.heading(),
    turn: f.get("turn_dps"),
    slip: f.get("slip"),
    rpm: f.get("rpm"),
  };
}

export function warnings(f: Flight): string[] {
  const found: string[] = [];
  if (f.get("on_ground") < 0.5) {
    if (f.get("stall_flag") > 0.5 || f.get("alpha_deg") > 15.5) {
      found.push("STALL");
    }
    const agl = f.altitudeAboveGround();
    const sink = -f.get("vs_fpm") * 0.00508;
    if (agl < 120 && sink > 7.5) {
      found.push("PULL UP");
    }
  }
  if (f.get("rpm") > 2700) {
    found.push("OVERSPEED");
  }
  return found;
}

export interface HudView {
  cockpit: boolean;
  /** Screen position (0..1) of the next ring, or null when there is none. */
  target: ScreenPoint | null;
  targetRange: number;
  /** Compass bearing to the next ring. */
  bearing: number | null;
  coach: string;
  /** Top of the run: a time, a count. */
  clock: string;
  /** Touchdown card, while it lasts. */
  touchdown: Touchdown | null;
  /** Wind as the pilot would read it. */
  wind: string;
}

const CHART = 1400;

/** The island as a chart: painted once, then the moving map is a window on it. North is up. */
export function bakeChart(heights: Float32Array, size: number): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = CHART;
  const c = canvas.getContext("2d") as CanvasRenderingContext2D;
  const image = c.createImageData(CHART, CHART);
  const tints: [number, [number, number, number]][] = [
    [-70, [10, 40, 58]], [0, [18, 66, 84]], [0.5, [190, 176, 128]], [40, [120, 134, 84]], [300, [92, 104, 72]], [900, [122, 112, 96]], [2500, [226, 222, 214]],
  ];
  for (let y = 0; y < CHART; y += 1) {
    for (let x = 0; x < CHART; x += 1) {
      const row = Math.floor(((CHART - 1 - y) / CHART) * size);
      const column = Math.floor((x / CHART) * size);
      const h = heights[row * size + column];
      let i = 1;
      while (i < tints.length - 1 && h > tints[i][0]) {
        i += 1;
      }
      const [h0, a] = tints[i - 1];
      const [h1, b] = tints[i];
      const t = Math.max(0, Math.min(1, (h - h0) / (h1 - h0)));
      const at = (y * CHART + x) * 4;
      image.data[at] = a[0] + (b[0] - a[0]) * t;
      image.data[at + 1] = a[1] + (b[1] - a[1]) * t;
      image.data[at + 2] = a[2] + (b[2] - a[2]) * t;
      image.data[at + 3] = 255;
    }
  }
  c.putImageData(image, 0, 0);
  return canvas;
}

export class Hud extends Overlay {
  private readonly dials = new Instruments();

  protected override text(s: string, x: number, y: number, size: number, align: CanvasTextAlign = "left", color = CREAM): void {
    super.text(s, x, y, size, align, color);
  }

  private map(f: Flight, ring: { north: number; east: number } | undefined, chart: HTMLCanvasElement): void {
    const c = this.c;
    const size = 158 * this.scale;
    const m = 14 * this.scale;
    const x = this.width - this.roomRight - size - m;
    const y = this.height - size - m;
    const reach = 7000;
    const perMetre = size / (2 * reach);
    const north = f.north();
    const east = f.east();
    c.save();
    c.beginPath();
    c.arc(x + size / 2, y + size / 2, size / 2, 0, Math.PI * 2);
    c.clip();
    c.translate(x + size / 2, y + size / 2);
    c.scale(perMetre, perMetre);
    c.translate(-east, north);
    c.imageSmoothingEnabled = true;
    c.drawImage(chart, -EXTENT / 2, -EXTENT / 2, EXTENT, EXTENT);
    // The runway, always worth finding.
    c.save();
    c.translate(AIRFIELD.east, -AIRFIELD.north);
    c.rotate((AIRFIELD.heading * Math.PI) / 180);
    c.fillStyle = CREAM;
    c.fillRect(-90, -AIRFIELD.length / 2, 180, AIRFIELD.length);
    c.restore();
    if (ring) {
      c.fillStyle = AMBER;
      c.beginPath();
      c.arc(ring.east, -ring.north, 170, 0, Math.PI * 2);
      c.fill();
    }
    c.translate(east, -north);
    c.rotate((f.heading() * Math.PI) / 180);
    c.fillStyle = GREEN;
    c.beginPath();
    c.moveTo(0, -540);
    c.lineTo(340, 420);
    c.lineTo(-340, 420);
    c.fill();
    c.restore();
    c.strokeStyle = "rgba(242,236,216,0.45)";
    c.lineWidth = 1;
    c.beginPath();
    c.arc(x + size / 2, y + size / 2, size / 2, 0, Math.PI * 2);
    c.stroke();
  }

  /** The levers, as a pilot sees them without looking: a thin bar each, by the dials. */
  private levers(f: Flight, x: number, y: number): void {
    const c = this.c;
    const { scale } = this;
    const tall = 92 * scale;
    const items: [string, number, string][] = [
      ["PWR", f.throttle, GREEN],
      ["FLP", f.flaps / 3, CREAM],
      ["TRM", 0.5 + f.trim / 2, CREAM],
    ];
    items.forEach(([name, value, color], i) => {
      const bx = x + i * 30 * scale;
      c.fillStyle = "rgba(7,16,20,0.55)";
      c.fillRect(bx, y - tall / 2, 13 * scale, tall);
      c.fillStyle = color;
      if (name === "TRM") {
        c.fillRect(bx, y + tall / 2 - tall * value - 2 * scale, 13 * scale, 4 * scale);
      } else {
        c.fillRect(bx, y + tall / 2 - tall * value, 13 * scale, tall * value);
      }
      this.text(name, bx + 6.5 * scale, y + tall / 2 + 15 * scale, 10, "center", CREAM);
    });
  }

  private touchdownCard(t: Touchdown): void {
    const c = this.c;
    const { scale, width } = this;
    const w = 300 * scale;
    const h = 68 * scale;
    const x = width / 2 - w / 2;
    const y = 78 * scale;
    c.fillStyle = "rgba(8,14,18,0.62)";
    c.fillRect(x, y, w, h);
    this.text(`${Math.round(t.sink)} FT/MIN`, width / 2, y + 28 * scale, 22, "center", t.sink < 200 ? GREEN : t.sink < 450 ? CREAM : AMBER);
    const point = Math.round(t.along - AIM_POINT);
    this.text(`${point >= 0 ? point + " m long" : -point + " m short"}   ${Math.abs(t.across).toFixed(1)} m off the line`, width / 2, y + 52 * scale, 13, "center", CREAM);
  }

  draw(f: Flight, view: HudView, chart: HTMLCanvasElement, time: number): void {
    const c = this.c;
    const { width, height, scale } = this;
    this.begin();
    const heading = f.heading();
    if (!view.cockpit) {
      const r = Math.round(62 * scale);
      const gap = 16 * scale;
      const y = height - r - 16 * scale;
      const read = readings(f);
      const step = r * 2 + gap;
      const left = width / 2 - step * 1.5;
      // A soft pool of dark, so the dials hold up over a bright runway or a white cloud.
      const shade = c.createLinearGradient(0, height - r * 3.2, 0, height);
      shade.addColorStop(0, "rgba(5,10,14,0)");
      shade.addColorStop(1, "rgba(5,10,14,0.5)");
      c.fillStyle = shade;
      c.fillRect(0, height - r * 3.2, width, r * 3.2);
      this.dials.speed(c, left, y, r, read.kias);
      this.dials.attitude(c, left + step, y, r, read.pitch, read.bank);
      this.dials.altitude(c, left + step * 2, y, r, read.feet);
      this.dials.climb(c, left + step * 3, y, r, read.fpm);
      this.levers(f, left - r - 118 * scale, y - 6 * scale);
      c.strokeStyle = CREAM;
      c.lineWidth = 1.4 * scale;
      this.headingTape(40 * scale, heading, 420 * scale, view.bearing);
    }
    if (view.target) {
      c.lineWidth = 1.8 * scale;
      this.gateMarker(view.target, view.targetRange);
    }
    if (view.clock) {
      this.text(view.clock, this.roomLeft + 22 * scale, 42 * scale, 22, "left", CREAM);
    }
    this.text(view.wind, this.roomLeft + 22 * scale, 66 * scale, 13, "left", CREAM);
    if (view.coach) {
      const c2 = this.c;
      c2.font = `600 ${17 * scale}px ${FONT}`;
      const w = c2.measureText(view.coach).width + 36 * scale;
      const y = view.cockpit ? 60 * scale : 90 * scale;
      c2.fillStyle = "rgba(8,14,18,0.5)";
      c2.fillRect(width / 2 - w / 2, y - 21 * scale, w, 31 * scale);
      this.text(view.coach, width / 2, y, 17, "center", CREAM);
    }
    if (view.touchdown) {
      this.touchdownCard(view.touchdown);
    }
    this.map(f, f.run.next(), chart);
    this.warningList(warnings(f), ["PULL UP", "STALL"], time);
    this.end();
  }
}
