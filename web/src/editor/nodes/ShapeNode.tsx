/**
 * A background shape on the canvas (`diagram.shapes`): a rectangle, rounded
 * rectangle or ellipse in its frame, or a line or arrow between two points,
 * with an optional centred label. Shapes sit behind notes, wires and blocks.
 *
 * * Only the painted shape takes the pointer (the xyflow node box does not,
 *   see `shapeNodes`): a filled shape is grabbed anywhere inside, an unfilled
 *   one by its outline (a wider transparent band) or label, and a press on
 *   the empty inside of an unfilled shape reaches the canvas.
 * * A selected, unlocked rectangle kind resizes from its corners and edges; a
 *   selected, unlocked line drags its two end points. Each drag is one undo
 *   step.
 * * A locked shape shows a padlock while hovered or selected.
 */

import { memo, useCallback, useRef } from "react";
import {
  NodeResizer,
  useReactFlow,
  useStore,
  type Node,
  type NodeProps,
  type OnResize,
} from "@xyflow/react";

import type { ShapeColor, ShapeKind, ShapeLabelPosition, ShapeStrokeStyle } from "../../contracts/model";
import { useDocumentStore } from "../../state/documentStore";
import { LINE_PAD, SHAPE_MIN_SIZE } from "../shapes";
import { activeDiagram } from "../subsystemPath";
import "./shape.css";

export interface ShapeNodeData extends Record<string, unknown> {
  /** The shape id (the canvas id is `shape:<id>`). */
  shapeId: string;
  kind: ShapeKind;
  /** The frame size, or a line's direction (may be negative). */
  w: number;
  h: number;
  text: string;
  locked: boolean;
  fill: ShapeColor;
  stroke: ShapeColor;
  strokeWidth: number;
  strokeStyle: ShapeStrokeStyle;
  opacity: number;
  /** Where a frame shape puts its label; a line always centres it. */
  labelPosition: ShapeLabelPosition;
}

export type ShapeNodeType = Node<ShapeNodeData, "shape">;

/** The SVG dash pattern of a stroke style at a stroke width. */
export function dashArray(style: ShapeStrokeStyle, width: number): string | undefined {
  if (style === "dashed") {
    return `${Math.max(6, width * 3)} ${Math.max(4, width * 2)}`;
  }
  if (style === "dotted") {
    return `0 ${Math.max(4, width * 2)}`;
  }
  return undefined;
}

/** The band around an outline or a line that still grabs the shape (px). */
const HIT_WIDTH = 12;

function Padlock() {
  return (
    <span className="canvas-shape__lock" data-testid="canvas-shape-lock" aria-hidden="true">
      <svg viewBox="0 0 16 16" width="12" height="12">
        <path
          d="M5 7V5a3 3 0 0 1 6 0v2"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
        <rect x="3" y="7" width="10" height="7" rx="1.5" fill="currentColor" />
      </svg>
    </span>
  );
}

function FrameShape({
  kind,
  width,
  height,
  strokeWidth,
  dash,
}: {
  kind: ShapeKind;
  width: number;
  height: number;
  strokeWidth: number;
  dash: string | undefined;
}) {
  // The stroke stays inside the frame, so the box is what the user sees.
  const inset = strokeWidth / 2;
  const w = Math.max(0, width - strokeWidth);
  const h = Math.max(0, height - strokeWidth);
  const hit = Math.max(HIT_WIDTH, strokeWidth + 8);
  if (kind === "ellipse") {
    const props = { cx: width / 2, cy: height / 2, rx: w / 2, ry: h / 2 };
    return (
      <>
        <ellipse className="canvas-shape__body" {...props} strokeWidth={strokeWidth} strokeDasharray={dash} />
        <ellipse className="canvas-shape__hit" {...props} strokeWidth={hit} />
      </>
    );
  }
  const radius = kind === "roundedRectangle" ? Math.min(24, Math.min(w, h) * 0.2) : 0;
  const props = { x: inset, y: inset, width: w, height: h, rx: radius, ry: radius };
  return (
    <>
      <rect className="canvas-shape__body" {...props} strokeWidth={strokeWidth} strokeDasharray={dash} />
      <rect className="canvas-shape__hit" {...props} strokeWidth={hit} />
    </>
  );
}

