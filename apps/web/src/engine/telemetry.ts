/**
 * The live data panel every game shares: a side panel over the world with what the model is doing,
 * each number in the form that reads best. A game describes its panel as data (`Panel`, in
 * `src/<game>/telemetry.ts`) and calls `update` once a frame; the keys, the history, the layout and
 * the drawing are all here. It has its own canvas under the menus, redrawn at 30 Hz. A game with
 * more than one vehicle hands over the next vehicle's panel with `use`.
 *
 * T shows it, through the side bar (`side.ts`). Time in the plots is the time the game was running,
 * so a pause freezes the trace and a restart clears it.
 */

import { AMBER, FONT, GREEN, RED } from "./overlay";
import type { Side, SideBar, SidePanel } from "./side";

const INK = "#f2f4ef";
const MUTED = "rgba(242,244,239,0.62)";
const FAINT = "rgba(242,244,239,0.16)";
const PLATE = "rgba(9,14,17,0.66)";
const FACE = '"Bahnschrift", "DIN Alternate", "Arial Narrow", "Segoe UI", sans-serif';

export const BLUE = "#6cc4ff";
export { AMBER, GREEN, RED };

export type Read = () => number;

/** A range coloured on a gauge or a bar: `[from, to, colour]`. */
export type Zone = readonly [number, number, string];

/** A number with its unit, for what only has to be read: a few to a row. */
export interface Value {
  kind: "value";
  label: string;
  unit?: string;
  get: Read;
  digits?: number;
  /** A colour for this value, or nothing for the usual one. */
  alert?: (value: number) => string | undefined;
}

/** A dial, for one quantity with a working range and limits: two to a row. */
export interface Gauge {
  kind: "gauge";
  label: string;
  unit?: string;
  get: Read;
  min: number;
  max: number;
  zones?: readonly Zone[];
  digits?: number;
}

/** A bar, for a share of a range. With `min` below zero it grows from the middle: a control surface. */
export interface Bar {
  kind: "bar";
  label: string;
  unit?: string;
  get: Read;
  min: number;
  max: number;
  zones?: readonly Zone[];
  digits?: number;
  /** A marker on the bar, such as what is available now. */
  mark?: Read;
}

export interface Series {
  label: string;
  get: Read;
  colour: string;
}

/** A trace against time, for what matters as a shape: a transient, a limit reached. */
export interface Plot {
  kind: "plot";
  label: string;
  unit?: string;
  series: readonly Series[];
  /** The range drawn; a trace past it grows the range for as long as it is on the plot. */
  min: number;
  max: number;
  /** Lines across, such as a limit. */
  lines?: readonly { at: number; colour: string }[];
  digits?: number;
}

/** A point with a tail on two axes, for two quantities that only mean something together. */
export interface Scatter {
  kind: "scatter";
  label: string;
  x: Read;
  y: Read;
  /** Half-width of the square, and the circles drawn inside it. */
  range: number;
  rings: readonly number[];
  /** Names of the four sides: left, right, up, down. */
  sides?: readonly [string, string, string, string];
}

/** One share per wheel, drawn where the wheel is: two columns, as seen from above. */
export interface Corners {
  kind: "corners";
  label: string;
  unit?: string;
  /** Front left, front right, rear left, rear right; three values for a tricycle, nose first. */
  get: readonly Read[];
  min: number;
  max: number;
  zones?: readonly Zone[];
  digits?: number;
}

export type Item = Value | Gauge | Bar | Plot | Scatter | Corners;

export interface Section {
  title: string;
  items: readonly Item[];
}

export interface Panel {
  sections: readonly Section[];
}

/** The trace of one series: the newest `size` samples, oldest first by index. */
export class History {
  readonly data: Float32Array;
  private head = 0;
  count = 0;

  constructor(readonly size: number) {
    this.data = new Float32Array(size);
  }

  push(value: number): void {
    this.data[this.head] = Number.isFinite(value) ? value : 0;
    this.head = (this.head + 1) % this.size;
    this.count = Math.min(this.count + 1, this.size);
  }

  /** The `i`th sample kept, 0 the oldest. */
  at(i: number): number {
    return this.data[(this.head - this.count + i + this.size * 2) % this.size];
  }

  clear(): void {
    this.head = 0;
    this.count = 0;
  }

