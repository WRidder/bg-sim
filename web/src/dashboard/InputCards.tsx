/**
 * The input cards of the dashboard (DASHBOARD_PLAN.md): Number, Slider, Knob, Toggle and
 * Select. Each binds one block parameter (`<instance path>/<param>`) and holds an override value
 * that the next run uses for the whole run (`parameterOverrides`); the model's own parameter is
 * not changed. Every input is keyboard operable.
 */

import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

import type { ModelDashboardCard } from "../contracts/model";
import { parseLiveValue } from "../inspector/liveEdit";
import { formatNumber } from "../plot/format";
import { useRunStore } from "../plot/runStore";
import { beginValueGesture, endValueGesture, setCardParameter, setCardValue } from "./actions";
import {
  clampToRange,
  effectiveInputValue,
  fractionOf,
  GLOBAL_TARGET_PREFIX,
  inputRange,
  snapToStep,
  typedValue,
  type InputRange,
  type ParameterInfo,
} from "./model";

export interface InputCardProps {
  card: ModelDashboardCard;
  info: ParameterInfo | null;
  titleId: string;
}

function unitOf(card: ModelDashboardCard, info: ParameterInfo | null): string {
  return card.options?.unit ?? info?.decl.unit ?? "";
}

function show(value: number, card: ModelDashboardCard): string {
  return card.options?.decimals === undefined ? formatNumber(value) : value.toFixed(card.options.decimals);
}

/**
 * "next run" when the value differs from what the current run uses, "model" when not overridden. The
 * current run's overrides are the ones this editor sent with it; a followed run (a replay) has only its
 * manifest's.
 */
function useOverrideState(card: ModelDashboardCard, info: ParameterInfo | null): string | null {
  const used = useRunStore((state) =>
    (state.sentOverrides ?? state.manifest?.parameterOverrides)?.find((entry) => entry.target === card.parameter)?.value,
  );
  const hasRun = useRunStore((state) => state.sentOverrides !== null || state.manifest !== null);
  if (card.value === undefined) {
    return used !== undefined ? "next run: model value" : null;
  }
  if (!hasRun) {
    return null;
  }
  const wanted = typedValue(card.value, info);
  // a manifest may carry a toggle as 1/0
  return used !== undefined && Number(used) === Number(wanted) ? null : "applies at the next run";
}

/**
 * A block parameter whose model expression reads global parameters (`Ref/final = h_step`):
 * say so, with the value the globals give it, and offer to bind the card to the global itself
 * when the expression is just that global's name (a card on the global moves every parameter
 * that uses it; an override of the block parameter replaces the expression for one block).
 */
function GlobalNote({ card, info }: { card: ModelDashboardCard; info: ParameterInfo }) {
  const single = info.drivenBy.length === 1 && info.modelText.trim() === info.drivenBy[0] ? info.drivenBy[0] : null;
  const value = info.modelValue === null ? "" : ` = ${formatNumber(info.modelValue)}`;
  return (
    <span className="dash-input__driven" data-testid={`dash-driven-${card.id}`}>
      <span title="This block parameter is an expression of global parameters; the card overrides the block parameter only">
        driven by {info.drivenBy.map((name) => `global ${name}`).join(", ")}
        {value}
      </span>
      {single !== null ? (
        <button
          type="button"
          className="dash-link"
          data-testid={`dash-bind-global-${card.id}`}
          onClick={() => setCardParameter(card.id, `${GLOBAL_TARGET_PREFIX}${single}`)}
          aria-label={`Bind this card to the global parameter ${single}`}
        >
          Bind to global {single}
        </button>
      ) : null}
    </span>
  );
}

function Footer({ card, info }: { card: ModelDashboardCard; info: ParameterInfo | null }) {
  const pending = useOverrideState(card, info);
  return (
    <div className="dash-input__footer">
      <span className="dash-input__model" title="The value written in the model">
        model {info?.modelText ?? "—"}
      </span>
      {info !== null && info.kind === "block" && info.drivenBy.length > 0 ? (
        <GlobalNote card={card} info={info} />
      ) : null}
      {pending !== null ? <span className="dash-input__pending">{pending}</span> : null}
      {card.value !== undefined ? (
        <button
          type="button"
          className="dash-link"
          onClick={() => setCardValue(card.id, null)}
          aria-label={`Use model value for ${card.parameter ?? "the parameter"}`}
        >
          Use model value
        </button>
      ) : null}
    </div>
  );
}

function Unbound() {
  return <p className="dash-card__hint">Pick a block parameter in the card settings.</p>;
}

// ------------------------------------------------------------------ number

