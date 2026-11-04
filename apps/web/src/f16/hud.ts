/**
 * The head-up display, drawn on a 2D canvas over the world. In the cockpit it is the real thing: the
 * pitch ladder and the flight-path marker sit on the view. Outside, the same readouts stay at the
 * screen's edges and the aircraft does the rest of the talking.
 */

import { AMBER, GREEN, Overlay, type ScreenPoint } from "../engine/overlay";
import type { Flight } from "./flight";

const M_TO_FT = 3.28084;
const MPS_TO_KT = 1.94384;

export interface HudView {
  cockpit: boolean;
  /** Vertical field of view in degrees. */
  fov: number;
  /** Screen position (0..1) of the next gate, or null when it is behind the view. */
  gateOnScreen: ScreenPoint | null;
  /** Screen position (0..1) the aircraft is flying towards, outside the cockpit. */
  velocityOnScreen: ScreenPoint | null;
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

export class Hud extends Overlay {
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

  draw(f: Flight, view: HudView, outline: Path2D, time: number): void {
    const c = this.c;
    const { width, height, scale } = this;
    this.begin();

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
    const gate = f.run.next();
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
      this.gateMarker(view.gateOnScreen, distance);
    }
    if (f.run.active) {
      this.gateClock(f.run.time, f.run.gates.filter((g) => g.passed).length, f.run.gates.length, f.run.missed());
    }
    this.minimap(f.north(), f.east(), f.get("psi_deg"), gate, outline, 96000);
    this.warningList(warnings(f), ["PULL UP", "DEPARTED"], time);
    this.end();
  }
}
