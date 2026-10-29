import { lazy, Suspense, useEffect, useState } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";

import { usePersistedPanelSizes } from "../state/layout";
import { useTheme } from "../theme/useTheme";
import { BlockHelp } from "./BlockHelp";
import { BottomDock, type DiagnosticCounts, type DockTabId } from "./BottomDock";
import { CenterTabs, type CenterTabId } from "./CenterTabs";
import { SHOW_PLOTS_EVENT } from "./dockBus";
import { InspectorPanel } from "./InspectorPanel";
import { LeftPanel } from "./LeftPanel";
import { hasProjectRoute } from "./route";
import { ShortcutsOverlay } from "./ShortcutsOverlay";
import { StartPage } from "./StartPage";
import { TopBar } from "./TopBar";
import { useAppShortcuts } from "./useAppShortcuts";
import { useAutoDetachStore, useDetachStore } from "../plot/detachStore";

// The popup windows pull in uPlot; they load only once a plot is detached (code splitting, W5.4).
const DetachedPlotWindow = lazy(() =>
  import("../plot/DetachedPlotWindow").then((m) => ({ default: m.DetachedPlotWindow })),
);
const DetachedAutoPlotWindow = lazy(() =>
  import("../plot/DetachedAutoPlotWindow").then((m) => ({ default: m.DetachedAutoPlotWindow })),
);

/**
 * Nothing has been checked yet, so the diagnostics badges start at zero; M1
 * feeds the real counts from `model.check`.
 */
const NO_DIAGNOSTICS: DiagnosticCounts = { error: 0, warning: 0 };

/**
 * The application shell of plan 7.2: top bar, a resizable three-column body
 * (library + model tree │ centre tabs │ inspector) and the bottom dock.
 * Without `?project=` in the URL the body is the start page (example gallery)
 * instead of the editor. Every split is a `Group`/`Panel`/`Separator` whose sizes persist in
 * localStorage (src/state/layout.ts).
 */
export function App() {
  const { theme, toggleTheme } = useTheme();
  const columns = usePersistedPanelSizes("columns", { library: 20, center: 58, inspector: 22 });
  const rows = usePersistedPanelSizes("rows", { main: 68, dock: 32 });
  const [centerTab, setCenterTab] = useState<CenterTabId>("diagram");
  const [dockTab, setDockTab] = useState<DockTabId>("plots");
  const [startPage] = useState(() => !hasProjectRoute());
  useAppShortcuts();
  const plotsDetached = useDetachStore((state) => state.detached);
  const autoPlotDetached = useAutoDetachStore((state) => state.detached);

  useEffect(() => {
    const showPlots = (): void => setDockTab("plots");
    window.addEventListener(SHOW_PLOTS_EVENT, showPlots);
    return () => window.removeEventListener(SHOW_PLOTS_EVENT, showPlots);
  }, []);

  return (
    <div className="app-shell" data-testid="app-shell">
      <a className="skip-link" href="#main">
        Skip to the main content
      </a>
      <TopBar theme={theme} onToggleTheme={toggleTheme} />
      <ShortcutsOverlay />
      <BlockHelp />
      {startPage ? <StartPage /> : null}
      <Suspense fallback={null}>
        {plotsDetached ? <DetachedPlotWindow /> : null}
        {autoPlotDetached ? <DetachedAutoPlotWindow /> : null}
      </Suspense>

      {startPage ? null : (
        <main id="main" tabIndex={-1} className="app-shell__main-landmark">
          <Group
            id="bgsim-rows"
            orientation="vertical"
            className="app-shell__body"
            defaultLayout={rows.defaultLayout}
            onLayoutChanged={rows.onLayoutChanged}
          >
            <Panel
              id="main"
              minSize="30"
              className="app-shell__main"
              style={{ overflow: "hidden" }}
            >
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

                <Panel
                  id="center"
                  minSize="30"
                  className="app-shell__center"
                  style={{ overflow: "hidden" }}
                >
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

            <Panel
              id="dock"
              defaultSize="32"
              minSize={140}
              maxSize="70"
              className="app-shell__dock"
              style={{ overflow: "hidden" }}
            >
              <BottomDock active={dockTab} onSelect={setDockTab} diagnostics={NO_DIAGNOSTICS} />
            </Panel>
          </Group>
        </main>
      )}
    </div>
  );
}
