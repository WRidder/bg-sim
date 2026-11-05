/**
 * Round instruments, drawn on any 2D canvas: the panel's texture in the cockpit and the overlay
 * outside. A dial's face changes only with its size, so each is painted once and blitted; only the
 * needles are drawn every time.
 */

const INK = "#e9e6da";
const FACE = "#0d0f11";
const FONT = '600 1px "Bahnschrift", "DIN Alternate", "Arial Narrow", "Segoe UI", sans-serif';

type Context = CanvasRenderingContext2D;

function font(c: Context, size: number): void {
  c.font = FONT.replace("1px", `${size}px`);
}

/** A round face with a bezel, into which `paint` draws on a unit circle of radius r. */
function dial(r: number, paint: (c: Context, r: number) => void): HTMLCanvasElement {
  const size = Math.ceil(r * 2 + 8);
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const c = canvas.getContext("2d") as Context;
  c.translate(size / 2, size / 2);
  const bezel = c.createLinearGradient(0, -r, 0, r);
  bezel.addColorStop(0, "#54585c");
  bezel.addColorStop(1, "#141618");
  c.fillStyle = bezel;
  c.beginPath();
  c.arc(0, 0, r + 3, 0, Math.PI * 2);
  c.fill();
  c.fillStyle = FACE;
  c.beginPath();
  c.arc(0, 0, r * 0.94, 0, Math.PI * 2);
  c.fill();
  paint(c, r * 0.94);
  return canvas;
}

function ticks(c: Context, r: number, from: number, to: number, count: number, major: number, angle: (v: number) => number, label?: (v: number) => string): void {
  c.strokeStyle = INK;
  c.fillStyle = INK;
  c.textAlign = "center";
  c.textBaseline = "middle";
  font(c, r * 0.2);
  for (let i = 0; i <= count; i += 1) {
    const value = from + ((to - from) * i) / count;
    const a = angle(value);
    const big = i % major === 0;
    const inner = r * (big ? 0.82 : 0.89);
    c.lineWidth = Math.max(r * (big ? 0.028 : 0.016), 0.8);
    c.beginPath();
    c.moveTo(Math.sin(a) * inner, -Math.cos(a) * inner);
    c.lineTo(Math.sin(a) * r * 0.97, -Math.cos(a) * r * 0.97);
    c.stroke();
    if (big && label) {
      c.fillText(label(value), Math.sin(a) * r * 0.66, -Math.cos(a) * r * 0.66);
    }
  }
}

function arc(c: Context, r: number, from: number, to: number, color: string, width = 0.07): void {
  c.strokeStyle = color;
  c.lineWidth = r * width;
  c.beginPath();
  c.arc(0, 0, r * 0.93, from - Math.PI / 2, to - Math.PI / 2);
  c.stroke();
}

function needle(c: Context, x: number, y: number, r: number, angle: number, length = 0.8, color = "#f4f1e6"): void {
  c.save();
  c.translate(x, y);
  c.rotate(angle);
  c.fillStyle = color;
  c.beginPath();
  c.moveTo(-r * 0.035, r * 0.16);
  c.lineTo(r * 0.035, r * 0.16);
  c.lineTo(r * 0.012, -r * length);
  c.lineTo(-r * 0.012, -r * length);
  c.fill();
  c.fillStyle = "#26282b";
  c.beginPath();
  c.arc(0, 0, r * 0.07, 0, Math.PI * 2);
  c.fill();
  c.restore();
}

const speedAngle = (kt: number): number => {
  // Slow speeds get the room: it is where a landing is flown.
  const clamped = Math.max(0, Math.min(kt, 180));
  return ((clamped <= 40 ? clamped * 0.55 : 22 + (clamped - 40) * 1.96) * Math.PI) / 180 + 0.2;
};
const verticalAngle = (fpm: number): number => (Math.max(-2000, Math.min(2000, fpm)) / 2000) * (Math.PI * 0.86) - Math.PI / 2;

export interface Readings {
  kias: number;
  feet: number;
  fpm: number;
  pitch: number;
  bank: number;
  heading: number;
  turn: number;
  slip: number;
  rpm: number;
}

export class Instruments {
  private faces = new Map<string, HTMLCanvasElement>();

  private face(name: string, r: number, paint: (c: Context, r: number) => void): HTMLCanvasElement {
    const key = `${name}:${Math.round(r)}`;
    let canvas = this.faces.get(key);
    if (!canvas) {
      canvas = dial(r, paint);
      this.faces.set(key, canvas);
    }
    return canvas;
  }

  private blit(c: Context, face: HTMLCanvasElement, x: number, y: number): void {
    c.drawImage(face, x - face.width / 2, y - face.height / 2);
  }

