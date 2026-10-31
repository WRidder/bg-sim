/**
 * The Equations manager (SolidWorks "Equations, Global Variables, and
 * Dimensions"), on the Parameters tab next to Code and Docs:
 *
 * * Global variables: name | expression | value | unit | comment, with add,
 *   delete (refused while used), rename (rewrites every reference, one undo
 *   step), reorder and a "used by" list that selects the blocks;
 * * Equations: every block parameter/start/constant driven by an equation,
 *   editable in place, with click-through to the block;
 * * Order: the evaluation (dependency) order the compiler folds the globals in.
 *
 * Every edit is a document-store command, so undo/redo and autosave apply.
 */

import { useMemo, useState } from "react";

import type { Model, ModelGlobalParameter } from "../contracts/model";
import { requestCenterTab } from "../app/dockBus";
import { DashboardOverrideBadge } from "../dashboard/OverrideBadge";
import { useDocumentStore } from "../state/documentStore";
import { CellInput } from "./CellInput";
import { useGlobalEvaluation } from "./equationField";
import { globalValueIssue, usersOf, type GlobalUsers } from "./globalEdits";
import {
  drivenFields,
  evaluateField,
  type ExpressionField,
  formatValue,
  type GlobalEvaluation,
  globalNameIssue,
  globalsOf,
} from "./globals";
import "./globals.css";

export type ManagerView = "globals" | "equations" | "order";
type Variant = "panel" | "tab";

function message(result: { ok: boolean; error?: string }): string | null {
  return result.ok ? null : (result.error ?? "The change was refused.");
}

function fieldLabel(field: ExpressionField): string {
  return `${field.instancePath.join("/")}.${field.key}`;
}

function selectField(field: Pick<ExpressionField, "diagramPath" | "nodeId">): void {
  useDocumentStore.getState().selectNodeAt(field.diagramPath, field.nodeId);
}

function valueText(value: number | null, unit: string | null | undefined): string {
  if (value === null) {
    return "—";
  }
  const suffix = unit === null || unit === undefined || unit.length === 0 ? "" : ` ${unit}`;
  return `${formatValue(value)}${suffix}`;
}

function UsersList({
  name,
  users,
  onSelect,
}: {
  name: string;
  users: GlobalUsers;
  onSelect: () => void;
}) {
  const diagrams = new Set(users.fields.map((field) => field.diagramPath.join("/")));
  const first = users.fields[0];
  return (
    <div className="equations-users" data-testid={`global-users-${name}`}>
      {users.fields.length === 0 && users.globals.length === 0 ? (
        <p className="equations-note">Nothing uses {name} yet.</p>
      ) : null}
      <ul>
        {users.fields.map((field) => (
          <li key={`${field.nodeId}-${field.kind}-${field.key}`}>
            <button
              type="button"
              className="equations-link"
              data-testid={`global-user-${name}-${fieldLabel(field)}`}
              onClick={() => {
                selectField(field);
                onSelect();
              }}
            >
              {fieldLabel(field)}
            </button>
            {field.kind !== "param" ? <span className="equations-kind">{field.kind}</span> : null}
          </li>
        ))}
        {users.globals.map((other) => (
          <li key={`global-${other}`}>
            <span className="equations-kind">global</span> <code>{other}</code>
          </li>
        ))}
      </ul>
      {first !== undefined && diagrams.size === 1 && users.fields.length > 1 ? (
        <button
          type="button"
          className="button equations-select-all"
          data-testid={`global-users-select-${name}`}
          onClick={() => {
            const store = useDocumentStore.getState();
            store.selectNodeAt(first.diagramPath, first.nodeId);
            store.setSelection([...new Set(users.fields.map((field) => field.nodeId))], []);
            onSelect();
          }}
        >
          Select all {new Set(users.fields.map((field) => field.nodeId)).size} blocks
        </button>
      ) : null}
    </div>
  );
}

