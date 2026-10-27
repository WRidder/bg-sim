/**
 * The plots inside an oscilloscope probe. A window shows every selected signal
 * together; a block uses its user-defined panels, or one panel with everything
 * when no panel was configured.
 */

import { useEffect, useMemo } from "react";

import type { Model, ModelProbe } from "../contracts/model";
import type { RunSignal } from "../contracts/run-manifest";
import { panelConfiguration, PLOT_SYNC_KEY } from "../plot/PlotPanel";
import { liveSeriesFor, useRunStore } from "../plot/runStore";
import { UPlotChart } from "../plot/UPlotChart";
import { probeSignalIds } from "./probeSignals";
import "./probe.css";

interface PanelPlan {
  id: string;
  title: string;
  signals: string[];
}

export function probePanelPlans(model: Model, probe: ModelProbe): PanelPlan[] {
  const available = probeSignalIds(model, probe);
  if (probe.kind === "window" || (probe.panels ?? []).length === 0) {
    return [{ id: "all", title: "All signals", signals: available }];
  }
  const panels = (probe.panels ?? []).map((panel) => ({
    id: panel.id,
    title: panel.title,
    signals: panel.signals.filter((id) => available.includes(id)),
  }));
  const assigned = new Set(panels.flatMap((panel) => panel.signals));
  const unassigned = available.filter((id) => !assigned.has(id));
  if (unassigned.length > 0) {
    panels.push({ id: "unassigned", title: "Unassigned", signals: unassigned });
  }
  return panels;
}

export function ProbePlot({ model, probe }: { model: Model; probe: ModelProbe }) {
  const manifest = useRunStore((state) => state.manifest);
  const status = useRunStore((state) => state.status);
  const progress = useRunStore((state) => state.progress);
  const data = useRunStore((state) => state.data);
  const view = useRunStore((state) => state.view);
  const cursorTime = useRunStore((state) => state.cursorTime);
  const liveVersion = useRunStore((state) => state.liveVersion);
  const plans = useMemo(() => probePanelPlans(model, probe), [model, probe]);
  const idsKey = plans.map((plan) => plan.signals.join(",")).join("|");

  useEffect(() => {
    if (manifest !== null) {
      void useRunStore.getState().ensureData();
    }
  }, [manifest?.id, idsKey, view?.t0, view?.t1]);

  const signalsById = useMemo(() => {
    const map = new Map<string, RunSignal>();
    for (const signal of manifest?.signals ?? []) {
      map.set(signal.id, signal);
    }
    return map;
  }, [manifest]);

  const fullRange = useMemo(() => {
    const t0 = manifest?.time.t0 ?? 0;
    let t1 = manifest?.time.t1 ?? t0 + 1;
    if (status === "running" || status === "starting") {
      t1 = Math.max(t1, progress?.t ?? t0);
    }
    return { t0, t1: t1 > t0 ? t1 : t0 + 1 };
  }, [manifest?.time.t0, manifest?.time.t1, status, progress?.t]);

  const live = useMemo(() => {
    if (status === "running") {
      return liveSeriesFor(manifest?.id);
    }
    if (status !== "done" && status !== "cancelled" && status !== "failed") {
      return null;
    }
    if (data === null || data.time.length === 0) {
      return liveSeriesFor(manifest?.id);
    }
    return null;
  }, [status, manifest?.id, liveVersion, data]);
  const chartData = live ?? data;

  if (manifest === null) {
    return (
      <div className="probe-plot__empty">
        Run the model to see {probe.name}.
      </div>
    );
  }

  return (
    <div className="probe-plot" data-testid={`probe-plot-${probe.id}`}>
      {plans.map((plan) => {
        const configuration = panelConfiguration(
          plan.signals,
          signalsById,
          new Set<string>(),
        );
        return (
          <section className="probe-plot__panel" key={plan.id}>
            <header className="probe-plot__title">{plan.title}</header>
            {configuration.signals.length === 0 ? (
              <div className="probe-plot__empty">
                No recorded signals for this probe lead.
              </div>
            ) : (
              <UPlotChart
                signals={configuration.current}
                compareSignals={[]}
                data={chartData}
                compare={null}
                view={view}
                fullRange={fullRange}
                syncKey={PLOT_SYNC_KEY}
                cursorTime={cursorTime}
                onZoom={(next, px) => useRunStore.getState().setView(next, px)}
                onReset={() => useRunStore.getState().setView(null)}
                onCursorTime={(time) => useRunStore.getState().setCursorTime(time)}
              />
            )}
          </section>
        );
      })}
    </div>
  );
}
