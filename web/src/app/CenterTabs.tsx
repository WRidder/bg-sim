import { CodeTab } from "../code/CodeTab";
import { DiagramTab } from "../editor/DiagramTab";
import { TabStrip, type TabDefinition } from "./TabStrip";

export type CenterTabId = "diagram" | "code";

const CENTER_TABS: readonly TabDefinition<CenterTabId>[] = [
  { id: "diagram", label: "Diagram" },
  { id: "code", label: "Code" },
];

export interface CenterTabsProps {
  active: CenterTabId;
  onSelect: (id: CenterTabId) => void;
}

/**
 * The centre tab area of plan 7.2: the diagram canvas (W1.1) and the Code tab
 * (W2.1, mounted as `CodeTab` so the editor and the canvas can be developed
 * independently).
 */
export function CenterTabs({ active, onSelect }: CenterTabsProps) {
  return (
    <div className="center-tabs" data-testid="center-tabs">
      <TabStrip
        tabs={CENTER_TABS}
        active={active}
        onSelect={onSelect}
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
        {active === "diagram" ? <DiagramTab /> : <CodeTab />}
      </div>
    </div>
  );
}