export function NumberCard({ card, info, titleId }: InputCardProps) {
  const current = effectiveInputValue(card, info);
  const shown = typeof current === "boolean" ? (current ? "1" : "0") : current === null ? "" : String(current);
  const [text, setText] = useState(shown);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setText(shown), [shown]);
  if (card.parameter === undefined) {
    return <Unbound />;
  }
  const commit = (): void => {
    if (text === shown) {
      setError(null);
      return;
    }
    const parsed = parseLiveValue(text);
    if (!parsed.ok) {
      setError(parsed.message);
      return;
    }
    const decl = info?.decl;
    if (decl?.min != null && parsed.value < decl.min) {
      setError(`The value must be at least ${decl.min}.`);
      return;
    }
    if (decl?.max != null && parsed.value > decl.max) {
      setError(`The value must be at most ${decl.max}.`);
      return;
    }
    setError(null);
    setCardValue(card.id, parsed.value);
  };
  const unit = unitOf(card, info);
  const errorId = `${titleId}-error`;
  return (
    <div className="dash-input dash-number">
      <div className="dash-number__row">
        <input
          className="dash-number__field"
          type="text"
          inputMode="decimal"
          value={text}
          aria-labelledby={titleId}
          aria-invalid={error !== null}
          aria-describedby={error !== null ? errorId : undefined}
          data-testid={`dash-number-${card.id}`}
          onChange={(event) => setText(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              commit();
            } else if (event.key === "Escape") {
              setText(shown);
              setError(null);
            }
          }}
        />
        {unit.length > 0 ? <span className="dash-input__unit">{unit}</span> : null}
      </div>
      {error !== null ? (
        <p className="dash-input__error" id={errorId} role="alert">
          {error}
        </p>
      ) : null}
      <Footer card={card} info={info} />
    </div>
  );
}

// ------------------------------------------------------------------ slider

export function SliderCard({ card, info, titleId }: InputCardProps) {
  if (card.parameter === undefined) {
    return <Unbound />;
  }
  const range = inputRange(card, info);
  const current = effectiveInputValue(card, info);
  const value = typeof current === "number" ? clampToRange(current, range) : range.min;
  const unit = unitOf(card, info);
  const key = `dashboard-value-${card.id}`;
  return (
    <div className="dash-input dash-slider">
      <div className="dash-slider__value" aria-hidden="true">
        {show(value, card)}
        {unit.length > 0 ? <span className="dash-input__unit"> {unit}</span> : null}
      </div>
      <input
        type="range"
        className="dash-slider__range"
        min={range.min}
        max={range.max}
        step={range.step}
        value={value}
        aria-labelledby={titleId}
        aria-valuetext={`${show(value, card)} ${unit}`.trim()}
        data-testid={`dash-slider-${card.id}`}
        onPointerDown={() => {
          beginValueGesture(key);
          // the pointer may be released outside the slider
          window.addEventListener("pointerup", () => endValueGesture(), { once: true });
        }}
        onPointerCancel={() => endValueGesture()}
        onChange={(event) => setCardValue(card.id, Number(event.target.value), key)}
      />
      <div className="dash-slider__limits" aria-hidden="true">
        <span>{formatNumber(range.min)}</span>
        <span>{formatNumber(range.max)}</span>
      </div>
      <Footer card={card} info={info} />
    </div>
  );
}

// -------------------------------------------------------------------- knob

const KNOB_START = 135;
const KNOB_SWEEP = 270;
/** Pixels of vertical drag for the whole range. */
const KNOB_DRAG_PX = 200;

/** The knob's next value for a key, or null when the key is not a knob key. */
export function knobKeyValue(key: string, value: number, range: InputRange): number | null {
  switch (key) {
    case "ArrowUp":
    case "ArrowRight":
      return snapToStep(value + range.step, range);
    case "ArrowDown":
    case "ArrowLeft":
      return snapToStep(value - range.step, range);
    case "PageUp":
      return snapToStep(value + range.step * 10, range);
    case "PageDown":
      return snapToStep(value - range.step * 10, range);
    case "Home":
      return range.min;
    case "End":
      return range.max;
    default:
      return null;
  }
}

function arcPath(fraction: number): string {
  const r = 34;
  const from = KNOB_START;
  const to = KNOB_START + KNOB_SWEEP * fraction;
  const point = (degrees: number): string => {
    const radians = (degrees * Math.PI) / 180;
    return `${(50 + r * Math.cos(radians)).toFixed(2)} ${(50 + r * Math.sin(radians)).toFixed(2)}`;
  };
  return `M ${point(from)} A ${r} ${r} 0 ${to - from > 180 ? 1 : 0} 1 ${point(to)}`;
}

