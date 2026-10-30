/**
 * Run, Stop and the simulation settings of plan 7.2, mounted by `TopBar`.
 *
 * The three settings are views of the open model document's `settings`
 * (`t_end`, `solver`, and `tol` = the relative tolerance); edits go back to
 * the document so auto-save persists them and the next run sends them to the
 * worker. The bar also shows the worker phase and `t / t_end` while running,
 * and `done in X s` afterwards. Ctrl+Enter runs; Escape cancels an in-progress
 * plot drag (handled by the chart).
 */

import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { useBreakpointStore } from "../debug/breakpointStore";
import { DebugControls } from "../debug/DebugControls";
import { isDebugging, useDebugStore } from "../debug/debugStore";
import { pausedStatusText } from "../debug/format";
import { useDocumentStore } from "../state/documentStore";
import { formatDuration, formatProgress } from "../plot/format";
import { useRunStore } from "../plot/runStore";
import {
  isValidEndTime,
  isValidTolerance,
  parseFiniteNumber,
  updateModelSettings,
} from "../plot/settings";
import "../plot/runbar.css";

/** The solvers offered by the top bar; the model may name any of them. */
const SOLVER_OPTIONS = [
  "auto",
  "Rodas5P",
  "Rodas5",
  "Rosenbrock23",
  "Tsit5",
  "Vern7",
] as const;

