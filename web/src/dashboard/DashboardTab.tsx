/**
 * The Dashboard centre tab (plan/DASHBOARD_PLAN.md): Home Assistant style cards in a plain CSS
 * grid. Use mode shows the cards (display cards follow the run and the inspect time; input
 * cards and schedule tables set the next run's parameter overrides). Edit mode adds, removes,
 * reorders (drag or the move buttons), resizes and configures cards.
 */

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
  type ReactNode,
} from "react";

import type { DashboardCardKind, ModelDashboardCard } from "../contracts/model";
import { useCatalogStore } from "../library/catalogStore";
import { readSignalDrag, SIGNAL_DRAG_MIME } from "../plot/signalDnd";
import { useDocumentStore } from "../state/documentStore";
import {
  addCard,
  dropSignalOnCard,
  moveCardTo,
  removeCard,
  setAutoRerun,
  setCardSize,
} from "./actions";
import { CardSettings } from "./CardSettings";
import { useDashboardUi } from "./dashboardUi";
import {
  BarCard,
  GaugeCard,
  IndicatorCard,
  PlotCard,
  TextCard,
  ValueCard,
  type DisplayCardProps,
} from "./DisplayCards";
import {
  KnobCard,
  NumberCard,
  SelectCard,
  SliderCard,
  ToggleCard,
  type InputCardProps,
} from "./InputCards";
import {
  boundParameters,
  CARD_KINDS,
  CARD_SIZES,
  cardTitle,
  dashboardRunInputs,
  findParameter,
  isDisplayKind,
  isInputKind,
  listParameters,
  sizeSpan,
  type DashboardIssue,
} from "./model";
import { ScheduleCard } from "./ScheduleCard";
import { useAutoRerun } from "./useAutoRerun";
import { useDashboardSignalSubscription, useRunSeries, type RunSeries } from "./useRunSeries";
import "./dashboard.css";

const CARD_DRAG_MIME = "application/x-bgsim-dashboard-card";
/** Minimum column width of the grid, in CSS pixels. */
const COLUMN_WIDTH = 170;

const DISPLAY: Partial<Record<DashboardCardKind, (props: DisplayCardProps) => ReactNode>> = {
  value: ValueCard,
  gauge: GaugeCard,
  bar: BarCard,
  indicator: IndicatorCard,
  plot: PlotCard,
  text: TextCard,
};

const INPUT: Partial<Record<DashboardCardKind, (props: InputCardProps) => ReactNode>> = {
  number: NumberCard,
  slider: SliderCard,
  knob: KnobCard,
  toggle: ToggleCard,
  select: SelectCard,
};

