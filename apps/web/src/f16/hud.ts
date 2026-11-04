/**
 * The head-up display, drawn on a 2D canvas over the world. In the cockpit it is the real thing: the
 * pitch ladder and the flight-path marker sit on the view. Outside, the same readouts stay at the
 * screen's edges and the aircraft does the rest of the talking.
 */

import type { Flight } from "./flight";

const GREEN = "#7dffb0";
const AMBER = "#ffc34d";
const RED = "#ff5a4d";
const FONT = 'ui-monospace, "Cascadia Mono", "SF Mono", Consolas, monospace';

const M_TO_FT = 3.28084;
const MPS_TO_KT = 1.94384;

export interface HudView {
  cockpit: boolean;
  /** Vertical field of view in degrees. */
  fov: number;
  /** Screen position (0..1) of the next gate, or null when it is behind the view. */
  gateOnScreen: { x: number; y: number; ahead: boolean } | null;
  /** Screen position (0..1) the aircraft is flying towards, outside the cockpit. */
  velocityOnScreen: { x: number; y: number; ahead: boolean } | null;
}

export function warnings(f: Flight): string[] {
  const found: string[] = [];
  if (f.get("departed") > 0.5) {
    found.push("DEPARTED");
  }
  const agl = f.altitudeAboveGround();
  const sink = -f.get("vs_mps");
  if (agl < 600 && sink > 1 && agl / sink < 8) {
    found.push("PULL UP");
  }
  if (f.get("alpha_deg") > 22 || f.get("cas_mps") * MPS_TO_KT < 130) {
    found.push("STALL");
  }
  if (f.get("limiter_active") > 0.5) {
    found.push(f.get("alpha_deg") > 20 ? "ALPHA LIMIT" : "G LIMIT");
  }
  return found;
}

export class Hud {
  private readonly c: CanvasRenderingContext2D;
  private width = 1;
  private height = 1;
  private scale = 1;

  constructor(private readonly canvas: HTMLCanvasElement) {
    this.c = canvas.getContext("2d") as CanvasRenderingContext2D;
  }

  resize(width: number, height: number, ratio: number): void {
    this.canvas.width = Math.round(width * ratio);
    this.canvas.height = Math.round(height * ratio);
    this.c.setTransform(ratio, 0, 0, ratio, 0, 0);
    this.width = width;
    this.height = height;
    this.scale = Math.max(0.75, Math.min(width / 1280, height / 720));
  }

  clear(): void {
    this.c.clearRect(0, 0, this.width, this.height);
  }

  private text(s: string, x: number, y: number, size: number, align: CanvasTextAlign = "left", color = GREEN): void {
    const c = this.c;
    c.font = `600 ${size * this.scale}px ${FONT}`;
    c.textAlign = align;
    c.fillStyle = color;
    c.fillText(s, x, y);
  }

  private line(x0: number, y0: number, x1: number, y1: number): void {
    this.c.beginPath();
    this.c.moveTo(x0, y0);
    this.c.lineTo(x1, y1);
    this.c.stroke();
  }

  private box(s: string, x: number, y: number, align: CanvasTextAlign): void {
    const c = this.c;
    const w = 86 * this.scale;
    const h = 28 * this.scale;
    const left = align === "right" ? x - w : x;
    c.fillStyle = "rgba(4,16,12,0.5)";
    c.fillRect(left, y - h / 2, w, h);
    c.strokeRect(left, y - h / 2, w, h);
    this.text(s, left + w / 2, y + 7 * this.scale, 20, "center");
  }

  /** A tape of values: `value` at the centre, a tick each `step`, labelled each `label`. */
  private tape(x: number, y: number, tall: number, value: number, step: number, label: number, side: 1 | -1, format: (v: number) => string): void {
    const c = this.c;
    const span = tall / 2;
    const perUnit = (tall / 8) / step;
    c.save();
    c.beginPath();
    c.rect(x - 90 * this.scale, y - span, 180 * this.scale, tall);
    c.clip();
    const first = Math.ceil((value - span / perUnit) / step) * step;
    for (let v = first; v <= value + span / perUnit; v += step) {
      const py = y - (v - value) * perUnit;
      const major = Math.abs(v / label - Math.round(v / label)) < 1e-6;
      this.line(x, py, x + side * (major ? 12 : 6) * this.scale, py);
      if (major && Math.abs(py - y) > 18 * this.scale) {
        this.text(format(v), x + side * 18 * this.scale, py + 5 * this.scale, 13, side > 0 ? "left" : "right");
      }
    }
    c.restore();
  }

