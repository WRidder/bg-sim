import { useEffect, useState } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";

import { usePersistedPanelSizes } from "../state/layout";
import { useTheme } from "../theme/useTheme";
import { BottomDock, type DiagnosticCounts, type DockTabId } from "./BottomDock";
import { CenterTabs, type CenterTabId } from "./CenterTabs";
import { SHOW_PLOTS_EVENT } from "./dockBus";
import { InspectorPanel } from "./InspectorPanel";
import { LeftPanel } from "./LeftPanel";
import { TopBar } from "./TopBar";
import { DetachedPlotWindow } from "../plot/DetachedPlotWindow";
import { DetachedAutoPlotWindow } from "../plot/DetachedAutoPlotWindow";

/**
 * Nothing has been checked yet, so the diagnostics badges start at zero; M1
 * feeds the real counts from `model.check`.
 */
const NO_DIAGNOSTICS: DiagnosticCounts = { error: 0, warning: 0 };

/**
 * The application shell of plan 7.2: top bar, a resizable three-column body
 * (library + model tree │ centre tabs │ inspector) and the bottom dock.
 * Every split is a `Group`/`Panel`/`Separator` whose sizes persist in
 * localStorage (src/state/layout.ts).
 */
export function App() {
  const { theme, toggleTheme } = useTheme();
  const columns = usePersistedPanelSizes("columns", { library: 20, center: 58, inspector: 22 });
  const rows = usePersistedPanelSizes("rows", { main: 68, dock: 32 });
  const [centerTab, setCenterTab] = useState<CenterTabId>("diagram");
  const [dockTab, setDockTab] = useState<DockTabId>("plots");

  useEffect(() => {
    const showPlots = (): void => setDockTab("plots");
    window.addEventListener(SHOW_PLOTS_EVENT, showPlots);
    return () => window.removeEventListener(SHOW_PLOTS_EVENT, showPlots);
  }, []);

  return (
    <div className="app-shell" data-testid="app-shell">
      <TopBar theme={theme} onToggleTheme={toggleTheme} />
      <DetachedPlotWindow />
      <DetachedAutoPlotWindow />

      <Group
        id="bgsim-rows"
        orientation="vertical"
        className="app-shell__body"
        defaultLayout={rows.defaultLayout}
        onLayoutChanged={rows.onLayoutChanged}
      >
        <Panel id="main" minSize="30" className="app-shell__main" style={{ overflow: "hidden" }}>
          <Group
            id="bgsim-columns"
            orientation="horizontal"
            defaultLayout={columns.defaultLayout}
            onLayoutChanged={columns.onLayoutChanged}
          >
            <Panel
              id="library"
              defaultSize="20"
              minSize={200}
              maxSize="40"
              className="app-shell__side"
              style={{ overflow: "hidden" }}
            >
              <LeftPanel />
            </Panel>

            <Separator className="splitter" />

            <Panel id="center" minSize="30" className="app-shell__center" style={{ overflow: "hidden" }}>
              <CenterTabs active={centerTab} onSelect={setCenterTab} />
            </Panel>

            <Separator className="splitter" />

            <Panel
              id="inspector"
              defaultSize="22"
              minSize={220}
              maxSize="45"
              className="app-shell__side"
              style={{ overflow: "hidden" }}
            >
              <InspectorPanel />
            </Panel>
          </Group>
        </Panel>

        <Separator className="splitter" />

        <Panel id="dock" defaultSize="32" minSize={140} maxSize="70" className="app-shell__dock" style={{ overflow: "hidden" }}>
          <BottomDock active={dockTab} onSelect={setDockTab} diagnostics={NO_DIAGNOSTICS} />
        </Panel>
      </Group>
    </div>
  );
}
