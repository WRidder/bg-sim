/**
 * The Inspector of plan 7.2 and 7.4, mounted by `InspectorPanel`.
 *
 * One selected node gets the full editor (name, block, parameters, constants,
 * start values, ports, source). A multiple selection gets a compact summary;
 * nothing selected gets guidance. All edits are document-store commands, so
 * Ctrl+Z / Ctrl+Y, the dirty marker and autosave keep working.
 */

import type { Diagnostic } from "../contracts/diagnostic";
import type { ModelConnection, ModelNode } from "../contracts/model";
import { EmptyState } from "../app/EmptyState";
import { useDiagnosticsStore } from "../diagnostics/store";
import { interfaceForNode } from "../editor/nodeInterface";
import { activeModel, subsystemPathCrumbs } from "../editor/subsystemPath";
import { useCatalogStore } from "../library/catalogStore";
import type { CatalogIndex } from "../library/catalogIndex";
import { useDocumentStore } from "../state/documentStore";
import { ProbeInspector } from "../probe/ProbeInspector";
import { ConnectionInspector } from "./ConnectionInspector";
import { NodeInspector } from "./NodeInspector";
import "./inspector.css";

export interface InspectorProps {
  /**
   * Override diagnostics for the open model. By default the inspector reads
   * the latest `model.check` result from the diagnostics store (W1.3) and
   * shows the entries for the selected node, such as the server-side unit
   * check of a parameter. The result is only shown while it belongs to the
   * current document revision.
   */
  diagnostics?: readonly Diagnostic[];
}

function nodeSummary(node: ModelNode, index: CatalogIndex | null): string {
  if (index === null) {
    return "junction" in node.block ? `${node.block.junction} junction` : "";
  }
  const iface = interfaceForNode(node, index);
  return iface.title;
}

