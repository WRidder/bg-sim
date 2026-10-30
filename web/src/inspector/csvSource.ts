/**
 * Pure helpers of the CsvSource inspector (F5.1): which blocks are CSV sources, how the file
 * settings (the node constants) select columns, and what the output vector `y` holds.
 */

import type { CsvColumn } from "../api/data";

export const CSV_SOURCE_REFS: readonly string[] = [
  "stdlib:sources/CsvSource",
  "stdlib:sources/CsvSourceSampled",
];

/** The interpolation methods in the order of the `method` constant (0, 1, 2). */
export const CSV_METHODS = ["hold", "linear", "cubic"] as const;
/** The extrapolation modes in the order of the `extrapolation` constant (0, 1). */
export const CSV_EXTRAPOLATION = ["hold", "error"] as const;

export function isCsvSourceRef(ref: string | null): boolean {
  return ref !== null && CSV_SOURCE_REFS.includes(ref);
}

export interface CsvSettings {
  file: string;
  timeColumn: string;
  columns: string[];
}

function textOf(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** The file settings stored in a node constants map (`columns` is a comma separated list). */
export function csvSettings(constants: Readonly<Record<string, unknown>> | undefined): CsvSettings {
  const columns = textOf(constants?.columns)
    .split(",")
    .map((name) => name.trim())
    .filter((name) => name.length > 0);
  return { file: textOf(constants?.file), timeColumn: textOf(constants?.time_column), columns };
}

export interface CsvOutput {
  /** 1-based index in the output vector `y`. */
  index: number;
  name: string;
  unit: string;
}

/**
 * The output columns for a header: the explicit `columns` list in its order, or every column
 * except the time column in file order (the first one unless `time_column` names another).
 * `missing` lists names that the header does not have.
 */
export function csvOutputs(
  header: readonly CsvColumn[],
  settings: CsvSettings,
): { outputs: CsvOutput[]; missing: string[]; timeColumn: string | null } {
  const timeName = settings.timeColumn.length > 0 ? settings.timeColumn : (header[0]?.name ?? null);
  const byName = new Map(header.map((column) => [column.name, column] as const));
  const missing: string[] = [];
  let chosen: CsvColumn[];
  if (settings.columns.length === 0) {
    chosen = header.filter((column) => column.name !== timeName);
  } else {
    chosen = [];
    for (const name of settings.columns) {
      const column = byName.get(name);
      if (column === undefined || name === timeName) {
        missing.push(name);
      } else {
        chosen.push(column);
      }
    }
  }
  if (settings.timeColumn.length > 0 && !byName.has(settings.timeColumn)) {
    missing.push(settings.timeColumn);
  }
  return {
    outputs: chosen.map((column, position) => ({
      index: position + 1,
      name: column.name,
      unit: column.unit,
    })),
    missing,
    timeColumn: timeName,
  };
}

/** `y[1] = q1 [rad]` for the output list under the preview. */
export function outputLabel(output: CsvOutput): string {
  return `y[${output.index}] = ${output.name}${output.unit.length > 0 ? ` [${output.unit}]` : ""}`;
}
