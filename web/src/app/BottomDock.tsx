import { lazy, Suspense, useState, type ReactElement } from "react";

import { DiagnosticsPanel } from "../diagnostics/DiagnosticsPanel";
import { useDiagnosticBadges } from "../diagnostics/useDiagnostics";
import { useAutoDetachStore, useDetachStore } from "../plot/detachStore";
import { SignalBrowser } from "../plot/SignalBrowser";
import { useViewerDetachStore } from "../viewer/detachStore";
import { EmptyState } from "./EmptyState";
import { TabStrip, type TabDefinition } from "./TabStrip";

// Babylon stays out of the main bundle: the viewer loads when the 3D View tab is first opened.
const DockViewer = lazy(() => import("../viewer/DockViewer"));
// uPlot loads with the first plot tab that is shown (code splitting, W5.4).
const PlotPanel = lazy(() => import("../plot/PlotPanel").then((m) => ({ default: m.PlotPanel })));
const AutoPlotPanel = lazy(() =>
  import("../plot/AutoPlotPanel").then((m) => ({ default: m.AutoPlotPanel })),
);

function loading(title: string): ReactElement {
  return <EmptyState title={title} hint="One moment." />;
}

export type DockTabId = "plots" | "auto" | "viewer" | "diagnostics" | "signals" | "log";

export interface DiagnosticCounts {
  error: number;
  warning: number;
}

const NO_DIAGNOSTICS: DiagnosticCounts = { error: 0, warning: 0 };

const DOCK_EMPTY_STATES: Record<DockTabId, { title: string; hint: string }> = {
  plots: {
    title: "No run data",
    hint: "Run a model to plot its signals here. Every signal is recorded by default.",
  },
  auto: {
    title: "No selection",
    hint: "Select a block, subsystem or connection and this tab plots only that item automatically.",
  },
  viewer: {
    title: "No scene",
    hint: "Open a model with a 3D scene to see it here. The view can also be popped into the centre tabs.",
  },
  diagnostics: {
    title: "No diagnostics",
    hint: "Checks report errors and warnings here. Click one to jump to the element or the line that caused it.",
  },
  signals: {
    title: "No signals",
    hint: "After a run, browse every recorded signal here and add it to a plot panel.",
  },
  log: {
    title: "No log entries",
    hint: "Nothing has been logged yet. Run the model and the backend and worker messages appear here.",
  },
};

export interface BottomDockProps {
  active: DockTabId;
  onSelect: (id: DockTabId) => void;
  /** Badge counts on the Diagnostics tab (plan 7.2). */
  diagnostics?: DiagnosticCounts;
}

/** The bottom dock of plan 7.2: Plots, 3D View, Diagnostics, Signals, Log. */
export function BottomDock({ active, onSelect, diagnostics = NO_DIAGNOSTICS }: BottomDockProps) {
  // W1.3: the live counts come from the diagnostics store; the prop stays for
  // callers that already have a count (the two are merged, never doubled).
  const live = useDiagnosticBadges();
  const detached = useDetachStore((state) => state.detached);
  const attach = useDetachStore((state) => state.attach);
  const autoDetached = useAutoDetachStore((state) => state.detached);
  const autoAttach = useAutoDetachStore((state) => state.attach);
  const viewerDetached = useViewerDetachStore((state) => state.detached);
  const viewerAttach = useViewerDetachStore((state) => state.attach);
  const counts: DiagnosticCounts = {
    error: Math.max(diagnostics.error, live.error),
    warning: Math.max(diagnostics.warning, live.warning),
  };
  const tabs: readonly TabDefinition<DockTabId>[] = [
    { id: "plots", label: "Plots" },
    { id: "auto", label: "Auto Plot" },
    { id: "viewer", label: "3D View" },
    {
      id: "diagnostics",
      label: "Diagnostics",
      badges: [
        { count: counts.error, tone: "error" },
        { count: counts.warning, tone: "warning" },
      ],
    },
    { id: "signals", label: "Signals" },
    { id: "log", label: "Log" },
  ];
  const empty = DOCK_EMPTY_STATES[active];
  // The viewer mounts on first use and then stays mounted (hidden) so its camera and scene survive tab switches.
  const [viewerSeen, setViewerSeen] = useState(active === "viewer");
  if (active === "viewer" && !viewerSeen) {
    setViewerSeen(true);
  }

  // The Plots, Signals and Diagnostics tabs are mounted components owned by
  // W1.4 and W1.3; the rest keep the shell's empty state until their WP lands.
  function panel() {
    switch (active) {
      case "plots":
        return detached ? (
          <div className="dock__detached" data-testid="plots-detached">
            <EmptyState
              title="Plots are in a separate window"
              hint="The detached window shares this run, its cursor and the live tail. Bring it back here whenever you like."
            />
            <button
              type="button"
              className="button"
              onClick={attach}
              data-testid="attach-plots"
            >
              Bring plots back
            </button>
          </div>
        ) : (
          <Suspense fallback={loading("Loading the plots")}>
            <PlotPanel />
          </Suspense>
        );
      case "auto":
        return autoDetached ? (
          <div className="dock__detached" data-testid="auto-plots-detached">
            <EmptyState
              title="Automatic plot is in a separate window"
              hint="The detached window follows the same canvas selection, run and cursor. Bring it back here whenever you like."
            />
            <button
              type="button"
              className="button"
              onClick={autoAttach}
              data-testid="attach-auto-plot"
            >
              Bring automatic plot back
            </button>
          </div>
        ) : (
          <Suspense fallback={loading("Loading the automatic plot")}>
            <AutoPlotPanel />
          </Suspense>
        );
      case "signals":
        return <SignalBrowser />;
      case "viewer":
        return viewerDetached ? (
          <div className="dock__detached" data-testid="viewer-detached">
            <EmptyState
              title="The 3D view is in a separate window"
              hint="The detached window shares this run, its bindings, the playback time and the plot cursor. Bring it back here whenever you like."
            />
            <button type="button" className="button" onClick={viewerAttach} data-testid="attach-viewer">
              Dock the 3D view
            </button>
          </div>
        ) : null;
      case "diagnostics":
        return <DiagnosticsPanel />;
      default:
        return <EmptyState title={empty.title} hint={empty.hint} />;
    }
  }

  return (
    <div className="dock" data-testid="bottom-dock">
      <TabStrip tabs={tabs} active={active} onSelect={onSelect} ariaLabel="Dock" idPrefix="dock" />
      <div
        className="dock__panels"
        role="tabpanel"
        id={`dock-panel-${active}`}
        aria-labelledby={`dock-tab-${active}`}
        tabIndex={0}
      >
        {panel()}
        {viewerSeen && !viewerDetached ? (
          <div style={{ height: "100%" }} hidden={active !== "viewer"} data-testid="dock-viewer">
            <Suspense fallback={<EmptyState title="Loading the 3D view" hint="One moment." />}>
              <DockViewer active={active === "viewer"} />
            </Suspense>
          </div>
        ) : null}
      </div>
    </div>
  );
}
