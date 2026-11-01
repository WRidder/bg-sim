/**
 * The x-axis control of a plot panel or a dashboard plot card: "Time" or a signal, as a native
 * select (keyboard accessible), and a drop target for a signal dragged from the Signals tab.
 * With a signal chosen, an "1:1" toggle keeps the axes at equal aspect.
 *
 * The select lists the panel's own signals first (picking one moves it from the y list to the x
 * axis) and then every other recorded signal. The option elements are memoised per manifest, so
 * the cursor re-renders of the plot dock do not rebuild thousands of options.
 */

import { memo, useMemo, useState, type DragEvent } from "react";

import type { RunSignal } from "../contracts/run-manifest";
import { readSignalDrag, SIGNAL_DRAG_MIME } from "./signalDnd";

const TIME = "";

function optionLabel(signal: RunSignal | undefined, id: string): string {
  const unit = signal?.unit?.trim() ?? "";
  return unit.length > 0 ? `${id} [${unit}]` : id;
}

export interface XAxisControlProps {
  /** For the labels: "Panel 2", "card Phase portrait". */
  ownerLabel: string;
  /** The current x signal; undefined is time. */
  x: string | undefined;
  /** The owner's y signals, offered first. */
  ownSignals: readonly string[];
  /** Every recorded signal of the run (empty before a run). */
  allSignals: readonly RunSignal[];
  equalAspect: boolean;
  onChange: (x: string | null) => void;
  onEqualAspect: (on: boolean) => void;
  testId?: string;
}

const AllSignalOptions = memo(function AllSignalOptions({
  signals,
}: {
  signals: readonly RunSignal[];
}) {
  return (
    <>
      {signals.map((signal) => (
        <option key={signal.id} value={signal.id}>
          {optionLabel(signal, signal.id)}
        </option>
      ))}
    </>
  );
});

export function XAxisControl({
  ownerLabel,
  x,
  ownSignals,
  allSignals,
  equalAspect,
  onChange,
  onEqualAspect,
  testId = "plot-x-axis",
}: XAxisControlProps) {
  const [dragOver, setDragOver] = useState(false);
  const byId = useMemo(() => new Map(allSignals.map((signal) => [signal.id, signal])), [allSignals]);
  const own = useMemo(() => {
    const ids = x === undefined ? [...ownSignals] : [x, ...ownSignals.filter((id) => id !== x)];
    return [...new Set(ids)];
  }, [ownSignals, x]);
  const others = useMemo(() => {
    const taken = new Set(own);
    return allSignals.filter((signal) => !taken.has(signal.id));
  }, [allSignals, own]);

  const isSignalDrag = (event: DragEvent<HTMLElement>): boolean =>
    Array.from(event.dataTransfer.types).includes(SIGNAL_DRAG_MIME);

  return (
    <span
      className={`plot-x-axis${dragOver ? " is-dragover" : ""}${x !== undefined ? " is-xy" : ""}`}
      data-testid={`${testId}-zone`}
      title="Drop a signal here to plot the others against it"
      onDragOver={(event) => {
        if (!isSignalDrag(event)) return;
        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = "copy";
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(event) => {
        if (!isSignalDrag(event)) return;
        event.preventDefault();
        event.stopPropagation();
        setDragOver(false);
        const id = readSignalDrag(event);
        if (id !== null) onChange(id);
      }}
    >
      <label className="plot-x-axis__label">
        <span>x</span>
        <select
          value={x ?? TIME}
          onChange={(event) => onChange(event.target.value === TIME ? null : event.target.value)}
          aria-label={`X axis of ${ownerLabel}`}
          title="Plot against time, or against a signal (an XY plot)"
          data-testid={testId}
        >
          <option value={TIME}>Time (t)</option>
          {own.length > 0 ? (
            <optgroup label="Signals of this plot">
              {own.map((id) => (
                <option key={id} value={id}>
                  {optionLabel(byId.get(id), id)}
                </option>
              ))}
            </optgroup>
          ) : null}
          {others.length > 0 ? (
            <optgroup label="Other signals">
              <AllSignalOptions signals={others} />
            </optgroup>
          ) : null}
        </select>
      </label>
      {x !== undefined ? (
        <button
          type="button"
          className={`plot-x-axis__aspect${equalAspect ? " is-on" : ""}`}
          aria-pressed={equalAspect}
          aria-label={`1:1 equal aspect for ${ownerLabel}`}
          title="Equal aspect: one unit is as long on both axes (a circle stays round)"
          data-testid={`${testId}-aspect`}
          onClick={() => onEqualAspect(!equalAspect)}
        >
          1:1
        </button>
      ) : null}
    </span>
  );
}
