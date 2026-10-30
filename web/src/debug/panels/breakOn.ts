/**
 * The "break on" switches of the Breakpoints section (plan 7.9, D24): pause
 * after every `@events` firing, on a solver failure (E901) and when the event
 * limit is reached (W206). They create and remove the `event` and `exception`
 * breakpoints, so they persist and are sent to the run like any other.
 */

import type { Breakpoint, EventBreakpoint, ExceptionBreakpoint } from "../../contracts/debug";
import { useBreakpointStore } from "../breakpointStore";

export const EXCEPTION_CODES = ["E901", "W206"] as const;
export type ExceptionCode = (typeof EXCEPTION_CODES)[number];

export const EXCEPTION_TEXT: Record<ExceptionCode, { label: string; hint: string }> = {
  E901: {
    label: "Solver failure (E901)",
    hint: "Pause before the run ends when the solver fails, to inspect the state at the failure",
  },
  W206: {
    label: "Event limit (W206)",
    hint: "Pause before the run ends when the event limit is reached (Zeno behaviour)",
  },
};

function eventBreakpoints(breakpoints: readonly Breakpoint[]): EventBreakpoint[] {
  return breakpoints.filter(
    (entry): entry is EventBreakpoint => entry.kind === "event" && entry.event.path === null,
  );
}

function exceptionBreakpoints(breakpoints: readonly Breakpoint[]): ExceptionBreakpoint[] {
  return breakpoints.filter((entry): entry is ExceptionBreakpoint => entry.kind === "exception");
}

/** True when an enabled event breakpoint for any instance exists. */
export function eventBreakOn(breakpoints: readonly Breakpoint[]): boolean {
  return eventBreakpoints(breakpoints).some((entry) => entry.enabled);
}

/** The diagnostic codes an enabled exception breakpoint pauses on. */
export function enabledExceptionCodes(breakpoints: readonly Breakpoint[]): string[] {
  return exceptionBreakpoints(breakpoints)
    .filter((entry) => entry.enabled)
    .flatMap((entry) => entry.exception.on);
}

export function setEventBreak(on: boolean): void {
  const store = useBreakpointStore.getState();
  const existing = eventBreakpoints(store.breakpoints);
  if (on) {
    if (existing.length === 0) {
      store.add({ enabled: true, kind: "event", event: { path: null } });
    } else {
      existing.forEach((entry) => store.setEnabled(entry.id, true));
    }
  } else {
    existing.forEach((entry) => store.setEnabled(entry.id, false));
  }
}

/** Switch one exception code; the exception breakpoint is rewritten with the new code set. */
export function setExceptionBreak(code: ExceptionCode, on: boolean): void {
  const store = useBreakpointStore.getState();
  const current = new Set(enabledExceptionCodes(store.breakpoints));
  if (on) {
    current.add(code);
  } else {
    current.delete(code);
  }
  const wanted = EXCEPTION_CODES.filter((entry) => current.has(entry));
  const existing = exceptionBreakpoints(store.breakpoints);
  const unchanged =
    existing.length === 1 &&
    existing[0] !== undefined &&
    existing[0].enabled &&
    existing[0].exception.on.join(",") === wanted.join(",");
  if (unchanged) {
    return;
  }
  existing.forEach((entry) => store.remove(entry.id));
  if (wanted.length > 0) {
    store.add({ enabled: true, kind: "exception", exception: { on: [...wanted] } });
  }
}