  private headingTape(y: number, heading: number, wide: number, gateBearing: number | null): void {
    const c = this.c;
    const cx = this.width / 2;
    const perDeg = wide / 60;
    c.save();
    c.beginPath();
    c.rect(cx - wide / 2, y - 26 * this.scale, wide, 50 * this.scale);
    c.clip();
    for (let d = Math.ceil((heading - 30) / 5) * 5; d <= heading + 30; d += 5) {
      const x = cx + (d - heading) * perDeg;
      const major = d % 10 === 0;
      this.line(x, y, x, y + (major ? 10 : 5) * this.scale);
      if (major) {
        const value = ((d % 360) + 360) % 360;
        const name = { 0: "N", 90: "E", 180: "S", 270: "W" }[value] ?? String(value / 10).padStart(2, "0");
        this.text(name, x, y - 5 * this.scale, 13, "center");
      }
    }
    c.restore();
    this.line(cx, y + 13 * this.scale, cx - 6 * this.scale, y + 21 * this.scale);
    this.line(cx, y + 13 * this.scale, cx + 6 * this.scale, y + 21 * this.scale);
    if (gateBearing !== null) {
      const off = ((gateBearing - heading + 540) % 360) - 180;
      const x = cx + Math.max(-30, Math.min(30, off)) * perDeg;
      c.fillStyle = AMBER;
      c.beginPath();
      c.moveTo(x, y + 12 * this.scale);
      c.lineTo(x - 6 * this.scale, y + 24 * this.scale);
      c.lineTo(x + 6 * this.scale, y + 24 * this.scale);
      c.fill();
    }
  }

  /** The conformal part, centred on the boresight. */
  private ladder(f: Flight, view: HudView): void {
    const c = this.c;
    const cx = this.width / 2;
    const cy = this.height * 0.5;
    const perDeg = this.height / 2 / Math.tan((view.fov * Math.PI) / 360) * (Math.PI / 180);
    const theta = f.get("theta_deg");
    const roll = (f.get("phi_deg") * Math.PI) / 180;
    c.save();
    c.beginPath();
    c.rect(cx - 260 * this.scale, cy - 240 * this.scale, 520 * this.scale, 460 * this.scale);
    c.clip();
    c.translate(cx, cy);
    c.rotate(-roll);
    for (let p = -90; p <= 90; p += 5) {
      const y = (theta - p) * perDeg;
      if (Math.abs(y) > 520 * this.scale) {
        continue;
      }
      if (p === 0) {
        this.line(-240 * this.scale, y, -34 * this.scale, y);
        this.line(34 * this.scale, y, 240 * this.scale, y);
        continue;
      }
      const inner = 34 * this.scale;
      const outer = 96 * this.scale;
      const tip = (p > 0 ? 8 : -8) * this.scale;
      c.setLineDash(p < 0 ? [8 * this.scale, 6 * this.scale] : []);
      for (const side of [-1, 1]) {
        this.line(side * inner, y, side * outer, y);
        this.line(side * outer, y, side * outer, y + tip);
      }
      c.setLineDash([]);
      const label = String(Math.abs(p));
      this.text(label, -(outer + 8 * this.scale), y + 5 * this.scale, 13, "right");
      this.text(label, outer + 8 * this.scale, y + 5 * this.scale, 13, "left");
    }
    c.restore();
    // Waterline: where the nose points.
    const w = 20 * this.scale;
    this.line(cx - 2 * w, cy, cx - w, cy);
    this.line(cx - w, cy, cx - w / 2, cy + w / 2);
    this.line(cx - w / 2, cy + w / 2, cx, cy);
    this.line(cx, cy, cx + w / 2, cy + w / 2);
    this.line(cx + w / 2, cy + w / 2, cx + w, cy);
    this.line(cx + w, cy, cx + 2 * w, cy);
    this.flightPath(cx + f.get("beta_deg") * perDeg, cy + f.get("alpha_deg") * perDeg);
  }

  private flightPath(x: number, y: number): void {
    const c = this.c;
    const r = 8 * this.scale;
    c.beginPath();
    c.arc(x, y, r, 0, Math.PI * 2);
    c.stroke();
    this.line(x - r, y, x - 2.6 * r, y);
    this.line(x + r, y, x + 2.6 * r, y);
    this.line(x, y - r, x, y - 2 * r);
  }

