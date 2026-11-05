/**
 * The model's parameters, set by the player. What can be set is what the FMU declares, with its
 * range: `build_wasm.py` carries that into the game, every `Sim` has a `Tuning`, and `Sim.restart`
 * hands the values to the FMU. The FMU refuses a value out of range, so nothing out of range gets
 * this far. An FMU parameter can only be set before initialisation: a change counts from the next
 * start of the model, and until then the panel says so.
 *
 * `Setup` is the window for it. A game with nothing to say about its parameters gets every one the
 * FMU has with a range, by name; `Knob`s give them a label, a group, a friendlier unit.
 */

import type { FmuParameter } from "./fmu";
import type { Side, SideBar, SidePanel } from "./side";

export class Tuning {
  readonly settable: readonly FmuParameter[];
  private readonly values = new Map<string, number>();
  private running: Record<string, number> = {};
  private readonly listeners = new Set<() => void>();

  /** `id` names the model, whose settings are kept in this browser. */
  constructor(
    private readonly id: string,
    readonly parameters: readonly FmuParameter[],
  ) {
    this.settable = parameters.filter((p) => Number.isFinite(p.min) && Number.isFinite(p.max) && (p.max as number) > (p.min as number));
    this.restore();
    this.running = this.changed;
  }

  private find(name: string): FmuParameter | undefined {
    return this.settable.find((p) => p.name === name);
  }

  has(name: string): boolean {
    return this.find(name) !== undefined;
  }

  /** The value set, which the model takes at its next start. */
  value(name: string): number {
    return this.values.get(name) ?? this.find(name)?.start ?? Number.NaN;
  }

  /** The value the running model has. */
  inUse(name: string): number {
    return this.running[name] ?? this.find(name)?.start ?? Number.NaN;
  }

  set(name: string, value: number): void {
    const parameter = this.find(name);
    if (!parameter || !Number.isFinite(value)) {
      return;
    }
    const held = Math.max(parameter.min as number, Math.min(parameter.max as number, value));
    if (held === parameter.start) {
      this.values.delete(name);
    } else {
      this.values.set(name, held);
    }
    this.changedNow();
  }

  /** Everything back to the model's own values. */
  reset(): void {
    this.values.clear();
    this.changedNow();
  }

  /** What differs from the model's own values: what a restart hands to the FMU. */
  get changed(): Record<string, number> {
    return Object.fromEntries(this.values);
  }

  /** True when the model runs with something other than what is set. */
  get pending(): boolean {
    const [now, then] = [this.changed, this.running];
    return Object.keys({ ...now, ...then }).some((name) => now[name] !== then[name]);
  }

  /** The model has just started with `changed`. */
  started(): void {
    this.running = this.changed;
    this.listeners.forEach((listener) => listener());
  }

  /** Called on every change; the return takes the listener away again. */
  listen(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private changedNow(): void {
    this.keep();
    this.listeners.forEach((listener) => listener());
  }

  private get key(): string {
    return `tuning:${this.id}`;
  }

  /** Whatever is kept may be from another build of the model: only what still fits comes back. */
  private restore(): void {
    let saved: unknown;
    try {
      saved = JSON.parse(localStorage.getItem(this.key) ?? "{}");
    } catch {
      return;
    }
    for (const [name, value] of Object.entries(saved as Record<string, unknown>)) {
      const parameter = this.find(name);
      if (parameter && typeof value === "number" && value >= (parameter.min as number) && value <= (parameter.max as number) && value !== parameter.start) {
        this.values.set(name, value);
      }
    }
  }

  private keep(): void {
    try {
      localStorage.setItem(this.key, JSON.stringify(this.changed));
    } catch {
      // A private window keeps nothing: the settings last as long as the page.
    }
  }
}

/** One slider of the setup window. */
export interface Knob {
  /** The FMU parameter. */
  name: string;
  label: string;
  group: string;
  /** What the value is multiplied by to show it, and the unit it then has. */
  scale?: number;
  unit?: string;
  digits?: number;
  /** One line on what it does to the machine. */
  hint?: string;
}

/** Start values, by the convention of the exports: a name ending in 0 belongs to the game, not the player. */
const START_VALUE = /0$/;

/** A slider for each parameter of `tuning`, for a game that gives no `Knob`s of its own. */
export function everyKnob(tuning: Tuning): Knob[] {
  return tuning.settable
    .filter((p) => !START_VALUE.test(p.name))
    .map((p) => ({ name: p.name, label: p.name, group: "Parameters", unit: p.unit, hint: p.description }));
}

/** A round step that cuts `span` into at most 200, so that 150 N m is 150 and not 149.75. */
export function roundStep(span: number): number {
  const fine = span / 200;
  const power = 10 ** Math.floor(Math.log10(fine));
  return ([1, 2, 5, 10].find((m) => m * power >= fine * (1 - 1e-9)) as number) * power;
}

function show(value: number, knob: Knob): string {
  const shown = value * (knob.scale ?? 1);
  return `${shown.toFixed(knob.digits ?? (Math.abs(shown) >= 100 ? 0 : Math.abs(shown) >= 10 ? 1 : 2))}${knob.unit ? ` ${knob.unit}` : ""}`;
}

export class Setup implements SidePanel {
  readonly root = document.createElement("aside");
  private readonly body = document.createElement("div");
  private readonly note = document.createElement("p");
  private readonly heading = document.createElement("h2");
  private readonly rows = new Map<string, { input: HTMLInputElement; output: HTMLOutputElement; row: HTMLElement; knob: Knob }>();
  private tuning: Tuning | null = null;
  private unlisten: () => void = () => {};
  private added = false;

