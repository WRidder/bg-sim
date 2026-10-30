/**
 * The outline of a subsystem port terminal (and of its "+ kind" ghost). The
 * shape tells the kind apart; the colour stays the domain's.
 *
 * * **input** — an arrow tag (off-sheet connector) with its point on the side
 *   its boundary wire leaves from, so it points into the diagram; the outer
 *   side is notched.
 * * **output** — an arrow tag with its flat side on the wire side, so it
 *   points out of the diagram.
 * * **power** — a hexagon: symmetric, no direction.
 *
 * The direction follows the wire side (`handleSide`), not a fixed left or
 * right, so a terminal moved to the other side still reads in the signal
 * direction. On a left or right side the point spans the full height; on a
 * top or bottom side (a terminal dragged above or below its port) a short
 * point sits in the middle of that edge, above or below the text.
 */

import type { Side } from "../geometry";
import type { TerminalKind } from "../subsystemPorts";

const OPPOSITE: Record<Side, Side> = { left: "right", right: "left", top: "bottom", bottom: "top" };

export interface TerminalShape {
  kind: TerminalKind;
  /** The side the arrow point is on; null for the symmetric power hexagon. */
  point: Side | null;
  /** The notched side (an input's outer side, left/right only). */
  notch: Side | null;
}

function horizontal(side: Side): boolean {
  return side === "left" || side === "right";
}

/** Which way the terminal of `kind` points when its wire leaves from `handleSide`. */
export function terminalShape(kind: TerminalKind, handleSide: Side): TerminalShape {
  switch (kind) {
    case "input":
      return {
        kind,
        point: handleSide,
        notch: horizontal(handleSide) ? OPPOSITE[handleSide] : null,
      };
    case "output":
      return { kind, point: OPPOSITE[handleSide], notch: null };
    case "power":
    default:
      return { kind: "power", point: null, notch: null };
  }
}

/** The depth of a full-height point (left/right) and of the hexagon ends. */
export function pointDepth(height: number): number {
  return Math.round(height / 3);
}

/** The depth of the short point on a top or bottom edge. */
export function edgePointDepth(height: number): number {
  return Math.round(height / 5);
}

/** Half the stroke: the outline sits inside the node box, like an inset border. */
const INSET = 0.75;
const CORNER = 4;
const TIP = 1.5;

export interface Vertex {
  x: number;
  y: number;
  /** Corner rounding radius. */
  r: number;
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}

/** A closed polygon with rounded corners (each cut back at most half an edge). */
function roundedPolygon(vertices: readonly Vertex[]): string {
  const count = vertices.length;
  const parts: string[] = [];
  vertices.forEach((vertex, i) => {
    const prev = vertices[(i + count - 1) % count] ?? vertex;
    const next = vertices[(i + 1) % count] ?? vertex;
    const toPrev = { x: prev.x - vertex.x, y: prev.y - vertex.y };
    const toNext = { x: next.x - vertex.x, y: next.y - vertex.y };
    const lenPrev = Math.hypot(toPrev.x, toPrev.y) || 1;
    const lenNext = Math.hypot(toNext.x, toNext.y) || 1;
    const cut = Math.min(vertex.r, lenPrev / 2, lenNext / 2);
    const a = { x: vertex.x + (toPrev.x / lenPrev) * cut, y: vertex.y + (toPrev.y / lenPrev) * cut };
    const b = { x: vertex.x + (toNext.x / lenNext) * cut, y: vertex.y + (toNext.y / lenNext) * cut };
    parts.push(
      `${i === 0 ? "M" : "L"} ${round(a.x)} ${round(a.y)} Q ${round(vertex.x)} ${round(vertex.y)} ${round(b.x)} ${round(b.y)}`,
    );
  });
  return `${parts.join(" ")} Z`;
}

/**
 * The outline vertices in the node box (`width` x `height`, origin top left).
 * Drawn as if the point were on the right, then mirrored or turned.
 */
export function terminalVertices(shape: TerminalShape, width: number, height: number): Vertex[] {
  const x0 = INSET;
  const y0 = INSET;
  const x1 = width - INSET;
  const y1 = height - INSET;
  const ym = height / 2;
  const depth = pointDepth(height);

  if (shape.point === null) {
    return [
      { x: x0 + depth, y: y0, r: CORNER },
      { x: x1 - depth, y: y0, r: CORNER },
      { x: x1, y: ym, r: TIP },
      { x: x1 - depth, y: y1, r: CORNER },
      { x: x0 + depth, y: y1, r: CORNER },
      { x: x0, y: ym, r: TIP },
    ];
  }

  if (horizontal(shape.point)) {
    const notch = shape.notch === null ? 0 : depth / 2;
    const right: Vertex[] = [
      { x: x0, y: y0, r: CORNER },
      { x: x1 - depth, y: y0, r: CORNER },
      { x: x1, y: ym, r: TIP },
      { x: x1 - depth, y: y1, r: CORNER },
      { x: x0, y: y1, r: CORNER },
      ...(notch > 0 ? [{ x: x0 + notch, y: ym, r: TIP }] : []),
    ];
    return shape.point === "right" ? right : right.map((v) => ({ ...v, x: width - v.x }));
  }

  // A short point in the middle of the top (or bottom) edge.
  const rise = edgePointDepth(height);
  const half = Math.min(rise * 1.5, (width - 2 * CORNER) / 2);
  const cx = width / 2;
  const top: Vertex[] = [
    { x: x0, y: y0 + rise, r: CORNER },
    { x: cx - half, y: y0 + rise, r: TIP },
    { x: cx, y: y0, r: TIP },
    { x: cx + half, y: y0 + rise, r: TIP },
    { x: x1, y: y0 + rise, r: CORNER },
    { x: x1, y: y1, r: CORNER },
    { x: x0, y: y1, r: CORNER },
  ];
  return shape.point === "top" ? top : top.map((v) => ({ ...v, y: height - v.y }));
}

/** The SVG path of the outline. */
export function terminalOutline(shape: TerminalShape, width: number, height: number): string {
  return roundedPolygon(terminalVertices(shape, width, height));
}

export interface TerminalInsets {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

/** The text padding that keeps the two lines clear of the point, notch or hexagon ends. */
export function terminalInsets(shape: TerminalShape, height: number): TerminalInsets {
  const depth = pointDepth(height);
  const flat = 10;
  if (shape.point === null) {
    return { top: 0, right: depth + 3, bottom: 0, left: depth + 3 };
  }
  if (horizontal(shape.point)) {
    const pointSide = depth + 3;
    const otherSide = shape.notch === null ? flat : depth / 2 + 6;
    return shape.point === "right"
      ? { top: 0, right: pointSide, bottom: 0, left: otherSide }
      : { top: 0, right: otherSide, bottom: 0, left: pointSide };
  }
  const rise = edgePointDepth(height);
  return shape.point === "top"
    ? { top: rise, right: flat, bottom: 0, left: flat }
    : { top: 0, right: flat, bottom: rise, left: flat };
}
