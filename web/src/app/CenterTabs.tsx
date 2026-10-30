import { lazy, Suspense } from "react";

import { useDebugStore } from "../debug/debugStore";
import { DiagramTab } from "../editor/DiagramTab";
import { hasUnsavedDocs, saveUnsavedDocs } from "../docs/leaveGuard";
import { EmptyState } from "./EmptyState";
import { TabStrip, type TabDefinition } from "./TabStrip";

// CodeMirror loads when the Code tab is first opened (code splitting, W5.4).
const CodeTab = lazy(() => import("../code/CodeTab").then((m) => ({ default: m.CodeTab })));

// The Docs tab (Markdown, KaTeX, CodeMirror) loads when it is first opened (code splitting, W5.6).
const DocsTab = lazy(() => import("../docs/DocsTab").then((m) => ({ default: m.DocsTab })));

export type CenterTabId = "diagram" | "code" | "docs";

function centerTabs(pausedPath: string | null): readonly TabDefinition<CenterTabId>[] {
  return [
    { id: "diagram", label: "Diagram" },
    // W4.1: a statement pause shows its instance path in the tab title.
    { id: "code", label: pausedPath === null ? "Code" : `Code · paused in ${pausedPath}` },
    { id: "docs", label: "Docs" },
  ];
}

export interface CenterTabsProps {
  active: CenterTabId;
  onSelect: (id: CenterTabId) => void;
}

/**
 * The centre tab area of plan 7.2: the diagram canvas (W1.1) and the Code tab
 * (W2.1, mounted as `CodeTab` so the editor and the canvas can be developed
 * independently), and the model's Docs wiki (W5.6). Leaving the Docs tab with
 * unsaved page edits asks first, like closing the browser tab does.
 */
export function CenterTabs({ active, onSelect }: CenterTabsProps) {
  const pausedPath = useDebugStore((state) => {
    const location = state.pausedInfo?.location;
    return location !== null && location !== undefined && location.scope !== "watch"
      ? location.path
      : null;
  });
  const tabs = centerTabs(pausedPath);
  const select = (id: CenterTabId): void => {
    if (active === "docs" && id !== "docs" && hasUnsavedDocs()) {
      const leave = window.confirm(
        "The open docs page has unsaved changes.\n\nOK saves them and leaves the Docs tab. Cancel stays on the page.",
      );
      if (!leave) {
        return;
      }
      void saveUnsavedDocs().then((saved) => {
        if (saved) {
          onSelect(id);
        }
      });
      return;
    }
    onSelect(id);
  };
  return (
    <div className="center-tabs" data-testid="center-tabs">
      <TabStrip
        tabs={tabs}
        active={active}
        onSelect={select}
        ariaLabel="Editor"
        idPrefix="center"
      />
      <div
        className={`tab-panel${active === "diagram" ? " tab-panel--diagram" : ""}`}
        role="tabpanel"
        id={`center-panel-${active}`}
        aria-labelledby={`center-tab-${active}`}
        tabIndex={0}
      >
        {active === "diagram" ? (
          <DiagramTab />
        ) : active === "code" ? (
          <Suspense fallback={<EmptyState title="Loading the code editor" hint="One moment." />}>
            <CodeTab />
          </Suspense>
        ) : (
          <Suspense fallback={<EmptyState title="Loading the docs" hint="One moment." />}>
            <DocsTab onShowDiagram={() => onSelect("diagram")} />
          </Suspense>
        )}
      </div>
    </div>
  );
}
