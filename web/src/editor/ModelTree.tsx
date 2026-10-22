/**
 * The model tree of plan 7.2: an outline of the open diagram. Clicking a row
 * selects the node on the canvas; the outline is read-only until subsystems
 * arrive (W2.2).
 */

import { useCatalogStore } from "../library/catalogStore";
import { useDocumentStore } from "../state/documentStore";
import { interfaceForNode } from "./nodeInterface";
import { BlockIcon, JunctionGlyph } from "./icons";

export function ModelTree() {
  const doc = useDocumentStore((state) => state.doc);
  const selection = useDocumentStore((state) => state.selection);
  const index = useCatalogStore((state) => state.index);

  if (doc === null || index === null) {
    return (
      <div className="model-tree" data-testid="model-tree">
        <p className="model-tree__empty">
          No model open. Open a project to see its blocks and subsystems here.
        </p>
      </div>
    );
  }

  return (
    <div className="model-tree" data-testid="model-tree">
      <div className="model-tree__summary" data-testid="model-tree-summary">
        {doc.diagram.nodes.length} {doc.diagram.nodes.length === 1 ? "block" : "blocks"} ·{" "}
        {doc.diagram.connections.length}{" "}
        {doc.diagram.connections.length === 1 ? "connection" : "connections"}
      </div>
      <ul className="model-tree__list" aria-label="Model tree">
        {doc.diagram.nodes.map((node) => {
          const iface = interfaceForNode(node, index);
          const selected = selection.nodes.includes(node.id);
          return (
            <li key={node.id}>
              <button
                type="button"
                className="model-tree__item"
                aria-selected={selected}
                data-testid={`tree-node-${node.name}`}
                onClick={() => useDocumentStore.getState().setSelection([node.id], [])}
              >
                <span className="model-tree__glyph" aria-hidden="true">
                  {iface.isJunction ? (
                    <JunctionGlyph kind={iface.junction ?? "0"} size={20} />
                  ) : (
                    <BlockIcon icon={iface.icon} name={iface.title} size={20} />
                  )}
                </span>
                <span className="model-tree__text">
                  <span className="model-tree__name">{node.name}</span>
                  <span className="model-tree__kind">{iface.title}</span>
                </span>
              </button>
            </li>
          );
        })}
        {doc.diagram.nodes.length === 0 ? (
          <li>
            <p className="model-tree__empty">The diagram is empty.</p>
          </li>
        ) : null}
      </ul>
    </div>
  );
}