  private gateMarker(view: HudView, distance: number): void {
    const g = view.gateOnScreen;
    if (!g) {
      return;
    }
    const c = this.c;
    const x = g.x * this.width;
    const y = g.y * this.height;
    const edge = 60 * this.scale;
    const inside = g.ahead && x > edge && x < this.width - edge && y > edge && y < this.height - edge;
    c.strokeStyle = AMBER;
    if (inside) {
      const r = 14 * this.scale;
      c.strokeRect(x - r, y - r, 2 * r, 2 * r);
      this.text(`${(distance / 1000).toFixed(1)} km`, x, y + r + 16 * this.scale, 13, "center", AMBER);
      return;
    }
    // Off the view: an arrow on a ring round the centre, pointing the way to turn.
    const cx = this.width / 2;
    const cy = this.height / 2;
    const dx = (x - cx) * (g.ahead ? 1 : -1);
    const dy = (y - cy) * (g.ahead ? 1 : -1);
    const a = Math.atan2(dy, dx);
    const radius = Math.min(this.width, this.height) * 0.38;
    const ax = cx + Math.cos(a) * radius;
    const ay = cy + Math.sin(a) * radius;
    c.save();
    c.translate(ax, ay);
    c.rotate(a);
    c.fillStyle = AMBER;
    c.beginPath();
    c.moveTo(18 * this.scale, 0);
    c.lineTo(-10 * this.scale, -11 * this.scale);
    c.lineTo(-4 * this.scale, 0);
    c.lineTo(-10 * this.scale, 11 * this.scale);
    c.fill();
    c.restore();
    this.text(`${(distance / 1000).toFixed(1)} km`, ax, ay + 30 * this.scale, 13, "center", AMBER);
  }

  private minimap(f: Flight, outline: Path2D): void {
    const c = this.c;
    const size = 132 * this.scale;
    const m = 16 * this.scale;
    const x = this.width - size - m;
    const y = this.height - size - m;
    const perMetre = size / 96000;
    c.save();
    c.beginPath();
    c.arc(x + size / 2, y + size / 2, size / 2, 0, Math.PI * 2);
    c.fillStyle = "rgba(4,16,12,0.45)";
    c.fill();
    c.clip();
    c.translate(x + size / 2, y + size / 2);
    c.scale(perMetre, perMetre);
    c.fillStyle = "rgba(125,255,176,0.22)";
    c.fill(outline);
    c.fillStyle = AMBER;
    const dot = 900;
    const next = f.nextGate();
    if (next) {
      c.beginPath();
      c.arc(next.east, -next.north, dot, 0, Math.PI * 2);
      c.fill();
    }
    c.translate(f.east(), -f.north());
    c.rotate((f.get("psi_deg") * Math.PI) / 180);
    c.fillStyle = GREEN;
    c.beginPath();
    c.moveTo(0, -2400);
    c.lineTo(1500, 1800);
    c.lineTo(-1500, 1800);
    c.fill();
    c.restore();
  }