  speed(c: Context, x: number, y: number, r: number, kias: number): void {
    this.blit(c, this.face("speed", r, (d, rr) => {
      arc(d, rr, speedAngle(33), speedAngle(85), "#eceae0", 0.05);
      arc(d, rr, speedAngle(44), speedAngle(127), "#2fb35c");
      arc(d, rr, speedAngle(127), speedAngle(163), "#e8b52c");
      ticks(d, rr, 0, 180, 18, 2, speedAngle, (v) => (v === 0 ? "" : String(v)));
      d.fillStyle = INK;
      font(d, rr * 0.13);
      d.textAlign = "center";
      d.fillText("KNOTS", 0, rr * 0.3);
    }), x, y);
    needle(c, x, y, r, speedAngle(kias));
  }

  altitude(c: Context, x: number, y: number, r: number, feet: number): void {
    this.blit(c, this.face("altitude", r, (d, rr) => {
      ticks(d, rr, 0, 1000, 50, 5, (v) => (v / 1000) * Math.PI * 2, (v) => (v === 1000 ? "" : String(v / 100)));
      d.fillStyle = INK;
      font(d, rr * 0.13);
      d.textAlign = "center";
      d.fillText("ALT FT", 0, rr * 0.34);
    }), x, y);
    const f = Math.max(feet, 0);
    needle(c, x, y, r, (f / 10000) * Math.PI * 2, 0.5);
    needle(c, x, y, r, (f / 1000) * Math.PI * 2, 0.84);
  }

  climb(c: Context, x: number, y: number, r: number, fpm: number): void {
    this.blit(c, this.face("climb", r, (d, rr) => {
      ticks(d, rr, -2000, 2000, 40, 10, verticalAngle, (v) => (v === 0 ? "0" : String(Math.abs(v) / 100)));
      d.fillStyle = INK;
      font(d, rr * 0.12);
      d.textAlign = "left";
      d.fillText("UP", rr * 0.05, -rr * 0.3);
      d.fillText("DOWN", rr * 0.02, rr * 0.34);
      d.textAlign = "center";
      d.fillText("100 FT/MIN", rr * 0.3, rr * 0.02);
    }), x, y);
    needle(c, x, y, r, verticalAngle(fpm));
  }

  attitude(c: Context, x: number, y: number, r: number, pitch: number, bank: number): void {
    const inner = r * 0.82;
    c.save();
    c.beginPath();
    c.arc(x, y, r + 3, 0, Math.PI * 2);
    c.fillStyle = "#1a1c1e";
    c.fill();
    c.beginPath();
    c.arc(x, y, inner + r * 0.1, 0, Math.PI * 2);
    c.clip();
    c.translate(x, y);
    c.rotate((-bank * Math.PI) / 180);
    const per = inner / 30;
    const shift = pitch * per;
    c.fillStyle = "#2c6fa8";
    c.fillRect(-r * 2, -r * 2 + shift, r * 4, r * 2);
    c.fillStyle = "#6b4426";
    c.fillRect(-r * 2, shift, r * 4, r * 2);
    c.strokeStyle = "#f4f1e6";
    c.lineWidth = Math.max(r * 0.022, 1);
    c.beginPath();
    c.moveTo(-r * 2, shift);
    c.lineTo(r * 2, shift);
    for (const p of [-20, -10, 10, 20]) {
      const wide = r * (Math.abs(p) === 10 ? 0.32 : 0.46);
      const py = shift - p * per;
      c.moveTo(-wide, py);
      c.lineTo(wide, py);
    }
    c.stroke();
    // The bank scale turns with the sky.
    for (const a of [-60, -30, -20, -10, 0, 10, 20, 30, 60]) {
      c.save();
      c.rotate((a * Math.PI) / 180);
      c.fillStyle = "#f4f1e6";
      c.fillRect(-r * 0.012, -inner - r * 0.09, r * 0.024, r * (a % 30 === 0 ? 0.1 : 0.06));
      c.restore();
    }
    c.restore();
    // The little aeroplane stays still.
    c.strokeStyle = "#ffb43a";
    c.lineWidth = Math.max(r * 0.05, 1.4);
    c.lineCap = "round";
    c.beginPath();
    c.moveTo(x - r * 0.46, y);
    c.lineTo(x - r * 0.16, y);
    c.lineTo(x - r * 0.08, y + r * 0.07);
    c.lineTo(x + r * 0.08, y + r * 0.07);
    c.lineTo(x + r * 0.16, y);
    c.lineTo(x + r * 0.46, y);
    c.stroke();
    c.lineCap = "butt";
    c.fillStyle = "#ffb43a";
    c.beginPath();
    c.moveTo(x, y - inner + r * 0.015);
    c.lineTo(x - r * 0.05, y - inner + r * 0.1);
    c.lineTo(x + r * 0.05, y - inner + r * 0.1);
    c.fill();
  }