function useGridColumns(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [columns, setColumns] = useState(4);
  useEffect(() => {
    const element = ref.current;
    if (element === null) {
      return;
    }
    const measure = (): void => {
      const width = element.clientWidth;
      setColumns(Math.max(1, Math.min(8, Math.floor((width + 12) / COLUMN_WIDTH))));
    };
    measure();
    if (typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, columns];
}

function AddCardMenu({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const groups: [string, typeof CARD_KINDS][] = [
    ["Display", CARD_KINDS.filter((k) => k.role === "display")],
    ["Input (for the next run)", CARD_KINDS.filter((k) => k.role !== "display")],
  ];
  return (
    <div className="dash-add-menu" ref={ref} role="menu" aria-label="Add a card" data-testid="dash-add-menu">
      {groups.map(([label, kinds]) => (
        <div key={label} className="dash-add-menu__group" role="group" aria-label={label}>
          <div className="dash-add-menu__label" aria-hidden="true">
            {label}
          </div>
          {kinds.map((info) => (
            <button
              key={info.kind}
              type="button"
              role="menuitem"
              className="dash-add-menu__item"
              data-testid={`dash-add-${info.kind}`}
              onClick={() => {
                const id = addCard(info.kind);
                onClose();
                if (info.kind !== "text") {
                  useDashboardUi.getState().openSettings(id);
                }
              }}
            >
              <span className="dash-add-menu__name">{info.label}</span>
              <span className="dash-add-menu__description">{info.description}</span>
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}

function CardFrame({
  card,
  index,
  count,
  columns,
  editMode,
  issues,
  children,
  titleId,
}: {
  card: ModelDashboardCard;
  index: number;
  count: number;
  columns: number;
  editMode: boolean;
  issues: readonly DashboardIssue[];
  children: ReactNode;
  titleId: string;
}) {
  const span = sizeSpan(card.size);
  const [dropping, setDropping] = useState(false);
  const display = isDisplayKind(card.kind) && card.kind !== "text";
  const title = cardTitle(card);
  const onDragOver = (event: DragEvent<HTMLElement>): void => {
    const types = event.dataTransfer.types;
    if ((editMode && types.includes(CARD_DRAG_MIME)) || (display && types.includes(SIGNAL_DRAG_MIME))) {
      event.preventDefault();
      event.stopPropagation();
      event.dataTransfer.dropEffect = types.includes(CARD_DRAG_MIME) ? "move" : "copy";
      setDropping(true);
    }
  };
  const onDrop = (event: DragEvent<HTMLElement>): void => {
    setDropping(false);
    const moved = event.dataTransfer.getData(CARD_DRAG_MIME);
    if (moved.length > 0) {
      event.preventDefault();
      event.stopPropagation();
      if (moved !== card.id) {
        moveCardTo(moved, index);
      }
      return;
    }
    if (display) {
      const signal = readSignalDrag(event);
      if (signal !== null) {
        event.preventDefault();
        event.stopPropagation();
        dropSignalOnCard(card.id, signal);
      }
    }
  };
  return (
    <section
      className={`dash-card dash-card--${card.kind}${editMode ? " is-editing" : ""}${dropping ? " is-drop-target" : ""}${issues.length > 0 ? " has-issue" : ""}`}
      style={{
        gridColumn: `span ${Math.min(columns, span.columns)}`,
        gridRow: `span ${span.rows}`,
      }}
      aria-labelledby={titleId}
      data-testid={`dash-card-${card.id}`}
      data-kind={card.kind}
      draggable={editMode}
      onDragStart={(event) => {
        if (!editMode) return;
        event.dataTransfer.setData(CARD_DRAG_MIME, card.id);
        event.dataTransfer.effectAllowed = "move";
      }}
      onDragOver={onDragOver}
      onDragLeave={() => setDropping(false)}
      onDrop={onDrop}
    >
      <header className="dash-card__header">
        <h3 className="dash-card__title" id={titleId} title={title}>
          {title}
        </h3>
        {isInputKind(card.kind) || card.kind === "schedule" ? (
          <span className="dash-card__badge" title="Applies to the next run">
            input
          </span>
        ) : null}
      </header>
      {editMode ? (
        <div className="dash-card__edit" role="toolbar" aria-label={`Edit ${title}`}>
          <span className="dash-card__grip" aria-hidden="true" title="Drag to reorder">
            ⠿
          </span>
          <button
            type="button"
            className="dash-icon-button"
            aria-label={`Move ${title} earlier`}
            disabled={index === 0}
            onClick={() => moveCardTo(card.id, index - 1)}
          >
            ←
          </button>
          <button
            type="button"
            className="dash-icon-button"
            aria-label={`Move ${title} later`}
            disabled={index === count - 1}
            onClick={() => moveCardTo(card.id, index + 1)}
          >
            →
          </button>
          <label className="visually-hidden" htmlFor={`${card.id}-quick-size`}>
            Size of {title}
          </label>
          <select
            id={`${card.id}-quick-size`}
            className="dash-card__size"
            value={card.size}
            onChange={(event) => setCardSize(card.id, event.target.value as ModelDashboardCard["size"])}
          >
            {CARD_SIZES.map((size) => (
              <option key={size} value={size}>
                {size.replace("x", "×")}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="dash-icon-button"
            aria-label={`Settings of ${title}`}
            data-testid={`dash-card-settings-${card.id}`}
            onClick={() => useDashboardUi.getState().openSettings(card.id)}
          >
            ⚙
          </button>
          <button
            type="button"
            className="dash-icon-button dash-icon-button--danger"
            aria-label={`Remove ${title}`}
            data-testid={`dash-card-remove-${card.id}`}
            onClick={() => removeCard(card.id)}
          >
            ×
          </button>
        </div>
      ) : null}
      <div className="dash-card__body">{children}</div>
      {issues.length > 0 ? (
        <p className="dash-card__issue" role="alert">
          {issues[0]!.message}
        </p>
      ) : null}
    </section>
  );
}

function RunInputsSummary({
  overrides,
  steps,
  issues,
}: {
  overrides: number;
  steps: number;
  issues: number;
}) {
  if (issues > 0) {
    return (
      <span className="dash-summary dash-summary--issue" data-testid="dash-summary">
        {issues === 1 ? "1 problem" : `${issues} problems`}: the next run is refused until fixed
      </span>
    );
  }
  if (overrides === 0 && steps === 0) {
    return (
      <span className="dash-summary" data-testid="dash-summary">
        The next run uses the model's parameter values
      </span>
    );
  }
  const parts: string[] = [];
  if (overrides > 0) parts.push(overrides === 1 ? "1 parameter override" : `${overrides} parameter overrides`);
  if (steps > 0) parts.push(steps === 1 ? "1 scheduled change" : `${steps} scheduled changes`);
  return (
    <span className="dash-summary" data-testid="dash-summary">
      Next run: {parts.join(", ")}
    </span>
  );
}

export function DashboardTab() {
  const doc = useDocumentStore((state) => state.doc);
  const index = useCatalogStore((state) => state.index);
  const editMode = useDashboardUi((state) => state.editMode);
  const settingsCardId = useDashboardUi((state) => state.settingsCardId);
  const [adding, setAdding] = useState(false);
  const series = useRunSeries();
  const dashboard = doc?.dashboard;
  useDashboardSignalSubscription(dashboard);
  useAutoRerun(doc, index);
  const [gridRef, columns] = useGridColumns();
  const [gridDrop, setGridDrop] = useState(false);

  const parameters = useMemo(() => (doc === null ? [] : listParameters(doc, index)), [doc, index]);
  const inputs = useMemo(
    () => (doc === null ? null : dashboardRunInputs(doc, index)),
    [doc, index],
  );
  const cards = dashboard?.cards ?? [];
  const settingsCard = cards.find((card) => card.id === settingsCardId) ?? null;
  const takenBy = useMemo(() => {
    const map = new Map<string, string>();
    for (const card of cards) {
      for (const target of boundParameters(card)) {
        map.set(target, card.id);
      }
    }
    return map;
  }, [cards]);
  const takenFor = (cardId: string): Set<string> =>
    new Set([...takenBy].filter(([, owner]) => owner !== cardId).map(([target]) => target));

  if (doc === null) {
    return null;
  }

  const issuesOf = (cardId: string): DashboardIssue[] =>
    (inputs?.issues ?? []).filter((issue) => issue.cardId === cardId);

  const onGridDragOver = (event: DragEvent<HTMLDivElement>): void => {
    if (event.dataTransfer.types.includes(SIGNAL_DRAG_MIME) || (editMode && event.dataTransfer.types.includes(CARD_DRAG_MIME))) {
      event.preventDefault();
      setGridDrop(true);
    }
  };
  const onGridDrop = (event: DragEvent<HTMLDivElement>): void => {
    setGridDrop(false);
    const moved = event.dataTransfer.getData(CARD_DRAG_MIME);
    if (moved.length > 0) {
      event.preventDefault();
      moveCardTo(moved, cards.length);
      return;
    }
    const signal = readSignalDrag(event);
    if (signal !== null) {
      event.preventDefault();
      addCard("value", signal);
    }
  };

  return (
    <div className="dashboard" data-testid="dashboard" data-mode={editMode ? "edit" : "use"}>
      <div className="dashboard__toolbar" role="toolbar" aria-label="Dashboard">
        <button
          type="button"
          className={`dash-button${editMode ? " dash-button--primary" : ""}`}
          aria-pressed={editMode}
          data-testid="dash-edit-toggle"
          onClick={() => {
            useDashboardUi.getState().setEditMode(!editMode);
            setAdding(false);
          }}
        >
          {editMode ? "Done" : "Edit dashboard"}
        </button>
        {editMode ? (
          <div className="dash-add">
            <button
              type="button"
              className="dash-button"
              aria-haspopup="menu"
              aria-expanded={adding}
              data-testid="dash-add-card"
              onClick={() => setAdding(!adding)}
            >
              + Add card
            </button>
            {adding ? <AddCardMenu onClose={() => setAdding(false)} /> : null}
          </div>
        ) : null}
        <span className="dashboard__spacer" />
        {inputs !== null ? (
          <RunInputsSummary
            overrides={inputs.parameterOverrides.length}
            steps={inputs.parameterSchedule.length}
            issues={inputs.issues.length}
          />
        ) : null}
        <label className="dash-check" title="Start a new run shortly after an input changes">
          <input
            type="checkbox"
            checked={dashboard?.autoRerun === true}
            data-testid="dash-auto-rerun"
            onChange={(event) => setAutoRerun(event.target.checked)}
          />
          Auto re-run
        </label>
      </div>
      <div
        className={`dashboard__grid${gridDrop ? " is-drop-target" : ""}`}
        ref={gridRef}
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
        onDragOver={onGridDragOver}
        onDragLeave={(event) => {
          if (!(event.relatedTarget instanceof Node && event.currentTarget.contains(event.relatedTarget))) {
            setGridDrop(false);
          }
        }}
        onDrop={onGridDrop}
      >
        {cards.length === 0 ? (
          <div className="dashboard__empty" style={{ gridColumn: `span ${columns}` }}>
            <h2>No cards yet</h2>
            <p>
              {editMode
                ? "Add a card with + Add card, or drag a signal from the Signals tab here."
                : "Choose Edit dashboard to add plots, gauges, values, sliders, knobs and schedule tables — or drag a signal from the Signals tab here."}
            </p>
          </div>
        ) : null}
        {cards.map((card, position) => {
          const titleId = `dash-card-title-${card.id}`;
          let body: ReactNode;
          const Display = DISPLAY[card.kind];
          const Input = INPUT[card.kind];
          if (Display !== undefined) {
            body = <Display card={card} series={series as RunSeries} titleId={titleId} />;
          } else if (Input !== undefined) {
            const info = card.parameter === undefined ? null : findParameter(doc, index, card.parameter);
            body = <Input card={card} info={info} titleId={titleId} />;
          } else {
            body = (
              <ScheduleCard
                card={card}
                titleId={titleId}
                parameters={parameters}
                taken={takenFor(card.id)}
              />
            );
          }
          return (
            <CardFrame
              key={card.id}
              card={card}
              index={position}
              count={cards.length}
              columns={columns}
              editMode={editMode}
              issues={issuesOf(card.id)}
              titleId={titleId}
            >
              {body}
            </CardFrame>
          );
        })}
      </div>
      {settingsCard !== null ? (
        <CardSettings
          key={settingsCard.id}
          card={settingsCard}
          signals={series.manifest?.signals ?? []}
          parameters={parameters}
          taken={takenFor(settingsCard.id)}
          onClose={() => useDashboardUi.getState().openSettings(null)}
        />
      ) : null}
    </div>
  );
}
