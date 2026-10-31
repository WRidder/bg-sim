/**
 * The schedule table card (DASHBOARD_PLAN.md): the first column is t in seconds, the others are
 * block parameters. From each row's t on, the parameters take the row's values (piecewise
 * constant); before the first row the model's values apply. The next run receives the table as
 * `parameterSchedule`. Rows stay sorted by t; cells are validated (numbers, t inside the run,
 * no duplicate t).
 */

import { useEffect, useMemo, useState } from "react";

import type { ModelDashboardCard, ModelDashboardSchedule } from "../contracts/model";
import { parseLiveValue } from "../inspector/liveEdit";
import { useDocumentStore } from "../state/documentStore";
import { setCardSchedule } from "./actions";
import { scheduleIssues, sortScheduleRows, type ParameterInfo } from "./model";

export interface ScheduleCardProps {
  card: ModelDashboardCard;
  titleId: string;
  /** Every block parameter of the model, for the column picker. */
  parameters: readonly ParameterInfo[];
  /** Parameters bound by other cards (they cannot become a column here). */
  taken: ReadonlySet<string>;
}

const EMPTY: ModelDashboardSchedule = { parameters: [], rows: [] };

function Cell({
  value,
  label,
  invalid,
  testId,
  onCommit,
}: {
  value: number | null;
  label: string;
  invalid: boolean;
  testId: string;
  onCommit: (value: number | null) => void;
}) {
  const shown = value === null ? "" : String(value);
  const [text, setText] = useState(shown);
  const [error, setError] = useState(false);
  useEffect(() => setText(shown), [shown]);
  const commit = (): void => {
    if (text === shown) {
      setError(false);
      return;
    }
    if (text.trim().length === 0) {
      setError(false);
      onCommit(null);
      return;
    }
    const parsed = parseLiveValue(text);
    if (!parsed.ok) {
      setError(true);
      return;
    }
    setError(false);
    onCommit(parsed.value);
  };
  return (
    <input
      className={`dash-schedule__cell${invalid || error ? " is-invalid" : ""}`}
      type="text"
      inputMode="decimal"
      value={text}
      aria-label={label}
      aria-invalid={invalid || error}
      data-testid={testId}
      onChange={(event) => setText(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          commit();
        } else if (event.key === "Escape") {
          setText(shown);
          setError(false);
        }
      }}
    />
  );
}

