/**
 * The display over the world. A helicopter's questions are not a fighter's: how fast am I drifting,
 * how high are the wheels, how fast am I sinking. So the middle of the screen stays clear, and close
 * to a pad a plan view comes up with the H, the drift and the sink.
 */

import { AMBER, GREEN, Overlay, RED, type ScreenPoint } from "../engine/overlay";
import { clock } from "../engine/ui";
import { type Flight, POWER_LIMIT } from "./flight";
import { HOLD, type Run } from "./mission";
import type { Pad } from "./pads";
import { bodySpeeds } from "./pilot";

const MPS_TO_KT = 1.94384;

export interface HudView {
  cockpit: boolean;
  aid: string;
  padOnScreen: ScreenPoint | null;
  velocityOnScreen: ScreenPoint | null;
}

export function warnings(f: Flight): string[] {
  const found: string[] = [];
  const nr = f.get("rotor_pct");
  if (nr < 95) {
    found.push("LOW ROTOR");
  } else if (nr > 106) {
    found.push("HIGH ROTOR");
  }
  if (f.get("power_hp") > POWER_LIMIT - 5) {
    found.push("TORQUE LIMIT");
  }
  if (f.get("kts") > 168) {
    found.push("VNE");
  }
  const radar = f.radar();
  const sink = -f.get("vs_mps");
  if (radar > 0.5 && sink > 1 && radar / sink < 6 && sink > 2.2) {
    found.push("SINK RATE");
  }
  if (f.onGround && Math.abs(f.get("phi_deg")) > 8) {
    found.push("BANK ON THE GROUND");
  }
  return found;
}

export class Hud extends Overlay {
  /** The last word on a landing, fading out. */
  private banner = "";
  private subline = "";
  private bannerAt = -100;
  private bannerColor = GREEN;

  say(title: string, line: string, time: number, color = GREEN): void {
    this.banner = title;
    this.subline = line;
    this.bannerAt = time;
    this.bannerColor = color;
  }

  /** A readout at the edge: the label small, the value large. */
  private readout(label: string, value: string, x: number, y: number, align: CanvasTextAlign, color = GREEN): void {
    this.text(label, x, y - 24 * this.scale, 12, align, "rgba(125,255,176,0.7)");
    this.text(value, x, y, 26, align, color);
  }

  private bar(x: number, y: number, tall: number, fraction: number, color: string, mark: number): void {
    const c = this.c;
    const w = 12 * this.scale;
    c.fillStyle = "rgba(4,16,12,0.5)";
    c.fillRect(x, y - tall, w, tall);
    c.fillStyle = color;
    const f = Math.max(0, Math.min(1, fraction));
    c.fillRect(x, y - tall * f, w, tall * f);
    c.strokeRect(x, y - tall, w, tall);
    this.line(x - 4 * this.scale, y - tall * mark, x + w + 4 * this.scale, y - tall * mark);
  }

  /** The plan view: the H and the drift, nose up, a few rotor spans across. */
  private planView(f: Flight, pad: Pad, run: Run): void {
    const c = this.c;
    const { scale, height, width } = this;
    const size = 92 * scale;
    const cx = width / 2;
    const cy = height - 196 * scale;
    const radar = f.radar();
    const psi = (f.get("psi_deg") * Math.PI) / 180;
    const dn = pad.north - f.north();
    const de = pad.east - f.east();
    const ahead = dn * Math.cos(psi) + de * Math.sin(psi);
    const right = -dn * Math.sin(psi) + de * Math.cos(psi);
    const reach = 40;
    const perMetre = size / reach;
    c.save();
    c.beginPath();
    c.arc(cx, cy, size, 0, Math.PI * 2);
    c.fillStyle = "rgba(4,16,12,0.5)";
    c.fill();
    c.stroke();
    c.clip();
    const px = cx + right * perMetre;
    const py = cy - ahead * perMetre;
    c.strokeStyle = AMBER;
    c.beginPath();
    c.arc(px, py, pad.radius * perMetre, 0, Math.PI * 2);
    c.stroke();
    this.text("H", px, py + 7 * scale, 20, "center", AMBER);
    c.strokeStyle = GREEN;
    c.restore();
    // The helicopter in the middle, with the way it is going.
    const [along, across] = bodySpeeds(f);
    c.strokeStyle = GREEN;
    this.line(cx - 12 * scale, cy, cx + 12 * scale, cy);
    this.line(cx, cy - 12 * scale, cx, cy + 16 * scale);
    const slow = Math.hypot(along, across) < 0.5;
    c.strokeStyle = slow ? GREEN : "#58d8ff";
    c.lineWidth = 3 * scale;
    this.line(cx, cy, cx + across * perMetre * 3, cy - along * perMetre * 3);
    c.lineWidth = 1.6 * scale;
    c.strokeStyle = GREEN;
    const sink = -f.get("vs_mps");
    const sinkColor = sink > 2 ? RED : sink > 1 ? AMBER : GREEN;
    this.text(`${Math.max(radar, 0).toFixed(1)} M`, cx - size - 12 * scale, cy + 6 * scale, 22, "right");
    this.text(`${sink >= 0 ? "SINK" : "RISE"} ${Math.abs(sink).toFixed(1)}`, cx + size + 12 * scale, cy + 6 * scale, 22, "left", sinkColor);
    if (run.holding > 0) {
      c.strokeStyle = GREEN;
      c.lineWidth = 5 * scale;
      c.beginPath();
      c.arc(cx, cy, size + 7 * scale, -Math.PI / 2, -Math.PI / 2 + (run.holding / HOLD) * Math.PI * 2);
      c.stroke();
      c.lineWidth = 1.6 * scale;
    }
  }

