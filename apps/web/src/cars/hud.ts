/**
 * The driver's readout, laid out like a race broadcast: the lap on the left, the map on the right,
 * speed and battery at the bottom where the eye drops to them. Nothing covers the road ahead.
 */

import { Overlay } from "../engine/overlay";
import type { Track } from "./track";
import type { Vehicle } from "./vehicle";

const WHITE = "#f4f5f1";
const MUTED = "rgba(244,245,241,0.62)";
const PLATE = "rgba(7,11,14,0.62)";
const HOT = "#ff5a26";
const GOOD = "#47e08a";
const BEST = "#c56bff";
const AMBER = "#ffc34d";
const FACE = '"Bahnschrift", "DIN Alternate", "Arial Narrow", "Segoe UI", sans-serif';

export function lapText(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return `${m}:${s.toFixed(3).padStart(6, "0")}`;
}

export function deltaText(seconds: number): string {
  return `${seconds >= 0 ? "+" : "−"}${Math.abs(seconds).toFixed(2)}`;
}

export interface HudState {
  /** Laps of the session; 0 for no limit. */
  laps: number;
  /** Best time to beat from earlier runs. */
  record: number | null;
  /** Gap to the best lap at this point of the lap, when there is one. */
  delta: number | null;
  /** The sector just finished, and how it compared. */
  flash: { text: string; color: string; until: number } | null;
  message: { text: string; color: string; until: number } | null;
  /** 0..5 red lights lit, -1 all out. */
  lights: number;
  time: number;
}

export class Hud extends Overlay {
  private map: Path2D | null = null;
  private mapScale = 1;
  private mapX = 0;
  private mapY = 0;

  /** Fits the route into the map's square. */
  setTrack(track: Track): void {
    const path = new Path2D();
    let [left, right, low, high] = [Infinity, -Infinity, Infinity, -Infinity];
    for (let i = 0; i < track.n; i += 8) {
      left = Math.min(left, track.x[i]);
      right = Math.max(right, track.x[i]);
      low = Math.min(low, track.y[i]);
      high = Math.max(high, track.y[i]);
    }
    for (let i = 0; i < track.n; i += 8) {
      if (i === 0) {
        path.moveTo(track.x[i], -track.y[i]);
      } else {
        path.lineTo(track.x[i], -track.y[i]);
      }
    }
    path.closePath();
    this.map = path;
    this.mapScale = 150 / Math.max(right - left, high - low);
    this.mapX = (left + right) / 2;
    this.mapY = (low + high) / 2;
  }

  private label(s: string, x: number, y: number, size: number, align: CanvasTextAlign = "left", color = WHITE, weight = 600): void {
    const c = this.c;
    c.font = `${weight} ${size * this.scale}px ${FACE}`;
    c.textAlign = align;
    c.fillStyle = color;
    c.fillText(s, x, y);
  }

  private plate(x: number, y: number, w: number, h: number, radius = 4): void {
    const c = this.c;
    c.beginPath();
    c.roundRect(x, y, w, h, radius * this.scale);
    c.fillStyle = PLATE;
    c.fill();
  }

  private lapPanel(car: Vehicle, state: HudState): void {
    const { scale: k } = this;
    const x = this.roomLeft + 18 * k;
    const y = 18 * k;
    const w = 208 * k;
    const lines = 1 + (car.laps.length > 0 ? 1 : 0) + (car.best !== null || state.record !== null ? 1 : 0);
    this.plate(x, y, w, (66 + lines * 20) * k);
    const count = car.laps.length + 1;
    this.label(state.laps ? `LAP ${Math.min(count, state.laps)}/${state.laps}` : `LAP ${count}`, x + 14 * k, y + 24 * k, 15, "left", MUTED);
    if (!car.lapValid) {
      this.label("NOT COUNTED", x + w - 14 * k, y + 24 * k, 12, "right", HOT);
    }
    this.label(lapText(car.running ? car.lapTime : 0), x + 14 * k, y + 58 * k, 32, "left", car.lapValid ? WHITE : MUTED);
    // Three sector ticks: filled as they are done.
    const sx = x + 14 * k;
    for (let i = 0; i < 3; i += 1) {
      const done = i < car.sector;
      this.c.fillStyle = done ? GOOD : i === car.sector ? AMBER : "rgba(244,245,241,0.2)";
      this.c.fillRect(sx + i * 62 * k, y + 68 * k, 56 * k, 3 * k);
    }
    let row = y + 92 * k;
    const last = car.laps[car.laps.length - 1];
    if (last) {
      this.label("LAST", x + 14 * k, row, 13, "left", MUTED);
      this.label(last.valid ? lapText(last.time) : "—", x + w - 14 * k, row, 15, "right");
      row += 20 * k;
    }
    const best = car.best !== null && (state.record === null || car.best < state.record) ? car.best : state.record;
    if (best !== null) {
      this.label("BEST", x + 14 * k, row, 13, "left", MUTED);
      this.label(lapText(best), x + w - 14 * k, row, 15, "right", BEST);
    }
  }

