import { useEffect, useState } from "react";

import { getHealth } from "../api/client";
import { describeHealth, isFakeWorker, type WorkerState } from "../api/health";

/** `/api/health` is polled once a second (plan 7.2: status is always visible). */
export const HEALTH_POLL_INTERVAL_MS = 1000;

const STATE_LABELS: Record<WorkerState, string> = {
  starting: "starting",
  warming: "warming up",
  ready: "ready",
  crashed: "crashed",
};

export interface WorkerStatusProps {
  /** Poll interval in milliseconds; tests shorten it. */
  pollIntervalMs?: number;
}

/**
 * The worker health indicator of the top bar. It polls `GET /api/health`,
 * maps an unreachable backend to `crashed`, and exposes
 * `data-testid="worker-status"` plus `data-state` for the e2e smoke test.
 */
export function WorkerStatus({ pollIntervalMs = HEALTH_POLL_INTERVAL_MS }: WorkerStatusProps) {
  const [state, setState] = useState<WorkerState>("starting");
  const [fake, setFake] = useState(false);
  const [detail, setDetail] = useState("Checking the bg-sim backend…");

  useEffect(() => {
    const controller = new AbortController();
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async (): Promise<void> => {
      try {
        const health = await getHealth({ signal: controller.signal });
        if (stopped) {
          return;
        }
        setState(health.worker);
        setFake(isFakeWorker(health));
        setDetail(describeHealth(health));
      } catch (error) {
        if (stopped) {
          return;
        }
        setState("crashed");
        setFake(false);
        setDetail(error instanceof Error ? error.message : "The backend did not answer.");
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
      title={detail}
      role="status"
      aria-live="polite"
      aria-label={`Worker status: ${label}`}
    >
      <span className="worker-status__dot" aria-hidden="true" />
      <span className="worker-status__label">{label}</span>
    </div>
  );
}
