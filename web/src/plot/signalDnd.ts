/**
 * The drag payload between the signal browser and a plot panel (plan 7.5:
 * "drag a signal onto a plot"). A dedicated MIME type keeps other draggable
 * things in the app (library blocks, nodes) from being mistaken for signals.
 */

import type { DragEvent } from "react";

/** The custom MIME type written by the signal browser. */
export const SIGNAL_DRAG_MIME = "application/x-bgsim-signal";

/** Write a signal id on a drag; `text/plain` is the fallback for other apps. */
export function writeSignalDrag(
  dataTransfer: DataTransfer,
  signalId: string,
): void {
  dataTransfer.setData(SIGNAL_DRAG_MIME, signalId);
  dataTransfer.setData("text/plain", signalId);
  dataTransfer.effectAllowed = "copy";
}

/** Read the signal id from a drag event, or null when it is not a signal. */
export function readSignalDrag(event: DragEvent<HTMLElement>): string | null {
  const custom = event.dataTransfer.getData(SIGNAL_DRAG_MIME);
  if (custom.length > 0) {
    return custom;
  }
  const plain = event.dataTransfer.getData("text/plain").trim();
  return plain.length > 0 ? plain : null;
}
