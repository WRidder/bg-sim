/**
 * At a statement pause the Code tab opens at the paused location (plan 7.9),
 * the same way a diagnostic's source link does. The line highlight, the
 * scroll-into-view and the tab title follow from the debug store itself
 * (`code/breakpoints.ts`, `CenterTabs`).
 */

import type { PausedInfo } from "../contracts/debug";
import type { DiagnosticSource } from "../contracts/diagnostic";
import { requestSource } from "../code/codeSession";

/** The source kind a block ref names. */
export function sourceKindOf(ref: string): DiagnosticSource["kind"] {
  if (ref.startsWith("inline:")) {
    return "inline";
  }
  return ref.startsWith("stdlib:") ? "stdlib" : "project";
}

/** Open the Code tab at a statement pause; false when the pause has no source line. */
export function openPauseLocation(info: PausedInfo): boolean {
  const location = info.location;
  if (location === null || location.scope === "watch") {
    return false;
  }
  requestSource(
    {
      kind: sourceKindOf(location.ref),
      ref: location.ref,
      line: location.range.line,
      col: location.range.col,
    },
    { reveal: true },
  );
  return true;
}
