import type { WorkerState } from "../api/health";
import { useWorkerStore } from "../api/workerStore";

const MESSAGES: Record<WorkerState, { title: string; hint: string }> = {
  starting: {
    title: "Waiting for the worker",
    hint: "The Julia worker is starting. This opens by itself when it is ready; the first start can take a minute.",
  },
  warming: {
    title: "The worker is warming up",
    hint: "The Julia worker is compiling its code. This opens by itself when it is ready.",
  },
  ready: {
    title: "Connecting to the worker",
    hint: "The worker is ready; opening…",
  },
  crashed: {
    title: "The worker is not answering",
    hint: "The editor keeps checking and opens this when the worker is back. Restart the backend if this lasts.",
  },
};

export interface WaitingForWorkerProps {
  /** What waits, e.g. "the library" (shown in the accessible name). */
  what: string;
  /** The last error, shown small under the hint when the worker is down. */
  detail?: string | null;
  onRetry?: () => void;
  compact?: boolean;
  testId?: string;
}

/**
 * Shown instead of an error while the worker is not ready: a spinning ring like the background-task
 * indicator, what the worker is doing, and that the panel fills in by itself when it is ready
 * (`session.ts` retries when the worker store reports ready).
 */
export function WaitingForWorker({ what, detail = null, onRetry, compact = false, testId }: WaitingForWorkerProps) {
  const state = useWorkerStore((s) => s.state);
  const { title, hint } = MESSAGES[state];
  return (
    <div
      className={`worker-wait${compact ? " worker-wait--compact" : ""}`}
      data-testid={testId}
      data-state={state}
      role="status"
      aria-live="polite"
      aria-label={`${title}: ${what} opens when the worker is ready`}
    >
      <span className="worker-wait__ring" aria-hidden="true" />
      <p className="worker-wait__title">{title}</p>
      <p className="worker-wait__hint">{hint}</p>
      {state === "crashed" && detail !== null ? <p className="worker-wait__detail">{detail}</p> : null}
      {state === "crashed" && onRetry !== undefined ? (
        <button type="button" className="button" onClick={onRetry}>
          Retry now
        </button>
      ) : null}
    </div>
  );
}