/** A line's end points in the node's own coordinates (the box has LINE_PAD around). */
function localEnds(w: number, h: number): { x1: number; y1: number; x2: number; y2: number } {
  const x1 = LINE_PAD + Math.max(0, -w);
  const y1 = LINE_PAD + Math.max(0, -h);
  return { x1, y1, x2: x1 + w, y2: y1 + h };
}

function LineShape({
  kind,
  w,
  h,
  strokeWidth,
  dash,
  selected,
}: {
  kind: ShapeKind;
  w: number;
  h: number;
  strokeWidth: number;
  dash: string | undefined;
  selected: boolean;
}) {
  const { x1, y1, x2, y2 } = localEnds(w, h);
  const length = Math.hypot(w, h);
  const arrow = kind === "arrow" && length > 0;
  const head = Math.min(length, Math.max(10, strokeWidth * 4));
  const ux = length > 0 ? w / length : 0;
  const uy = length > 0 ? h / length : 0;
  // The shaft stops inside the head, so a thick or dashed stroke does not poke out of the tip.
  const shaftEnd = arrow ? { x: x2 - ux * head * 0.7, y: y2 - uy * head * 0.7 } : { x: x2, y: y2 };
  const half = head * 0.45;
  const baseX = x2 - ux * head;
  const baseY = y2 - uy * head;
  const headPoints = `${x2},${y2} ${baseX - uy * half},${baseY + ux * half} ${baseX + uy * half},${baseY - ux * half}`;
  return (
    <>
      {selected ? (
        <line className="canvas-shape__halo" x1={x1} y1={y1} x2={x2} y2={y2} strokeWidth={strokeWidth + 8} />
      ) : null}
      <line
        className="canvas-shape__body canvas-shape__body--line"
        x1={x1}
        y1={y1}
        x2={shaftEnd.x}
        y2={shaftEnd.y}
        strokeWidth={strokeWidth}
        strokeDasharray={dash}
      />
      {arrow ? <polygon className="canvas-shape__head" points={headPoints} /> : null}
      <line
        className="canvas-shape__hit"
        x1={x1}
        y1={y1}
        x2={x2}
        y2={y2}
        strokeWidth={Math.max(HIT_WIDTH, strokeWidth + 8)}
      />
    </>
  );
}

/**
 * The two end-point handles of a selected, unlocked line: a drag moves one end
 * (snapped to the grid when the canvas snaps) in one undo step.
 */
function LineEnds({ shapeId, w, h }: { shapeId: string; w: number; h: number }) {
  const { screenToFlowPosition } = useReactFlow();
  const snap = useStore((state) => (state.snapToGrid ? state.snapGrid : null));
  const drag = useRef<{ end: "start" | "end"; fixed: { x: number; y: number } } | null>(null);

  const onPointerDown = (end: "start" | "end") => (event: React.PointerEvent<HTMLSpanElement>) => {
    if (event.button !== 0) {
      return;
    }
    const state = useDocumentStore.getState();
    const diagram = state.doc === null ? null : activeDiagram(state.doc, state.activePath);
    const shape = diagram?.shapes?.find((entry) => entry.id === shapeId);
    if (shape === undefined) {
      return;
    }
    event.stopPropagation();
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const fixed = end === "start" ? { x: shape.x + shape.w, y: shape.y + shape.h } : { x: shape.x, y: shape.y };
    drag.current = { end, fixed };
    state.beginGesture(`shape-end:${shapeId}`);
  };
  const onPointerMove = (event: React.PointerEvent<HTMLSpanElement>) => {
    const current = drag.current;
    if (current === null) {
      return;
    }
    let point = screenToFlowPosition({ x: event.clientX, y: event.clientY }, { snapToGrid: false });
    if (snap !== null) {
      point = {
        x: Math.round(point.x / snap[0]) * snap[0],
        y: Math.round(point.y / snap[1]) * snap[1],
      };
    }
    const { fixed } = current;
    const frame =
      current.end === "end"
        ? { x: fixed.x, y: fixed.y, w: point.x - fixed.x, h: point.y - fixed.y }
        : { x: point.x, y: point.y, w: fixed.x - point.x, h: fixed.y - point.y };
    useDocumentStore.getState().setShapeFrame(shapeId, frame, `shape-end:${shapeId}`);
  };
  const onPointerUp = (event: React.PointerEvent<HTMLSpanElement>) => {
    if (drag.current === null) {
      return;
    }
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    useDocumentStore.getState().endGesture();
  };

  const { x1, y1, x2, y2 } = localEnds(w, h);
  return (
    <>
      {(
        [
          ["start", x1, y1],
          ["end", x2, y2],
        ] as const
      ).map(([end, x, y]) => (
        <span
          key={end}
          className="canvas-shape__end nodrag nopan"
          data-testid={`canvas-shape-${end}`}
          style={{ left: x, top: y }}
          onPointerDown={onPointerDown(end)}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        />
      ))}
    </>
  );
}

