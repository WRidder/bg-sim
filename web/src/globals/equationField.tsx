/**
 * SolidWorks-style "driven value" decoration of an inspector expression field.
 *
 * A field holds either a plain value or an equation (anything that is not a
 * plain literal: a global parameter, arithmetic, a function). An equation gets
 * the Σ marker, shows its evaluated value with the unit ("= 8 N/m"), and the
 * input's tooltip shows the equation. Global names are offered while typing.
 * The stored value stays the plain expression string; a leading `=` is
 * accepted as the SolidWorks equation prefix and dropped on commit.
 */

import { useMemo, type ReactNode } from "react";

import { useDocumentStore } from "../state/documentStore";
import {
  evaluateField,
  evaluateGlobals,
  formatValue,
  type GlobalEvaluation,
  globalsOf,
} from "./globals";
import { stripEquationPrefix } from "../inspector/expression";
import "./globals.css";

const EMPTY: GlobalEvaluation = evaluateGlobals([]);

/** The global parameter table of the open model, evaluated (memoised on the array). */
export function useGlobalEvaluation(): GlobalEvaluation {
  const parameters = useDocumentStore((state) => state.doc?.parameters);
  return useMemo(
    () => (parameters === undefined ? EMPTY : evaluateGlobals(globalsOf({ parameters }))),
    [parameters],
  );
}

export interface EquationFieldProps {
  completions: readonly string[];
  describeCompletion: (name: string) => string | null;
  readout: ReactNode;
  inputTitle: string | undefined;
  /** The Σ badge, or null for a plain value. */
  sigma: ReactNode;
}

/** The TextField props that decorate `text` (the stored value) as a driven value. */
export function equationFieldProps(
  text: string,
  unit: string | null | undefined,
  evaluation: GlobalEvaluation,
  testId: string,
): EquationFieldProps {
  const expression = stripEquationPrefix(text);
  const completions = [...evaluation.byName.keys()];
  const describeCompletion = (name: string): string | null => {
    const status = evaluation.byName.get(name);
    if (status === undefined) {
      return null;
    }
    return status.value === null ? "error" : `= ${formatValue(status.value)}`;
  };
  if (expression.length === 0) {
    return { completions, describeCompletion, readout: null, inputTitle: undefined, sigma: null };
  }
  const field = evaluateField(expression, evaluation);
  if (!field.driven) {
    return { completions, describeCompletion, readout: null, inputTitle: undefined, sigma: null };
  }
  const unitText = unit === null || unit === undefined || unit.length === 0 ? "" : ` ${unit}`;
  const readout =
    field.value !== null ? (
      <span className="equation-readout" data-testid={`${testId}-value`} title={`${expression} = ${formatValue(field.value)}${unitText}`}>
        = {formatValue(field.value)}
        {unitText}
      </span>
    ) : null;
  const sigma = (
    <span
      className="inspector-tag inspector-tag--equation"
      data-testid={`${testId}-sigma`}
      title={`Driven by an equation: ${expression}`}
      aria-label="Driven by an equation"
    >
      Σ
    </span>
  );
  return {
    completions,
    describeCompletion,
    readout,
    inputTitle: `Equation: ${expression}`,
    sigma,
  };
}
