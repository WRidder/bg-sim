/**
 * The plot area of plan 7.5, mounted in the bottom dock's Plots tab.
 *
 * Layout: a toolbar (run status, range, global inspect time, live badge, add
 * panel, reset, follow-live, pin, CSV), an optional pinned-run banner, and one
 * or more stacked uPlot panels. A panel has at most two y axes; a signal with a
 * third unit group starts a new panel. A panel that was deliberately given a
 * third group (drag-and-drop) offers "Split panel" in its header.
 *
 * Every zoom reports its window and the canvas width in device pixels, and the
 * store re-requests `/data`. "Show all" is a raw request (`px=0`); a zoom is
 * min/max decimated (`px = canvas width × devicePixelRatio`). A pinned run is
 * fetched through the same cache and overlaid as dashed lines. While a run is
 * streaming, the toolbar shows whether the live tail is following or paused;
 * "Follow live" returns to autoscroll.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
} from "react";

import { EmptyState } from "../app/EmptyState";
import type { RunManifest, RunSignal } from "../contracts/run-manifest";
import { signalColor } from "./colors";
import {
  formatCursorTime,
  formatDuration,
  formatNumber,
  formatProgress,
} from "./format";
import { runExportUrl } from "./runApi";
import {
  useRunStore,
  livePointCount,
  liveSeriesFor,
  panelLabel,
  plottedSignalIds,
  type PlotPanelState,
} from "./runStore";
import { useDetachStore } from "./detachStore";
import { readSignalDrag } from "./signalDnd";
import { assignPanelAxes, groupSignalsByUnit, panelUnitSummary } from "./units";
import { UPlotChart, type ChartSeriesConfig } from "./UPlotChart";
import "uplot/dist/uPlot.min.css";
import "./plot.css";

/** The uPlot cursor-sync key shared by all charts (plan 7.5). */
export const PLOT_SYNC_KEY = "bgsim-plots";

function statusLine(
  status: string,
  phase: string | null,
  progress: { t: number } | null,
  stats: { sim_s: number } | null,
  manifest: RunManifest | null,
  error: string | null,
): string {
  if (status === "starting") {
    return "starting…";
  }
  if (status === "running") {
    const t = progress?.t ?? manifest?.time.t0 ?? 0;
    const tEnd = manifest?.settings.t_end ?? 0;
    return `${phase ?? "running"} · ${formatProgress(t, tEnd)}`;
  }
  if (status === "done") {
    return `done in ${formatDuration(stats?.sim_s ?? manifest?.stats?.sim_s)}`;
  }
  if (status === "cancelled") {
    return "cancelled";
  }
  if (status === "failed") {
    return error !== null ? `failed — ${error}` : "failed";
  }
  return "ready";
}

function panelConfiguration(
  panelSignalIds: readonly string[],
  signalsById: ReadonlyMap<string, RunSignal>,
  pinnedSignals: ReadonlySet<string>,
): {
  signals: RunSignal[];
  current: ChartSeriesConfig[];
  compare: ChartSeriesConfig[];
  groups: number;
} {
  const signals = panelSignalIds
    .map((id) => signalsById.get(id))
    .filter((signal): signal is RunSignal => signal !== undefined);
  const axes = assignPanelAxes(signals);
  const axisByUnit = new Map<string, "y" | "y2">();
  if (axes.left !== null) {
    axisByUnit.set(axes.left.unit ?? "", "y");
  }
  if (axes.right !== null) {
    axisByUnit.set(axes.right.unit ?? "", "y2");
  }
  for (const group of axes.overflow) {
    axisByUnit.set(group.unit ?? "", "y2");
  }

  const current: ChartSeriesConfig[] = signals.map((signal) => ({
    id: signal.id,
    label: signal.id,
    unit: signal.unit ?? null,
    type: signal.type,
    kind: signal.kind,
    color: signalColor(signal.id),
    axis: axisByUnit.get(signal.unit ?? "") ?? "y",
    compare: false,
  }));
  const compare = current
    .filter((signal) => pinnedSignals.has(signal.id))
    .map((signal) => ({
      ...signal,
      label: `${signal.label} (pinned)`,
      compare: true,
    }));

  return {
    signals,
    current,
    compare,
    groups: groupSignalsByUnit(signals).length,
  };
}

