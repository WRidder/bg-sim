/**
 * The head-up display, drawn on a 2D canvas over the world. In the cockpit it is the real thing: the
 * pitch ladder and the flight-path marker sit on the view. Outside, the same readouts stay at the
 * screen's edges and the aircraft does the rest of the talking.
 */

import { AMBER, GREEN, Overlay, RED, type ScreenPoint } from "../engine/overlay";
import type { Flight } from "./flight";
import type { Contact, LockState } from "./targets";
import type { SeekerMark } from "./seeker";

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
  /** The locked/selected target, if any, and its seeker state. */
  targetOnScreen: ScreenPoint | null;
  targetRange: number;
  lock: LockState | null;
  contacts: readonly Contact[];
  /** The seeker picture-in-picture is showing at the bottom. */
  seeker: boolean;
  /** The missile's target projected into that picture-in-picture. */
  seekerMark: SeekerMark | null;
  /** Seconds left before the wingtips reload, or null. */
  reload: number | null;
}

export function warnings(f: Flight): string[] {
  const found: string[] = [];
  if (f.get("departed") > 0.5) {
    found.push("DEPARTED");
  }
  if (f.onGround) {
    return found;
  }
  const agl = f.altitudeAboveGround();
  const sink = -f.get("vs_mps");
  // With the gear down the ground is where the pilot means to go, and only a dive is a warning.
  if (agl < 600 && sink > (f.gearDown ? 7 : 1) && agl / sink < 8) {
    found.push("PULL UP");
  }
  const cas = f.get("cas_mps") * MPS_TO_KT;
  if (f.get("alpha_deg") > 22 || cas < (f.gearDown ? 115 : 130)) {
    found.push("STALL");
  }
  if (!f.gearDown && agl < 150 && sink > 1 && cas < 200) {
    found.push("GEAR UP");
  }
  if (f.get("limiter_active") > 0.5) {
    found.push(f.get("alpha_deg") > 20 ? "ALPHA LIMIT" : "G LIMIT");
  }
  return found;
}

export class Hud extends Overlay {
  /** A target box, or an edge arrow when it is outside the view. */
  private targetMarker(g: ScreenPoint, range: number, lock: LockState | null): void {
    const c = this.c;
    const x = g.x * this.width;
    const y = g.y * this.height;
    const edge = 60 * this.scale;
    const inside = g.ahead && x > edge && x < this.width - edge && y > edge && y < this.height - edge;
    const color = lock?.locked ? GREEN : AMBER;
    c.strokeStyle = color;
    if (inside) {
      const r = 16 * this.scale;
      c.strokeRect(x - r, y - r, 2 * r, 2 * r);
      if (lock?.locked) {
        c.beginPath();
        c.arc(x, y, 23 * this.scale, 0, Math.PI * 2);
        c.stroke();
      }
      this.text(`${(range / 1000).toFixed(1)} km`, x, y + r + 17 * this.scale, 13, "center", color);
      return;
    }
    const cx = this.width / 2;
    const cy = this.height / 2;
    const dx = (x - cx) * (g.ahead ? 1 : -1);
    const dy = (y - cy) * (g.ahead ? 1 : -1);
    const angle = Math.atan2(dy, dx);
    const radius = Math.min(this.width, this.height) * 0.39;
    const ax = cx + Math.cos(angle) * radius;
    const ay = cy + Math.sin(angle) * radius;
    c.save();
    c.translate(ax, ay);
    c.rotate(angle);
    c.fillStyle = color;
    c.beginPath();
    c.moveTo(17 * this.scale, 0);
    c.lineTo(-9 * this.scale, -10 * this.scale);
    c.lineTo(-3 * this.scale, 0);
    c.lineTo(-9 * this.scale, 10 * this.scale);
    c.fill();
    c.restore();
    this.text(`${(range / 1000).toFixed(1)} km`, ax, ay + 30 * this.scale, 13, "center", color);
  }