function GlobalsTable({
  doc,
  evaluation,
  variant,
  onNavigate,
}: {
  doc: Model;
  evaluation: GlobalEvaluation;
  variant: Variant;
  onNavigate: () => void;
}) {
  const globals = globalsOf(doc);
  const [open, setOpen] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ name: string; text: string } | null>(null);
  const prefix = "global";
  const wide = variant === "tab";
  const names = [...evaluation.byName.keys()];
  const describe = (name: string): string | null => {
    const status = evaluation.byName.get(name);
    return status === undefined ? null : status.value === null ? "error" : `= ${formatValue(status.value)}`;
  };
  const store = useDocumentStore.getState;

  const add = (): void => {
    const result = store().addGlobalParameter();
    if (result.ok && result.name !== undefined) {
      const id = `${prefix}-name-${result.name}`;
      requestAnimationFrame(() => {
        const input = document.getElementById(id);
        if (input instanceof HTMLInputElement) {
          input.focus();
          input.select();
        }
      });
    }
  };

  return (
    <div className="equations-view" data-testid={`${prefix}s-view`}>
      {globals.length === 0 ? (
        <p className="equations-note" data-testid={`${prefix}s-empty`}>
          No global parameters yet. Add one, then type its name into any block parameter or start
          value (for example <code>k</code> or <code>4*m</code>).
        </p>
      ) : (
        <table className={wide ? "equations-table equations-table--wide" : "equations-table"}>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Expression</th>
              <th scope="col">Value</th>
              {wide ? <th scope="col">Unit</th> : null}
              {wide ? <th scope="col">Comment</th> : null}
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {globals.map((entry: ModelGlobalParameter, index) => {
              const status = evaluation.rows[index];
              const users = usersOf(doc, entry.name);
              const count = users.fields.length + users.globals.length;
              const others = names.filter((name) => name !== entry.name);
              return (
                <GlobalRow
                  key={`${index}-${entry.name}`}
                  entry={entry}
                  index={index}
                  last={index === globals.length - 1}
                  prefix={prefix}
                  wide={wide}
                  value={status?.value ?? null}
                  error={status?.error ?? null}
                  count={count}
                  open={open === entry.name}
                  onToggle={() => setOpen(open === entry.name ? null : entry.name)}
                  users={users}
                  names={others}
                  describe={describe}
                  rowError={rowError?.name === entry.name ? rowError.text : null}
                  onRowError={(text) => setRowError(text === null ? null : { name: entry.name, text })}
                  onNavigate={onNavigate}
                  globals={globals}
                />
              );
            })}
          </tbody>
        </table>
      )}
      <div className="equations-actions">
        <button type="button" className="button" data-testid={`${prefix}-add`} onClick={add}>
          + Add global parameter
        </button>
      </div>
    </div>
  );
}

