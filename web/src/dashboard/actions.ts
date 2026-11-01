/**
 * Dashboard edits (DASHBOARD_PLAN.md). Every change goes through the document store, so it is
 * undoable, autosaved and travels with the model; gestures (a slider or knob drag) coalesce
 * into one undo entry.
 */

import type {
  DashboardCardKind,
  DashboardCardSize,
  ModelDashboardCard,
  ModelDashboardCardOptions,
  ModelDashboardSchedule,
} from "../contracts/model";
import { useDocumentStore } from "../state/documentStore";
import { moveCard, newCard, nextCardId } from "./model";

function edit(
  recipe: Parameters<ReturnType<typeof useDocumentStore.getState>["editDashboard"]>[0],
  coalesce?: string,
): void {
  useDocumentStore.getState().editDashboard(recipe, coalesce === undefined ? {} : { coalesce });
}

function withCard(id: string, recipe: (card: ModelDashboardCard) => void, coalesce?: string): void {
  edit((dashboard) => {
    const card = dashboard.cards.find((entry) => entry.id === id);
    if (card !== undefined) {
      recipe(card);
    }
  }, coalesce);
}

/** Add a card at the end (or with a first signal); returns its id. */
export function addCard(kind: DashboardCardKind, signal?: string): string {
  const id = nextCardId(useDocumentStore.getState().doc?.dashboard);
  edit((dashboard) => {
    const card = newCard(kind, id);
    if (signal !== undefined) {
      card.signals = [signal];
    }
    dashboard.cards.push(card);
  });
  return id;
}

export function removeCard(id: string): void {
  edit((dashboard) => {
    dashboard.cards = dashboard.cards.filter((card) => card.id !== id);
  });
}

export function moveCardTo(id: string, index: number): void {
  edit((dashboard) => {
    dashboard.cards = moveCard(dashboard.cards, id, index);
  });
}

export function setCardSize(id: string, size: DashboardCardSize): void {
  withCard(id, (card) => {
    card.size = size;
  });
}

export function setCardTitle(id: string, title: string): void {
  withCard(id, (card) => {
    if (title.trim().length === 0) {
      delete card.title;
    } else {
      card.title = title;
    }
  });
}

/** Bind a display card to signals (a plot keeps several, the others one). */
export function setCardSignals(id: string, signals: readonly string[]): void {
  withCard(id, (card) => {
    if (signals.length === 0) {
      delete card.signals;
    } else {
      card.signals = [...signals];
    }
  });
}

/**
 * XY: draw a plot card's signals against `x` (a signal id), or against time again (null), as
 * `x` of a model plot. The new x leaves the card's signals; the previous x returns to their front.
 */
export function setCardX(id: string, x: string | null): void {
  withCard(id, (card) => {
    if (card.kind !== "plot" || (x ?? undefined) === card.x) {
      return;
    }
    const previous = card.x;
    let signals = (card.signals ?? []).filter((signal) => signal !== x);
    if (previous !== undefined && !signals.includes(previous)) {
      signals = [previous, ...signals];
    }
    if (signals.length > 0) card.signals = signals;
    else delete card.signals;
    if (x === null) {
      delete card.x;
      delete card.equalAspect;
    } else {
      card.x = x;
    }
  });
}

/** XY: equal units per pixel on both axes of a plot card (`equalAspect`; false is not written). */
export function setCardEqualAspect(id: string, on: boolean): void {
  withCard(id, (card) => {
    if (on && card.x !== undefined) card.equalAspect = true;
    else delete card.equalAspect;
  });
}

/** Drop a signal on a display card: a plot adds it, the others replace their binding. */
export function dropSignalOnCard(id: string, signal: string): void {
  withCard(id, (card) => {
    if (card.kind === "plot") {
      const signals = card.signals ?? [];
      if (!signals.includes(signal) && signal !== card.x) {
        card.signals = [...signals, signal];
      }
    } else {
      card.signals = [signal];
    }
  });
}

/** Bind an input card to a parameter; the old override value is dropped. */
export function setCardParameter(id: string, target: string | null): void {
  withCard(id, (card) => {
    if (target === null) {
      delete card.parameter;
    } else {
      card.parameter = target;
    }
    delete card.value;
  });
}

/** The override value of an input card; null returns to the model's value. */
export function setCardValue(id: string, value: number | boolean | null, coalesce?: string): void {
  withCard(
    id,
    (card) => {
      if (value === null) {
        delete card.value;
      } else {
        card.value = value;
      }
    },
    coalesce,
  );
}

export function setCardOptions(id: string, patch: Partial<ModelDashboardCardOptions>): void {
  withCard(id, (card) => {
    const options: ModelDashboardCardOptions = { ...(card.options ?? {}) };
    for (const [key, value] of Object.entries(patch) as [keyof ModelDashboardCardOptions, unknown][]) {
      if (value === undefined || value === null || (key === "zones" && Array.isArray(value) && value.length === 0)) {
        delete options[key];
      } else {
        (options as Record<string, unknown>)[key] = value;
      }
    }
    if (Object.keys(options).length === 0) {
      delete card.options;
    } else {
      card.options = options;
    }
  });
}

export function setCardSchedule(id: string, schedule: ModelDashboardSchedule): void {
  withCard(id, (card) => {
    card.schedule = structuredClone(schedule);
  });
}

export function setAutoRerun(on: boolean): void {
  edit((dashboard) => {
    if (on) {
      dashboard.autoRerun = true;
    } else {
      delete dashboard.autoRerun;
    }
  });
}

export function beginValueGesture(key: string): void {
  useDocumentStore.getState().beginGesture(key);
}

export function endValueGesture(): void {
  useDocumentStore.getState().endGesture();
}
