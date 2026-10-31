/**
 * Background shapes on the diagram canvas: the model's `diagram.shapes`, one
 * list per diagram level (rectangle, rounded rectangle, ellipse, line, arrow).
 * A shape is editor state only; compile, simulation and export ignore it.
 *
 * On the canvas a shape is a virtual xyflow node `shape:<shape id>`, like the
 * sticky notes (`note:<id>`), so it selects, drags, copies and deletes with
 * the blocks. Shapes always sit behind everything else, notes included; the
 * array order is their z order (the first entry is the back-most).
 *
 * A locked shape (`locked: true`) is neither draggable nor resizable, the
 * selection rectangle skips it and Del leaves it alone; a click still selects
 * it, so its menu and inspector can unlock it.
 */

import type { ModelShape, ShapeColor, ShapeKind, ShapeStrokeStyle } from "../contracts/model";
import { GRID_SIZE } from "./geometry";
import { NOTE_Z_INDEX } from "./notes";

export const SHAPE_PREFIX = "shape:";

export const SHAPE_KINDS: readonly ShapeKind[] = [
  "rectangle",
  "roundedRectangle",
  "ellipse",
  "line",
  "arrow",
];

export const SHAPE_KIND_LABELS: Record<ShapeKind, string> = {
  rectangle: "Rectangle",
  roundedRectangle: "Rounded rectangle",
  ellipse: "Ellipse",
  line: "Line",
  arrow: "Arrow",
};

/** The colours of the contract, in the order the inspector offers them. */
export const SHAPE_COLORS: readonly ShapeColor[] = [
  "none",
  "ink",
  "yellow",
  "blue",
  "green",
  "pink",
  "grey",
];

export const SHAPE_COLOR_LABELS: Record<ShapeColor, string> = {
  none: "None",
  ink: "Ink",
  yellow: "Yellow",
  blue: "Blue",
  green: "Green",
  pink: "Pink",
  grey: "Grey",
};

export const SHAPE_STROKE_STYLES: readonly ShapeStrokeStyle[] = ["solid", "dashed", "dotted"];
export const SHAPE_STROKE_STYLE_LABELS: Record<ShapeStrokeStyle, string> = {
  solid: "Solid",
  dashed: "Dashed",
  dotted: "Dotted",
};
export const SHAPE_STROKE_WIDTHS: readonly number[] = [1, 2, 3, 4, 6, 8];
export const SHAPE_STROKE_WIDTH_RANGE = { min: 0.5, max: 24 } as const;

/** The values an absent field stands for (the editor never writes them). */
export const SHAPE_DEFAULTS = {
  fill: "none",
  stroke: "ink",
  strokeWidth: 2,
  strokeStyle: "solid",
  opacity: 1,
} as const satisfies {
  fill: ShapeColor;
  stroke: ShapeColor;
  strokeWidth: number;
  strokeStyle: ShapeStrokeStyle;
  opacity: number;
};

/** A new shape's size (flow units); a line's `w`/`h` is its direction. */
export const SHAPE_DEFAULT_SIZE: Record<ShapeKind, { w: number; h: number }> = {
  rectangle: { w: 200, h: 120 },
  roundedRectangle: { w: 200, h: 120 },
  ellipse: { w: 180, h: 120 },
  line: { w: 200, h: 0 },
  arrow: { w: 200, h: 0 },
};

/** The smallest frame the resize handles allow (rectangle kinds). */
export const SHAPE_MIN_SIZE = { w: 20, h: 20 } as const;

/**
 * A line's canvas node is its segment's bounding box grown by this margin on
 * every side, so a horizontal line still has a box and its end handles fit. A
 * whole grid cell keeps the end points on the grid while the node snaps.
 */
export const LINE_PAD = GRID_SIZE;

/**
 * xyflow raises a selected node's z-index by 1000. Shape `i` of `n` sits at
 * `NOTE_Z_INDEX - STRIDE * (n - i)` with a stride above that, so a selected
 * shape stays below the next shape up (the order on screen is the document
 * order, selected or not) and the front-most shape, even selected, stays
 * below every note.
 */