function GlobalRow({
  entry,
  index,
  last,
  prefix,
  wide,
  value,
  error,
  count,
  open,
  onToggle,
  users,
  names,
  describe,
  rowError,
  onRowError,
  onNavigate,
  globals,
}: {
  entry: ModelGlobalParameter;
  index: number;
  last: boolean;
  prefix: string;
  wide: boolean;
  value: number | null;
  error: string | null;
  count: number;
  open: boolean;
  onToggle: () => void;
  users: GlobalUsers;
  names: readonly string[];
  describe: (name: string) => string | null;
  rowError: string | null;
  onRowError: (text: string | null) => void;
  onNavigate: () => void;
  globals: readonly ModelGlobalParameter[];
}) {
  const store = useDocumentStore.getState;
  const name = entry.name;
  const columns = wide ? 6 : 4;
  return (
    <>
      <tr data-testid={`${prefix}-row-${name}`} className={error !== null ? "equations-row--error" : undefined}>
        <td>
          <CellInput
            id={`${prefix}-name-${name}`}
            testId={`${prefix}-name-${name}`}
            label={`Name of global parameter ${name}`}
            value={name}
            mono
            issue={(text) => globalNameIssue(globals, text.trim(), name)}
            onCommit={(text) => message(store().renameGlobalParameter(name, text.trim()))}
          />
        </td>
        <td>
          <CellInput
            id={`${prefix}-value-${name}`}
            testId={`${prefix}-value-${name}`}
            label={`Expression of global parameter ${name}`}
            value={entry.value}
            mono
            title={entry.value}
            issue={(text) => globalValueIssue(text.trim().replace(/^=(?!=)/, ""))}
            onCommit={(text) => message(store().updateGlobalParameter(name, { value: text }))}
            completions={names}
            describeCompletion={describe}
          />
        </td>
        <td className="equations-value" data-testid={`${prefix}-result-${name}`} title={error ?? undefined}>
          {error !== null ? (
            <span className="equations-value__error" aria-label={`Error: ${error}`}>
              ⚠
            </span>
          ) : (
            valueText(value, wide ? null : entry.unit)
          )}
          {/* DASHBOARD_PLAN.md: a dashboard input card overrides this global for the next run. */}
          <DashboardOverrideBadge target={`global:${name}`} />
        </td>
        {wide ? (
          <td>
            <CellInput
              id={`${prefix}-unit-${name}`}
              testId={`${prefix}-unit-${name}`}
              label={`Unit of global parameter ${name}`}
              value={entry.unit ?? ""}
              placeholder="—"
              onCommit={(text) => message(store().updateGlobalParameter(name, { unit: text }))}
            />
          </td>
        ) : null}
        {wide ? (
          <td>
            <CellInput
              id={`${prefix}-comment-${name}`}
              testId={`${prefix}-comment-${name}`}
              label={`Comment of global parameter ${name}`}
              value={entry.description ?? ""}
              placeholder="Comment"
              onCommit={(text) =>
                message(store().updateGlobalParameter(name, { description: text }))
              }
            />
          </td>
        ) : null}
        <td className="equations-row-actions">
          <button
            type="button"
            className="equations-icon-button equations-uses"
            data-testid={`${prefix}-uses-${name}`}
            aria-expanded={open}
            title={`Used by ${count} ${count === 1 ? "value" : "values"}`}
            onClick={onToggle}
          >
            {count}×
          </button>
          <button
            type="button"
            className="equations-icon-button"
            data-testid={`${prefix}-up-${name}`}
            aria-label={`Move ${name} up`}
            title="Move up"
            disabled={index === 0}
            onClick={() => store().moveGlobalParameter(name, index - 1)}
          >
            ↑
          </button>
          <button
            type="button"
            className="equations-icon-button"
            data-testid={`${prefix}-down-${name}`}
            aria-label={`Move ${name} down`}
            title="Move down"
            disabled={last}
            onClick={() => store().moveGlobalParameter(name, index + 1)}
          >
            ↓
          </button>
          <button
            type="button"
            className="equations-icon-button equations-icon-button--danger"
            data-testid={`${prefix}-delete-${name}`}
            aria-label={`Delete ${name}`}
            title={count > 0 ? `Used by ${count}; change those first` : "Delete"}
            onClick={() => onRowError(message(store().deleteGlobalParameter(name)))}
          >
            ×
          </button>
        </td>
      </tr>
      {error !== null ? (
        <tr className="equations-detail">
          <td colSpan={columns}>
            <p className="equations-error" role="status" data-testid={`${prefix}-error-${name}`}>
              {error}
            </p>
          </td>
        </tr>
      ) : null}
      {rowError !== null ? (
        <tr className="equations-detail">
          <td colSpan={columns}>
            <p className="equations-error" role="alert" data-testid={`${prefix}-refusal-${name}`}>
              {rowError}
            </p>
          </td>
        </tr>
      ) : null}
      {!wide && (entry.unit || entry.description) ? (
        <tr className="equations-detail">
          <td colSpan={columns} className="equations-doc">
            {entry.description ?? ""}
          </td>
        </tr>
      ) : null}
      {open ? (
        <tr className="equations-detail">
          <td colSpan={columns}>
            <UsersList name={name} users={users} onSelect={onNavigate} />
          </td>
        </tr>
      ) : null}
    </>
  );
}

