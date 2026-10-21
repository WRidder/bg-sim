import { EmptyState } from "./EmptyState";
import { TabStrip, type TabDefinition } from "./TabStrip";

export type CenterTabId = "diagram" | "code";

const CENTER_TABS: readonly TabDefinition<CenterTabId>[] = [
  { id: "diagram", label: "Diagram" },
  { id: "code", label: "Code" },
];

const CENTER_EMPTY_STATES: Record<CenterTabId, { title: string; hint: string }> = {
  diagram: {
    title: "No diagram open",
    hint: "Select a model to see its block diagram here, then drag blocks from the library onto the canvas.",
  },
  code: {
    title: "No source open",
    hint: "Select a block and choose “Open source” to read and edit its code here.",
  },
};

export interface CenterTabsProps {
  active: CenterTabId;
  onSelect: (id: CenterTabId) => void;
}

/** The centre tab area of plan 7.2: Diagram and Code, empty until M1. */
export function CenterTabs({ active, onSelect }: CenterTabsProps) {
  const empty = CENTER_EMPTY_STATES[active];

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
        className="tab-panel"
        role="tabpanel"
        id={`center-panel-${active}`}
        aria-labelledby={`center-tab-${active}`}
        tabIndex={0}
      >
        <EmptyState title={empty.title} hint={empty.hint} />
      </div>
    </div>
  );
}
