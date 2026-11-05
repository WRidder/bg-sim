/**
 * Drawing tools for a head-up display on a 2D canvas over the world: text with a shadow, tapes, a
 * heading scale, a marker for the next gate and a small map. The layout is each game's own.
 */

export const GREEN = "#7dffb0";
export const AMBER = "#ffc34d";
export const RED = "#ff5a4d";
export const FONT = 'ui-monospace, "Cascadia Mono", "SF Mono", Consolas, monospace';

/** A position on the view, 0..1 across and down. */
export interface ScreenPoint {
  x: number;
  y: number;
  ahead: boolean;
}

export class Overlay {
  protected readonly c: CanvasRenderingContext2D;
  protected width = 1;
  protected height = 1;
  protected scale = 1;

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

  protected text(s: string, x: number, y: number, size: number, align: CanvasTextAlign = "left", color = GREEN): void {
    const c = this.c;
    c.font = `600 ${size * this.scale}px ${FONT}`;
    c.textAlign = align;
    c.fillStyle = color;
    c.fillText(s, x, y);
  }

  protected line(x0: number, y0: number, x1: number, y1: number): void {
    this.c.beginPath();
    this.c.moveTo(x0, y0);
    this.c.lineTo(x1, y1);
    this.c.stroke();
  }

  protected box(s: string, x: number, y: number, align: CanvasTextAlign): void {
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
  protected tape(x: number, y: number, tall: number, value: number, step: number, label: number, side: 1 | -1, format: (v: number) => string): void {
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

  protected headingTape(y: number, heading: number, wide: number, gateBearing: number | null): void {
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

  protected flightPath(x: number, y: number): void {
    const c = this.c;
    const r = 8 * this.scale;
    c.beginPath();
    c.arc(x, y, r, 0, Math.PI * 2);
    c.stroke();
    this.line(x - r, y, x - 2.6 * r, y);
    this.line(x + r, y, x + 2.6 * r, y);
    this.line(x, y - r, x, y - 2 * r);
  }

  /** A box on the next gate; when it is off the view, an arrow the way to turn. */
  protected gateMarker(g: ScreenPoint | null, distance: number): void {
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

  /** A round map of the land, north up: the craft in green, the next gate in amber. */
  protected minimap(north: number, east: number, heading: number, next: { north: number; east: number } | undefined, outline: Path2D, extent: number): void {
    const c = this.c;
    const size = 132 * this.scale;
    const m = 16 * this.scale;
    const x = this.width - size - m;
    const y = this.height - size - m;
    const perMetre = size / extent;
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
    if (next) {
      c.beginPath();
      c.arc(next.east, -next.north, 900, 0, Math.PI * 2);
      c.fill();
    }
    c.translate(east, -north);
    c.rotate((heading * Math.PI) / 180);
    c.fillStyle = GREEN;
    c.beginPath();
    c.moveTo(0, -2400);
    c.lineTo(1500, 1800);
    c.lineTo(-1500, 1800);
    c.fill();
    c.restore();
  }

  /** The clock and the gate count, bottom centre. */
  protected gateClock(seconds: number, passed: number, total: number, missed: number): void {
    const { width: w, height: h, scale } = this;
    const m = Math.floor(seconds / 60);
    const s = (seconds % 60).toFixed(1).padStart(4, "0");
    this.text(`${m}:${s}`, w / 2, h - 54 * scale, 26, "center", GREEN);
    this.text(`GATE ${Math.min(passed + 1, total)}/${total}${missed ? `   ${missed} MISSED` : ""}`, w / 2, h - 30 * scale, 14, "center", missed ? AMBER : GREEN);
  }

  /** Warnings, blinking; `red` ones are the kind that hurt. */
  protected warningList(active: string[], red: readonly string[], time: number): void {
    if (active.length > 0 && Math.floor(time * 4) % 2 === 0) {
      active.forEach((message, i) => {
        this.text(message, this.width / 2, this.height * 0.27 + i * 34 * this.scale, 28, "center", red.includes(message) ? RED : AMBER);
      });
    }
  }

  protected begin(): void {
    const c = this.c;
    this.clear();
    c.lineWidth = 1.6 * this.scale;
    c.strokeStyle = GREEN;
    c.shadowColor = "rgba(0,0,0,0.55)";
    c.shadowBlur = 3 * this.scale;
    c.lineJoin = "round";
  }

  protected end(): void {
    this.c.shadowBlur = 0;
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
