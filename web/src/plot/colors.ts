/**
 * Stable signal colours for plots (plan 7.5).
 *
 * A signal's colour is derived from its id, so the same signal keeps its
 * colour when it moves panels, when a new run starts, and when a pinned run is
 * overlaid as dashed lines. The palette avoids the reserved error/warning
 * colours of the theme and keeps enough contrast on both light and dark
 * surfaces.
 */

/** Accessible, medium-saturation plot colours (light and dark themes). */
export const SIGNAL_PALETTE = [
  "#4d8bf0",
  "#3fa877",
  "#9a7ce8",
  "#2fa4c4",
  "#d18a2f",
  "#d9648f",
  "#7f9f35",
  "#b06f4b",
] as const;

/** FNV-1a over the id; deterministic across sessions and runs. */
function hash(text: string): number {
  let value = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    value ^= text.charCodeAt(index);
    value = Math.imul(value, 0x01000193);
  }
  return value >>> 0;
}

/** The colour of a signal id (same on every render, panel and run). */
export function signalColor(signalId: string): string {
  return SIGNAL_PALETTE[hash(signalId) % SIGNAL_PALETTE.length] ?? SIGNAL_PALETTE[0];
}
