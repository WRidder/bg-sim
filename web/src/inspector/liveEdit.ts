/**
 * Live parameter edits (plan 7.9, "At a pause"): while a debug run is paused the inspector changes a
 * parameter of the paused run, not of the model. The change is sent as
 *
 *     POST /api/runs/{id}/debug/setParameter  { name: "<instance path>/<param>", value }
 *
 * and shows up under Edits (the run manifest's `debug.edits`). The model document, its undo stack and
 * autosave are never touched; "Save parameters to model" (W4.2) is the only way into the model.
 */

import type { Diagnostic } from "../contracts/diagnostic";
import type { Edit } from "../contracts/debug";
import { postDebugCommand } from "../debug/debugApi";
import { useDebugStore } from "../debug/debugStore";
import { fetchRunManifest } from "../plot/runApi";
import { useRunStore } from "../plot/runStore";
import { evaluateLiteral, parseExpression } from "./expression";

/** `Rig/Motor1/R`: the instance names from the root diagram to the node, then the parameter. */
export function liveParameterName(
  path: readonly string[],
  nodeName: string,
  parameter: string,
): string {
  return [...path, nodeName, parameter].join("/");
}

export type LiveValue = { ok: true; value: number } | { ok: false; message: string };

const NUMERIC_HINT =
  "Live edits take a number such as 2.5 or 1e-3 (constants like pi and plain arithmetic work). " +
  "Names and function calls can only be edited in the model after the run.";

/** Parse the text of a live edit: a finite number, possibly written as literal arithmetic. */
export function parseLiveValue(text: string): LiveValue {
  const trimmed = text.trim();
  if (trimmed.length === 0) {
    return { ok: false, message: "Enter a number." };
  }
  const parsed = parseExpression(trimmed);
  if (!parsed.ok) {
    return { ok: false, message: parsed.message };
  }
  const value = evaluateLiteral(parsed.ast);
  if (value === null) {
    return { ok: false, message: `"${trimmed}" is not a number. ${NUMERIC_HINT}` };
  }
  if (!Number.isFinite(value)) {
    return { ok: false, message: "The value must be a finite number." };
  }
  return { ok: true, value };
}

/** The pause the inspector is live at, or null when the shown run is not paused. */
export interface LiveMode {
  runId: string;
  /** The pause time in seconds. */
  t: number;
}

/** Pure form of {@link useLiveMode}: live only while the shown run is the paused debug run. */
export function liveModeOf(
  debug: { status: string; runId: string | null; pausedInfo: { t: number } | null },
  shownRunId: string | null,
): LiveMode | null {
  if (debug.status !== "paused" || debug.runId === null || debug.runId !== shownRunId) {
    return null;
  }
  return debug.pausedInfo === null ? null : { runId: debug.runId, t: debug.pausedInfo.t };
}

export function currentLiveMode(): LiveMode | null {
  return liveModeOf(useDebugStore.getState(), useRunStore.getState().runId);
}

function diagnosticText(diagnostics: readonly Diagnostic[]): string | null {
  const first = diagnostics.find((entry) => entry.severity === "error") ?? diagnostics[0];
  if (first === undefined) {
    return null;
  }
  const code = first.code.length > 0 ? `${first.code}: ` : "";
  const hint = first.hint !== undefined && first.hint !== null && first.hint.length > 0 ? ` ${first.hint}` : "";
  return `${code}${first.message}${hint}`;
}

export type LiveEditResult = { ok: true; edit: Edit } | { ok: false; message: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Send one live parameter edit. Resolves with the recorded edit, or with the server's refusal (its
 * diagnostics) or the validation message; it never rejects. On success the run manifest is refreshed so
 * the edit is listed under Edits at once.
 */
export async function sendLiveParameter(
  runId: string,
  name: string,
  text: string,
): Promise<LiveEditResult> {
  const parsed = parseLiveValue(text);
  if (!parsed.ok) {
    return parsed;
  }
  let body: unknown;
  try {
    body = await postDebugCommand(runId, "setParameter", { name, value: parsed.value });
  } catch (error) {
    return { ok: false, message: error instanceof Error ? error.message : String(error) };
  }
  if (!isRecord(body) || body.ok !== true || !isRecord(body.edit)) {
    const diagnostics = isRecord(body) && Array.isArray(body.diagnostics) ? (body.diagnostics as Diagnostic[]) : [];
    return {
      ok: false,
      message: diagnosticText(diagnostics) ?? `The worker refused to change ${name}.`,
    };
  }
  await refreshEdits(runId);
  return { ok: true, edit: body.edit as unknown as Edit };
}

/** Re-read the run manifest so the new edit appears under Edits without waiting for the poll. */
async function refreshEdits(runId: string): Promise<void> {
  try {
    const manifest = await fetchRunManifest(runId);
    if (useRunStore.getState().runId === runId) {
      useRunStore.setState({ manifest });
    }
  } catch {
    /* the manifest poll publishes the edit within a poll interval */
  }
}

/** The latest live value of `name` in the run's edits, or null. */
export function latestLiveValue(edits: readonly Edit[] | undefined, name: string): number | null {
  let value: number | null = null;
  for (const edit of edits ?? []) {
    if (edit.kind === "parameter" && edit.target === name) {
      value = edit.value;
    }
  }
  return value;
}
