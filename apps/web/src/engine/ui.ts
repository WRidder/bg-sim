/** The few things every game's menus share. */

export const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;

export function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
}

/** A best time kept in this browser; a private window may keep nothing, and the run still counts. */
export class BestTime {
  constructor(private readonly key: string) {}

  get(): number | null {
    try {
      const value = Number(localStorage.getItem(this.key));
      return value > 0 ? value : null;
    } catch {
      return null;
    }
  }

  /** True when `seconds` beat the record. */
  offer(seconds: number): boolean {
    const best = this.get();
    if (best !== null && seconds >= best) {
      return false;
    }
    try {
      localStorage.setItem(this.key, String(seconds));
    } catch {
      // Not kept; see above.
    }
    return true;
  }
}

/** Best is the highest score, not the lowest time, so it is kept upside down in a BestTime. */
export class BestScore {
  private readonly store: BestTime;
  constructor(key: string) {
    this.store = new BestTime(key);
  }
  get(): number | null {
    const value = this.store.get();
    return value === null ? null : 1000 - value;
  }
  offer(score: number): boolean {
    return this.store.offer(1000 - score);
  }
}

/** Radio buttons made of big buttons with a heading and a line of text. */
export function choices<V extends string>(group: HTMLElement, onChange: (value: V) => void, initial: V): (value: V) => void {
  const pick = (value: V): void => {
    for (const button of group.querySelectorAll("button")) {
      button.setAttribute("aria-checked", String(button.dataset.value === value));
    }
    onChange(value);
  };
  for (const button of group.querySelectorAll("button")) {
    button.addEventListener("click", () => pick(button.dataset.value as V));
  }
  pick(initial);
  return pick;
}

/** Tells the smoke tests the page is up, with whatever the game wants them to reach. */
export function announce<T extends { state: () => unknown }>(game: T): void {
  (window as unknown as { game: T }).game = game;
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      (window as unknown as { ready: unknown }).ready = game.state();
    }),
  );
}