  /** Lowest and highest sample kept. */
  extent(): [number, number] {
    let [low, high] = [Infinity, -Infinity];
    for (let i = 0; i < this.count; i += 1) {
      const value = this.at(i);
      low = Math.min(low, value);
      high = Math.max(high, value);
    }
    return [low, high];
  }
}

/** The range a plot draws: its own, grown to the traces it holds. */
export function plotRange(item: Pick<Plot, "min" | "max">, traces: readonly History[]): [number, number] {
  let [low, high] = [item.min, item.max];
  for (const trace of traces) {
    if (trace.count > 0) {
      const [a, b] = trace.extent();
      low = Math.min(low, a);
      high = Math.max(high, b);
    }
  }
  return [low, high];
}

/** Where `value` falls in `min..max`, held to 0..1. */
export function share(value: number, min: number, max: number): number {
  return Number.isFinite(value) && max > min ? Math.max(0, Math.min(1, (value - min) / (max - min))) : 0;
}

/** A reading with a sensible number of digits for its size. */
export function reading(value: number, digits?: number): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  const places = digits ?? (Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 10 ? 1 : 2);
  const text = value.toFixed(places);
  // Never "-0".
  return Number(text) === 0 ? text.replace("-", "") : text;
}

export function zoneColour(value: number, zones: readonly Zone[] | undefined, otherwise: string): string {
  return zones?.find(([from, to]) => value >= from && value <= to)?.[2] ?? otherwise;
}

/** Items of one kind side by side, the rest a row each. */
const COLUMNS = { value: 3, gauge: 2, bar: 1, plot: 1, scatter: 2, corners: 2 } as const;
const HEIGHTS = { value: 36, gauge: 92, bar: 25, plot: 70, scatter: 104, corners: 104 } as const;
const TITLE = 19;
const GAP = 6;
export const WIDTH = 276;
const PAD = 10;

export interface Placed {
  item: Item;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Puts a panel's items in rows, in the panel's own units; `height` is the whole. */
export function layout(sections: readonly Section[]): { placed: Placed[]; titles: { text: string; y: number }[]; height: number } {
  const inner = WIDTH - PAD * 2;
  const placed: Placed[] = [];
  const titles: { text: string; y: number }[] = [];
  let y = PAD;
  for (const section of sections) {
    titles.push({ text: section.title, y: y + 11 });
    y += TITLE;
    let i = 0;
    while (i < section.items.length) {
      // Items in a row share the columns of the widest kind among them, so a gauge and a scatter pair up.
      const first = section.items[i];
      const columns = COLUMNS[first.kind];
      const row: Item[] = [first];
      while (row.length < columns && i + row.length < section.items.length && COLUMNS[section.items[i + row.length].kind] === columns) {
        row.push(section.items[i + row.length]);
      }
      const w = (inner - GAP * (columns - 1)) / columns;
      const h = Math.max(...row.map((item) => HEIGHTS[item.kind]));
      row.forEach((item, at) => placed.push({ item, x: PAD + at * (w + GAP), y, w, h }));
      y += h + 3;
      i += row.length;
    }
    y += GAP;
  }
  return { placed, titles, height: y + PAD - GAP };
}

const SAMPLE = 1 / 30;
/** Seconds of history on a plot, and the samples that takes. */
export const SPAN = 12;
const SAMPLES = Math.round(SPAN / SAMPLE);
const TAIL = 45;

export class Telemetry implements SidePanel {
  readonly canvas = document.createElement("canvas");
  private readonly c = this.canvas.getContext("2d") as CanvasRenderingContext2D;
  private readonly traces = new Map<Read, History>();
  private readonly tails = new Map<Scatter, { x: History; y: History }>();
  private arrangement: ReturnType<typeof layout> = layout([]);
  private shown = false;
  private side: Side = "right";
  private mode: "running" | "frozen" | "hidden" = "hidden";
  private ratio = 1;
  private scale = 1;
  private owed = 0;
  private lastSize = "";

  constructor(bar: SideBar, panel: Panel = { sections: [] }) {
    this.canvas.id = "telemetry";
    this.canvas.hidden = true;
    document.body.append(this.canvas);
    this.use(panel);
    bar.add("KeyT", this);
  }
  /** Shows `panel` from now on, with empty traces. */
  use(panel: Panel): void {
    this.arrangement = layout(panel.sections);
    this.lastSize = "";
    this.traces.clear();
    this.tails.clear();
    for (const { item } of this.arrangement.placed) {
      if (item.kind === "plot") {
        for (const series of item.series) {
          this.traces.set(series.get, new History(SAMPLES));
        }
      } else if (item.kind === "scatter") {
        this.tails.set(item, { x: new History(TAIL), y: new History(TAIL) });
      }
    }
  }