function MultiSelection({
  nodes,
  connectionCount,
  index,
}: {
  nodes: readonly ModelNode[];
  connectionCount: number;
  index: CatalogIndex | null;
}) {
  return (
    <div className="inspector-body" data-testid="inspector-multi">
      <header className="inspector-header inspector-header--summary">
        <div className="inspector-header__text">
          <p className="inspector-header__kicker">Multiple selection</p>
          <h3 className="inspector-header__title">
            {nodes.length} {nodes.length === 1 ? "block" : "blocks"} selected
          </h3>
          <p className="inspector-header__description">
            The inspector edits one block at a time. Use the canvas to move, rotate, flip or
            delete the whole selection.
          </p>
          {connectionCount > 0 ? (
            <p className="inspector-header__ref">
              and {connectionCount} {connectionCount === 1 ? "connection" : "connections"}
            </p>
          ) : null}
        </div>
      </header>
      <ul className="inspector-summary" aria-label="Selected blocks">
        {nodes.map((node) => (
          <li key={node.id} data-testid={`inspector-multi-${node.name}`}>
            <span className="inspector-summary__name">{node.name}</span>
            <span className="inspector-summary__kind">{nodeSummary(node, index)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function endpointText(
  endpoint: ModelConnection["from"],
  nodes: readonly ModelNode[],
): string {
  const name = nodes.find((node) => node.id === endpoint.node)?.name ?? endpoint.node;
  return endpoint.port === undefined ? name : `${name}.${endpoint.port}`;
}

function ConnectionSelection({
  connections,
  nodes,
}: {
  connections: readonly ModelConnection[];
  nodes: readonly ModelNode[];
}) {
  return (
    <div className="inspector-body" data-testid="inspector-connections">
      <header className="inspector-header inspector-header--summary">
        <div className="inspector-header__text">
          <p className="inspector-header__kicker">Connections</p>
          <h3 className="inspector-header__title">
            {connections.length} {connections.length === 1 ? "connection" : "connections"}{" "}
            selected
          </h3>
          <p className="inspector-header__description">
            Right-click a bond on the canvas to reverse its direction, or delete the selection
            with Del. Select a block to edit its parameters.
          </p>
        </div>
      </header>
      <ul className="inspector-summary" aria-label="Selected connections">
        {connections.map((connection) => (
          <li key={connection.id} data-testid={`inspector-connection-summary-${connection.id}`}>
            <span className={`inspector-tag inspector-tag--${connection.kind}`}>
              {connection.kind}
            </span>
            <code>
              {endpointText(connection.from, nodes)} → {endpointText(connection.to, nodes)}
            </code>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Inspector({ diagnostics }: InspectorProps) {
  const doc = useDocumentStore((state) => state.doc);
  const activePath = useDocumentStore((state) => state.activePath);
  const selection = useDocumentStore((state) => state.selection);
  const project = useDocumentStore((state) => state.project);
  const revision = useDocumentStore((state) => state.revision);
  const index = useCatalogStore((state) => state.index);
  const liveDiagnostics = useDiagnosticsStore((state) => state.diagnostics);
  const liveFrames = useDiagnosticsStore((state) => state.frames);
  const liveDomains = useDiagnosticsStore((state) => state.domains);
  const checkedRevision = useDiagnosticsStore((state) => state.checkedRevision);
  const current = checkedRevision === revision;
  const effectiveDiagnostics = diagnostics ?? (current ? liveDiagnostics : []);

  if (doc === null) {
    return (
      <EmptyState
        title="Nothing selected"
        hint="Open a model and select a block to edit its name, parameters, ports and start values here."
      />
    );
  }

  const selectedNodes = doc.diagram.nodes.filter((node) =>
    selection.nodes.includes(node.id),
  );
  const active = activeModel(doc, activePath);
  const selectedProbe =
    selection.nodes.length === 1
      ? (active?.diagram.probes ?? []).find(
          (probe) => probe.id === selection.nodes[0],
        )
      : undefined;
  if (selectedProbe !== undefined && active !== null) {
    return <ProbeInspector model={active} probe={selectedProbe} />;
  }
  if (selectedNodes.length > 1) {
    return (
      <MultiSelection
        nodes={selectedNodes}
        connectionCount={selection.connections.length}
        index={index}
      />
    );
  }
  if (selectedNodes.length === 0) {
    if (selection.connections.length > 0) {
      const selectedConnections = doc.diagram.connections.filter((connection) =>
        selection.connections.includes(connection.id),
      );
      const pathNames = subsystemPathCrumbs(doc, activePath).map((crumb) => crumb.name);
      if (selectedConnections.length === 1 && index !== null) {
        const connection = selectedConnections[0];
        if (connection !== undefined) {
          return (
            <ConnectionInspector
              connection={connection}
              nodes={doc.diagram.nodes}
              index={index}
              frames={current ? liveFrames : {}}
              domains={current ? liveDomains : {}}
              diagnostics={effectiveDiagnostics}
              path={pathNames}
            />
          );
        }
      }
      return <ConnectionSelection connections={selectedConnections} nodes={doc.diagram.nodes} />;
    }
    return (
      <EmptyState
        title="Nothing selected"
        hint="Select a block on the diagram to edit its name, parameters, ports and start values here."
      />
    );
  }

  const node = selectedNodes[0];
  if (node === undefined) {
    return (
      <EmptyState
        title="Nothing selected"
        hint="Select a block on the diagram to edit its name, parameters, ports and start values here."
      />
    );
  }
  if (index === null) {
    return (
      <div className="inspector-body" data-testid="inspector-loading" role="status">
        <p className="inspector-note">
          The library catalog is loading; the parameters of {node.name} appear when it is ready.
        </p>
      </div>
    );
  }

  return (
    <NodeInspector
      key={node.id}
      node={node}
      siblings={doc.diagram.nodes}
      connections={doc.diagram.connections}
      index={index}
      project={project}
      diagnostics={effectiveDiagnostics}
      path={subsystemPathCrumbs(doc, activePath).map((crumb) => crumb.name)}
    />
  );
}