  draw(f: Flight, view: HudView, outline: Path2D, time: number): void {
    const c = this.c;
    const { width, height, scale } = this;
    this.clear();
    c.lineWidth = 1.6 * scale;
    c.strokeStyle = GREEN;
    c.shadowColor = "rgba(0,0,0,0.55)";
    c.shadowBlur = 3 * scale;
    c.lineJoin = "round";

    const cx = width / 2;
    const wide = 420 * scale;
    const tall = 300 * scale;
    const left = view.cockpit ? cx - 290 * scale : 150 * scale;
    const right = view.cockpit ? cx + 290 * scale : width - 150 * scale;
    const middle = height * 0.5;

    if (view.cockpit) {
      this.ladder(f, view);
    } else if (view.velocityOnScreen?.ahead) {
      c.globalAlpha = 0.85;
      this.flightPath(view.velocityOnScreen.x * width, view.velocityOnScreen.y * height);
      c.globalAlpha = 1;
    }
    const heading = ((f.get("psi_deg") % 360) + 360) % 360;
    const gate = f.nextGate();
    let bearing: number | null = null;
    let distance = 0;
    if (gate) {
      const dn = gate.north - f.north();
      const de = gate.east - f.east();
      bearing = (Math.atan2(de, dn) * 180) / Math.PI;
      distance = Math.hypot(dn, de, gate.alt - f.get("alt_m"));
    }
    this.headingTape(view.cockpit ? middle - 250 * scale : 44 * scale, heading, wide, bearing);

    const speed = f.get("cas_mps") * MPS_TO_KT;
    const altitude = f.get("alt_m") * M_TO_FT;
    this.tape(left, middle, tall, speed, 10, 50, -1, (v) => String(Math.round(v)));
    this.tape(right, middle, tall, altitude, 100, 500, 1, (v) => (v / 1000).toFixed(1));
    this.box(String(Math.round(speed)), left + 4 * scale, middle, "right");
    this.box(String(Math.round(altitude / 10) * 10), right - 4 * scale, middle, "left");
    this.text("KCAS", left - 44 * scale, middle - tall / 2 - 12 * scale, 12, "center");
    this.text("FT", right + 44 * scale, middle - tall / 2 - 12 * scale, 12, "center");

    const vs = Math.round((f.get("vs_mps") * M_TO_FT * 60) / 50) * 50;
    this.text(`${vs > 0 ? "+" : ""}${vs}`, right + 44 * scale, middle + tall / 2 + 24 * scale, 14, "center");
    this.text(`M ${f.get("mach").toFixed(2)}`, left - 44 * scale, middle + tall / 2 + 24 * scale, 14, "center");
    const nz = f.get("nz_g");
    this.text(`${nz.toFixed(1)} G`, left - 44 * scale, middle + tall / 2 + 44 * scale, 14, "center", Math.abs(nz) > 7.5 ? AMBER : GREEN);
    this.text(`AOA ${f.get("alpha_deg").toFixed(0)}`, left - 44 * scale, middle + tall / 2 + 64 * scale, 14, "center");
    const agl = f.altitudeAboveGround() * M_TO_FT;
    if (agl < 2500) {
      this.text(`R ${Math.round(agl / 10) * 10}`, right + 44 * scale, middle + tall / 2 + 44 * scale, 14, "center");
    }

    // The throttle: a bar with a mark at full dry thrust, afterburner beyond it.
    const throttle = f.u[3];
    const bar = 150 * scale;
    const bx = 22 * scale;
    const by = height - 28 * scale;
    c.fillStyle = "rgba(4,16,12,0.5)";
    c.fillRect(bx, by - bar, 12 * scale, bar);
    c.fillStyle = throttle > 0.77 ? AMBER : GREEN;
    c.fillRect(bx, by - bar * throttle, 12 * scale, bar * throttle);
    c.strokeRect(bx, by - bar, 12 * scale, bar);
    this.line(bx - 4 * scale, by - bar * 0.77, bx + 16 * scale, by - bar * 0.77);
    const power = f.get("power_pct");
    this.text(power > 50 ? "AB" : "MIL", bx + 22 * scale, by - bar * 0.77 + 5 * scale, 12, "left", power > 50 ? AMBER : GREEN);
    this.text(`${Math.round(power)}%`, bx + 22 * scale, by, 14);

    if (gate) {
      this.gateMarker(view, distance);
    }
    if (f.gates.length > 0) {
      const passed = f.gates.filter((g) => g.passed).length;
      const missed = f.gates.filter((g) => g.passed && !g.hit).length;
      const time2 = f.gateTime;
      const m = Math.floor(time2 / 60);
      const s = (time2 % 60).toFixed(1).padStart(4, "0");
      this.text(`${m}:${s}`, cx, height - 54 * scale, 26, "center", GREEN);
      this.text(`GATE ${Math.min(passed + 1, f.gates.length)}/${f.gates.length}${missed ? `   ${missed} MISSED` : ""}`, cx, height - 30 * scale, 14, "center", missed ? AMBER : GREEN);
    }
    this.minimap(f, outline);

    const active = warnings(f);
    if (active.length > 0 && Math.floor(time * 4) % 2 === 0) {
      active.forEach((message, i) => {
        const red = message === "PULL UP" || message === "DEPARTED";
        this.text(message, cx, height * 0.27 + i * 34 * scale, 28, "center", red ? RED : AMBER);
      });
    }
    c.shadowBlur = 0;
  }
}

/** The outline of the land for the map, from the same grid as the terrain. */
export function coastOutline(heights: Float32Array, size: number, extent: number): Path2D {
  const outline = new Path2D();
  const cells = 128;
  const step = Math.floor(size / cells);
  const cell = (extent / (size - 1)) * step;
  for (let row = 0; row * step < size; row += 1) {
    for (let column = 0; column * step < size; column += 1) {
      if (heights[row * step * size + column * step] > 0) {
        outline.rect(-extent / 2 + column * cell, extent / 2 - row * cell - cell, cell, cell);
      }
    }
  }
  return outline;
}