  place(open: boolean, side: Side): void {
    this.shown = open;
    this.side = side;
    this.canvas.hidden = !open || this.mode === "hidden";
  }

  private get scaleNow(): number {
    return Math.max(0.55, Math.min(1, (innerHeight - 16) / this.arrangement.height));
  }

  breadth(): number {
    return Math.ceil(WIDTH * this.scaleNow) + 16;
  }

  /** For the smoke tests. */
  get state(): { shown: boolean; side: Side; samples: number } {
    const [first] = this.traces.values();
    return { shown: this.shown, side: this.side, samples: first?.count ?? 0 };
  }

  /** Empties the traces: a new run owes nothing to the last. */
  reset(): void {
    this.traces.forEach((trace) => trace.clear());
    this.tails.forEach((tail) => {
      tail.x.clear();
      tail.y.clear();
    });
  }

  /**
   * Once a frame, with the seconds that frame took. "running" records and draws, "frozen" (a pause,
   * the end of a run) keeps the last trace on show, and "hidden" (the title) takes the panel away.
   */
  update(dt: number, mode: "running" | "frozen" | "hidden"): void {
    this.mode = mode;
    this.canvas.hidden = !this.shown || mode === "hidden";
    if (mode !== "running") {
      this.owed = 0;
      if (mode === "frozen" && this.shown) {
        this.fit();
        this.draw();
      }
      return;
    }
    this.owed += dt;
    if (this.owed < SAMPLE) {
      return;
    }
    // A long frame gives one sample: the trace only has to look right, and a stall must not cost more.
    this.owed = Math.min(this.owed - SAMPLE, SAMPLE);
    this.traces.forEach((trace, get) => trace.push(get()));
    this.tails.forEach((tail, item) => {
      tail.x.push(item.x());
      tail.y.push(item.y());
    });
    if (this.shown) {
      this.fit();
      this.draw();
    }
  }

  /** Sizes the canvas to the panel, on the chosen side, scaled to fit the window's height. */
  private fit(): void {
    const ratio = Math.min(devicePixelRatio, 2);
    const scale = this.scaleNow;
    const size = `${innerHeight}x${ratio}x${scale}x${this.side}`;
    if (size === this.lastSize) {
      return;
    }
    this.lastSize = size;
    this.ratio = ratio;
    this.scale = scale;
    const [w, h] = [Math.ceil(WIDTH * scale), Math.ceil(this.arrangement.height * scale)];
    this.canvas.width = Math.round(w * ratio);
    this.canvas.height = Math.round(h * ratio);
    this.canvas.style.width = `${w}px`;
    this.canvas.style.height = `${h}px`;
    this.canvas.style.left = this.side === "left" ? "8px" : "auto";
    this.canvas.style.right = this.side === "right" ? "8px" : "auto";
  }

  private text(text: string, x: number, y: number, size: number, align: CanvasTextAlign, colour: string, font = FACE): void {
    const c = this.c;
    c.font = `${size}px ${font}`;
    c.textAlign = align;
    c.fillStyle = colour;
    c.fillText(text, x, y);
  }

  private draw(): void {
    const c = this.c;
    const k = this.ratio * this.scale;
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, this.canvas.width, this.canvas.height);
    c.setTransform(k, 0, 0, k, 0, 0);
    c.fillStyle = PLATE;
    c.beginPath();
    c.roundRect(0, 0, WIDTH, this.arrangement.height, 8);
    c.fill();
    c.textBaseline = "alphabetic";
    for (const { text, y } of this.arrangement.titles) {
      this.text(text.toUpperCase(), PAD, y, 11, "left", AMBER);
      c.fillStyle = FAINT;
      c.fillRect(PAD + c.measureText(text.toUpperCase()).width + 6, y - 4, WIDTH - PAD * 2 - c.measureText(text.toUpperCase()).width - 6, 1);
    }
    for (const place of this.arrangement.placed) {
      switch (place.item.kind) {
        case "value":
          this.value(place, place.item);
          break;
        case "gauge":
          this.gauge(place, place.item);
          break;
        case "bar":
          this.bar(place, place.item);
          break;
        case "plot":
          this.plot(place, place.item);
          break;
        case "scatter":
          this.scatter(place, place.item);
          break;
        case "corners":
          this.corners(place, place.item);
          break;
      }
    }
  }

