/**
 * The Explain popover (plan 7.9, 5.13): the `model.explain` result of one
 * signal: kind, unit, the defining expression, the alias target, the source
 * equations (their origins open the Code tab at the line) and the W201 / W202
 * findings. It works without a run.
 */

import { useEffect, useRef } from "react";

import { requestSource } from "../../code/codeSession";
import type { ExplainEquation, ExplainKind, ExplainResult } from "../../contracts/debug";
import { sourceKindOf } from "../pauseNavigation";
import { openExplain, useExplainStore } from "./explainStore";

export const EXPLAIN_KIND_TEXT: Record<ExplainKind, string> = {
  state: "State variable",
  algebraic: "Algebraic variable",
  observed: "Observed variable",
  alias: "Alias",
  parameter: "Parameter",
  discrete: "Discrete signal",
};

/** `LQGController line 14`, or the path alone when the origin has no range. */
export function originLabel(equation: ExplainEquation): string {
  const { path, ref, range } = equation.origin;
  const where =
    ref === null
      ? "source unknown"
      : range === null
        ? ref
        : `${ref.slice(ref.indexOf(":") + 1)} line ${range.line}`;
  return path !== null && path.length > 0 ? `${where} (${path})` : where;
}

/** Open the Code tab at an equation's origin; false when the origin has no source reference. */
export function openOrigin(equation: ExplainEquation): boolean {
  const { ref, range } = equation.origin;
  if (ref === null) {
    return false;
  }
  requestSource(
    {
      kind: sourceKindOf(ref),
      ref,
      line: range?.line ?? 1,
      col: range?.col ?? 1,
    },
    { reveal: true },
  );
  return true;
}

/** The body of the popover; separate from the shell so tests can render a fixed result. */
export function ExplainBody({
  result,
  onNavigate,
}: {
  result: ExplainResult;
  onNavigate?: () => void;
}) {
  return (
    <div className="explain__body" data-testid="explain-body">
      <dl className="explain__facts">
        <dt>Kind</dt>
        <dd data-testid="explain-kind">{EXPLAIN_KIND_TEXT[result.kind]}</dd>
        <dt>Unit</dt>
        <dd data-testid="explain-unit">{result.unit ?? "dimensionless"}</dd>
        {result.expression !== null ? (
          <>
            <dt>Defined by</dt>
            <dd>
              <code data-testid="explain-expression">{result.expression}</code>
            </dd>
          </>
        ) : null}
        {result.aliasOf !== null ? (
          <>
            <dt>Alias of</dt>
            <dd>
              <button
                type="button"
                className="explain__link"
                data-testid="explain-alias"
                title={`Explain ${result.aliasOf}`}
                onClick={() => openExplain(result.aliasOf as string)}
              >
                {result.aliasOf}
              </button>
            </dd>
          </>
        ) : null}
      </dl>
      <h3 className="explain__heading">Source equations</h3>
      {result.equations.length === 0 ? (
        <p className="explain__empty">
          No source equation defines this signal directly. It is set by the solver or by a connection.
        </p>
      ) : (
        <ul className="explain__equations" data-testid="explain-equations">
          {result.equations.map((equation, index) => (
            <li key={`${equation.text}-${index}`}>
              <code>{equation.text}</code>
              {equation.origin.ref !== null ? (
                <button
                  type="button"
                  className="explain__link"
                  data-testid="explain-origin"
                  title="Open this equation in the Code tab"
                  onClick={() => {
                    if (openOrigin(equation)) {
                      onNavigate?.();
                    }
                  }}
                >
                  {originLabel(equation)}
                </button>
              ) : (
                <span className="explain__muted">{originLabel(equation)}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {result.diagnostics.length > 0 ? (
        <>
          <h3 className="explain__heading">Findings</h3>
          <ul className="explain__findings" data-testid="explain-findings">
            {result.diagnostics.map((diagnostic, index) => (
              <li key={`${diagnostic.code}-${index}`} data-severity={diagnostic.severity}>
                <strong>{diagnostic.code}</strong> {diagnostic.message}
                {diagnostic.hint ? <span className="explain__muted"> {diagnostic.hint}</span> : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

/** Mounted once (in the bottom dock); shows the popover while a signal is being explained. */
export function ExplainPopover() {
  const signalId = useExplainStore((state) => state.signalId);
  const status = useExplainStore((state) => state.status);
  const result = useExplainStore((state) => state.result);
  const error = useExplainStore((state) => state.error);
  const close = useExplainStore((state) => state.close);
  const root = useRef<HTMLElement>(null);

  const open = signalId !== null;
  useEffect(() => {
    if (!open) {
      return;
    }
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    root.current?.focus();
    return () => {
      if (opener !== null && document.contains(opener)) {
        opener.focus();
      }
    };
  }, [open]);

  if (signalId === null) {
    return null;
  }
  return (
    <section
      className="explain"
      role="dialog"
      aria-label={`Explain ${signalId}`}
      data-testid="explain-popover"
      data-status={status}
      ref={root}
      tabIndex={-1}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          close();
        }
      }}
    >
      <header className="explain__header">
        <h2 className="explain__title" data-testid="explain-title">
          {signalId}
        </h2>
        <button
          type="button"
          className="icon-button"
          aria-label="Close the explanation"
          title="Close (Esc)"
          data-testid="explain-close"
          onClick={close}
        >
          <span aria-hidden="true">✕</span>
        </button>
      </header>
      {status === "loading" ? (
        <p className="explain__empty" role="status">
          Explaining the signal…
        </p>
      ) : null}
      {status === "error" ? (
        <p className="explain__error" role="alert" data-testid="explain-error">
          {error} Check the model for errors (Diagnostics tab), then try again.
        </p>
      ) : null}
      {status === "ready" && result !== null ? <ExplainBody result={result} onNavigate={close} /> : null}
    </section>
  );
}