  /** The seeker state, above the gate clock. */
  private lockText(lock: LockState | null, seeker: boolean): void {
    if (!lock) {
      return;
    }
    if (lock.selectedId === null) {
      this.text("NO TARGET", this.width / 2, this.height - (seeker ? 196 : 82) * this.scale, 16, "center", AMBER);
      return;
    }
    const colour = lock.locked ? GREEN : lock.inFov ? AMBER : RED;
    const message = lock.locked
      ? `LOCK  ${(lock.rangeM / 1000).toFixed(1)} km   M: FOX 2`
      : lock.inFov
        ? `SEEKER  ${Math.round(lock.progress * 100)}%   ${(lock.rangeM / 1000).toFixed(1)} km`
        : `${lock.reason}   ${Math.round(lock.angleDeg)} deg`;
    this.text(message, this.width / 2, this.height - (seeker ? 196 : 82) * this.scale, 16, "center", colour);
  }

  /** A 12 km tactical scope above the throttle: own ship in green, drones red, lock green. */
  private tactical(north: number, east: number, heading: number, contacts: readonly Contact[]): void {
    if (contacts.length === 0) {
      return;
    }
    const c = this.c;
    const size = 118 * this.scale;
    const margin = 16 * this.scale;
    const x0 = this.roomLeft + margin;
    const y0 = margin;
    const cx = x0 + size / 2;
    const cy = y0 + size / 2;
    const range = 12000;
    const perMetre = size / 2 / range;
    c.save();
    c.beginPath();
    c.arc(cx, cy, size / 2, 0, Math.PI * 2);
    c.fillStyle = "rgba(4,16,12,0.55)";
    c.fill();
    c.clip();
    c.strokeStyle = "rgba(125,255,176,0.35)";
    for (const r of [4, 8, 12]) {
      c.beginPath();
      c.arc(cx, cy, r * 1000 * perMetre, 0, Math.PI * 2);
      c.stroke();
    }
    this.line(cx - size / 2, cy, cx + size / 2, cy);
    this.line(cx, cy - size / 2, cx, cy + size / 2);
    for (const contact of contacts) {
      let dx = (contact.east - east) * perMetre;
      let dy = -(contact.north - north) * perMetre;
      const distance = Math.hypot(dx, dy);
      const edge = size / 2 - 5 * this.scale;
      if (distance > edge) {
        dx = (dx / distance) * edge;
        dy = (dy / distance) * edge;
      }
      const px = cx + dx;
      const py = cy + dy;
      const colour = contact.locked ? GREEN : contact.selected ? AMBER : RED;
      c.fillStyle = colour;
      c.strokeStyle = colour;
      c.beginPath();
      c.moveTo(px, py - 4 * this.scale);
      c.lineTo(px + 4 * this.scale, py);
      c.lineTo(px, py + 4 * this.scale);
      c.lineTo(px - 4 * this.scale, py);
      c.closePath();
      c.fill();
      if (contact.selected) {
        c.beginPath();
        c.arc(px, py, 7 * this.scale, 0, Math.PI * 2);
        c.stroke();
      }
      if (contact.locked) {
        c.beginPath();
        c.arc(px, py, 10 * this.scale, 0, Math.PI * 2);
        c.stroke();
      }
    }
    // Own ship: a triangle pointing along the heading.
    const radians = (heading * Math.PI) / 180;
    const fx = Math.sin(radians);
    const fy = -Math.cos(radians);
    const rx = Math.cos(radians);
    const ry = Math.sin(radians);
    c.fillStyle = GREEN;
    c.beginPath();
    c.moveTo(cx + fx * 8 * this.scale, cy + fy * 8 * this.scale);
    c.lineTo(cx - fx * 4 * this.scale + rx * 4 * this.scale, cy - fy * 4 * this.scale + ry * 4 * this.scale);
    c.lineTo(cx - fx * 4 * this.scale - rx * 4 * this.scale, cy - fy * 4 * this.scale - ry * 4 * this.scale);
    c.closePath();
    c.fill();
    c.restore();
    this.text(`DRONES ${contacts.length}`, x0, y0 - 4 * this.scale, 12, "left");
    this.text("12 km", x0 + size, y0 + size + 16 * this.scale, 11, "right");
  }

