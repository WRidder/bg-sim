import { DiagramTab } from "../editor/DiagramTab";
import { EmptyState } from "./EmptyState";
import { TabStrip, type TabDefinition } from "./TabStrip";

export type CenterTabId = "diagram" | "code";

const CENTER_TABS: readonly TabDefinition<CenterTabId>[] = [
  { id: "diagram", label: "Diagram" },
  { id: "code", label: "Code" },
];

const CODE_EMPTY_STATE = {
  title: "No source open",
  hint: "Select a block and choose “Open source” to read and edit its code here.",
};

export interface CenterTabsProps {
  active: CenterTabId;
  onSelect: (id: CenterTabId) => void;
}

/**
 * The centre tab area of plan 7.2: the diagram canvas (W1.1) and the Code tab,
 * which stays empty until W2.1 adds the block editor.
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
        {active === "diagram" ? (
          <DiagramTab />
        ) : (
          <EmptyState title={CODE_EMPTY_STATE.title} hint={CODE_EMPTY_STATE.hint} />
        )}
      </div>
    </div>
  );
}
