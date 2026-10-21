import { EmptyState } from "./EmptyState";
import { TabStrip, type TabDefinition } from "./TabStrip";

export type DockTabId = "plots" | "viewer" | "diagnostics" | "signals" | "log";

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
    hint: "Backend and worker messages appear here.",
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
  const tabs: readonly TabDefinition<DockTabId>[] = [
    { id: "plots", label: "Plots" },
    { id: "viewer", label: "3D View" },
    {
      id: "diagnostics",
      label: "Diagnostics",
      badges: [
        { count: diagnostics.error, tone: "error" },
        { count: diagnostics.warning, tone: "warning" },
      ],
    },
    { id: "signals", label: "Signals" },
    { id: "log", label: "Log" },
  ];
  const empty = DOCK_EMPTY_STATES[active];

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
        <EmptyState title={empty.title} hint={empty.hint} />
      </div>
    </div>
  );
}
