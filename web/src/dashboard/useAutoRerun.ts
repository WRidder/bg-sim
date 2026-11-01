/**
 * "Auto re-run" of the dashboard (DASHBOARD_PLAN.md, off by default): while the Dashboard tab
 * is open and the option is on, a change of the run inputs (an input card value, a schedule
 * cell) starts a new run once the change has settled for {@link AUTO_RERUN_DELAY_MS} and no input
 * card is being dragged. A change made while a run is going waits for that run to end. Inputs
 * with a problem never start one.
 */

import { useEffect, useMemo, useRef } from "react";

import type { Model } from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import { useRunStore } from "../plot/runStore";
import { useDocumentStore } from "../state/documentStore";
import { dashboardRunInputs } from "./model";

export const AUTO_RERUN_DELAY_MS = 250;

/** A stable signature of what the dashboard asks of the next run. */
export function runInputsSignature(doc: Model | null, index: CatalogIndex | null): string | null {
  if (doc === null || doc.dashboard === undefined) {
    return null;
  }
  const inputs = dashboardRunInputs(doc, index);
  if (inputs.issues.length > 0) {
    return null;
  }
  return JSON.stringify([inputs.parameterOverrides, inputs.parameterSchedule]);
}

export function useAutoRerun(doc: Model | null, index: CatalogIndex | null): void {
  const enabled = doc?.dashboard?.autoRerun === true;
  const signature = useMemo(() => runInputsSignature(doc, index), [doc, index]);
  const last = useRef<string | null>(signature);
  const pending = useRef(false);
  // a slider or knob held down: wait until it is let go
  const dragging = useDocumentStore((state) => state.gestureKey?.startsWith("dashboard-value-") === true);

  useEffect(() => {
    if (!enabled || signature === null || signature === last.current) {
      last.current = signature;
      return;
    }
    if (dragging) {
      return;
    }
    const timer = setTimeout(() => {
      last.current = signature;
      const status = useRunStore.getState().status;
      if (status === "running" || status === "starting" || status === "paused") {
        pending.current = true;
        return;
      }
      void useRunStore.getState().startRun();
    }, AUTO_RERUN_DELAY_MS);
    return () => clearTimeout(timer);
  }, [enabled, signature, dragging]);

  useEffect(
    () =>
      useRunStore.subscribe((state, previous) => {
        if (!pending.current || state.status === previous.status) {
          return;
        }
        if (state.status === "done" || state.status === "cancelled" || state.status === "failed") {
          pending.current = false;
          void useRunStore.getState().startRun();
        }
      }),
    [],
  );
}
