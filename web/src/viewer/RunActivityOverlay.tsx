import { describeRunActivity, formatElapsed, hasSamples, PRE_SIM_STAGES, useElapsed } from "../app/runActivity";
import { useDebugStore } from "../debug/debugStore";
import { useRunStore } from "../plot/runStore";
import "../plot/runbar.css";

/**
 * Over the 3D view while a run compiles, initializes and takes its first step (no sample yet): the stages with the current one
 * marked, the time spent, and Stop. It goes away with the first samples, when the view starts to move.
 */
export function RunActivityOverlay() {
  const status = useRunStore((s) => s.status);
  const phase = useRunStore((s) => s.phase);
  const startedAt = useRunStore((s) => s.startedAt);
  const phaseAt = useRunStore((s) => s.phaseAt);
  const runId = useRunStore((s) => s.runId);
  const stopping = useRunStore((s) => s.stopping);
  const stopRun = useRunStore((s) => s.stopRun);
  const progress = useRunStore((s) => s.progress);
  const debugPaused = useDebugStore((s) => s.status === "paused");
  const activity = describeRunActivity(status, phase, debugPaused, hasSamples(progress));
  const elapsed = useElapsed(startedAt, activity.preparing);
  const phaseElapsed = useElapsed(phaseAt, activity.preparing);
  if (!activity.preparing) return null;

  const current = PRE_SIM_STAGES.findIndex((s) => s.stage === activity.stage);
  return (
    <div className="run-overlay" data-testid="run-overlay" data-stage={activity.stage ?? ""}>
      <div className="run-overlay__card" role="status" aria-live="polite">
        <div className="run-overlay__head">
          <span className="run-activity__spinner" aria-hidden="true" />
          <span className="run-overlay__title">{activity.stage === "simulate" ? "Starting the solver…" : `${activity.label} the model…`}</span>
          <span className="run-overlay__time" title="Since Run">
            {formatElapsed(elapsed)}
          </span>
        </div>
        <ol className="run-overlay__steps">
          {PRE_SIM_STAGES.map((s, i) => {
            const state = i < current ? "done" : i === current ? "active" : "todo";
            return (
              <li key={s.stage} className="run-overlay__step" data-state={state}>
                <span className="run-overlay__mark" aria-hidden="true">
                  {state === "done" ? "✓" : state === "active" ? "●" : "○"}
                </span>
                <span>{s.label}</span>
                {state === "active" ? <span className="run-overlay__step-time">{formatElapsed(phaseElapsed)}</span> : null}
              </li>
            );
          })}
        </ol>
        <div className="run-activity__bar is-indeterminate" aria-hidden="true">
          <span />
        </div>
        <p className="run-overlay__hint">
          {activity.stage === "simulate"
            ? "The solver compiles its first step; the view starts moving with the first samples."
            : "Large models can take a while to compile; the view starts moving with the first samples."}
        </p>
        <button
          type="button"
          className="button"
          data-testid="run-overlay-stop"
          disabled={runId === null || stopping}
          onClick={() => void stopRun()}
        >
          {stopping ? "Stopping…" : "Stop"}
        </button>
      </div>
    </div>
  );
}
