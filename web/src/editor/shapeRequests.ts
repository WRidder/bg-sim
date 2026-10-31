/**
 * "Add this shape in the middle of the canvas", asked from outside the canvas (a click or Enter on
 * a shape of the library's Shapes category). The mounted canvas registers the adder, which knows
 * the viewport; when no canvas is mounted (another centre tab is showing), the request waits, the
 * Diagram tab is selected, and the canvas takes the request once it has mounted.
 */

import type { ShapeKind } from "../contracts/model";
import { requestCenterTab } from "../app/dockBus";
import { useDocumentStore } from "../state/documentStore";

type ShapeAdder = (kind: ShapeKind) => void;

let adder: ShapeAdder | null = null;
let pending: ShapeKind | null = null;

/** The canvas registers its adder; the returned function unregisters it. Takes a waiting request. */
export function registerShapeAdder(next: ShapeAdder): () => void {
  adder = next;
  if (pending !== null) {
    const kind = pending;
    pending = null;
    next(kind);
  }
  return () => {
    if (adder === next) {
      adder = null;
    }
  };
}

/** Add a shape of `kind` centred in the visible canvas (one undo step; it gets selected). */
export function requestShapeAtCentre(kind: ShapeKind): void {
  if (useDocumentStore.getState().doc === null) {
    // No model is open: there is no diagram to draw on.
    return;
  }
  if (adder !== null) {
    adder(kind);
    return;
  }
  pending = kind;
  requestCenterTab("diagram");
}

/** Forget a waiting request (tests). */
export function resetShapeRequests(): void {
  adder = null;
  pending = null;
}
