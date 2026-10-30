/**
 * Text for debug pauses (plan 7.9): "Paused at t = 0.4123 s: LQGController
 * line 14 (Ctrl)". Pure, so the run bar, the tab title and the tests share it.
 */

import type { Breakpoint, PausedInfo } from "../contracts/debug";
import type { Model } from "../contracts/model";

export function formatPauseTime(t: number): string {
  return `${Number.isFinite(t) ? t.toFixed(4) : String(t)} s`;
}

/**
 * A short name for a block reference: `project:LQGController` gives
 * `LQGController`, `stdlib:discrete/PIController` gives `PIController`, and
 * `inline:<node-id>` gives the node's name when the document is known.
 */
export function blockLabel(ref: string, doc: Model | null = null): string {
  if (ref.startsWith("inline:")) {
    const id = ref.slice("inline:".length);
    const node = doc?.diagram.nodes.find((entry) => entry.id === id);
    return node?.name ?? id;
  }
  const colon = ref.indexOf(":");
  const rest = colon >= 0 ? ref.slice(colon + 1) : ref;
  const slash = rest.lastIndexOf("/");
  return slash >= 0 ? rest.slice(slash + 1) : rest;
}

/** `LQGController line 14 (Ctrl)`, or null when the pause has no source location. */
export function describeLocation(info: PausedInfo, doc: Model | null = null): string | null {
  const location = info.location;
  if (location === null || location.scope === "watch") {
    return null;
  }
  const where = `${blockLabel(location.ref, doc)} line ${location.range.line}`;
  return location.path.length > 0 ? `${where} (${location.path})` : where;
}

function watchExpression(info: PausedInfo, breakpoints: readonly Breakpoint[]): string | null {
  if (info.breakpointId === null) {
    return null;
  }
  const hit = breakpoints.find((entry) => entry.id === info.breakpointId);
  return hit !== undefined && hit.kind === "watch" ? hit.watch.expr : null;
}

/** The run bar status of a paused run. */
export function pausedStatusText(
  info: PausedInfo,
  breakpoints: readonly Breakpoint[] = [],
  doc: Model | null = null,
): string {
  const head = `Paused at t = ${formatPauseTime(info.t)}`;
  const place = describeLocation(info, doc);
  if (info.location?.scope === "watch") {
    const expr = watchExpression(info, breakpoints);
    return expr === null ? `${head}: watch` : `${head}: watch ${expr}`;
  }
  if (place !== null) {
    return `${head}: ${place}`;
  }
  switch (info.reason) {
    case "entry":
      return `${head} (entry)`;
    case "time":
      return `${head} (time breakpoint)`;
    case "event":
      return `${head} (event)`;
    case "exception": {
      const code = info.diagnostics[0]?.code;
      return code === undefined ? `${head} (exception)` : `${head} (exception ${code})`;
    }
    case "pause":
      return `${head} (paused)`;
    case "step":
      return `${head} (step)`;
    case "breakpoint": {
      const expr = watchExpression(info, breakpoints);
      return expr === null ? `${head} (breakpoint)` : `${head}: watch ${expr}`;
    }
  }
}