function ShapeNodeView({ data, selected, width, height }: NodeProps<ShapeNodeType>) {
  const line = data.kind === "line" || data.kind === "arrow";
  const boxWidth = width ?? Math.abs(data.w);
  const boxHeight = height ?? Math.abs(data.h);

  const onResizeStart = useCallback(() => {
    useDocumentStore.getState().beginGesture(`shape-resize:${data.shapeId}`);
  }, [data.shapeId]);
  const onResize: OnResize = useCallback(
    (_event, params) => {
      useDocumentStore.getState().setShapeFrame(
        data.shapeId,
        { x: params.x, y: params.y, w: params.width, h: params.height },
        `shape-resize:${data.shapeId}`,
      );
    },
    [data.shapeId],
  );
  const onResizeEnd = useCallback(() => {
    useDocumentStore.getState().endGesture();
  }, []);

  const dash = dashArray(data.strokeStyle, data.strokeWidth);
  const editable = selected && !data.locked;
  const classes = [
    "canvas-shape",
    `canvas-shape--${data.kind}`,
    `shape-fill--${data.fill}`,
    `shape-stroke--${data.stroke}`,
    data.strokeStyle === "dotted" ? "is-dotted" : "",
    data.fill === "none" ? "is-unfilled" : "is-filled",
    selected ? "is-selected" : "",
    data.locked ? "is-locked" : "",
  ]
    .filter((name) => name.length > 0)
    .join(" ");

  return (
    <div
      className={classes}
      style={{ width: boxWidth, height: boxHeight }}
      data-testid="canvas-shape"
      data-shape-id={data.shapeId}
      data-kind={data.kind}
      data-fill={data.fill}
      data-stroke={data.stroke}
      data-locked={data.locked ? "true" : "false"}
    >
      <div className="canvas-shape__art" style={{ opacity: data.opacity }}>
        <svg className="canvas-shape__svg" width={boxWidth} height={boxHeight} aria-hidden="true">
          {line ? (
            <LineShape
              kind={data.kind}
              w={data.w}
              h={data.h}
              strokeWidth={data.strokeWidth}
              dash={dash}
              selected={selected}
            />
          ) : (
            <FrameShape
              kind={data.kind}
              width={boxWidth}
              height={boxHeight}
              strokeWidth={data.strokeWidth}
              dash={dash}
            />
          )}
        </svg>
        {data.text.length > 0 ? (
          <div
            className={`canvas-shape__label${line ? " canvas-shape__label--line" : ""}`}
            data-position={line ? "center" : data.labelPosition}
          >
            <span data-testid="canvas-shape-label">{data.text}</span>
          </div>
        ) : null}
      </div>
      {/* The handles come after the art, so they are on top of its grab band. */}
      {!line ? (
        <NodeResizer
          isVisible={editable}
          minWidth={SHAPE_MIN_SIZE.w}
          minHeight={SHAPE_MIN_SIZE.h}
          handleClassName="canvas-shape__handle"
          lineClassName="canvas-shape__resize-line"
          onResizeStart={onResizeStart}
          onResize={onResize}
          onResizeEnd={onResizeEnd}
        />
      ) : null}
      {line && editable ? <LineEnds shapeId={data.shapeId} w={data.w} h={data.h} /> : null}
      {data.locked ? <Padlock /> : null}
    </div>
  );
}

export const ShapeNode = memo(ShapeNodeView);
