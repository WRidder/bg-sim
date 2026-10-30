/**
 * The automatic selection plot tab.
 *
 * It follows the canvas selection (a block, subsystem or connection) and plots
 * only that item's recorded signals. The layout selector chooses one panel for
 * everything, one panel per signal, or one panel per unit/type group. The run
 * store owns the auto signal list so the same `/data` request and live socket
 * serve both this tab and the manual Plots panels.
 */

import { useEffect, useMemo } from "react";

import { EmptyState } from "../app/EmptyState";
import type { RunSignal } from "../contracts/run-manifest";
import { useDocumentStore } from "../state/documentStore";
import { autoPlotSelection } from "./autoPlotSelection";
import { groupSignalsForAuto } from "./autoPlotGroups";
import { useAutoDetachStore } from "./detachStore";
import { usePausedSeries } from "./pauseState";
import { panelConfiguration, PLOT_SYNC_KEY } from "./PlotPanel";
import {
  liveSeriesFor,
  useRunStore,
  type AutoPlotLayout,
} from "./runStore";
import { panelUnitSummary } from "./units";
import { UPlotChart } from "./UPlotChart";
import "./plot.css";

export function AutoPlotPanel({ detached = false }: { detached?: boolean }) {
  const doc = useDocumentStore((state) => state.doc);
  const activePath = useDocumentStore((state) => state.activePath);
  const selection = useDocumentStore((state) => state.selection);
  const manifest = useRunStore((state) => state.manifest);
  const status = useRunStore((state) => state.status);
  const progress = useRunStore((state) => state.progress);
  const data = useRunStore((state) => state.data);
  const dataLoading = useRunStore((state) => state.dataLoading);
  const view = useRunStore((state) => state.view);
  const cursorTime = useRunStore((state) => state.cursorTime);
  const liveVersion = useRunStore((state) => state.liveVersion);
  const autoSignals = useRunStore((state) => state.autoSignals);
  const autoLayout = useRunStore((state) => state.autoLayout);
  const notice = useRunStore((state) => state.notice);
  const setNotice = useRunStore((state) => state.setNotice);
  const setAutoSignals = useRunStore((state) => state.setAutoSignals);
  const setAutoLayout = useRunStore((state) => state.setAutoLayout);
  const detachPanel = useAutoDetachStore((state) => state.detach);
  const attachPanel = useAutoDetachStore((state) => state.attach);

  const selected = useMemo(
    () => autoPlotSelection(doc, activePath, selection, manifest),
    [doc, activePath, selection, manifest],
  );
  const selectionKey = selected?.key ?? "";
  const idsKey = autoSignals.join(",");

  useEffect(() => {
    setAutoSignals(selected?.signalIds ?? []);
  }, [selectionKey, selected?.signalIds, setAutoSignals]);

  // The tab is the only consumer while it is open; clear its extra ids when
  // the user switches to the manual Plots tab.
  useEffect(
    () => () => {
      useRunStore.getState().setAutoSignals([]);
    },
    [],
  );

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

  const signals = useMemo(
    () =>
      autoSignals
        .map((id) => signalsById.get(id))
        .filter((signal): signal is RunSignal => signal !== undefined),
    [autoSignals, signalsById],
  );

  const groups = useMemo(
    () => groupSignalsForAuto(signals, autoLayout),
    [signals, autoLayout],
  );

  const fullRange = useMemo(() => {
    const t0 = manifest?.time.t0 ?? 0;
    let t1 = manifest?.time.t1 ?? t0 + 1;
    if (status === "running" || status === "starting") {
      t1 = Math.max(t1, progress?.t ?? t0);
    }
    return { t0, t1: t1 > t0 ? t1 : t0 + 1 };
  }, [manifest?.time.t0, manifest?.time.t1, status, progress?.t]);

  const live = useMemo(() => {
    if (view !== null) {
      return null;
    }
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
  }, [status, view, manifest?.id, liveVersion, data]);

  // M4 debug: while paused the series end at the pause time (plan 7.9)
  const chartData = usePausedSeries(live, data);
  const handleZoom = (next: { t0: number; t1: number } | null, px: number) => {
    useRunStore.getState().setView(next, px);
  };
  const handleReset = () => useRunStore.getState().setView(null);
  const handleCursor = (time: number | null) => {
    useRunStore.getState().setCursorTime(time);
  };

  if (manifest === null) {
    return (
      <EmptyState
        title="No run data"
        hint="Run the model, then select a block, subsystem or connection to plot it automatically."
      />
    );
  }

  return (
    <div className="auto-plot" data-testid="auto-plot-panel">
      <div className="plot-toolbar" data-testid="auto-plot-toolbar">
        <span className="auto-plot__selection" data-testid="auto-plot-selection">
          {selected === null ? "No selection" : selected.label}
        </span>
        <span className="plot-toolbar__range">
          {signals.length} signal{signals.length === 1 ? "" : "s"}
        </span>
        {dataLoading ? (
          <span className="plot-toolbar__loading" role="status">
            loading…
          </span>
        ) : null}
        <span className="plot-toolbar__spacer" />
        <label className="plot-toolbar__target">
          <span>Layout</span>
          <select
            value={autoLayout}
            onChange={(event) =>
              setAutoLayout(event.target.value as AutoPlotLayout)
            }
            data-testid="auto-layout-select"
            aria-label="Automatic plot layout"
          >
            <option value="single">All signals in one panel</option>
            <option value="separate">One signal per panel</option>
            <option value="unit">Group by unit/type</option>
          </select>
        </label>
        <button
          type="button"
          className="button"
          onClick={() => {
            if (detached) {
              attachPanel();
              return;
            }
            if (!detachPanel()) {
              setNotice(
                useAutoDetachStore.getState().error ??
                  "The automatic plot window could not be opened.",
              );
            }
          }}
          data-testid={detached ? "dock-auto-plot" : "detach-auto-plot"}
          title={
            detached
              ? "Move the automatic plot back into the bottom dock"
              : "Open the automatic plot in a separate browser window"
          }
        >
          {detached ? "Dock" : "Detach"}
        </button>
      </div>

      {notice !== null && !detached ? (
        <p className="plot-notice" role="status" data-testid="auto-plot-notice">
          {notice}
        </p>
      ) : null}

      {selected === null ? (
        <div className="auto-plot__empty">
          <EmptyState
            title="Select an item"
            hint="Click a block, subsystem or bond in the diagram and this tab plots everything that item recorded."
          />
        </div>
      ) : signals.length === 0 ? (
        <div className="auto-plot__empty">
          <EmptyState
            title={`No recorded signals for ${selected.label}`}
            hint="The run did not record a signal owned by this item, or the selection is a pure junction."
          />
        </div>
      ) : (
        <div className="plot-panel__charts" data-testid="auto-plot-charts">
          {groups.map((group, index) => {
            const configuration = panelConfiguration(
              group.signals.map((signal) => signal.id),
              signalsById,
              new Set<string>(),
            );
            return (
              <section
                className="plot-chart-panel"
                key={group.key}
                data-testid="auto-chart-panel"
                data-layout={autoLayout}
                data-panel-index={index}
              >
                <header className="plot-chart__header">
                  <span className="plot-chart__title auto-plot__group-title">
                    {autoLayout === "single"
                      ? `All signals (${group.signals.length})`
                      : autoLayout === "separate"
                        ? group.label
                        : `${group.label} (${group.signals.length})`}
                  </span>
                  <span className="plot-chart__units">
                    {panelUnitSummary(configuration.signals)}
                  </span>
                  <span className="plot-chart__spacer" />
                  <span className="auto-plot__count">
                    {group.signals.length} signal
                    {group.signals.length === 1 ? "" : "s"}
                  </span>
                </header>
                <UPlotChart
                  signals={configuration.current}
                  compareSignals={[]}
                  data={chartData}
                  compare={null}
                  view={view}
                  fullRange={fullRange}
                  syncKey={PLOT_SYNC_KEY}
                  cursorTime={cursorTime}
                  onZoom={handleZoom}
                  onReset={handleReset}
                  onCursorTime={handleCursor}
                />
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