export function RunBar() {
  const project = useDocumentStore((state) => state.project);
  const modelName = useDocumentStore((state) => state.modelName);
  const doc = useDocumentStore((state) => state.doc);
  const settings = doc?.settings ?? null;

  const status = useRunStore((state) => state.status);
  const phase = useRunStore((state) => state.phase);
  const progress = useRunStore((state) => state.progress);
  const stats = useRunStore((state) => state.stats);
  const manifestStats = useRunStore((state) => state.manifest?.stats);
  const manifestSettings = useRunStore((state) => state.manifest?.settings);
  const error = useRunStore((state) => state.error);
  const stopping = useRunStore((state) => state.stopping);
  const runId = useRunStore((state) => state.runId);
  const debugPaused = useDebugStore((state) => state.status === "paused");
  const debugging = useDebugStore((state) => isDebugging(state));
  const pausedInfo = useDebugStore((state) => state.pausedInfo);
  const debugBreakpoints = useBreakpointStore((state) => state.breakpoints);
  const startRun = useRunStore((state) => state.startRun);
  const stopRun = useRunStore((state) => state.stopRun);

  const [endDraft, setEndDraft] = useState("1");
  const [tolDraft, setTolDraft] = useState("1e-6");
  const [endInvalid, setEndInvalid] = useState(false);
  const [tolInvalid, setTolInvalid] = useState(false);

  const hasModel = doc !== null && project !== null;
  const busy = status === "starting" || status === "running";
  const canRun = hasModel && !busy && !stopping;
  const canStop = runId !== null && busy && !stopping;

  // Keep the inputs in step with the document (including a reload or undo).
  useEffect(() => {
    if (settings === null) {
      return;
    }
    setEndDraft(String(settings.t_end));
    setTolDraft(String(settings.reltol));
    setEndInvalid(false);
    setTolInvalid(false);
  }, [settings?.t_end, settings?.reltol]);

  // A different model must not inherit the previous run's plots or status.
  const modelKey =
    project !== null && modelName !== null ? `${project}/${modelName}` : null;
  const lastModelKey = useRef<string | null>(null);
  useEffect(() => {
    if (modelKey !== lastModelKey.current) {
      lastModelKey.current = modelKey;
      useRunStore.getState().reset();
    }
  }, [modelKey]);

  // Ctrl+Enter (or Cmd+Enter) runs from anywhere in the editor.
  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent): void => {
      if (
        (event.ctrlKey || event.metaKey) &&
        (event.key === "Enter" || event.key === "NumpadEnter")
      ) {
        event.preventDefault();
        if (canRun) {
          void startRun();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [canRun, startRun]);

  const commitEnd = (): void => {
    if (settings === null) {
      return;
    }
    const value = parseFiniteNumber(endDraft);
    if (value === null || !isValidEndTime(value, settings.t_start)) {
      setEndInvalid(true);
      return;
    }
    if (updateModelSettings({ t_end: value })) {
      setEndDraft(String(value));
      setEndInvalid(false);
    } else {
      setEndInvalid(true);
    }
  };

  const commitTolerance = (): void => {
    const value = parseFiniteNumber(tolDraft);
    if (value === null || !isValidTolerance(value)) {
      setTolInvalid(true);
      return;
    }
    if (updateModelSettings({ reltol: value })) {
      setTolDraft(String(value));
      setTolInvalid(false);
    } else {
      setTolInvalid(true);
    }
  };

  const resetDrafts = (): void => {
    if (settings === null) {
      return;
    }
    setEndDraft(String(settings.t_end));
    setTolDraft(String(settings.reltol));
    setEndInvalid(false);
    setTolInvalid(false);
  };

  const onSettingKeyDown = (
    event: KeyboardEvent<HTMLInputElement>,
    commit: () => void,
  ): void => {
    if (event.key === "Enter") {
      event.preventDefault();
      commit();
      event.currentTarget.blur();
    } else if (event.key === "Escape") {
      event.preventDefault();
      resetDrafts();
      event.currentTarget.blur();
    }
  };

  const tEnd = manifestSettings?.t_end ?? settings?.t_end ?? 0;
  const t = progress?.t ?? settings?.t_start ?? 0;
  const solver = settings?.solver ?? "auto";
  const solverOptions = (SOLVER_OPTIONS as readonly string[]).includes(solver)
    ? SOLVER_OPTIONS
    : [solver, ...SOLVER_OPTIONS];

  let statusText = "ready";
  if (!hasModel) {
    statusText = "open a model to run";
  } else if (status === "starting") {
    statusText = "starting…";
  } else if (status === "running" && debugPaused && pausedInfo !== null) {
    statusText = pausedStatusText(pausedInfo, debugBreakpoints, doc);
  } else if (status === "running") {
    statusText = `${phase ?? "running"} · ${formatProgress(t, tEnd)}`;
  } else if (status === "done") {
    statusText = `done in ${formatDuration(stats?.sim_s ?? manifestStats?.sim_s)}`;
  } else if (status === "cancelled") {
    statusText = "cancelled";
  } else if (status === "failed") {
    statusText = error === null ? "failed" : `failed: ${error}`;
  }

  return (
    <>
      <div className="top-bar__run" role="group" aria-label="Simulation controls">
        <button
          type="button"
          className="button button--primary"
          onClick={() => void startRun()}
          disabled={!canRun}
          aria-label="Run simulation"
          data-testid="run-button"
          title={
            canRun
              ? "Run the model (Ctrl+Enter)"
              : hasModel
                ? "A run is already active"
                : "Open a model to run it"
          }
        >
          <span className="button__glyph" aria-hidden="true">
            ▶
          </span>
          Run
        </button>
        <DebugControls canStart={canRun} />
        <button
          type="button"
          className="button"
          onClick={() => void stopRun()}
          disabled={!canStop}
          aria-label="Stop simulation"
          data-testid="stop-button"
          title={
            canStop
              ? debugPaused || status === "running"
                ? "Stop the run (Shift+F5 while debugging)"
                : "Stop the run"
              : "Stop is available while a run is active"
          }
        >
          <span className="button__glyph" aria-hidden="true">
            ■
          </span>
          {stopping ? "Stopping…" : "Stop"}
        </button>
      </div>

      <div className="top-bar__settings" hidden={debugging}>
        <label className="setting">
          <span className="setting__label">t_end</span>
          <input
            className={`setting__value${endInvalid ? " is-invalid" : ""}`}
            type="text"
            inputMode="decimal"
            value={hasModel ? endDraft : ""}
            placeholder="—"
            disabled={!hasModel}
            aria-label="t_end"
            aria-invalid={endInvalid}
            data-testid="setting-tend"
            title="End time in seconds; must be greater than t_start"
            onChange={(event) => {
              setEndDraft(event.target.value);
              setEndInvalid(false);
            }}
            onBlur={commitEnd}
            onKeyDown={(event) => onSettingKeyDown(event, commitEnd)}
          />
        </label>

        <label className="setting">
          <span className="setting__label">solver</span>
          <select
            className="setting__value setting__value--solver"
            value={solver}
            disabled={!hasModel}
            aria-label="solver"
            data-testid="setting-solver"
            title="Solver name, or auto"
            onChange={(event) => {
              updateModelSettings({ solver: event.target.value });
            }}
          >
            {solverOptions.map((option) => (
              <option value={option} key={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="setting">
          <span className="setting__label">tol</span>
          <input
            className={`setting__value${tolInvalid ? " is-invalid" : ""}`}
            type="text"
            inputMode="decimal"
            value={hasModel ? tolDraft : ""}
            placeholder="—"
            disabled={!hasModel}
            aria-label="tol"
            aria-invalid={tolInvalid}
            data-testid="setting-tol"
            title="Relative tolerance (reltol); must be positive"
            onChange={(event) => {
              setTolDraft(event.target.value);
              setTolInvalid(false);
            }}
            onBlur={commitTolerance}
            onKeyDown={(event) => onSettingKeyDown(event, commitTolerance)}
          />
        </label>
      </div>

      {status === "starting" || (status === "running" && !debugPaused) ? (
        <span
          className="run-bar__progress"
          data-testid="run-progress"
          title={`Simulation time ${formatProgress(t, tEnd)}`}
        >
          <progress
            value={Math.max(0, Math.min(t, tEnd))}
            max={tEnd > 0 ? tEnd : 1}
            aria-label="Simulation progress"
          />
          <span>{formatProgress(t, tEnd)}</span>
        </span>
      ) : null}

      <span
        className="run-bar__status"
        data-testid="run-status"
        data-status={debugPaused && pausedInfo !== null ? "paused" : status}
        role="status"
        aria-live="polite"
        title={error ?? statusText}
      >
        {statusText}
      </span>
    </>
  );
}