  /** A card that turns under a fixed aeroplane, and the bearing to a ring when there is one. */
  compass(c: Context, x: number, y: number, r: number, heading: number, bug: number | null): void {
    this.blit(c, this.face("compass", r, () => {}), x, y);
    c.save();
    c.translate(x, y);
    c.rotate((-heading * Math.PI) / 180);
    c.fillStyle = INK;
    c.strokeStyle = INK;
    c.textAlign = "center";
    c.textBaseline = "middle";
    font(c, r * 0.2);
    for (let d = 0; d < 360; d += 5) {
      const big = d % 30 === 0;
      c.save();
      c.rotate((d * Math.PI) / 180);
      c.lineWidth = Math.max(r * (big ? 0.024 : 0.012), 0.7);
      c.beginPath();
      c.moveTo(0, -r * 0.93);
      c.lineTo(0, -r * (big ? 0.78 : d % 10 === 0 ? 0.83 : 0.88));
      c.stroke();
      if (big) {
        c.fillText({ 0: "N", 90: "E", 180: "S", 270: "W" }[d] ?? String(d / 10), 0, -r * 0.62);
      }
      c.restore();
    }
    if (bug !== null) {
      c.save();
      c.rotate((bug * Math.PI) / 180);
      c.fillStyle = "#ffb43a";
      c.fillRect(-r * 0.05, -r * 0.94, r * 0.1, r * 0.1);
      c.restore();
    }
    c.restore();
    c.strokeStyle = "#ffb43a";
    c.lineWidth = Math.max(r * 0.04, 1.2);
    c.lineCap = "round";
    c.beginPath();
    c.moveTo(x, y - r * 0.44);
    c.lineTo(x, y + r * 0.34);
    c.moveTo(x - r * 0.28, y - r * 0.08);
    c.lineTo(x + r * 0.28, y - r * 0.08);
    c.moveTo(x - r * 0.11, y + r * 0.3);
    c.lineTo(x + r * 0.11, y + r * 0.3);
    c.stroke();
    c.lineCap = "butt";
  }

  turn(c: Context, x: number, y: number, r: number, rate: number, slip: number): void {
    this.blit(c, this.face("turn", r, (d, rr) => {
      d.fillStyle = INK;
      for (const side of [-1, 1]) {
        d.save();
        d.rotate((side * 18 * Math.PI) / 180);
        d.fillRect(-rr * 0.02, -rr * 0.9, rr * 0.04, rr * 0.16);
        d.restore();
        d.fillRect(side * rr * 0.86 - rr * 0.08, -rr * 0.02, rr * 0.16, rr * 0.04);
      }
      d.textAlign = "center";
      font(d, rr * 0.16);
      d.fillText("TURN", 0, -rr * 0.4);
      d.fillStyle = "#17191b";
      d.fillRect(-rr * 0.5, rr * 0.34, rr, rr * 0.22);
    }), x, y);
    c.save();
    c.translate(x, y);
    c.rotate((Math.max(-6, Math.min(6, rate)) * 15 * Math.PI) / 180 / 3);
    c.fillStyle = "#f4f1e6";
    c.fillRect(-r * 0.62, -r * 0.03, r * 1.24, r * 0.06);
    c.beginPath();
    c.arc(0, 0, r * 0.1, 0, Math.PI * 2);
    c.fill();
    c.fillRect(-r * 0.02, -r * 0.2, r * 0.04, r * 0.16);
    c.restore();
    c.fillStyle = "#0a0a0b";
    c.beginPath();
    c.arc(x + Math.max(-1, Math.min(1, slip)) * r * 0.36, y + r * 0.45, r * 0.09, 0, Math.PI * 2);
    c.fill();
    c.strokeStyle = INK;
    c.lineWidth = 1;
    c.strokeRect(x - r * 0.13, y + r * 0.34, r * 0.26, r * 0.22);
  }

  revs(c: Context, x: number, y: number, r: number, rpm: number): void {
    const angle = (v: number): number => ((Math.max(0, Math.min(3500, v)) / 3500) * 1.6 - 0.8) * Math.PI;
    this.blit(c, this.face("revs", r, (d, rr) => {
      arc(d, rr, angle(2100) + Math.PI, angle(2700) + Math.PI, "#2fb35c");
      arc(d, rr, angle(2700) + Math.PI, angle(2760) + Math.PI, "#e0442a");
      ticks(d, rr, 0, 3500, 35, 5, (v) => angle(v), (v) => String(v / 100));
      d.fillStyle = INK;
      font(d, rr * 0.13);
      d.textAlign = "center";
      d.fillText("RPM", 0, rr * 0.34);
      d.fillText("x100", 0, rr * 0.52);
    }), x, y);
    needle(c, x, y, r, angle(rpm));
  }
}
