import { useMemo, useState } from "react";

import { EmptyState } from "../app/EmptyState";
import type { WorkerState } from "../api/health";
import type { Diagnostic, DiagnosticSeverity } from "../contracts/diagnostic";
import type { DiagnosticSource } from "../contracts/diagnostic";
import { useDocumentStore } from "../state/documentStore";
import {
  createNodeResolver,
  navigateToDiagnostic,
  navigateToPath,
  type NavigationTarget,
  type NodeResolver,
} from "./navigation";
import {
  SEVERITIES,
  useDiagnosticsStore,
  type DiagnosticsStatus,
} from "./store";
import "./diagnostics.css";

export interface IndexedDiagnostic {
  diagnostic: Diagnostic;
  /** Index in the unfiltered result; keeps test ids stable while filtering. */
  index: number;
}

export interface DiagnosticGroup {
  path: string | null;
  label: string;
  items: IndexedDiagnostic[];
}

const SEVERITY_LABEL: Record<DiagnosticSeverity, string> = {
  error: "Errors",
  warning: "Warnings",
  info: "Info",
};

const SEVERITY_GLYPH: Record<DiagnosticSeverity, string> = {
  error: "!",
  warning: "▲",
  info: "i",
};

/**
 * Group by instance path (plan 7.3/7.4). Model-wide diagnostics (path null)
 * come first, then the paths in alphabetical order; within a group the worker's
 * order is kept, because it is already the order a person reads the model in.
 */
export function groupDiagnostics(items: readonly IndexedDiagnostic[]): DiagnosticGroup[] {
  const groups = new Map<string, DiagnosticGroup>();
  for (const item of items) {
    const path = item.diagnostic.path ?? null;
    const key = path ?? "";
    let group = groups.get(key);
    if (group === undefined) {
      group = { path, label: path ?? "Model", items: [] };
      groups.set(key, group);
    }
    group.items.push(item);
  }
  return [...groups.values()].sort((a, b) => {
    if (a.path === null) {
      return b.path === null ? 0 : -1;
    }
    if (b.path === null) {
      return 1;
    }
    return a.path.localeCompare(b.path);
  });
}

export function filterDiagnostics(
  items: readonly IndexedDiagnostic[],
  enabled: ReadonlySet<DiagnosticSeverity>,
): IndexedDiagnostic[] {
  return items.filter((item) => enabled.has(item.diagnostic.severity));
}

function sourceLabel(source: DiagnosticSource): string {
  return `${source.kind}:${source.ref} · ${source.range.line}:${source.range.col}`;
}

function targetFor(resolveNode: NodeResolver, diagnostic: Diagnostic): NavigationTarget {
  if (resolveNode(diagnostic) !== null) {
    return "node";
  }
  return diagnostic.source === null || diagnostic.source === undefined ? "none" : "source";
}

function statusLabel(
  status: DiagnosticsStatus,
  workerState: WorkerState | null,
  checkedRevision: number | null,
): string {
  if (workerState === null || workerState === "starting") {
    return "Worker starting — checks paused";
  }
  if (workerState === "warming") {
    return "Worker warming up — checks paused";
  }
  if (workerState === "crashed") {
    return "Worker offline — checks paused";
  }
  switch (status) {
    case "checking":
      return "Checking…";
    case "waiting":
      return "Waiting for the worker…";
    case "ok":
      return checkedRevision === null ? "Up to date" : `Revision ${checkedRevision} checked`;
    case "error":
      return "The last check failed";
    default:
      return "Not checked yet";
  }
}

/**
 * The Diagnostics tab of the bottom dock. Filter by severity, group by path,
 * click a row to select and pan to the element (or to reveal its source range).
 */