export function ScheduleCard({ card, titleId, parameters, taken }: ScheduleCardProps) {
  const settings = useDocumentStore((state) => state.doc?.settings ?? null);
  const schedule = card.schedule ?? EMPTY;
  const range = { t_start: settings?.t_start ?? 0, t_end: settings?.t_end ?? Infinity };
  const issues = useMemo(() => scheduleIssues(schedule, range), [schedule, range.t_start, range.t_end]);
  const [adding, setAdding] = useState("");
  const byTarget = useMemo(() => new Map(parameters.map((p) => [p.target, p])), [parameters]);
  const choices = parameters.filter(
    (p) =>
      !schedule.parameters.includes(p.target) &&
      !taken.has(p.target) &&
      p.decl.type !== "Bool",
  );

  const save = (next: ModelDashboardSchedule): void => setCardSchedule(card.id, next);
  const baseValue = (target: string): number | null => byTarget.get(target)?.modelValue ?? null;

  const setT = (row: number, t: number | null): void => {
    if (t === null) {
      return;
    }
    const rows = schedule.rows.map((entry, index) => (index === row ? { ...entry, t } : entry));
    save(sortScheduleRows({ ...schedule, rows }));
  };
  const setValue = (row: number, column: number, value: number | null): void => {
    const rows = schedule.rows.map((entry, index) =>
      index === row
        ? { ...entry, values: entry.values.map((v, c) => (c === column ? value : v)) }
        : entry,
    );
    save({ ...schedule, rows });
  };
  const addRow = (): void => {
    const last = schedule.rows[schedule.rows.length - 1];
    const span = Number.isFinite(range.t_end) ? range.t_end - range.t_start : 1;
    const t =
      last === undefined
        ? range.t_start
        : Math.min(range.t_end, Number((last.t + span / 10).toPrecision(6)));
    const values = schedule.parameters.map((target, column) =>
      last?.values[column] ?? baseValue(target),
    );
    save({ ...schedule, rows: [...schedule.rows, { t, values }] });
  };
  const removeRow = (row: number): void => {
    save({ ...schedule, rows: schedule.rows.filter((_, index) => index !== row) });
  };
  const addColumn = (target: string): void => {
    if (target.length === 0) {
      return;
    }
    const base = baseValue(target);
    save({
      parameters: [...schedule.parameters, target],
      rows: schedule.rows.map((row) => ({ ...row, values: [...row.values, base] })),
    });
    setAdding("");
  };
  const removeColumn = (column: number): void => {
    save({
      parameters: schedule.parameters.filter((_, index) => index !== column),
      rows: schedule.rows.map((row) => ({
        ...row,
        values: row.values.filter((_, index) => index !== column),
      })),
    });
  };

  const cellInvalid = (row: number, column: number): boolean =>
    issues.some((issue) => issue.row === row && issue.column === column);

  return (
    <div className="dash-schedule" data-testid={`dash-schedule-${card.id}`}>
      <div className="dash-schedule__scroll">
        <table className="dash-schedule__table" aria-labelledby={titleId}>
          <thead>
            <tr>
              <th scope="col">t [s]</th>
              {schedule.parameters.map((target, column) => {
                const unit = byTarget.get(target)?.decl.unit;
                return (
                  <th scope="col" key={target}>
                    <span className="dash-schedule__head">
                      {target}
                      {unit ? <span className="dash-input__unit"> [{unit}]</span> : null}
                    </span>
                    <button
                      type="button"
                      className="dash-icon-button"
                      aria-label={`Remove the column ${target}`}
                      onClick={() => removeColumn(column)}
                    >
                      ×
                    </button>
                  </th>
                );
              })}
              <th scope="col">
                <span className="visually-hidden">Row actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {schedule.rows.length === 0 ? (
              <tr>
                <td colSpan={schedule.parameters.length + 2} className="dash-schedule__empty">
                  {schedule.parameters.length === 0
                    ? "Add a parameter column, then rows."
                    : "No rows: the model's values apply for the whole run."}
                </td>
              </tr>
            ) : (
              schedule.rows.map((row, index) => (
                <tr key={`${index}-${row.t}`}>
                  <td>
                    <Cell
                      value={row.t}
                      label={`Row ${index + 1} t in seconds`}
                      invalid={cellInvalid(index, -1)}
                      testId={`dash-schedule-${card.id}-t-${index}`}
                      onCommit={(t) => setT(index, t)}
                    />
                  </td>
                  {schedule.parameters.map((target, column) => (
                    <td key={target}>
                      <Cell
                        value={row.values[column] ?? null}
                        label={`Row ${index + 1} ${target}`}
                        invalid={cellInvalid(index, column)}
                        testId={`dash-schedule-${card.id}-v-${index}-${column}`}
                        onCommit={(value) => setValue(index, column, value)}
                      />
                    </td>
                  ))}
                  <td>
                    <button
                      type="button"
                      className="dash-icon-button"
                      aria-label={`Remove row ${index + 1}`}
                      onClick={() => removeRow(index)}
                    >
                      ×
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="dash-schedule__actions">
        <button
          type="button"
          className="dash-button"
          onClick={addRow}
          disabled={schedule.parameters.length === 0}
          data-testid={`dash-schedule-${card.id}-add-row`}
        >
          + Row
        </button>
        <label className="dash-schedule__add-column">
          <span className="visually-hidden">Add a parameter column</span>
          <select
            value={adding}
            onChange={(event) => addColumn(event.target.value)}
            data-testid={`dash-schedule-${card.id}-add-column`}
          >
            <option value="">+ Column…</option>
            {choices.map((p) => (
              <option key={p.target} value={p.target}>
                {p.target}
              </option>
            ))}
          </select>
        </label>
      </div>
      {issues.length > 0 ? (
        <ul className="dash-schedule__issues" role="alert">
          {issues.slice(0, 3).map((issue, index) => (
            <li key={index}>
              {issue.row >= 0 ? `Row ${issue.row + 1}: ` : ""}
              {issue.message}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
