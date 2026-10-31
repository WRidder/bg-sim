/**
 * What a library drop on the canvas adds (plan 7.2): a catalog block, a junction, or a background
 * shape. `position` is the drop point in flow coordinates; with `snap` it goes to the grid like the
 * canvas menu's Add. Each kind is one undo step, and the new element is selected.
 */

import type { ModelPoint } from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import type { LibraryDragPayload } from "../library/dnd";
import { useDocumentStore } from "../state/documentStore";
import { GRID_SIZE } from "./geometry";
import { addShapeAt } from "./ShapeMenu";

/** Add the dropped element; returns its canvas id, or null when nothing was added. */
export function dropLibraryPayload(
  payload: LibraryDragPayload,
  position: ModelPoint,
  snap: boolean,
  index: CatalogIndex,
): string | null {
  if (payload.kind === "shape") {
    // The shape's top-left corner (a line: its start) at the drop point.
    return addShapeAt(payload.shape, position, snap);
  }
  const placement = snap
    ? {
        x: Math.round(position.x / GRID_SIZE) * GRID_SIZE,
        y: Math.round(position.y / GRID_SIZE) * GRID_SIZE,
      }
    : position;
  const store = useDocumentStore.getState();
  if (payload.kind === "junction") {
    return store.addJunction(payload.junction, placement);
  }
  const block = index.blocksByRef.get(payload.ref);
  return block === undefined ? null : store.addBlock(block, placement);
}