function PanelTitle({
  panel,
  index,
  onActivate,
  onRename,
}: {
  panel: PlotPanelState;
  index: number;
  onActivate: () => void;
  onRename: (name: string) => void;
}) {
  const label = panelLabel(panel, index);
  const [draft, setDraft] = useState<string | null>(null);
  const cancelled = useRef(false);
  const commit = (): void => {
    if (cancelled.current) {
      cancelled.current = false;
      setDraft(null);
      return;
    }
    if (draft !== null) {
      onRename(draft);
      setDraft(null);
    }
  };
  return (
    <input
      type="text"
      className="plot-chart__title"
      value={draft ?? label}
      aria-label={`Name of ${label}`}
      title="Rename this panel"
      data-testid={`plot-panel-title-${index + 1}`}
      onFocus={() => {
        onActivate();
        setDraft(label);
      }}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.currentTarget.blur();
        } else if (event.key === "Escape") {
          cancelled.current = true;
          setDraft(null);
          event.currentTarget.blur();
        }
      }}
    />
  );
}

export function PlotPanel({ detached = false }: { detached?: boolean }) {
  const manifest = useRunStore((state) => state.manifest);
  const status = useRunStore((state) => state.status);
  const phase = useRunStore((state) => state.phase);
  const progress = useRunStore((state) => state.progress);
  const stats = useRunStore((state) => state.stats);
  const error = useRunStore((state) => state.error);
  const notice = useRunStore((state) => state.notice);
  const data = useRunStore((state) => state.data);
  const dataLoading = useRunStore((state) => state.dataLoading);
  const dataError = useRunStore((state) => state.dataError);
  const compareData = useRunStore((state) => state.compareData);
  const pinned = useRunStore((state) => state.pinned);
  const panels = useRunStore((state) => state.panels);
  const activePanelId = useRunStore((state) => state.activePanelId);
  const view = useRunStore((state) => state.view);
  const cursorTime = useRunStore((state) => state.cursorTime);
  const liveVersion = useRunStore((state) => state.liveVersion);
  const storedPixelWidth = useRunStore((state) => state.pixelWidth);
  const addSignal = useRunStore((state) => state.addSignal);
  const addPanel = useRunStore((state) => state.addPanel);
  const removePanel = useRunStore((state) => state.removePanel);
  const splitPanel = useRunStore((state) => state.splitPanel);
  const setActivePanel = useRunStore((state) => state.setActivePanel);
  const renamePanel = useRunStore((state) => state.renamePanel);
  const setNotice = useRunStore((state) => state.setNotice);
  const detachPlots = useDetachStore((state) => state.detach);
  const attachPlots = useDetachStore((state) => state.attach);
  const followLive = useRunStore((state) => state.followLive);
  const pinRun = useRunStore((state) => state.pinRun);
  const unpinRun = useRunStore((state) => state.unpinRun);

  const chartsRef = useRef<HTMLDivElement>(null);
  const [pixelWidth, setPixelWidth] = useState(storedPixelWidth);

  const signalsById = useMemo(() => {
    const map = new Map<string, RunSignal>();
    for (const signal of manifest?.signals ?? []) {
      map.set(signal.id, signal);
    }
    return map;
  }, [manifest]);

  const plottedIds = useMemo(() => plottedSignalIds(panels), [panels]);
  const idsKey = plottedIds.join(",");
  const hasCharts = manifest !== null && plottedIds.length > 0;

  const pinnedSignals = useMemo(() => {
    const set = new Set<string>();
    for (const signal of pinned?.manifest.signals ?? []) {
      set.add(signal.id);
    }
    return set;
  }, [pinned]);

  const fullRange = useMemo(() => {
    const t0 = manifest?.time.t0 ?? 0;
    let t1 = manifest?.time.t1 ?? t0 + 1;
    if (status === "running" || status === "starting") {
      t1 = Math.max(t1, progress?.t ?? t0);
    }
    if (!(t1 > t0)) {
      t1 = t0 + 1;
    }
    return { t0, t1 };
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
    // After run.done the final `/data` refresh may still be in flight; keep the
    // last live tail on screen instead of flashing an empty chart.
    if (data === null || data.time.length === 0) {
      return liveSeriesFor(manifest?.id);
    }
    return null;
  }, [status, view, manifest?.id, liveVersion, data]);

  // The live tail replaces the fetched window while running at "show all";
  // a zoomed view reads `/data` from the stream instead.
  const chartData = live ?? data;
  const following = status === "running" && view === null;
  const livePoints = status === "running" ? livePointCount() : 0;

  // Measure the charts area once it exists (a run with at least one signal).
  useEffect(() => {
    const element = chartsRef.current;
    if (element === null) {
      return;
    }
    const measure = (): void => {
      const ratio =
        typeof window === "undefined" ? 1 : window.devicePixelRatio || 1;
      // The canvas host excludes the panel border and the dock padding; that
      // is the width the plan means by "canvas width × devicePixelRatio".
      const canvas = element.querySelector<HTMLElement>(
        '[data-testid="plot-chart"]',
      );
      const width = canvas?.clientWidth ?? element.clientWidth;
      setPixelWidth(Math.max(1, Math.round(width * ratio)));
    };
    measure();
    if (typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [hasCharts]);

  // Data for the current run/ids/window. The store deduplicates requests by
  // its request key and consults the LRU before touching the network.
  useEffect(() => {
    if (manifest === null) {
      return;
    }
    void useRunStore.getState().ensureData(pixelWidth || undefined);
  }, [manifest?.id, idsKey, view?.t0, view?.t1, pixelWidth]);

  useEffect(() => {
    if (manifest === null || pinned === null) {
      return;
    }
    void useRunStore.getState().ensureCompareData(pixelWidth || undefined);
  }, [
    manifest?.id,
    pinned?.manifest.id,
    idsKey,
    view?.t0,
    view?.t1,
    pixelWidth,
  ]);

  const handleZoom = useCallback(
    (next: { t0: number; t1: number } | null, px: number) => {
      useRunStore.getState().setView(next, px);
    },
    [],
  );
  const handleReset = useCallback(() => {
    useRunStore.getState().setView(null);
  }, []);
  const handleCursor = useCallback((time: number | null) => {
    useRunStore.getState().setCursorTime(time);
  }, []);

  const [dragOver, setDragOver] = useState(false);
  const handleDragOver = (event: DragEvent<HTMLDivElement>): void => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setDragOver(true);
  };
  const handleDragLeave = (event: DragEvent<HTMLDivElement>): void => {
    const related = event.relatedTarget;
    if (related instanceof Node && event.currentTarget.contains(related)) {
      return;
    }
    setDragOver(false);
  };
  const handleDrop = (event: DragEvent<HTMLDivElement>): void => {
    event.preventDefault();
    setDragOver(false);
    const signalId = readSignalDrag(event);
    if (signalId === null) {
      return;
    }
    const panelElement = (event.target as HTMLElement).closest(
      "[data-panel-id]",
    );
    const panelId = panelElement?.getAttribute("data-panel-id") ?? undefined;
    // An explicit drop on a panel is a deliberate choice: keep the signal
    // there even when it is a third unit group, and offer "Split panel".
    addSignal(signalId, panelId, { force: panelId !== undefined });
  };

  if (manifest === null) {
    if (status === "starting") {
      return (
        <EmptyState
          title="Starting the run…"
          hint="The worker is compiling the model. Signals appear here when the run reports them."
        />
      );
    }
    if (status === "failed") {
      return (
        <EmptyState
          title="The run did not start"
          hint={error ?? "The backend reported no detail. Check the model for errors."}
        />
      );
    }
    return (
      <EmptyState
        title="No run data"
        hint={
          <>
            Press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> (or Run) to simulate the model,
            then double-click a signal in the <strong>Signals</strong> tab — or drag
            it onto a panel here.
          </>
        }
      />
    );
  }

  const exportIds = plottedIds.filter((id) => signalsById.has(id));
  const exportUrl = runExportUrl(manifest.id, exportIds);
  const statusText = statusLine(
    status,
    phase,
    progress,
    stats,
    manifest,
    error,
  );

  return (
    <div
      className={`plot-panel${dragOver ? " is-dragover" : ""}`}
      data-testid="plot-panel"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="plot-toolbar" data-testid="plot-toolbar">
        <span
          className="plot-toolbar__run"
          data-testid="plot-run-status"
          data-status={status}
          title={error ?? manifest.id}
        >
          {statusText}
        </span>
        <span className="plot-toolbar__range" title="Recorded time range">
          t {formatNumber(fullRange.t0)}–{formatNumber(fullRange.t1)} s
        </span>
        <span
          className="plot-toolbar__inspect"
          data-testid="plot-inspect-time"
          title="Global inspect time (plan 7.5): every panel cursor and, later, the 3D playback head"
        >
          inspect t ={" "}
          {cursorTime === null ? "—" : formatCursorTime(cursorTime)}
        </span>
        {status === "running" ? (
          <span
            className="plot-live"
            data-testid="live-badge"
            data-following={following ? "true" : "false"}
            data-points={livePoints}
            title={
              following
                ? "Live: new tail points are appended and the plots autoscroll"
                : "Live: autoscroll is paused because the view is zoomed"
            }
          >
            ● live {following ? "· following" : "· paused"}
          </span>
        ) : null}
        {dataLoading ? (
          <span className="plot-toolbar__loading" role="status">
            loading…
          </span>
        ) : null}
        <span className="plot-toolbar__spacer" />
        {panels.length > 0 ? (
          <label className="plot-toolbar__target">
            <span>Active</span>
            <select
              value={activePanelId}
              onChange={(event) => setActivePanel(event.target.value)}
              data-testid="active-panel-select"
              aria-label="Active plot panel"
              title="The panel that receives a signal from the canvas"
            >
              {panels.map((panel, index) => (
                <option key={panel.id} value={panel.id}>
                  {panelLabel(panel, index)}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <button
          type="button"
          className="button"
          onClick={() => {
            if (detached) {
              attachPlots();
              return;
            }
            if (!detachPlots()) {
              setNotice(
                useDetachStore.getState().error ??
                  "The plot window could not be opened.",
              );
            }
          }}
          data-testid={detached ? "dock-plot" : "detach-plot"}
          title={
            detached
              ? "Move the plots back into the bottom dock"
              : "Open the plots in a separate browser window"
          }
        >
          {detached ? "Dock" : "Detach"}
        </button>
        <button
          type="button"
          className="button"
          onClick={() => addPanel()}
          data-testid="add-plot-panel"
          title="Add a plot panel"
        >
          + Panel
        </button>
        <button
          type="button"
          className="button"
          onClick={handleReset}
          disabled={view === null}
          data-testid="plot-reset-zoom"
          title="Reset the zoom to the whole run (double-click a plot)"
        >
          Reset zoom
        </button>
        {status === "running" && view !== null ? (
          <button
            type="button"
            className="button"
            onClick={followLive}
            data-testid="follow-live"
            title="Resume the live tail and autoscroll"
          >
            Follow live
          </button>
        ) : null}
        {pinned === null ? (
          <button
            type="button"
            className="button"
            onClick={pinRun}
            disabled={status === "running" || status === "starting"}
            data-testid="pin-run"
            title="Pin this run, then start another to compare them"
          >
            Pin run
          </button>
        ) : (
          <button
            type="button"
            className="button"
            onClick={unpinRun}
            data-testid="unpin-run"
            title="Stop showing the pinned run"
          >
            Unpin
          </button>
        )}
        <a
          className={`button${exportIds.length === 0 ? " is-disabled" : ""}`}
          href={exportUrl}
          download={`${manifest.id}.csv`}
          data-testid="export-csv"
          aria-disabled={exportIds.length === 0}
          title={
            exportIds.length === 0
              ? "Plot at least one signal to export it as CSV"
              : `Download the ${exportIds.length} plotted signal${
                  exportIds.length === 1 ? "" : "s"
                } as CSV`
          }
          onClick={(event) => {
            if (exportIds.length === 0) {
              event.preventDefault();
            }
          }}
        >
          CSV
        </a>
      </div>

      {pinned !== null ? (
        <div className="plot-pinned" data-testid="pinned-run">
          <span>
            Comparing with <code>{pinned.manifest.id}</code> — dashed lines.
          </span>
          <button type="button" className="plot-link" onClick={unpinRun}>
            stop comparing
          </button>
        </div>
      ) : null}

      {notice !== null ? (
        <p className="plot-notice" role="status" data-testid="plot-notice">
          {notice}
        </p>
      ) : null}

      {dataError !== null ? (
        <p className="plot-error" role="alert" data-testid="plot-data-error">
          {dataError}
        </p>
      ) : null}

      {plottedIds.length === 0 ? (
        <div className="plot-panel__empty">
          <EmptyState
            title="No signals plotted"
            hint={
              <>
                Open the <strong>Signals</strong> tab and double-click a signal to
                add it to the active panel. Only two unit groups fit on one panel;
                a third starts a new one.
              </>
            }
          />
        </div>
      ) : (
        <div className="plot-panel__charts" ref={chartsRef} data-testid="plot-charts">
          {panels.map((panel, index) => {
            const configuration = panelConfiguration(
              panel.signals,
              signalsById,
              pinnedSignals,
            );
            return (
              <section
                className={`plot-chart-panel${panel.id === activePanelId ? " is-active" : ""}`}
                key={panel.id}
                data-testid="plot-chart-panel"
                data-panel-id={panel.id}
                onMouseDown={() => setActivePanel(panel.id)}
              >
                <header className="plot-chart__header">
                  <PanelTitle
                    panel={panel}
                    index={index}
                    onActivate={() => setActivePanel(panel.id)}
                    onRename={(name) => renamePanel(panel.id, name)}
                  />
                  <span className="plot-chart__units">
                    {panelUnitSummary(configuration.signals)}
                  </span>
                  {configuration.groups > 2 ? (
                    <>
                      <span
                        className="plot-chart__warning"
                        title="A panel shows at most two y axes; the extra unit group shares the right axis. Split the panel to separate it."
                      >
                        {configuration.groups} unit groups
                      </span>
                      <button
                        type="button"
                        className="button"
                        onClick={() => splitPanel(panel.id)}
                        data-testid="split-panel"
                        title="Move the third and later unit groups to a new panel"
                      >
                        Split panel
                      </button>
                    </>
                  ) : null}
                  <span className="plot-chart__spacer" />
                  <button
                    type="button"
                    className="plot-chart__remove"
                    onClick={() => removePanel(panel.id)}
                    aria-label={`Remove ${panelLabel(panel, index)}`}
                    title={
                      panels.length > 1
                        ? `Remove ${panelLabel(panel, index)}`
                        : "Clear this panel's signals"
                    }
                  >
                    ×
                  </button>
                </header>
                <UPlotChart
                  signals={configuration.current}
                  compareSignals={configuration.compare}
                  data={chartData}
                  compare={compareData}
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