function EquationsTable({
  doc,
  evaluation,
  onNavigate,
}: {
  doc: Model;
  evaluation: GlobalEvaluation;
  onNavigate: () => void;
}) {
  const fields = useMemo(() => drivenFields(doc), [doc]);
  const prefix = "equation";
  const names = [...evaluation.byName.keys()];
  const store = useDocumentStore.getState;
  if (fields.length === 0) {
    return (
      <p className="equations-note" data-testid={`${prefix}s-empty`}>
        No block value is driven by an equation yet. Type a global parameter's name or any
        arithmetic (<code>2*k</code>, <code>sqrt(k/m)</code>) into a block parameter or start
        value; it then appears here with a Σ.
      </p>
    );
  }
  return (
    <table className="equations-table" data-testid={`${prefix}s-view`}>
      <thead>
        <tr>
          <th scope="col">Block value</th>
          <th scope="col">Expression</th>
          <th scope="col">Value</th>
        </tr>
      </thead>
      <tbody>
        {fields.map((field) => {
          const label = fieldLabel(field);
          const result = evaluateField(field.text, evaluation);
          return (
            <tr key={`${field.nodeId}-${field.kind}-${field.key}`} data-testid={`${prefix}-row-${label}`}>
              <td>
                <button
                  type="button"
                  className="equations-link"
                  data-testid={`${prefix}-select-${label}`}
                  title="Select the block"
                  onClick={() => {
                    selectField(field);
                    onNavigate();
                  }}
                >
                  {label}
                </button>
                {field.kind !== "param" ? <span className="equations-kind">{field.kind}</span> : null}
              </td>
              <td>
                <CellInput
                  id={`${prefix}-expr-${label}`}
                  testId={`${prefix}-expr-${label}`}
                  label={`Expression of ${label}`}
                  value={field.text}
                  mono
                  issue={(text) => (text.trim().length === 0 ? null : globalValueIssue(text.trim().replace(/^=(?!=)/, "")))}
                  onCommit={(text) => message(store().setFieldExpression(field, text))}
                  completions={names}
                />
              </td>
              <td className="equations-value" title={result.error ?? undefined} data-testid={`${prefix}-value-${label}`}>
                {result.error !== null ? (
                  <span className="equations-value__error" aria-label={`Error: ${result.error}`}>
                    ⚠
                  </span>
                ) : result.value === null ? (
                  "—"
                ) : (
                  formatValue(result.value)
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function OrderList({ doc, evaluation }: { doc: Model; evaluation: GlobalEvaluation }) {
  const globals = globalsOf(doc);
  if (globals.length === 0) {
    return <p className="equations-note">No global parameters yet.</p>;
  }
  return (
    <ol className="equations-order" data-testid="globals-order">
      {evaluation.order.map((name) => {
        const entry = globals.find((candidate) => candidate.name === name);
        const status = evaluation.byName.get(name);
        return (
          <li key={name} className={status?.error ? "equations-order__item--error" : undefined}>
            <code>
              {name} = {entry?.value}
            </code>
            <span className="equations-order__value">
              {status?.error ? status.error : `→ ${valueText(status?.value ?? null, entry?.unit)}`}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function EquationsManager({
  variant = "panel",
  initialView = "globals",
  onNavigate = () => undefined,
}: {
  variant?: Variant;
  initialView?: ManagerView;
  /** Called after a click-through selected a block (the dialog closes). */
  onNavigate?: () => void;
}) {
  const doc = useDocumentStore((state) => state.doc);
  const evaluation = useGlobalEvaluation();
  const [view, setView] = useState<ManagerView>(initialView);
  const driven = useMemo(() => (doc === null ? 0 : drivenFields(doc).length), [doc]);
  if (doc === null) {
    return null;
  }
  const tabs: { key: ManagerView; label: string }[] = [
    { key: "globals", label: `Global variables (${globalsOf(doc).length})` },
    { key: "equations", label: `Equations (${driven})` },
    { key: "order", label: "Order" },
  ];
  const idPrefix = "equations";
  return (
    <div className={`equations-manager equations-manager--${variant}`} data-testid={`${idPrefix}-manager`}>
      <div className="equations-tabs" role="tablist" aria-label="Equations manager views">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${tab.key}`}
            aria-selected={view === tab.key}
            aria-controls={`${idPrefix}-panel`}
            className={view === tab.key ? "equations-tab equations-tab--active" : "equations-tab"}
            data-testid={`${idPrefix}-tab-${tab.key}`}
            onClick={() => setView(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${idPrefix}-panel`} aria-labelledby={`${idPrefix}-tab-${view}`}>
        {view === "globals" ? (
          <GlobalsTable doc={doc} evaluation={evaluation} variant={variant} onNavigate={onNavigate} />
        ) : view === "equations" ? (
          <EquationsTable doc={doc} evaluation={evaluation} onNavigate={onNavigate} />
        ) : (
          <OrderList doc={doc} evaluation={evaluation} />
        )}
      </div>
    </div>
  );
}

/**
 * The Parameters tab (centre, next to Code and Docs): the full-width Equations
 * manager with unit and comment columns. A click-through selects the block and
 * shows it on the Diagram tab.
 */
export function ParametersTab() {
  const name = useDocumentStore((state) => state.doc?.name ?? state.modelName ?? null);
  if (name === null) {
    return null;
  }
  return (
    <div className="parameters-tab" data-testid="parameters-tab">
      <header className="parameters-tab__header">
        <h2 className="parameters-tab__title">Global parameters &amp; equations</h2>
        <p className="parameters-tab__hint">
          Block parameters and start values can use these names (e.g. <code>4*m</code>). They are
          evaluated once, before the model is compiled; simulation and export see plain numbers.
        </p>
      </header>
      <EquationsManager variant="tab" onNavigate={() => requestCenterTab("diagram")} />
    </div>
  );
}

/**
 * The inspector when nothing is selected: the model, a summary of its global
 * parameters and the way to the Parameters tab.
 */
export function ModelInspector() {
  const name = useDocumentStore((state) => state.doc?.name ?? state.modelName ?? "Model");
  const count = useDocumentStore((state) => (state.doc === null ? 0 : globalsOf(state.doc).length));
  const driven = useDocumentStore((state) => (state.doc === null ? 0 : drivenFields(state.doc).length));
  return (
    <div className="inspector-body" data-testid="inspector-model">
      <header className="inspector-header inspector-header--summary">
        <div className="inspector-header__text">
          <p className="inspector-header__kicker">Model</p>
          <h3 className="inspector-header__title">{name}</h3>
          <p className="inspector-header__description">
            Nothing is selected. Select a block on the diagram to edit its name, parameters, ports and
            start values here.
          </p>
        </div>
      </header>
      <section className="inspector-section" aria-labelledby="inspector-globals-title">
        <h4 className="inspector-section__title" id="inspector-globals-title">
          Global parameters
        </h4>
        <p className="inspector-none" data-testid="inspector-globals-summary">
          {count === 0
            ? "No global parameters yet."
            : `${count} global ${count === 1 ? "parameter" : "parameters"}, ${driven} driven ${driven === 1 ? "value" : "values"}.`}
        </p>
        <button
          type="button"
          className="button"
          data-testid="equations-open-tab"
          onClick={() => requestCenterTab("parameters")}
        >
          Open the Parameters tab
        </button>
      </section>
    </div>
  );
}
