/**
 * The settings popover of one dashboard card (DASHBOARD_PLAN.md): title, size, binding (a
 * searchable signal list for display cards, a parameter picker for input cards) and the
 * kind's options (range, decimals, unit label, zones, threshold, orientation, sparkline, text).
 * Every change is a document edit, so it is undoable and saved with the model.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { useDialogFocus } from "../app/useDialogFocus";
import type {
  DashboardZoneTone,
  ModelDashboardCard,
  ModelDashboardZone,
} from "../contracts/model";
import type { RunSignal } from "../contracts/run-manifest";
import { parseLiveValue } from "../inspector/liveEdit";
import {
  setCardEqualAspect,
  setCardOptions,
  setCardParameter,
  setCardSignals,
  setCardSize,
  setCardTitle,
  setCardX,
} from "./actions";
import {
  CARD_SIZES,
  inputKindsFor,
  isDisplayKind,
  isInputKind,
  kindInfo,
  type ParameterInfo,
} from "./model";

export interface CardSettingsProps {
  card: ModelDashboardCard;
  signals: readonly RunSignal[];
  parameters: readonly ParameterInfo[];
  /** Parameters bound by other cards. */
  taken: ReadonlySet<string>;
  onClose: () => void;
}

/** A number field that commits on blur/Enter; empty clears the option. */
function NumberOption({
  id,
  label,
  value,
  onCommit,
  integer = false,
}: {
  id: string;
  label: string;
  value: number | undefined;
  onCommit: (value: number | undefined) => void;
  integer?: boolean;
}) {
  const shown = value === undefined ? "" : String(value);
  const [text, setText] = useState(shown);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setText(shown), [shown]);
  const commit = (): void => {
    if (text.trim() === shown) {
      return;
    }
    if (text.trim().length === 0) {
      setError(null);
      onCommit(undefined);
      return;
    }
    const parsed = parseLiveValue(text);
    if (!parsed.ok || (integer && !Number.isInteger(parsed.value))) {
      setError(integer ? "Enter a whole number." : parsed.ok ? null : parsed.message);
      return;
    }
    setError(null);
    onCommit(parsed.value);
  };
  return (
    <div className="dash-settings__field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        inputMode="decimal"
        value={text}
        aria-invalid={error !== null}
        onChange={(event) => setText(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") commit();
        }}
      />
      {error !== null ? <span className="dash-input__error">{error}</span> : null}
    </div>
  );
}