  private reloadText(left: number | null): void {
    if (left === null) {
      return;
    }
    this.text(`RELOADING  ${left.toFixed(1)} s`, this.width / 2, this.height - 224 * this.scale, 14, "center", AMBER);
  }

  /** The target box inside the seeker picture-in-picture, so the plane's future path is visible. */
  private seekerTarget(mark: SeekerMark | null): void {
    if (!mark || !mark.visible) {
      return;
    }
    const c = this.c;
    const r = 16 * this.scale;
    c.strokeStyle = AMBER;
    c.lineWidth = 1.5 * this.scale;
    c.strokeRect(mark.x - r, mark.y - r, 2 * r, 2 * r);
    c.beginPath();
    c.arc(mark.x, mark.y, r + 6 * this.scale, 0, Math.PI * 2);
    c.stroke();
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

  draw(f: Flight, view: HudView, outline: Path2D, time: number): void {
    const c = this.c;
    const { width, height, scale } = this;
    this.begin();

    const cx = width / 2;
    const wide = 420 * scale;
    const tall = 300 * scale;
    const left = view.cockpit ? cx - 290 * scale : this.roomLeft + 150 * scale;
    const right = view.cockpit ? cx + 290 * scale : width - this.roomRight - 150 * scale;
    const middle = height * 0.5;

    if (view.cockpit) {
      this.ladder(f, view);
    } else if (view.velocityOnScreen?.ahead) {
      c.globalAlpha = 0.85;
      this.flightPath(view.velocityOnScreen.x * width, view.velocityOnScreen.y * height);
      c.globalAlpha = 1;
    }
    const heading = f.heading();
    const gate = f.run.next();
    let bearing: number | null = null;
    let distance = 0;
    if (gate) {
      const dn = gate.north - f.north();
      const de = gate.east - f.east();
      bearing = (Math.atan2(de, dn) * 180) / Math.PI;
      distance = Math.hypot(dn, de, gate.alt - f.altitude());
    }
    this.headingTape(view.cockpit ? middle - 250 * scale : 44 * scale, heading, wide, bearing);

    const speed = f.get("cas_mps") * MPS_TO_KT;
    const altitude = f.altitude() * M_TO_FT;
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
    const bx = this.roomLeft + 22 * scale;
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

    // The gear, in green when it is down and locked, and the brakes while they are held.
    const gear = f.get("gear_pos");
    if (gear > 0.001 || f.gearDown) {
      this.text(gear > 0.999 ? "GEAR DOWN" : "GEAR", bx, by - bar - 30 * scale, 12, "left", gear > 0.999 ? GREEN : AMBER);
    }
    if (f.braking) {
      this.text("BRAKES", bx, by - bar - 48 * scale, 12, "left", AMBER);
    }

    if (gate) {
      this.gateMarker(view.gateOnScreen, distance);
    }
    if (view.targetOnScreen) {
      this.targetMarker(view.targetOnScreen, view.targetRange, view.lock);
    }
    this.lockText(view.lock, view.seeker);
    this.reloadText(view.reload);
    this.tactical(f.north(), f.east(), f.heading(), view.contacts);
    this.seekerTarget(view.seekerMark);
    if (f.run.active) {
      this.gateClock(f.run.time, f.run.gates.filter((g) => g.passed).length, f.run.gates.length, f.run.missed());
    }
    this.minimap(f.north(), f.east(), f.heading(), gate, outline, 96000);
    this.warningList(warnings(f), ["PULL UP", "DEPARTED", "GEAR UP"], time);
    this.end();
  }
}
