/**
 * Canvas menu items for background shapes: "Add rectangle" and friends on the
 * empty canvas, and arrange / lock / duplicate / delete on a shape. The
 * canvas owns the menu; these are its rows.
 */

import type { ModelShape, ShapeKind } from "../contracts/model";
import { useDocumentStore } from "../state/documentStore";
import { GRID_SIZE } from "./geometry";
import {
  canReorder,
  isLocked,
  SHAPE_KIND_LABELS,
  SHAPE_KINDS,
  SHAPE_ORDER_LABELS,
  selectedShapeIds,
  shapeIdOf,
  type ShapeOrder,
} from "./shapes";
import { activeDiagram } from "./subsystemPath";
import "./nodes/shape.css";

const NO_SHAPES: readonly ModelShape[] = [];

/**
 * Add a shape with its top-left corner (a line: its start) at `point` (flow
 * coordinates; on the grid when snapping). Returns the canvas id or null.
 */
export function addShapeAt(
  kind: ShapeKind,
  point: { x: number; y: number },
  snap: boolean,
): string | null {
  const position = snap
    ? {
        x: Math.round(point.x / GRID_SIZE) * GRID_SIZE,
        y: Math.round(point.y / GRID_SIZE) * GRID_SIZE,
      }
    : point;
  return useDocumentStore.getState().addShape(kind, position);
}

/** "Add rectangle", ... in the empty canvas's menu. */
export function AddShapeMenuItems({ onAdd }: { onAdd: (kind: ShapeKind) => void }) {
  return (
    <>
      <div className="editor-menu__separator" role="separator" />
      {SHAPE_KINDS.map((kind) => (
        <button
          key={kind}
          type="button"
          role="menuitem"
          data-testid={`add-shape-${kind}`}
          onClick={() => onAdd(kind)}
        >
          Add {SHAPE_KIND_LABELS[kind].toLowerCase()}
        </button>
      ))}
    </>
  );
}

/** The shapes a shape's menu acts on: the selected shapes when it is one of them. */
export function shapeMenuTargets(id: string): string[] {
  const selected = selectedShapeIds(useDocumentStore.getState().selection.nodes);
  return selected.includes(id) ? selected : [id];
}

const ORDERS: readonly ShapeOrder[] = ["front", "forward", "backward", "back"];

/** The menu of a shape: arrange, lock or unlock, duplicate, delete. */
export function ShapeMenuItems({
  flowId,
  onDone,
  onDelete,
}: {
  flowId: string;
  onDone: () => void;
  onDelete: () => void;
}) {
  const id = shapeIdOf(flowId);
  const shapes = useDocumentStore((state) => {
    const diagram = state.doc === null ? null : activeDiagram(state.doc, state.activePath);
    return diagram?.shapes ?? NO_SHAPES;
  });
  const shape = shapes.find((entry) => entry.id === id);
  if (id === null || shape === undefined) {
    return null;
  }
  const targets = shapeMenuTargets(id);
  const locked = isLocked(shape);
  const allLocked = shapes.filter((entry) => targets.includes(entry.id)).every(isLocked);
  const run = (action: () => void): void => {
    action();
    onDone();
  };
  return (
    <>
      {ORDERS.map((order) => (
        <button
          key={order}
          type="button"
          role="menuitem"
          data-testid={`shape-order-${order}`}
          disabled={!canReorder(shapes, targets, order)}
          onClick={() => run(() => useDocumentStore.getState().reorderShapes(targets, order))}
        >
          {SHAPE_ORDER_LABELS[order]}
        </button>
      ))}
      <div className="editor-menu__separator" role="separator" />
      <button
        type="button"
        role="menuitem"
        data-testid={locked ? "shape-unlock" : "shape-lock"}
        onClick={() => run(() => useDocumentStore.getState().setShapeLocked(targets, !locked))}
      >
        {locked ? "Unlock" : "Lock"}
      </button>
      <button
        type="button"
        role="menuitem"
        data-testid="shape-duplicate"
        onClick={() => run(() => useDocumentStore.getState().duplicateShapes(targets))}
      >
        Duplicate
      </button>
      <button
        type="button"
        role="menuitem"
        data-testid="shape-delete"
        disabled={allLocked}
        title={allLocked ? "Unlock the shape to delete it" : undefined}
        onClick={onDelete}
      >
        Delete (Del)
      </button>
    </>
  );
}