  private value({ x, y }: Placed, item: Value): void {
    const value = item.get();
    this.text(item.label, x, y + 10, 10.5, "left", MUTED);
    const size = 16;
    this.text(reading(value, item.digits), x, y + 29, size, "left", item.alert?.(value) ?? INK, FONT);
    if (item.unit) {
      const width = this.c.measureText(reading(value, item.digits)).width;
      this.text(item.unit, x + width + 3, y + 29, 10, "left", MUTED);
    }
  }

  private gauge({ x, y, w }: Placed, item: Gauge): void {
    const c = this.c;
    const value = item.get();
    const [cx, cy, r] = [x + w / 2, y + 54, Math.min(w / 2 - 6, 37)];
    const [start, sweep] = [Math.PI * 0.75, Math.PI * 1.5];
    const angle = (v: number): number => start + sweep * share(v, item.min, item.max);
    c.lineCap = "butt";
    c.lineWidth = 5;
    c.strokeStyle = FAINT;
    c.beginPath();
    c.arc(cx, cy, r, start, start + sweep);
    c.stroke();
    for (const [from, to, colour] of item.zones ?? []) {
      c.strokeStyle = colour;
      c.globalAlpha = 0.45;
      c.beginPath();
      c.arc(cx, cy, r, angle(from), angle(to));
      c.stroke();
      c.globalAlpha = 1;
    }
    const colour = zoneColour(value, item.zones, INK);
    c.strokeStyle = colour;
    c.lineWidth = 2;
    c.lineCap = "round";
    const a = angle(value);
    c.beginPath();
    c.moveTo(cx + Math.cos(a) * r * 0.32, cy + Math.sin(a) * r * 0.32);
    c.lineTo(cx + Math.cos(a) * (r + 2), cy + Math.sin(a) * (r + 2));
    c.stroke();
    this.text(reading(value, item.digits), cx, cy + 6, 17, "center", colour, FONT);
    this.text(item.unit ?? "", cx, cy + 19, 10, "center", MUTED);
    this.text(item.label, cx, y + 10, 10.5, "center", MUTED);
  }

  private bar({ x, y, w }: Placed, item: Bar): void {
    const c = this.c;
    const value = item.get();
    this.text(item.label, x, y + 10, 10.5, "left", MUTED);
    this.text(`${reading(value, item.digits)}${item.unit ? ` ${item.unit}` : ""}`, x + w, y + 10, 11, "right", INK, FONT);
    const [top, tall] = [y + 15, 6];
    c.fillStyle = FAINT;
    c.fillRect(x, top, w, tall);
    const from = share(Math.max(0, item.min), item.min, item.max);
    const to = share(value, item.min, item.max);
    c.fillStyle = zoneColour(value, item.zones, BLUE);
    c.fillRect(x + Math.min(from, to) * w, top, Math.abs(to - from) * w, tall);
    if (item.mark) {
      c.fillStyle = INK;
      c.fillRect(x + share(item.mark(), item.min, item.max) * w - 1, top - 2, 2, tall + 4);
    }
    if (item.min < 0) {
      c.fillStyle = MUTED;
      c.fillRect(x + from * w - 0.5, top - 1, 1, tall + 2);
    }
  }

  private plot({ x, y, w, h }: Placed, item: Plot): void {
    const c = this.c;
    const traces = item.series.map((series) => this.traces.get(series.get) as History);
    const [low, high] = plotRange(item, traces);
    const [top, tall] = [y + 14, h - 16];
    const place = (v: number): number => top + tall * (1 - share(v, low, high));
    // The names and readings of the traces, in the trace's colour.
    this.text(`${item.label}${item.unit ? ` (${item.unit})` : ""}`, x, y + 10, 10.5, "left", MUTED);
    let right = x + w;
    for (let i = item.series.length - 1; i >= 0; i -= 1) {
      const series = item.series[i];
      const text = `${item.series.length > 1 ? `${series.label} ` : ""}${reading(series.get(), item.digits)}`;
      this.text(text, right, y + 10, 10.5, "right", series.colour, FONT);
      right -= c.measureText(text).width + 8;
    }
    c.fillStyle = "rgba(255,255,255,0.05)";
    c.fillRect(x, top, w, tall);
    if (low < 0 && high > 0) {
      c.fillStyle = FAINT;
      c.fillRect(x, place(0), w, 1);
    }
    for (const line of item.lines ?? []) {
      if (line.at >= low && line.at <= high) {
        c.fillStyle = line.colour;
        c.globalAlpha = 0.6;
        c.fillRect(x, place(line.at), w, 1);
        c.globalAlpha = 1;
      }
    }
    c.lineWidth = 1.25;
    c.lineJoin = "round";
    c.lineCap = "butt";
    c.save();
    c.beginPath();
    c.rect(x, top, w, tall);
    c.clip();
    traces.forEach((trace, t) => {
      c.strokeStyle = item.series[t].colour;
      c.beginPath();
      // The newest sample at the right edge, whether the trace is full yet or not.
      const newest = trace.count - 1;
      const stride = Math.max(1, Math.floor(trace.size / w / 2));
      for (let i = newest; i >= 0; i -= stride) {
        const px = x + w - ((newest - i) / (trace.size - 1)) * w;
        const py = place(trace.at(i));
        if (i === newest) {
          c.moveTo(px, py);
        } else {
          c.lineTo(px, py);
        }
      }
      c.stroke();
    });
    c.restore();
  }

