import { Group, Panel, Separator } from "react-resizable-panels";

import { LibraryBrowser } from "../library/LibraryBrowser";
import { ModelTree } from "../editor/ModelTree";
import { usePersistedPanelSizes } from "../state/layout";

/**
 * The left column of plan 7.2: the block library on top, the model tree below,
 * with a resizable split between them. Both are filled by the editor module:
 * the catalog browser (W1.1) and the diagram outline.
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
              <LibraryBrowser />
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
              <ModelTree />
            </div>
          </section>
        </Panel>
      </Group>
    </div>
  );
}