export function DiagnosticsPanel() {
  const modelDiagnostics = useDiagnosticsStore((state) => state.diagnostics);
  // W5.2: the 3D view reports its scene problems (E305, E306) next to the model check.
  const viewerDiagnostics = useDiagnosticsStore((state) => state.viewerDiagnostics);
  const diagnostics = useMemo(
    () => (viewerDiagnostics.length === 0 ? modelDiagnostics : [...modelDiagnostics, ...viewerDiagnostics]),
    [modelDiagnostics, viewerDiagnostics],
  );
  const status = useDiagnosticsStore((state) => state.status);
  const error = useDiagnosticsStore((state) => state.error);
  const workerState = useDiagnosticsStore((state) => state.workerState);
  const counts = useDiagnosticsStore((state) => state.counts);
  const checkedRevision = useDiagnosticsStore((state) => state.checkedRevision);
  const sourceFocus = useDiagnosticsStore((state) => state.sourceFocus);
  const doc = useDocumentStore((state) => state.doc);
  const [enabled, setEnabled] = useState<ReadonlySet<DiagnosticSeverity>>(
    () => new Set(SEVERITIES),
  );
  const [active, setActive] = useState<number | null>(null);

  const indexed = useMemo(
    () => diagnostics.map((diagnostic, index) => ({ diagnostic, index })),
    [diagnostics],
  );
  const resolveNode = useMemo(() => createNodeResolver(doc), [doc]);
  const filtered = useMemo(() => filterDiagnostics(indexed, enabled), [indexed, enabled]);
  const groups = useMemo(() => groupDiagnostics(filtered), [filtered]);
  const allEnabled = SEVERITIES.every((severity) => enabled.has(severity));

  function toggle(severity: DiagnosticSeverity): void {
    setEnabled((current) => {
      const next = new Set(current);
      if (next.has(severity)) {
        next.delete(severity);
      } else {
        next.add(severity);
      }
      return next;
    });
  }

  function showAll(): void {
    setEnabled(new Set(SEVERITIES));
  }

  function select(item: IndexedDiagnostic): void {
    setActive(item.index);
    navigateToDiagnostic(item.diagnostic);
  }

  const paused =
    workerState === null ||
    workerState === "starting" ||
    workerState === "warming" ||
    workerState === "crashed";

  return (
    <div className="diagnostics" data-testid="diagnostics-panel">
      <header className="diagnostics__header">
        <div className="diagnostics__summary">
          {SEVERITIES.map((severity) => (
            <span
              key={severity}
              className="diagnostics__count"
              data-tone={severity}
              data-testid={`diagnostics-count-${severity}`}
              title={SEVERITY_LABEL[severity]}
            >
              <span className={`diagnostics__dot diagnostics__dot--${severity}`} aria-hidden="true" />
              {counts[severity]} {severity === "info" ? "info" : `${severity}${counts[severity] === 1 ? "" : "s"}`}
            </span>
          ))}
          <span className="diagnostics__spacer" />
          <span
            className="diagnostics__status"
            data-testid="diagnostics-status"
            data-state={paused ? "paused" : status}
            role="status"
            aria-live="polite"
          >
            {statusLabel(status, workerState, checkedRevision)}
          </span>
        </div>

        <div className="diagnostics__filters" role="group" aria-label="Filter by severity">
          {SEVERITIES.map((severity) => {
            const activeFilter = enabled.has(severity);
            return (
              <button
                key={severity}
                type="button"
                className="diagnostics__filter"
                data-testid={`diagnostics-filter-${severity}`}
                data-active={activeFilter ? "true" : "false"}
                aria-pressed={activeFilter}
                onClick={() => toggle(severity)}
              >
                <span
                  className={`diagnostics__dot diagnostics__dot--${severity}`}
                  aria-hidden="true"
                />
                {SEVERITY_LABEL[severity]}
                <span className="diagnostics__filter-count">{counts[severity]}</span>
              </button>
            );
          })}
          {!allEnabled ? (
            <button
              type="button"
              className="diagnostics__show-all"
              data-testid="diagnostics-show-all"
              onClick={showAll}
            >
              Show all
            </button>
          ) : null}
        </div>

        {error !== null ? (
          <p className="diagnostics__error" role="alert" data-testid="diagnostics-error">
            {error}
          </p>
        ) : null}

        {sourceFocus !== null ? (
          <p className="diagnostics__source-focus" data-testid="diagnostics-source-focus">
            Source <code>{sourceFocus.ref}</code> line {sourceFocus.line}, column{" "}
            {sourceFocus.col} — open the Code tab to edit it.
          </p>
        ) : null}
      </header>

      <div className="diagnostics__body">
        {doc === null ? (
          <EmptyState
            title="No model open"
            hint="Open a model to check it. Errors and warnings then appear here and on the canvas."
          />
        ) : diagnostics.length === 0 ? (
          paused ? (
            <p className="diagnostics__notice" data-testid="diagnostics-waiting">
              {statusLabel(status, workerState, checkedRevision)}. The model is checked
              automatically as soon as the worker is ready.
            </p>
          ) : status === "checking" ? (
            <p className="diagnostics__notice" data-testid="diagnostics-checking">
              Checking the model…
            </p>
          ) : status === "idle" ? (
            <p className="diagnostics__notice" data-testid="diagnostics-idle">
              Waiting for the first check…
            </p>
          ) : error !== null ? (
            <p className="diagnostics__notice" data-testid="diagnostics-check-failed">
              The checker did not return diagnostics. The message above says why.
            </p>
          ) : (
            <EmptyState
              title="No diagnostics"
              hint="The model check found nothing to report. Errors and warnings appear here and mark the canvas."
            />
          )
        ) : filtered.length === 0 ? (
          <div className="diagnostics__notice" data-testid="diagnostics-filter-empty">
            <span>No diagnostics match the filter.</span>
            <button type="button" className="diagnostics__show-all" onClick={showAll}>
              Show all
            </button>
          </div>
        ) : (
          <div className="diagnostics__groups">
            {groups.map((group, groupIndex) => {
              const groupId = `diagnostics-group-${groupIndex}`;
              return (
                <section
                  key={group.path ?? "\u0000model"}
                  className="diagnostics-group"
                  data-testid="diagnostics-group"
                  data-path={group.path ?? ""}
                  aria-labelledby={groupId}
                >
                  <h3 className="diagnostics-group__header" id={groupId}>
                    <span className="diagnostics-group__path">{group.label}</span>
                    <span className="diagnostics-group__count">{group.items.length}</span>
                  </h3>
                  <ul className="diagnostics-group__items">
                    {group.items.map((item) => {
                      const { diagnostic, index } = item;
                      const target = targetFor(resolveNode, diagnostic);
                      return (
                        <li key={index} className="diagnostics-item__row">
                          <button
                            type="button"
                            className="diagnostic-item"
                            data-testid={`diagnostic-item-${index}`}
                            data-code={diagnostic.code}
                            data-severity={diagnostic.severity}
                            data-path={diagnostic.path ?? ""}
                            data-node={diagnostic.node ?? ""}
                            data-target={target}
                            aria-current={active === index ? "true" : undefined}
                            title={diagnostic.hint ?? diagnostic.message}
                            onClick={() => select(item)}
                          >
                            <span
                              className={`diagnostic-item__severity diagnostic-item__severity--${diagnostic.severity}`}
                              aria-hidden="true"
                            >
                              {SEVERITY_GLYPH[diagnostic.severity]}
                            </span>
                            <span className="diagnostic-item__code">{diagnostic.code}</span>
                            <span className="diagnostic-item__text">
                              <span className="diagnostic-item__message">{diagnostic.message}</span>
                              {diagnostic.hint !== null && diagnostic.hint !== undefined ? (
                                <span className="diagnostic-item__hint">{diagnostic.hint}</span>
                              ) : null}
                              <span className="diagnostic-item__meta">
                                {diagnostic.block !== null && diagnostic.block !== undefined ? (
                                  <span className="diagnostic-item__chip">{diagnostic.block}</span>
                                ) : null}
                                {diagnostic.scope !== null && diagnostic.scope !== undefined ? (
                                  <span className="diagnostic-item__chip">{diagnostic.scope}</span>
                                ) : null}
                                {diagnostic.source !== null && diagnostic.source !== undefined ? (
                                  <span
                                    className="diagnostic-item__source"
                                    data-testid={`diagnostic-source-${index}`}
                                  >
                                    {sourceLabel(diagnostic.source)}
                                  </span>
                                ) : null}
                              </span>
                            </span>
                            <span className="diagnostic-item__goto" aria-hidden="true">
                              {target === "node" ? "→" : target === "source" ? "↧" : ""}
                            </span>
                          </button>
                          {diagnostic.related !== undefined && diagnostic.related.length > 0 ? (
                            <ul
                              className="diagnostics-related"
                              data-testid={`diagnostic-related-${index}`}
                            >
                              {diagnostic.related.map((related, relatedIndex) => (
                                <li key={relatedIndex}>
                                  <button
                                    type="button"
                                    className="diagnostics-related__button"
                                    data-testid={`diagnostic-related-${index}-${relatedIndex}`}
                                    onClick={() => navigateToPath(related.path)}
                                  >
                                    <span className="diagnostics-related__arrow" aria-hidden="true">
                                      ↳
                                    </span>
                                    <span className="diagnostics-related__path">
                                      {related.path ?? "Model"}
                                    </span>
                                    <span className="diagnostics-related__message">
                                      {related.message}
                                    </span>
                                  </button>
                                </li>
                              ))}
                            </ul>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                </section>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
