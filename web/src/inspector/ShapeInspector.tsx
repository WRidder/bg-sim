/**
 * Inspector for selected background shapes: fill, stroke (colour, width,
 * style), opacity, the label of one shape, the z order and the lock. Shapes
 * are editor state; the model ignores them.
 */

import { useEffect, useRef, useState } from "react";

import type { ModelShape, ShapeColor, ShapeStrokeStyle } from "../contracts/model";
import {
  canReorder,
  FOCUS_SHAPE_LABEL_EVENT,
  isLineKind,
  isLocked,
  SHAPE_COLOR_LABELS,
  SHAPE_COLORS,
  SHAPE_KIND_LABELS,
  SHAPE_ORDER_LABELS,
  SHAPE_STROKE_STYLE_LABELS,
  SHAPE_STROKE_STYLES,
  SHAPE_STROKE_WIDTHS,
  shapeStyle,
  type ShapeOrder,
} from "../editor/shapes";
import { useDocumentStore } from "../state/documentStore";
import "../editor/nodes/shape.css";

/** The common value of `pick` over the shapes, or null when they differ. */
function common<T>(shapes: readonly ModelShape[], pick: (shape: ModelShape) => T): T | null {
  const first = shapes[0];
  if (first === undefined) {
    return null;
  }
  const value = pick(first);
  return shapes.every((shape) => pick(shape) === value) ? value : null;
}

function textGesture(id: string): string {
  return `shape-text:${id}`;
}

function ShapeLabelField({ shape }: { shape: ModelShape }) {
  const [draft, setDraft] = useState(shape.text ?? "");
  const [focused, setFocused] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  // Follow the document (undo) while not typing here.
  useEffect(() => {
    if (!focused) {
      setDraft(shape.text ?? "");
    }
  }, [shape.text, focused]);
  // A double-click on the shape asks for this field.
  useEffect(() => {
    const onFocus = (event: Event): void => {
      if ((event as CustomEvent<unknown>).detail === shape.id) {
        ref.current?.focus();
        ref.current?.select();
      }
    };
    window.addEventListener(FOCUS_SHAPE_LABEL_EVENT, onFocus);
    return () => window.removeEventListener(FOCUS_SHAPE_LABEL_EVENT, onFocus);
  }, [shape.id]);
  useEffect(
    () => () => {
      if (useDocumentStore.getState().gestureKey === textGesture(shape.id)) {
        useDocumentStore.getState().endGesture();
      }
    },
    [shape.id],
  );
  return (
    <textarea
      ref={ref}
      className="shape-inspector__text"
      data-testid="shape-inspector-text"
      aria-label="Shape label"
      rows={2}
      value={draft}
      placeholder="No label"
      onFocus={() => {
        setFocused(true);
        useDocumentStore.getState().beginGesture(textGesture(shape.id));
      }}
      onBlur={() => {
        setFocused(false);
        if (useDocumentStore.getState().gestureKey === textGesture(shape.id)) {
          useDocumentStore.getState().endGesture();
        }
      }}
      onChange={(event) => {
        setDraft(event.target.value);
        useDocumentStore.getState().setShapeText(shape.id, event.target.value, { coalesce: true });
      }}
    />
  );
}

function Swatches({
  label,
  testId,
  role,
  current,
  onPick,
}: {
  label: string;
  testId: string;
  role: "fill" | "stroke";
  current: ShapeColor | null;
  onPick: (color: ShapeColor) => void;
}) {
  const headingId = `shape-${role}-label`;
  return (
    <section className="shape-inspector__section">
      <h4 id={headingId}>{label}</h4>
      <div className="shape-inspector__swatches" role="radiogroup" aria-labelledby={headingId}>
        {SHAPE_COLORS.map((color) => (
          <button
            key={color}
            type="button"
            role="radio"
            aria-checked={current === color}
            className={`shape-swatch shape-swatch--${role} shape-swatch--${color}${current === color ? " is-current" : ""}`}
            data-testid={`${testId}-${color}`}
            title={SHAPE_COLOR_LABELS[color]}
            aria-label={`${label}: ${SHAPE_COLOR_LABELS[color]}`}
            onClick={() => onPick(color)}
          />
        ))}
      </div>
    </section>
  );
}

const ORDERS: readonly ShapeOrder[] = ["front", "forward", "backward", "back"];