  private speedPanel(car: Vehicle): void {
    const { width: w, height: h, scale: k, c } = this;
    const cx = w / 2;
    const y = h - 22 * k;
    const speed = Math.round(car.get("kmh"));
    this.label(String(Math.abs(speed)), cx, y - 18 * k, 54, "center");
    this.label(car.reversing ? "R" : "KM/H", cx, y, 13, "center", car.reversing ? AMBER : MUTED);
    // The motor's power, right; what it gives back, left, in green.
    const power = (car.get("motor_r_power") * (car.kind === "buggy" ? 2 : 1)) / 1000;
    const peak = car.kind === "racecar" ? 260 : 120;
    const bar = 190 * k;
    const by = y - 34 * k;
    const gap = 62 * k;
    c.fillStyle = "rgba(244,245,241,0.14)";
    c.fillRect(cx + gap, by, bar, 5 * k);
    c.fillRect(cx - gap - bar, by, bar, 5 * k);
    c.fillStyle = power >= 0 ? HOT : GOOD;
    const share = Math.min(1, Math.abs(power) / peak);
    if (power >= 0) {
      c.fillRect(cx + gap, by, bar * share, 5 * k);
    } else {
      c.fillRect(cx - gap - bar * share, by, bar * share, 5 * k);
    }
    this.label(`${Math.round(Math.abs(power))} kW`, cx + gap, by - 7 * k, 13, "left", MUTED);
    this.label(power < -1 ? "REGEN" : "", cx - gap, by - 7 * k, 12, "right", GOOD);
    // The battery, in the corner of the same strip.
    const soc = car.get("soc");
    this.label(`${Math.round(soc * 100)}%`, cx + gap + bar, by + 22 * k, 14, "right", soc < 0.12 ? HOT : WHITE);
    this.label("BATTERY", cx + gap + bar - 44 * k, by + 22 * k, 11, "right", MUTED);
    const u = car.u;
    c.fillStyle = "rgba(244,245,241,0.14)";
    c.fillRect(cx - gap - bar, by + 16 * k, bar, 3 * k);
    c.fillRect(cx - gap - bar, by + 23 * k, bar, 3 * k);
    c.fillStyle = GOOD;
    c.fillRect(cx - gap - bar, by + 16 * k, bar * u[1], 3 * k);
    c.fillStyle = HOT;
    c.fillRect(cx - gap - bar, by + 23 * k, bar * Math.min(1, u[2]), 3 * k);
  }

  private mapPanel(car: Vehicle): void {
    const { width: w, scale: k, c } = this;
    if (!this.map) {
      return;
    }
    const size = 172 * k;
    const x = w - this.roomRight - size - 18 * k;
    const y = 18 * k;
    this.plate(x, y, size, size);
    const s = this.mapScale * k;
    c.save();
    c.translate(x + size / 2, y + size / 2);
    c.scale(s, s);
    c.translate(-this.mapX, this.mapY);
    c.lineJoin = "round";
    c.lineWidth = 7 / s;
    c.strokeStyle = "rgba(244,245,241,0.3)";
    c.stroke(this.map);
    c.lineWidth = 3 / s;
    c.strokeStyle = WHITE;
    c.stroke(this.map);
    c.fillStyle = HOT;
    c.beginPath();
    c.arc(car.get("chassis_px"), -car.get("chassis_py"), 6 / s, 0, Math.PI * 2);
    c.fill();
    c.restore();
  }

  /** The five reds of a start gantry, large, at the top of the view. */
  private lights(count: number): void {
    const { width: w, height: h, scale: k, c } = this;
    const r = 15 * k;
    const gap = 46 * k;
    const y = h * 0.17;
    this.plate(w / 2 - 2.5 * gap - 6 * k, y - 26 * k, 5 * gap + 12 * k, 52 * k, 8);
    for (let i = 0; i < 5; i += 1) {
      c.beginPath();
      c.arc(w / 2 + (i - 2) * gap, y, r, 0, Math.PI * 2);
      c.fillStyle = count === -1 ? "#3dff8e" : i < count ? "#ff2a12" : "rgba(244,245,241,0.14)";
      c.fill();
    }
  }

  draw(car: Vehicle, state: HudState): void {
    this.begin();
    const { c, width: w, height: h, scale: k } = this;
    c.shadowBlur = 0;
    this.lapPanel(car, state);
    this.mapPanel(car);
    this.speedPanel(car);
    if (state.lights !== -2) {
      this.lights(state.lights);
    }
    if (state.delta !== null && car.running) {
      const good = state.delta < 0;
      const x = w / 2;
      const y = 26 * k;
      this.plate(x - 58 * k, y - 12 * k, 116 * k, 36 * k);
      this.label(deltaText(state.delta), x, y + 15 * k, 22, "center", good ? GOOD : HOT);
    }
    if (state.flash && state.time < state.flash.until) {
      this.label(state.flash.text, w / 2, 96 * k, 22, "center", state.flash.color);
    }
    if (state.message && state.time < state.message.until) {
      c.shadowColor = "rgba(0,0,0,0.6)";
      c.shadowBlur = 8 * k;
      this.label(state.message.text, w / 2, h * 0.3, 30, "center", state.message.color);
    }
    this.end();
  }
}

export const COLOURS = { WHITE, HOT, GOOD, BEST, AMBER, MUTED };