export function KnobCard({ card, info, titleId }: InputCardProps) {
  const knobRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ y: number; value: number } | null>(null);
  const range = inputRange(card, info);
  const current = effectiveInputValue(card, info);
  const value = typeof current === "number" ? clampToRange(current, range) : range.min;
  const valueRef = useRef(value);
  valueRef.current = value;
  const rangeRef = useRef(range);
  rangeRef.current = range;
  const key = `dashboard-value-${card.id}`;

  // React's wheel listener is passive; the knob must keep the page from scrolling.
  useEffect(() => {
    const element = knobRef.current;
    if (element === null) {
      return;
    }
    const onWheel = (event: WheelEvent): void => {
      event.preventDefault();
      const r = rangeRef.current;
      const direction = event.deltaY < 0 ? 1 : -1;
      const factor = event.shiftKey ? 10 : 1;
      setCardValue(card.id, snapToStep(valueRef.current + direction * factor * r.step, r), key);
    };
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => element.removeEventListener("wheel", onWheel);
  }, [card.id, key, card.parameter]);

  if (card.parameter === undefined) {
    return <Unbound />;
  }
  const unit = unitOf(card, info);
  const fraction = fractionOf(value, range.min, range.max);
  const angle = KNOB_START + KNOB_SWEEP * fraction;

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>): void => {
    event.currentTarget.setPointerCapture(event.pointerId);
    event.currentTarget.focus();
    drag.current = { y: event.clientY, value };
    beginValueGesture(key);
  };
  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>): void => {
    const start = drag.current;
    if (start === null) {
      return;
    }
    const dy = start.y - event.clientY;
    const scale = event.shiftKey ? 0.1 : 1;
    const next = snapToStep(start.value + (dy * scale * (range.max - range.min)) / KNOB_DRAG_PX, range);
    if (next !== valueRef.current) {
      setCardValue(card.id, next, key);
    }
  };
  const onPointerUp = (): void => {
    drag.current = null;
    endValueGesture();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    const next = knobKeyValue(event.key, value, range);
    if (next === null) {
      return;
    }
    event.preventDefault();
    setCardValue(card.id, next);
  };

  return (
    <div className="dash-input dash-knob">
      <div
        ref={knobRef}
        className="dash-knob__dial"
        role="slider"
        tabIndex={0}
        aria-labelledby={titleId}
        aria-valuemin={range.min}
        aria-valuemax={range.max}
        aria-valuenow={value}
        aria-valuetext={`${show(value, card)} ${unit}`.trim()}
        aria-orientation="vertical"
        data-testid={`dash-knob-${card.id}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onKeyDown={onKeyDown}
      >
        <svg viewBox="0 0 100 100" aria-hidden="true">
          <path d={arcPath(1)} className="dash-knob__track" />
          <path d={arcPath(fraction)} className="dash-knob__arc" />
          <circle cx={50} cy={50} r={24} className="dash-knob__cap" />
          <line
            x1={50 + 10 * Math.cos((angle * Math.PI) / 180)}
            y1={50 + 10 * Math.sin((angle * Math.PI) / 180)}
            x2={50 + 22 * Math.cos((angle * Math.PI) / 180)}
            y2={50 + 22 * Math.sin((angle * Math.PI) / 180)}
            className="dash-knob__pointer"
          />
        </svg>
        <span className="dash-knob__value">
          {show(value, card)}
          {unit.length > 0 ? <span className="dash-input__unit"> {unit}</span> : null}
        </span>
      </div>
      <Footer card={card} info={info} />
    </div>
  );
}

// ------------------------------------------------------------------ toggle

export function ToggleCard({ card, info, titleId }: InputCardProps) {
  if (card.parameter === undefined) {
    return <Unbound />;
  }
  const current = effectiveInputValue(card, info);
  const on = typeof current === "boolean" ? current : current !== null && current !== 0;
  return (
    <div className="dash-input dash-toggle">
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-labelledby={titleId}
        className={`dash-toggle__switch${on ? " is-on" : ""}`}
        data-testid={`dash-toggle-${card.id}`}
        onClick={() => setCardValue(card.id, !on)}
      >
        <span className="dash-toggle__thumb" aria-hidden="true" />
        <span className="dash-toggle__label">{on ? "On" : "Off"}</span>
      </button>
      <Footer card={card} info={info} />
    </div>
  );
}

// ------------------------------------------------------------------ select

export function SelectCard({ card, info, titleId }: InputCardProps) {
  if (card.parameter === undefined) {
    return <Unbound />;
  }
  const options = info?.decl.options ?? [];
  const current = effectiveInputValue(card, info);
  const value = typeof current === "number" ? String(Math.round(current)) : "";
  if (options.length === 0) {
    return (
      <p className="dash-card__hint">
        {card.parameter} has no options; use a Number, Slider or Knob card.
      </p>
    );
  }
  return (
    <div className="dash-input dash-select">
      <select
        className="dash-select__field"
        value={value}
        aria-labelledby={titleId}
        data-testid={`dash-select-${card.id}`}
        onChange={(event) => setCardValue(card.id, Number(event.target.value))}
      >
        {options.map((label, position) => (
          <option key={label} value={String(position)}>
            {position} · {label}
          </option>
        ))}
      </select>
      <Footer card={card} info={info} />
    </div>
  );
}
