/**
 * The inspector in live mode (plan 7.9, "At a pause"): while the debug run is paused, parameter fields edit
 * the paused run. A change is sent to the worker (`liveEdit.ts`), listed under Edits, and never written to
 * the model document. The banner says so.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";

import type { ParameterDecl } from "../contracts/catalog";
import type { ModelNode } from "../contracts/model";
import { useDebugStore } from "../debug/debugStore";
import { useRunStore } from "../plot/runStore";
import {
  latestLiveValue,
  liveModeOf,
  liveParameterName,
  parseLiveValue,
  sendLiveParameter,
  type LiveMode,
} from "./liveEdit";
import { parameterIssue } from "./validation";

/** The pause the inspector is live at, or null when the shown run is not paused. */
export function useLiveMode(): LiveMode | null {
  const runId = useRunStore((state) => state.runId);
  const status = useDebugStore((state) => state.status);
  const debugRunId = useDebugStore((state) => state.runId);
  const pausedInfo = useDebugStore((state) => state.pausedInfo);
  return liveModeOf({ status, runId: debugRunId, pausedInfo }, runId);
}

/** "Live: changes apply to the paused run"; nothing when the run is not paused. */
export function LiveBanner(): ReactNode {
  const live = useLiveMode();
  if (live === null) {
    return null;
  }
  return (
    <p className="inspector-live" role="status" data-testid="inspector-live-banner" data-pause-time={live.t}>
      <strong>Live:</strong> changes apply to the paused run (t = {live.t.toFixed(4)} s) and are listed under
      Edits. The model is not changed until you choose Save parameters to model.
    </p>
  );
}

export interface LiveParameterFieldProps {
  node: ModelNode;
  decl: ParameterDecl;
  /** Instance names of the subsystem path to the node's diagram, root first. */
  path: readonly string[];
  live: LiveMode;
}

/** A numeric parameter field that edits the paused run. */
export function LiveParameterField({ node, decl, path, live }: LiveParameterFieldProps) {
  const name = liveParameterName(path, node.name, decl.name);
  const edits = useRunStore((state) => state.manifest?.debug?.edits);
  const edited = latestLiveValue(edits, name);
  const modelValue = node.params?.[decl.name] ?? decl.default;
  const shown = edited === null ? modelValue : String(edited);
  const [draft, setDraft] = useState(shown);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const lastShown = useRef(shown);
  const skipBlur = useRef(false);
  const sending = useRef(false);
  const id = `inspector-param-${decl.name}`;

  useEffect(() => {
    if (lastShown.current !== shown) {
      lastShown.current = shown;
      setDraft(shown);
    }
  }, [shown]);

  const issue = (text: string): string | null => {
    if (decl.type === "Bool") {
      return "Live edits change numbers. Edit a true/false parameter in the model after the run.";
    }
    const parsed = parseLiveValue(text);
    if (!parsed.ok) {
      return parsed.message;
    }
    return parameterIssue(String(parsed.value), decl);
  };

  const commit = async (): Promise<boolean> => {
    const text = draft.trim();
    const problem = issue(text);
    if (problem !== null) {
      setError(problem);
      return false;
    }
    if (text === shown.trim()) {
      setError(null);
      return true;
    }
    if (sending.current) {
      return false;
    }
    sending.current = true;
    setBusy(true);
    const result = await sendLiveParameter(live.runId, name, text);
    sending.current = false;
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return false;
    }
    setError(null);
    lastShown.current = String(result.edit.value);
    setDraft(String(result.edit.value));
    return true;
  };

  return (
    <div className="inspector-field inspector-field--live" data-testid={`${id}-field`}>
      <div className="inspector-field__head">
        <label className="inspector-field__label" htmlFor={id}>
          {decl.name}
        </label>
        <span className="inspector-tag inspector-tag--live">live</span>
        {decl.unit !== undefined ? (
          <span
            className="inspector-field__unit"
            title={decl.unit === null ? "Dimensionless" : `Unit: ${decl.unit}`}
          >
            {decl.unit ?? "—"}
          </span>
        ) : null}
      </div>
      <div className="inspector-field__row">
        <input
          id={id}
          className="inspector-input"
          data-testid={id}
          data-live="true"
          type="text"
          inputMode="decimal"
          value={draft}
          disabled={busy}
          aria-invalid={error !== null}
          aria-describedby={error !== null ? `${id}-error` : undefined}
          autoComplete="off"
          spellCheck={false}
          onChange={(event) => {
            setDraft(event.target.value);
            setError(issue(event.target.value));
          }}
          onBlur={() => {
            if (skipBlur.current) {
              skipBlur.current = false;
              return;
            }
            void commit();
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void commit();
            } else if (event.key === "Escape") {
              event.preventDefault();
              skipBlur.current = true;
              setDraft(shown);
              setError(null);
              event.currentTarget.blur();
            }
          }}
        />
      </div>
      <p className="inspector-field__meta">
        {edited === null ? (
          <span>
            model value <code>{modelValue}</code>
          </span>
        ) : (
          <span data-testid={`${id}-live-value`}>
            live value <code>{edited}</code> (model <code>{modelValue}</code>)
          </span>
        )}
        <span className="inspector-dot">·</span>
        <span>
          sent as <code>{name}</code>
        </span>
      </p>
      {error !== null ? (
        <p className="inspector-field__error" id={`${id}-error`} role="alert" data-testid={`${id}-error`}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
