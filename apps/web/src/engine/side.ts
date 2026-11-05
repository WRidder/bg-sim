/**
 * The one place on the screen for a side window, and the keys that use it: telemetry, the model's
 * setup, whatever comes next. Only one is open at a time; opening another closes it. Holding Shift
 * moves the place to the other side. The HUD is told how much room is taken, so nothing sits under
 * the window. What was open, and where, is remembered per game.
 */

export type Side = "left" | "right";

export interface SidePanel {
  /** Shows or hides the window, on `side`. */
  place(open: boolean, side: Side): void;
  /** Screen pixels it takes from the edge, with its margin. */
  breadth(): number;
}

export class SideBar {
  private readonly panels = new Map<string, SidePanel>();
  private open: string | null = null;
  private side: Side = "right";

  /** `onRoom` hears the pixels taken from the left and from the right. */
  constructor(
    private readonly id: string,
    private readonly onRoom: (left: number, right: number) => void,
  ) {
    this.restore();
    addEventListener("keydown", (event) => {
      if (this.panels.has(event.code) && !event.repeat && !event.ctrlKey && !event.altKey && !event.metaKey) {
        this.press(event.code, event.shiftKey);
      }
    });
    addEventListener("resize", () => this.sync());
  }

  /** `code` is the key that shows and hides `panel`. */
  add(code: string, panel: SidePanel): void {
    this.panels.set(code, panel);
    this.sync();
  }

  /** What a key does: Shift moves the place and opens the window there, plain toggles it. */
  private press(code: string, shift: boolean): void {
    if (shift) {
      this.side = this.side === "left" ? "right" : "left";
      this.open = code;
    } else {
      this.open = this.open === code ? null : code;
    }
    this.sync();
    this.keep();
  }

  /** For the smoke tests. */
  get state(): { open: string | null; side: Side } {
    return { open: this.open, side: this.side };
  }

  private sync(): void {
    this.panels.forEach((panel, code) => {
      if (code !== this.open) {
        panel.place(false, this.side);
      }
    });
    const panel = this.open === null ? undefined : this.panels.get(this.open);
    panel?.place(true, this.side);
    const room = panel?.breadth() ?? 0;
    this.onRoom(this.side === "left" ? room : 0, this.side === "right" ? room : 0);
  }

  private get key(): string {
    return `side:${this.id}`;
  }

  /** A private window keeps nothing, and the game simply starts with no window open. */
  private restore(): void {
    try {
      const saved = localStorage.getItem(this.key);
      if (saved) {
        const [open, side] = saved.split(":");
        this.open = open || null;
        this.side = side === "left" ? "left" : "right";
      }
    } catch {
      // See above.
    }
  }

  private keep(): void {
    try {
      localStorage.setItem(this.key, `${this.open ?? ""}:${this.side}`);
    } catch {
      // See `restore`.
    }
  }
}
