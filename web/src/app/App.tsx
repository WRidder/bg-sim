import { lazy, Suspense, useEffect, useState } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";

import { useAssistantPanelStore } from "../assistant/panelStore";
import { usePersistedPanelSizes } from "../state/layout";
import { useTheme } from "../theme/useTheme";
import { BlockHelp } from "./BlockHelp";
import { BottomDock, type DiagnosticCounts, type DockTabId } from "./BottomDock";
import { CenterTabs, type CenterTabId } from "./CenterTabs";
import { SHOW_CENTER_TAB_EVENT, SHOW_PLOTS_EVENT } from "./dockBus";
import { InspectorPanel } from "./InspectorPanel";
import { LeftPanel } from "./LeftPanel";
import { ModelPicker } from "./ModelPicker";
import { readAppRoute, readScreenTab } from "./route";
import { ShortcutsOverlay } from "./ShortcutsOverlay";
import { StartPage } from "./StartPage";
import { TopBar } from "./TopBar";
import { useAppShortcuts } from "./useAppShortcuts";
import { useAutoDetachStore, useDetachStore } from "../plot/detachStore";
import { useViewerDetachStore } from "../viewer/detachStore";

// The chat pulls in the Markdown stack; it loads when the panel first opens.
const AssistantPanel = lazy(() =>
  import("../assistant/AssistantPanel").then((m) => ({ default: m.AssistantPanel })),
);
// The popup windows pull in uPlot; they load only once a plot is detached (code splitting, W5.4).
const DetachedPlotWindow = lazy(() =>
  import("../plot/DetachedPlotWindow").then((m) => ({ default: m.DetachedPlotWindow })),
);
const DetachedAutoPlotWindow = lazy(() =>
  import("../plot/DetachedAutoPlotWindow").then((m) => ({ default: m.DetachedAutoPlotWindow })),
);
// Likewise the detached 3D View pulls in Babylon (W5.5).
const DetachedViewerWindow = lazy(() =>
  import("../viewer/DetachedViewerWindow").then((m) => ({ default: m.DetachedViewerWindow })),
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
 * instead of the editor; with a project but no `model=` it is the project's
 * model picker (src/app/route.ts). Every split is a `Group`/`Panel`/`Separator` whose sizes persist in
 * localStorage (src/state/layout.ts).
 */
export function App() {
  const { theme, toggleTheme } = useTheme();
  const columns = usePersistedPanelSizes("columns", { library: 20, center: 58, inspector: 22 });
  const rows = usePersistedPanelSizes("rows", { main: 68, dock: 32 });
  // `tab=docs` in the editor URL opens the Docs tab (a deep link to a docs page, `page=`).
  const [centerTab, setCenterTab] = useState<CenterTabId>(() =>
    readAppRoute().kind === "editor" && readScreenTab().tab === "docs" ? "docs" : "diagram",
  );
  const [dockTab, setDockTab] = useState<DockTabId>("plots");
  const [route] = useState(() => readAppRoute());
  useAppShortcuts();
  const plotsDetached = useDetachStore((state) => state.detached);
  const autoPlotDetached = useAutoDetachStore((state) => state.detached);
  const viewerDetached = useViewerDetachStore((state) => state.detached);
  const assistantOpen = useAssistantPanelStore((state) => state.open);

  useEffect(() => {
    const showPlots = (): void => setDockTab("plots");
    window.addEventListener(SHOW_PLOTS_EVENT, showPlots);
    return () => window.removeEventListener(SHOW_PLOTS_EVENT, showPlots);
  }, []);

  // A sticky note's page: link asks for the Docs tab.
  useEffect(() => {
    const showCenter = (event: Event): void => {
      const tab = (event as CustomEvent<unknown>).detail;
      if (
        tab === "diagram" ||
        tab === "code" ||
        tab === "docs" ||
        tab === "parameters" ||
        tab === "dashboard"
      ) {
        setCenterTab(tab);
      }
    };
    window.addEventListener(SHOW_CENTER_TAB_EVENT, showCenter);
    return () => window.removeEventListener(SHOW_CENTER_TAB_EVENT, showCenter);
  }, []);

  return (
    <div className="app-shell" data-testid="app-shell">
      <a className="skip-link" href="#main">
        Skip to the main content
      </a>
      <TopBar theme={theme} onToggleTheme={toggleTheme} route={route} />
      <ShortcutsOverlay />
      <BlockHelp />
      <Suspense fallback={null}>
        {plotsDetached ? <DetachedPlotWindow /> : null}
        {autoPlotDetached ? <DetachedAutoPlotWindow /> : null}
        {viewerDetached ? <DetachedViewerWindow /> : null}
      </Suspense>

      <div className="app-shell__work">
        <div className="app-shell__screen">
          {route.kind === "start" ? <StartPage /> : null}
          {route.kind === "picker" ? <ModelPicker project={route.project} /> : null}
          {route.kind !== "editor" ? null : (
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
        {assistantOpen ? (
          <Suspense fallback={null}>
            <AssistantPanel route={route} />
          </Suspense>
        ) : null}
      </div>
    </div>
  );
}
