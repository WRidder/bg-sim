import { Group, Panel, Separator } from "react-resizable-panels";

import { usePersistedPanelSizes } from "../state/layout";
import { EmptyState } from "./EmptyState";

/**
 * The left column of plan 7.2: the block library on top, the model tree
 * below, with a resizable split between them. Both are empty until a project
 * and its catalog are loaded (M1/M2).
 */
export function LeftPanel() {
  const sections = usePersistedPanelSizes("left-column", { library: 55, tree: 45 });

  return (
    <div className="left-panel" data-testid="left-panel">
      <Group
        id="bgsim-left-column"
        orientation="vertical"
        defaultLayout={sections.defaultLayout}
        onLayoutChanged={sections.onLayoutChanged}
      >
        <Panel id="library-section" minSize="20" style={{ overflow: "hidden" }}>
          <section className="panel-section" aria-labelledby="library-heading">
            <h2 className="panel-section__title" id="library-heading">
              Library
            </h2>
            <div className="panel-section__body">
              <EmptyState
                title="Library is empty"
                hint="Open a project to load its catalog of blocks. Drag a block from here onto the diagram to add it."
              />
            </div>
          </section>
        </Panel>

        <Separator className="splitter" />

        <Panel id="tree-section" minSize="20" style={{ overflow: "hidden" }}>
          <section className="panel-section" aria-labelledby="model-tree-heading">
            <h2 className="panel-section__title" id="model-tree-heading">
              Model tree
            </h2>
            <div className="panel-section__body">
              <EmptyState
                title="No models open"
                hint="Open a project, then pick a model to see its blocks and subsystems in this outline."
              />
            </div>
          </section>
        </Panel>
      </Group>
    </div>
  );
}