  private scatter({ x, y, w, h }: Placed, item: Scatter): void {
    const c = this.c;
    const tail = this.tails.get(item) as { x: History; y: History };
    const [cx, cy] = [x + w / 2, y + 12 + (h - 14) / 2];
    const r = Math.min(w, h - 14) / 2 - 2;
    const px = (v: number): number => cx + (Math.max(-1, Math.min(1, v / item.range))) * r;
    const py = (v: number): number => cy - (Math.max(-1, Math.min(1, v / item.range))) * r;
    this.text(item.label, x, y + 10, 10.5, "left", MUTED);
    c.lineWidth = 1;
    c.strokeStyle = FAINT;
    for (const ring of item.rings) {
      c.beginPath();
      c.arc(cx, cy, (ring / item.range) * r, 0, Math.PI * 2);
      c.stroke();
    }
    c.fillStyle = FAINT;
    c.fillRect(cx - r, cy, r * 2, 1);
    c.fillRect(cx, cy - r, 1, r * 2);
    if (item.sides) {
      const [left, right, up, down] = item.sides;
      this.text(left, cx - r, cy - 3, 8.5, "left", MUTED);
      this.text(right, cx + r, cy - 3, 8.5, "right", MUTED);
      this.text(up, cx + 3, cy - r + 8, 8.5, "left", MUTED);
      this.text(down, cx + 3, cy + r - 1, 8.5, "left", MUTED);
    }
    for (let i = 1; i < tail.x.count; i += 1) {
      c.strokeStyle = BLUE;
      c.globalAlpha = i / tail.x.count;
      c.beginPath();
      c.moveTo(px(tail.x.at(i - 1)), py(tail.y.at(i - 1)));
      c.lineTo(px(tail.x.at(i)), py(tail.y.at(i)));
      c.stroke();
    }
    c.globalAlpha = 1;
    c.fillStyle = INK;
    c.beginPath();
    c.arc(px(item.x()), py(item.y()), 3, 0, Math.PI * 2);
    c.fill();
  }

  private corners({ x, y, w, h }: Placed, item: Corners): void {
    const c = this.c;
    this.text(`${item.label}${item.unit ? ` (${item.unit})` : ""}`, x, y + 10, 10.5, "left", MUTED);
    const tricycle = item.get.length === 3;
    const [cw, ch] = [14, 34];
    const [left, right] = [x + 6, x + w - 6 - cw];
    const [front, rear] = [y + 16, y + h - ch - 3];
    const spots = tricycle ? [[x + (w - cw) / 2, front], [left, rear], [right, rear]] : [[left, front], [right, front], [left, rear], [right, rear]];
    item.get.forEach((get, i) => {
      const value = get();
      const [sx, sy] = spots[i];
      c.fillStyle = FAINT;
      c.fillRect(sx, sy, cw, ch);
      const filled = share(value, item.min, item.max) * ch;
      c.fillStyle = zoneColour(value, item.zones, BLUE);
      c.fillRect(sx, sy + ch - filled, cw, filled);
      const toward = sx < x + w / 2 - cw ? sx + cw + 3 : sx === spots[0][0] && tricycle ? sx + cw + 3 : sx - 3;
      const align: CanvasTextAlign = toward > sx ? "left" : "right";
      this.text(reading(value, item.digits), toward, sy + ch / 2 + 4, 11, align, INK, FONT);
    });
  }
}