export const SHAPE_Z_STRIDE = 1001;

export function shapeZIndex(index: number, count: number): number {
  return NOTE_Z_INDEX - SHAPE_Z_STRIDE * (count - index);
}

export function shapeFlowId(shapeId: string): string {
  return `${SHAPE_PREFIX}${shapeId}`;
}

/** The shape id of a `shape:<id>` canvas id, else null. */
export function shapeIdOf(flowId: string): string | null {
  return flowId.startsWith(SHAPE_PREFIX) ? flowId.slice(SHAPE_PREFIX.length) : null;
}

export function isShapeId(flowId: string | null | undefined): boolean {
  return typeof flowId === "string" && flowId.startsWith(SHAPE_PREFIX);
}

/** The shape ids among canvas selection ids. */
export function selectedShapeIds(ids: readonly string[]): string[] {
  const result: string[] = [];
  for (const id of ids) {
    const shape = shapeIdOf(id);
    if (shape !== null) {
      result.push(shape);
    }
  }
  return result;
}

export function isLineKind(kind: ShapeKind): boolean {
  return kind === "line" || kind === "arrow";
}

export function isLocked(shape: Pick<ModelShape, "locked">): boolean {
  return shape.locked === true;
}

export interface ResolvedShapeStyle {
  fill: ShapeColor;
  stroke: ShapeColor;
  strokeWidth: number;
  strokeStyle: ShapeStrokeStyle;
  opacity: number;
}

/** A shape's style with every absent field at its default. */
export function shapeStyle(shape: ModelShape): ResolvedShapeStyle {
  return {
    fill: isLineKind(shape.kind) ? "none" : (shape.fill ?? SHAPE_DEFAULTS.fill),
    stroke: shape.stroke ?? SHAPE_DEFAULTS.stroke,
    strokeWidth: shape.strokeWidth ?? SHAPE_DEFAULTS.strokeWidth,
    strokeStyle: shape.strokeStyle ?? SHAPE_DEFAULTS.strokeStyle,
    opacity: shape.opacity ?? SHAPE_DEFAULTS.opacity,
  };
}

export type ShapeStylePatch = Partial<ResolvedShapeStyle>;

/**
 * Apply a style patch to a shape (a draft): a value equal to the default
 * removes the field, so documents only carry what differs.
 */
export function applyShapeStyle(shape: ModelShape, patch: ShapeStylePatch): void {
  const set = <K extends keyof ResolvedShapeStyle>(key: K, value: ResolvedShapeStyle[K] | undefined): void => {
    if (value === undefined) {
      return;
    }
    if (value === SHAPE_DEFAULTS[key]) {
      if (key in shape) {
        delete shape[key];
      }
    } else if (shape[key] !== value) {
      (shape as unknown as Record<string, unknown>)[key] = value;
    }
  };
  set("fill", patch.fill);
  set("stroke", patch.stroke);
  if (patch.strokeWidth !== undefined && Number.isFinite(patch.strokeWidth)) {
    const width = Math.min(
      SHAPE_STROKE_WIDTH_RANGE.max,
      Math.max(SHAPE_STROKE_WIDTH_RANGE.min, Math.round(patch.strokeWidth * 10) / 10),
    );
    set("strokeWidth", width);
  }
  set("strokeStyle", patch.strokeStyle);
  if (patch.opacity !== undefined && Number.isFinite(patch.opacity)) {
    set("opacity", Math.min(1, Math.max(0, Math.round(patch.opacity * 100) / 100)));
  }
}

