import { useEffect } from "react";

import { getHealth } from "../api/client";
import { describeHealth, isFakeWorker, type WorkerState } from "../api/health";
import { useWorkerStore } from "../api/workerStore";

/** `/api/health` is polled once a second (plan 7.2: status is always visible). */
export const HEALTH_POLL_INTERVAL_MS = 1000;

const STATE_LABELS: Record<WorkerState, string> = {
  starting: "starting",
  warming: "warming up",
  ready: "ready",
  crashed: "crashed",
};

/** What the state means for the user, first line of the tooltip. */
const STATE_HINTS: Record<WorkerState, string> = {
  starting: "The Julia worker is starting. The library, models and runs become available when it is ready.",
  warming: "The Julia worker is compiling its code. The library, models and runs become available when it is ready.",
  ready: "The Julia worker is ready.",
  crashed: "The worker or the backend is not answering. The editor keeps checking and recovers when it is back.",
};

export interface WorkerStatusProps {
  /** Poll interval in milliseconds; tests shorten it. */
  pollIntervalMs?: number;
}

/**
 * The worker health indicator of the top bar: a dot, steady green when ready and pulsing while the worker
 * starts, warms up or is down; the tooltip says what that means. It polls `GET /api/health`, maps an
 * unreachable backend to `crashed`, publishes the state to `useWorkerStore` and exposes
 * `data-testid="worker-status"` plus `data-state` for the e2e smoke test.
 */
export function WorkerStatus({ pollIntervalMs = HEALTH_POLL_INTERVAL_MS }: WorkerStatusProps) {
  const state = useWorkerStore((s) => s.state);
  const fake = useWorkerStore((s) => s.fake);
  const detail = useWorkerStore((s) => s.detail);

  useEffect(() => {
    const controller = new AbortController();
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const report = useWorkerStore.getState().report;

    const poll = async (): Promise<void> => {
      try {
        const health = await getHealth({ signal: controller.signal });
        if (stopped) {
          return;
        }
        report({ state: health.worker, fake: isFakeWorker(health), detail: describeHealth(health) });
      } catch (error) {
        if (stopped) {
          return;
        }
        report({
          state: "crashed",
          fake: false,
          detail: error instanceof Error ? error.message : "The backend did not answer.",
        });
      } finally {
        if (!stopped) {
          timer = setTimeout(() => void poll(), pollIntervalMs);
        }
      }
    };

    void poll();

    return () => {
      stopped = true;
      controller.abort();
      if (timer !== undefined) {
        clearTimeout(timer);
      }
    };
  }, [pollIntervalMs]);

  const label = `Worker ${STATE_LABELS[state]}${fake ? " · fake worker" : ""}`;

  return (
    <div
      className="worker-status"
      data-testid="worker-status"
      data-state={state}
      data-fake={fake ? "true" : "false"}
      title={`${label}\n${STATE_HINTS[state]}\n${detail}`}
      role="status"
      aria-live="polite"
      aria-label={`Worker status: ${label}`}
    >
      <span className="worker-status__dot" aria-hidden="true" />
      <span className="worker-status__label visually-hidden">{label}</span>
    </div>
  );
}