  private mapView(f: Flight, pads: readonly Pad[], next: Pad | undefined, outline: Path2D): void {
    const c = this.c;
    const { scale, width, height } = this;
    const size = 150 * scale;
    const m = 16 * scale;
    const cx = width - m - size / 2;
    const cy = height - m - size / 2;
    const span = 24000;
    const perMetre = size / span;
    const centreN = -9800;
    const centreE = 7400;
    c.save();
    c.beginPath();
    c.arc(cx, cy, size / 2, 0, Math.PI * 2);
    c.fillStyle = "rgba(4,16,12,0.5)";
    c.fill();
    c.stroke();
    c.clip();
    c.save();
    c.translate(cx, cy);
    c.scale(perMetre, perMetre);
    c.translate(-centreE, centreN);
    c.fillStyle = "rgba(125,255,176,0.2)";
    c.fill(outline);
    c.restore();
    const at = (north: number, east: number): [number, number] => [cx + (east - centreE) * perMetre, cy - (north - centreN) * perMetre];
    for (const pad of pads) {
      const [x, y] = at(pad.north, pad.east);
      c.fillStyle = pad === next ? AMBER : "rgba(255,255,255,0.55)";
      c.beginPath();
      c.arc(x, y, (pad === next ? 5 : 3) * scale, 0, Math.PI * 2);
      c.fill();
    }
    const [x, y] = at(f.north(), f.east());
    c.translate(x, y);
    c.rotate((f.get("psi_deg") * Math.PI) / 180);
    c.fillStyle = GREEN;
    c.beginPath();
    c.moveTo(0, -8 * scale);
    c.lineTo(5 * scale, 6 * scale);
    c.lineTo(-5 * scale, 6 * scale);
    c.fill();
    c.restore();
  }

  draw(f: Flight, view: HudView, run: Run, pads: readonly Pad[], outline: Path2D, time: number): void {
    const c = this.c;
    const { width, height, scale } = this;
    this.begin();
    const pad = run.next;
    let bearing: number | null = null;
    let distance = 0;
    if (pad) {
      const dn = pad.north - f.north();
      const de = pad.east - f.east();
      bearing = (Math.atan2(de, dn) * 180) / Math.PI;
      distance = Math.hypot(dn, de);
    }
    const heading = ((f.get("psi_deg") % 360) + 360) % 360;
    this.headingTape(40 * scale, heading, 380 * scale, bearing);
    if (!view.cockpit && view.velocityOnScreen?.ahead && f.get("kts") > 20) {
      c.globalAlpha = 0.8;
      this.flightPath(view.velocityOnScreen.x * width, view.velocityOnScreen.y * height);
      c.globalAlpha = 1;
    }
    if (pad) {
      this.gateMarker(view.padOnScreen, distance);
    }
    if (!view.cockpit) {
      const left = 30 * scale;
      const right = width - 30 * scale;
      const middle = height * 0.5;
      const radar = Math.max(f.radar(), 0);
      this.readout("KNOTS", String(Math.round(f.get("kts"))), left, middle - 30 * scale, "left");
      this.readout("GROUND KT", (f.groundSpeed() * MPS_TO_KT).toFixed(0), left, middle + 34 * scale, "left");
      this.readout(radar < 300 ? "WHEELS M" : "HEIGHT M", radar < 300 ? radar.toFixed(radar < 30 ? 1 : 0) : f.altitude().toFixed(0), right, middle - 30 * scale, "right", radar < 6 ? AMBER : GREEN);
      const vs = f.get("vs_mps");
      this.readout("CLIMB M/S", `${vs >= 0 ? "+" : ""}${vs.toFixed(1)}`, right, middle + 34 * scale, "right", vs < -2.5 ? AMBER : GREEN);
      const base = height - 28 * scale;
      const tall = 130 * scale;
      const torque = f.get("power_hp") / POWER_LIMIT;
      const x = 22 * scale;
      this.bar(x, base, tall, f.u[0], GREEN, 0.6);
      this.bar(x + 42 * scale, base, tall, torque, torque > 0.98 ? RED : torque > 0.9 ? AMBER : GREEN, 1);
      this.bar(x + 84 * scale, base, tall, f.get("rotor_pct") / 120, f.get("rotor_pct") < 95 ? RED : GREEN, 100 / 120);
      for (const [label, at] of [["COLL", 6], ["TQ", 48], ["NR", 90]] as const) {
        this.text(label, x + at * scale, base + 16 * scale, 11, "center");
      }
    }
    if (pad && distance < 260 && f.radar() < 140) {
      this.planView(f, pad, run);
    }
    if (run.active) {
      // From the cockpit the bottom of the screen is the panel.
      const up = view.cockpit ? 104 * scale : height - 54 * scale;
      this.text(clock(run.time), width / 2, up, 26, "center", GREEN);
      const leg = pad ? `PAD ${run.leg}/${run.pads.length - 1}   ${pad.name.toUpperCase()}` : "";
      this.text(leg, width / 2, up + 24 * scale, 14, "center", GREEN);
    }
    this.mapView(f, pads, pad, outline);
    if (view.aid !== "assist" && !f.scas) {
      this.text("SCAS OFF", width / 2, 84 * scale, 14, "center", AMBER);
    }
    this.warningList(warnings(f), ["LOW ROTOR", "SINK RATE", "BANK ON THE GROUND"], time);
    const shown = time - this.bannerAt;
    if (shown < 3.4) {
      c.globalAlpha = Math.min(1, 3.4 - shown);
      this.text(this.banner, width / 2, height * 0.3, 44, "center", this.bannerColor);
      this.text(this.subline, width / 2, height * 0.3 + 30 * scale, 16, "center", "#f2f4ef");
      c.globalAlpha = 1;
    }
    this.end();
  }
}