/** A shape's canvas node box (flow units): the frame, or a line's padded bounds. */
export function shapeNodeFrame(shape: ModelShape): { x: number; y: number; width: number; height: number } {
  if (!isLineKind(shape.kind)) {
    return { x: shape.x, y: shape.y, width: shape.w, height: shape.h };
  }
  return {
    x: Math.min(shape.x, shape.x + shape.w) - LINE_PAD,
    y: Math.min(shape.y, shape.y + shape.h) - LINE_PAD,
    width: Math.abs(shape.w) + 2 * LINE_PAD,
    height: Math.abs(shape.h) + 2 * LINE_PAD,
  };
}

/** The shape's `x`/`y` once its canvas node sits at `position` (a drag). */
export function shapeOriginAt(
  shape: Pick<ModelShape, "kind" | "w" | "h">,
  position: { x: number; y: number },
): { x: number; y: number } {
  if (!isLineKind(shape.kind)) {
    return { x: position.x, y: position.y };
  }
  return {
    x: position.x + LINE_PAD - Math.min(0, shape.w),
    y: position.y + LINE_PAD - Math.min(0, shape.h),
  };
}

/** A line's two end points (flow units). */
export function lineEnds(shape: Pick<ModelShape, "x" | "y" | "w" | "h">): {
  start: { x: number; y: number };
  end: { x: number; y: number };
} {
  return { start: { x: shape.x, y: shape.y }, end: { x: shape.x + shape.w, y: shape.y + shape.h } };
}

/** A double-click on a shape asks the shape inspector to focus its label field. */
export const FOCUS_SHAPE_LABEL_EVENT = "bgsim:focus-shape-label";

export function requestShapeLabelFocus(shapeId: string): void {
  if (typeof window !== "undefined") {
    // After the inspector has rendered the selected shape.
    window.requestAnimationFrame(() => {
      window.dispatchEvent(new CustomEvent<string>(FOCUS_SHAPE_LABEL_EVENT, { detail: shapeId }));
    });
  }
}

export type ShapeOrder = "front" | "forward" | "backward" | "back";

export const SHAPE_ORDER_LABELS: Record<ShapeOrder, string> = {
  front: "Bring to front",
  forward: "Bring forward",
  backward: "Send backward",
  back: "Send to back",
};

/**
 * The shapes in a new z order (back to front). `front`/`back` move the chosen
 * shapes to the end/start in their relative order; `forward`/`backward` move
 * each chosen shape one place past its next unchosen neighbour. Returns the
 * input array itself when nothing moves.
 */
export function reorderShapes<T extends { id: string }>(
  shapes: readonly T[],
  ids: Iterable<string>,
  order: ShapeOrder,
): readonly T[] {
  const chosen = new Set(ids);
  if (chosen.size === 0 || !shapes.some((shape) => chosen.has(shape.id))) {
    return shapes;
  }
  let next: T[];
  if (order === "front" || order === "back") {
    const moving = shapes.filter((shape) => chosen.has(shape.id));
    const staying = shapes.filter((shape) => !chosen.has(shape.id));
    next = order === "front" ? [...staying, ...moving] : [...moving, ...staying];
  } else {
    next = [...shapes];
    if (order === "forward") {
      // From the top down, so a chosen shape never jumps over another chosen one.
      for (let i = next.length - 2; i >= 0; i -= 1) {
        const here = next[i];
        const above = next[i + 1];
        if (here !== undefined && above !== undefined && chosen.has(here.id) && !chosen.has(above.id)) {
          next[i] = above;
          next[i + 1] = here;
        }
      }
    } else {
      for (let i = 1; i < next.length; i += 1) {
        const here = next[i];
        const below = next[i - 1];
        if (here !== undefined && below !== undefined && chosen.has(here.id) && !chosen.has(below.id)) {
          next[i] = below;
          next[i - 1] = here;
        }
      }
    }
  }
  return next.every((shape, index) => shape === shapes[index]) ? shapes : next;
}

/** Whether a reorder would move anything (menus disable the no-op entries). */
export function canReorder(
  shapes: readonly { id: string }[],
  ids: Iterable<string>,
  order: ShapeOrder,
): boolean {
  return reorderShapes(shapes, ids, order) !== shapes;
}
