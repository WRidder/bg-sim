/**
 * The model tree of plan 7.2: a recursive outline of the open diagram.
 *
 * A subsystem row shows its exposed-port count and nests its children at any
 * depth. Clicking a row opens the Diagram tab on the diagram that owns the
 * element, selects it and centres it; double-clicking a subsystem row enters it.
 */

import { requestCenterTab } from "../app/dockBus";

import { useCatalogStore } from "../library/catalogStore";
import { useDocumentStore } from "../state/documentStore";
import { clearCenterNode, requestCenterNode } from "./canvasFocus";
import { interfaceForNode } from "./nodeInterface";
import { BlockIcon, JunctionGlyph } from "./icons";
import type { ModelNode } from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";

interface TreeRowsProps {
  nodes: readonly ModelNode[];
  /** Subsystem node ids from the root to this diagram. */
  path: readonly string[];
  index: CatalogIndex;
  activePath: readonly string[];
  selectedNodeIds: readonly string[];
  depth: number;
}

function samePath(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((id, index) => id === b[index]);
}

function TreeRows({
  nodes,
  path,
  index,
  activePath,
  selectedNodeIds,
  depth,
}: TreeRowsProps) {
  const inActiveDiagram = samePath(path, activePath);
  return (
    <ul className={`model-tree__list${depth > 0 ? " model-tree__list--nested" : ""}`}>
      {nodes.map((node) => {
        const iface = interfaceForNode(node, index);
        const subsystem = "subsystem" in node.block ? node.block.subsystem : null;
        const selected = inActiveDiagram && selectedNodeIds.includes(node.id);
        return (
          <li key={node.id} data-tree-path={[...path, node.id].join("/")}>
            <button
              type="button"
              className="model-tree__item"
              aria-current={selected ? "true" : undefined}
              data-testid={`tree-node-${node.name}`}
              data-depth={depth}
              data-subsystem={subsystem !== null ? "true" : "false"}
              data-port-count={subsystem?.ports.length ?? 0}
              onClick={() => {
                if (useDocumentStore.getState().selectNodeAt(path, node.id)) {
                  requestCenterNode(node.id);
                  requestCenterTab("diagram");
                }
              }}
              onDoubleClick={
                subsystem !== null
                  ? () => {
                      // The two clicks before asked to centre the subsystem block; inside it there is none.
                      clearCenterNode(node.id);
                      useDocumentStore.getState().navigateToPath([...path, node.id]);
                      requestCenterTab("diagram");
                    }
                  : undefined
              }
              title={
                subsystem !== null
                  ? `Show ${node.name} on the diagram; double-click to enter it (${subsystem.ports.length} exposed ports)`
                  : `Show ${node.name} on the diagram`
              }
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
                <span className="model-tree__kind">
                  {subsystem !== null
                    ? `Subsystem · ${subsystem.ports.length} ports`
                    : iface.title}
                </span>
              </span>
            </button>
            {subsystem !== null ? (
              <TreeRows
                nodes={subsystem.diagram.nodes}
                path={[...path, node.id]}
                index={index}
                activePath={activePath}
                selectedNodeIds={selectedNodeIds}
                depth={depth + 1}
              />
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

export function ModelTree() {
  const doc = useDocumentStore((state) => state.doc);
  const selection = useDocumentStore((state) => state.selection);
  const activePath = useDocumentStore((state) => state.activePath);
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
      {doc.diagram.nodes.length === 0 ? (
        <p className="model-tree__empty">
          The diagram is empty. Drag a block from the library onto the canvas and it is listed here.
        </p>
      ) : (
        <TreeRows
          nodes={doc.diagram.nodes}
          path={[]}
          index={index}
          activePath={activePath}
          selectedNodeIds={selection.nodes}
          depth={0}
        />
      )}
    </div>
  );
}