function SignalPicker({
  card,
  signals,
}: {
  card: ModelDashboardCard;
  signals: readonly RunSignal[];
}) {
  const [query, setQuery] = useState("");
  const bound = card.signals ?? [];
  const multi = card.kind === "plot";
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return signals
      .filter((signal) => q.length === 0 || signal.id.toLowerCase().includes(q))
      .slice(0, 60);
  }, [signals, query]);
  const choose = (id: string): void => {
    if (multi) {
      setCardSignals(card.id, bound.includes(id) ? bound.filter((s) => s !== id) : [...bound, id]);
    } else {
      setCardSignals(card.id, [id]);
    }
  };
  const typed = query.trim();
  return (
    <fieldset className="dash-settings__group">
      <legend>{multi ? "Signals" : "Signal"}</legend>
      {bound.length > 0 ? (
        <ul className="dash-settings__chips">
          {bound.map((id) => (
            <li key={id}>
              <code>{id}</code>
              <button
                type="button"
                className="dash-icon-button"
                aria-label={`Unbind ${id}`}
                onClick={() => setCardSignals(card.id, bound.filter((s) => s !== id))}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <input
        type="search"
        className="dash-settings__search"
        placeholder={signals.length > 0 ? "Search the run's signals…" : "Type a signal id, e.g. Motor1/i"}
        aria-label="Search signals"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && typed.length > 0 && typed.includes("/")) {
            choose(typed);
            setQuery("");
          }
        }}
      />
      {signals.length === 0 ? (
        <p className="dash-card__hint">
          Run the model to list its signals, or type an id and press Enter.
        </p>
      ) : (
        <ul className="dash-settings__list" role="listbox" aria-label="Signals" aria-multiselectable={multi}>
          {matches.map((signal) => (
            <li
              key={signal.id}
              role="option"
              aria-selected={bound.includes(signal.id)}
              tabIndex={0}
              className={bound.includes(signal.id) ? "is-selected" : undefined}
              onClick={() => choose(signal.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  choose(signal.id);
                }
              }}
            >
              <code>{signal.id}</code>
              {signal.unit ? <span className="dash-input__unit"> {signal.unit}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </fieldset>
  );
}

/** Plot cards: the x axis (time or a signal, an XY plot) and the equal-aspect switch. */
function PlotAxisSettings({
  card,
  signals,
}: {
  card: ModelDashboardCard;
  signals: readonly RunSignal[];
}) {
  const bound = card.signals ?? [];
  const own = card.x === undefined ? bound : [card.x, ...bound.filter((id) => id !== card.x)];
  const others = signals.filter((signal) => !own.includes(signal.id));
  const unitOf = (id: string): string => {
    const unit = signals.find((signal) => signal.id === id)?.unit?.trim() ?? "";
    return unit.length > 0 ? `${id} [${unit}]` : id;
  };
  const selectId = `${card.id}-x-axis`;
  return (
    <fieldset className="dash-settings__group">
      <legend>X axis</legend>
      <div className="dash-settings__row">
        <div className="dash-settings__field">
          <label htmlFor={selectId}>Plot against</label>
          <select
            id={selectId}
            value={card.x ?? ""}
            data-testid="dash-settings-x"
            onChange={(event) => setCardX(card.id, event.target.value === "" ? null : event.target.value)}
          >
            <option value="">Time (t)</option>
            {own.length > 0 ? (
              <optgroup label="Signals of this card">
                {own.map((id) => (
                  <option key={id} value={id}>
                    {unitOf(id)}
                  </option>
                ))}
              </optgroup>
            ) : null}
            {others.length > 0 ? (
              <optgroup label="Other signals">
                {others.map((signal) => (
                  <option key={signal.id} value={signal.id}>
                    {unitOf(signal.id)}
                  </option>
                ))}
              </optgroup>
            ) : null}
          </select>
        </div>
      </div>
      <label className="dash-settings__check">
        <input
          type="checkbox"
          checked={card.equalAspect === true}
          disabled={card.x === undefined}
          data-testid="dash-settings-equal-aspect"
          onChange={(event) => setCardEqualAspect(card.id, event.target.checked)}
        />
        Equal aspect (one unit as long on both axes)
      </label>
      <p className="dash-card__hint">
        {card.x === undefined
          ? "Pick a signal to draw the card's signals against it (a phase portrait or a force-deflection loop)."
          : `The card's signals are drawn against ${card.x}, sample by sample.`}
      </p>
    </fieldset>
  );
}

function ParameterPicker({
  card,
  parameters,
  taken,
}: {
  card: ModelDashboardCard;
  parameters: readonly ParameterInfo[];
  taken: ReadonlySet<string>;
}) {
  const [query, setQuery] = useState("");
  const suitable = parameters.filter((p) => inputKindsFor(p.decl).includes(card.kind));
  const q = query.trim().toLowerCase();
  const matches = suitable.filter((p) => q.length === 0 || p.target.toLowerCase().includes(q)).slice(0, 60);
  return (
    <fieldset className="dash-settings__group">
      <legend>Parameter</legend>
      {card.parameter !== undefined ? (
        <p className="dash-settings__current">
          Bound to <code>{card.parameter}</code>
        </p>
      ) : null}
      <input
        type="search"
        className="dash-settings__search"
        placeholder="Search parameters, e.g. Motor1/R"
        aria-label="Search parameters"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      {suitable.length === 0 ? (
        <p className="dash-card__hint">
          No parameter of this model suits a {kindInfo(card.kind).label} card.
        </p>
      ) : (
        <ul className="dash-settings__list" role="listbox" aria-label="Parameters">
          {matches.map((p) => {
            const busy = taken.has(p.target) && p.target !== card.parameter;
            return (
              <li
                key={p.target}
                role="option"
                aria-selected={p.target === card.parameter}
                aria-disabled={busy}
                tabIndex={busy ? -1 : 0}
                className={`${p.target === card.parameter ? "is-selected" : ""}${busy ? " is-disabled" : ""}`}
                title={busy ? "Bound by another input card or schedule column" : p.decl.description}
                onClick={() => {
                  if (!busy) setCardParameter(card.id, p.target);
                }}
                onKeyDown={(event) => {
                  if (!busy && (event.key === "Enter" || event.key === " ")) {
                    event.preventDefault();
                    setCardParameter(card.id, p.target);
                  }
                }}
              >
                <code>{p.target}</code>
                <span className="dash-input__unit">
                  {" "}
                  = {p.modelText}
                  {p.decl.unit ? ` ${p.decl.unit}` : ""}
                  {busy ? " · bound" : ""}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </fieldset>
  );
}

const TONES: DashboardZoneTone[] = ["good", "warn", "bad", "info"];

function ZonesEditor({ card }: { card: ModelDashboardCard }) {
  const zones = card.options?.zones ?? [];
  const save = (next: ModelDashboardZone[]): void => setCardOptions(card.id, { zones: next });
  return (
    <fieldset className="dash-settings__group">
      <legend>Colour zones</legend>
      {zones.map((zone, index) => (
        <div className="dash-settings__zone" key={index}>
          <NumberOption
            id={`${card.id}-zone-${index}-from`}
            label="From"
            value={zone.from}
            onCommit={(v) => save(zones.map((z, i) => (i === index ? { ...z, from: v ?? 0 } : z)))}
          />
          <NumberOption
            id={`${card.id}-zone-${index}-to`}
            label="To"
            value={zone.to}
            onCommit={(v) => save(zones.map((z, i) => (i === index ? { ...z, to: v ?? 0 } : z)))}
          />
          <div className="dash-settings__field">
            <label htmlFor={`${card.id}-zone-${index}-tone`}>Colour</label>
            <select
              id={`${card.id}-zone-${index}-tone`}
              value={zone.tone}
              onChange={(event) =>
                save(zones.map((z, i) => (i === index ? { ...z, tone: event.target.value as DashboardZoneTone } : z)))
              }
            >
              {TONES.map((tone) => (
                <option key={tone} value={tone}>
                  {tone}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            className="dash-icon-button"
            aria-label={`Remove zone ${index + 1}`}
            onClick={() => save(zones.filter((_, i) => i !== index))}
          >
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        className="dash-button"
        onClick={() => {
          const lo = card.options?.min ?? 0;
          const hi = card.options?.max ?? 1;
          save([...zones, { from: lo + 0.8 * (hi - lo), to: hi, tone: "warn" }]);
        }}
      >
        + Zone
      </button>
    </fieldset>
  );
}

export function CardSettings({ card, signals, parameters, taken, onClose }: CardSettingsProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  useDialogFocus(true, dialogRef, onClose);
  const kind = card.kind;
  const options = card.options ?? {};
  const hasRange = ["gauge", "bar", "slider", "knob"].includes(kind);
  const hasDecimals = ["value", "gauge", "bar", "number", "slider", "knob"].includes(kind);
  const hasUnit = isDisplayKind(kind) ? kind !== "text" && kind !== "plot" : isInputKind(kind);
  const hasZones = ["value", "gauge", "bar"].includes(kind);
  const titleId = `dash-settings-title-${card.id}`;
  const [title, setTitle] = useState(card.title ?? "");

  return (
    <div className="dash-settings__backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div
        className="dash-settings"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={dialogRef}
        tabIndex={-1}
        data-testid="dash-settings"
      >
        <header className="dash-settings__header">
          <h2 id={titleId}>{kindInfo(kind).label} card settings</h2>
          <button type="button" className="dash-icon-button" aria-label="Close the settings" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="dash-settings__body">
          <div className="dash-settings__row">
            <div className="dash-settings__field">
              <label htmlFor={`${card.id}-title`}>Title</label>
              <input
                id={`${card.id}-title`}
                type="text"
                value={title}
                placeholder="(the binding)"
                onChange={(event) => setTitle(event.target.value)}
                onBlur={() => setCardTitle(card.id, title)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") setCardTitle(card.id, title);
                }}
              />
            </div>
            <div className="dash-settings__field">
              <label htmlFor={`${card.id}-size`}>Size</label>
              <select
                id={`${card.id}-size`}
                value={card.size}
                onChange={(event) => setCardSize(card.id, event.target.value as ModelDashboardCard["size"])}
              >
                {CARD_SIZES.map((size) => (
                  <option key={size} value={size}>
                    {size.replace("x", " × ")}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {isDisplayKind(kind) && kind !== "text" ? <SignalPicker card={card} signals={signals} /> : null}
          {kind === "plot" ? <PlotAxisSettings card={card} signals={signals} /> : null}
          {isInputKind(kind) ? <ParameterPicker card={card} parameters={parameters} taken={taken} /> : null}

          {hasRange || hasDecimals || hasUnit ? (
            <div className="dash-settings__row">
              {hasRange ? (
                <>
                  <NumberOption id={`${card.id}-min`} label="Min" value={options.min} onCommit={(v) => setCardOptions(card.id, { min: v })} />
                  <NumberOption id={`${card.id}-max`} label="Max" value={options.max} onCommit={(v) => setCardOptions(card.id, { max: v })} />
                </>
              ) : null}
              {kind === "slider" || kind === "knob" ? (
                <NumberOption
                  id={`${card.id}-step`}
                  label="Step"
                  value={options.step}
                  onCommit={(v) => setCardOptions(card.id, { step: v !== undefined && v > 0 ? v : undefined })}
                />
              ) : null}
              {hasDecimals ? (
                <NumberOption
                  id={`${card.id}-decimals`}
                  label="Decimals"
                  integer
                  value={options.decimals}
                  onCommit={(v) =>
                    setCardOptions(card.id, { decimals: v === undefined ? undefined : Math.max(0, Math.min(12, v)) })
                  }
                />
              ) : null}
              {hasUnit ? (
                <div className="dash-settings__field">
                  <label htmlFor={`${card.id}-unit`}>Unit label</label>
                  <input
                    id={`${card.id}-unit`}
                    type="text"
                    defaultValue={options.unit ?? ""}
                    placeholder="(from the model)"
                    onBlur={(event) =>
                      setCardOptions(card.id, { unit: event.target.value.length === 0 ? undefined : event.target.value })
                    }
                  />
                </div>
              ) : null}
            </div>
          ) : null}

          {kind === "indicator" ? (
            <div className="dash-settings__row">
              <NumberOption
                id={`${card.id}-threshold`}
                label="Threshold"
                value={options.threshold}
                onCommit={(v) => setCardOptions(card.id, { threshold: v })}
              />
              <div className="dash-settings__field">
                <label htmlFor={`${card.id}-onwhen`}>On when</label>
                <select
                  id={`${card.id}-onwhen`}
                  value={options.onWhen ?? "above"}
                  onChange={(event) => setCardOptions(card.id, { onWhen: event.target.value as "above" | "below" })}
                >
                  <option value="above">above the threshold</option>
                  <option value="below">below the threshold</option>
                </select>
              </div>
            </div>
          ) : null}

          {kind === "bar" ? (
            <div className="dash-settings__field">
              <label htmlFor={`${card.id}-orientation`}>Orientation</label>
              <select
                id={`${card.id}-orientation`}
                value={options.orientation ?? "vertical"}
                onChange={(event) =>
                  setCardOptions(card.id, { orientation: event.target.value as "vertical" | "horizontal" })
                }
              >
                <option value="vertical">vertical</option>
                <option value="horizontal">horizontal</option>
              </select>
            </div>
          ) : null}

          {kind === "value" ? (
            <label className="dash-settings__check">
              <input
                type="checkbox"
                checked={options.sparkline === true}
                onChange={(event) => setCardOptions(card.id, { sparkline: event.target.checked ? true : undefined })}
              />
              Sparkline
            </label>
          ) : null}

          {kind === "text" ? (
            <>
              <div className="dash-settings__field">
                <label htmlFor={`${card.id}-text`}>Text</label>
                <textarea
                  id={`${card.id}-text`}
                  rows={6}
                  defaultValue={options.text ?? ""}
                  onBlur={(event) => setCardOptions(card.id, { text: event.target.value })}
                />
              </div>
              <label className="dash-settings__check">
                <input
                  type="checkbox"
                  checked={options.markdown !== false}
                  onChange={(event) => setCardOptions(card.id, { markdown: event.target.checked })}
                />
                Markdown
              </label>
            </>
          ) : null}

          {hasZones ? <ZonesEditor card={card} /> : null}
        </div>
      </div>
    </div>
  );
}