export function ShapeInspector({
  shapes,
  all,
}: {
  shapes: readonly ModelShape[];
  /** Every shape of the diagram, back to front (for the arrange buttons). */
  all: readonly ModelShape[];
}) {
  const first = shapes[0];
  if (first === undefined) {
    return null;
  }
  const ids = shapes.map((shape) => shape.id);
  const single = shapes.length === 1;
  const store = () => useDocumentStore.getState();
  const fill = common(shapes, (shape) => shapeStyle(shape).fill);
  const stroke = common(shapes, (shape) => shapeStyle(shape).stroke);
  const strokeWidth = common(shapes, (shape) => shapeStyle(shape).strokeWidth);
  const strokeStyle = common(shapes, (shape) => shapeStyle(shape).strokeStyle);
  const opacity = common(shapes, (shape) => shapeStyle(shape).opacity);
  const locked = common(shapes, isLocked);
  const allLines = shapes.every((shape) => isLineKind(shape.kind));
  const allLocked = shapes.every(isLocked);
  const widths =
    strokeWidth !== null && !SHAPE_STROKE_WIDTHS.includes(strokeWidth)
      ? [...SHAPE_STROKE_WIDTHS, strokeWidth].sort((a, b) => a - b)
      : SHAPE_STROKE_WIDTHS;
  const opacityPercent = Math.round((opacity ?? 1) * 100);
  const kindLabel = SHAPE_KIND_LABELS[first.kind];

  return (
    <div className="inspector-body shape-inspector" data-testid="shape-inspector">
      <header className="inspector-header">
        <div className="inspector-header__text">
          <p className="inspector-header__kicker">{single ? "Shape" : "Shapes"}</p>
          <h3 className="inspector-header__title">
            {single ? kindLabel : `${shapes.length} shapes`}
          </h3>
          <p className="inspector-header__description">
            A drawing behind the diagram. Simulation, checks and export ignore it.
          </p>
        </div>
      </header>

      {allLines ? null : (
        <Swatches
          label="Fill"
          testId="shape-fill"
          role="fill"
          current={fill}
          onPick={(color) => store().setShapeStyle(ids, { fill: color })}
        />
      )}
      <Swatches
        label={allLines ? "Line colour" : "Outline"}
        testId="shape-stroke"
        role="stroke"
        current={stroke}
        onPick={(color) => store().setShapeStyle(ids, { stroke: color })}
      />

      <section className="shape-inspector__section">
        <label className="shape-inspector__row">
          <span>Width</span>
          <select
            data-testid="shape-stroke-width"
            value={strokeWidth === null ? "" : String(strokeWidth)}
            onChange={(event) => {
              const value = Number(event.target.value);
              if (Number.isFinite(value) && event.target.value !== "") {
                store().setShapeStyle(ids, { strokeWidth: value });
              }
            }}
          >
            {strokeWidth === null ? <option value="">Mixed</option> : null}
            {widths.map((width) => (
              <option key={width} value={String(width)}>
                {width} px
              </option>
            ))}
          </select>
        </label>
        <label className="shape-inspector__row">
          <span>Style</span>
          <select
            data-testid="shape-stroke-style"
            value={strokeStyle ?? ""}
            onChange={(event) => {
              const value = event.target.value as ShapeStrokeStyle;
              if (SHAPE_STROKE_STYLES.includes(value)) {
                store().setShapeStyle(ids, { strokeStyle: value });
              }
            }}
          >
            {strokeStyle === null ? <option value="">Mixed</option> : null}
            {SHAPE_STROKE_STYLES.map((style) => (
              <option key={style} value={style}>
                {SHAPE_STROKE_STYLE_LABELS[style]}
              </option>
            ))}
          </select>
        </label>
        <label className="shape-inspector__row">
          <span>Opacity</span>
          <span className="shape-inspector__opacity">
            <input
              type="range"
              min={10}
              max={100}
              step={5}
              data-testid="shape-opacity"
              aria-valuetext={`${opacityPercent}%`}
              value={opacityPercent}
              onFocus={() => store().beginGesture("shape-opacity")}
              onBlur={() => {
                if (store().gestureKey === "shape-opacity") {
                  store().endGesture();
                }
              }}
              onChange={(event) =>
                store().setShapeStyle(
                  ids,
                  { opacity: Number(event.target.value) / 100 },
                  { coalesce: "shape-opacity" },
                )
              }
            />
            <output>{opacity === null ? "Mixed" : `${opacityPercent}%`}</output>
          </span>
        </label>
      </section>

      {single ? (
        <section className="shape-inspector__section">
          <h4>Label</h4>
          <ShapeLabelField key={first.id} shape={first} />
        </section>
      ) : null}

      <section className="shape-inspector__section">
        <h4>Arrange</h4>
        <div className="shape-inspector__actions">
          {ORDERS.map((order) => (
            <button
              key={order}
              type="button"
              className="button button--compact"
              data-testid={`shape-inspector-order-${order}`}
              disabled={!canReorder(all, ids, order)}
              onClick={() => store().reorderShapes(ids, order)}
            >
              {SHAPE_ORDER_LABELS[order]}
            </button>
          ))}
        </div>
        <label className="shape-inspector__lock">
          <input
            type="checkbox"
            data-testid="shape-inspector-locked"
            checked={locked === true}
            ref={(element) => {
              if (element !== null) {
                element.indeterminate = locked === null;
              }
            }}
            onChange={(event) => store().setShapeLocked(ids, event.target.checked)}
          />
          Locked (no moving, resizing or deleting on the canvas)
        </label>
        <div className="shape-inspector__actions">
          <button
            type="button"
            className="button button--compact"
            data-testid="shape-inspector-duplicate"
            onClick={() => store().duplicateShapes(ids)}
          >
            Duplicate
          </button>
          <button
            type="button"
            className="button button--compact"
            data-testid="shape-inspector-delete"
            disabled={allLocked}
            title={allLocked ? "Unlock the shape to delete it" : undefined}
            onClick={() => store().deleteSelection()}
          >
            {single ? "Delete shape" : "Delete shapes"}
          </button>
        </div>
        {allLocked ? (
          <p className="shape-inspector__hint">Unlock to move, resize or delete on the canvas.</p>
        ) : null}
      </section>
    </div>
  );
}