  constructor(private readonly bar: SideBar) {
    this.root.id = "setup";
    this.root.hidden = true;
    const header = document.createElement("header");
    const stock = document.createElement("button");
    stock.textContent = "Stock";
    stock.title = "Everything back to the model's own values";
    stock.addEventListener("click", () => {
      this.tuning?.reset();
      stock.blur();
    });
    header.append(this.heading, stock);
    this.note.className = "setup-note";
    this.body.className = "setup-body";
    this.root.append(header, this.note, this.body);
    // The window is over the view: a drag or a wheel in it is not for the camera.
    for (const name of ["pointerdown", "mousedown", "wheel", "contextmenu"]) {
      this.root.addEventListener(name, (event) => event.stopPropagation());
    }
    document.body.append(this.root);
  }

  /** Shows the parameters of `tuning`; a model with none has no window, and its key does nothing. */
  use(tuning: Tuning, title: string, knobs: readonly Knob[] = everyKnob(tuning)): void {
    this.unlisten();
    this.tuning = tuning;
    this.heading.textContent = title;
    this.body.replaceChildren();
    this.rows.clear();
    const usable = knobs.filter((knob) => tuning.has(knob.name));
    for (const group of new Set(usable.map((knob) => knob.group))) {
      const section = document.createElement("section");
      const name = document.createElement("h3");
      name.textContent = group;
      section.append(name);
      for (const knob of usable.filter((k) => k.group === group)) {
        section.append(this.row(tuning, knob));
      }
      this.body.append(section);
    }
    this.unlisten = tuning.listen(() => this.refresh());
    this.refresh();
    if (usable.length > 0 && !this.added) {
      this.added = true;
      this.bar.add("KeyY", this);
    }
  }

  private row(tuning: Tuning, knob: Knob): HTMLElement {
    const parameter = tuning.settable.find((p) => p.name === knob.name) as FmuParameter;
    const [min, max] = [parameter.min as number, parameter.max as number];
    const row = document.createElement("label");
    row.className = "setup-row";
    const name = document.createElement("span");
    name.textContent = knob.label;
    const output = document.createElement("output");
    const input = document.createElement("input");
    input.type = "range";
    input.min = String(min);
    input.max = String(max);
    const step = roundStep(max - min);
    input.step = String(step);
    input.setAttribute("aria-label", knob.label);
    input.addEventListener("input", () => {
      // The ends of a range and the stock value must stay reachable whatever the step lands on.
      const value = Number(input.value);
      tuning.set(knob.name, Math.abs(value - parameter.start) < step / 2 ? parameter.start : value);
    });
    // Arrow keys belong to the machine again as soon as the mouse lets go.
    input.addEventListener("pointerup", () => input.blur());
    const stock = document.createElement("small");
    stock.textContent = `stock ${show(parameter.start, knob)}`;
    row.append(name, output, input, stock);
    if (knob.hint) {
      const hint = document.createElement("small");
      hint.className = "setup-hint";
      hint.textContent = knob.hint;
      row.append(hint);
    }
    this.rows.set(knob.name, { input, output, row, knob });
    return row;
  }

  private refresh(): void {
    const tuning = this.tuning;
    if (!tuning) {
      return;
    }
    for (const [name, { input, output, row, knob }] of this.rows) {
      const value = tuning.value(name);
      input.value = String(value);
      output.textContent = show(value, knob);
      row.classList.toggle("changed", name in tuning.changed);
    }
    this.note.textContent = tuning.pending ? "Changed: restart to drive with it (R)." : "The running model has these values.";
    this.note.classList.toggle("pending", tuning.pending);
  }

  place(open: boolean, side: Side): void {
    this.root.hidden = !open;
    this.root.dataset.side = side;
  }

  breadth(): number {
    return this.root.offsetWidth + 16;
  }
}
