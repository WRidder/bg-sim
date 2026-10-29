/**
 * The inspector for one selected connection (W-MB3).
 *
 * A bond is a pure power connection: it never transforms, and a
 * FixedTransform/JointTransform is the only legal bridge between two frames
 * (D-MB5). Frame identity is face-scoped (FIX-MB-6) and decided by the worker;
 * this panel shows the port frames, the worker's display-qualified
 * `{path}/{frame}` name from `model.check.frames`, and any E007 raised for
 * this connection, and never re-implements the rule client-side.
 */

import type { Diagnostic } from "../contracts/diagnostic";
import type { DomainName } from "../contracts/catalog";
import type { ModelConnection, ModelNode } from "../contracts/model";
import { interfaceForNode } from "../editor/nodeInterface";
import { multibondComponents, multibondStrokes } from "../editor/geometry";
import type { CatalogIndex } from "../library/catalogIndex";
import {
  explainBondFrames,
  frameDiagnostic,
  portFrame,
  type PortFrame,
} from "./frames";

export interface ConnectionInspectorProps {
  connection: ModelConnection;
  nodes: readonly ModelNode[];
  index: CatalogIndex;
  /** Connection id -> instance-qualified frame from `model.check`. */
  frames: Record<string, string>;
  /** Connection id -> adopted domain from `model.check`. */
  domains: Record<string, DomainName>;
  /** The current `model.check` diagnostics (E007 is matched by connection id). */
  diagnostics?: readonly Diagnostic[];
  /** Instance names of the subsystem path to this diagram, root first. */
  path: readonly string[];
}

function endpointText(
  endpoint: ModelConnection["from"],
  nodes: readonly ModelNode[],
): string {
  const name = nodes.find((node) => node.id === endpoint.node)?.name ?? endpoint.node;
  return endpoint.port === undefined ? name : `${name}.${endpoint.port}`;
}

function endpointFrame(
  endpoint: ModelConnection["from"],
  nodes: readonly ModelNode[],
  index: CatalogIndex,
  path: readonly string[],
): PortFrame | null {
  if (endpoint.port === undefined) {
    return null;
  }
  const node = nodes.find((entry) => entry.id === endpoint.node);
  if (node === undefined) {
    return null;
  }
  const port = interfaceForNode(node, index).ports.find(
    (entry) => entry.name === endpoint.port,
  );
  return port === undefined ? null : portFrame(node, port, path);
}

const EMPTY_FRAME: PortFrame = { endpoint: "", declared: null, qualified: null };

function EndpointFrame({
  label,
  frame,
  testId,
}: {
  label: string;
  frame: PortFrame | null;
  testId: string;
}) {
  return (
    <div className="inspector-frame__row" data-testid={testId}>
      <dt>{label}</dt>
      <dd>
        {frame === null ? (
          <span className="inspector-frame__neutral">no power port</span>
        ) : frame.declared === null ? (
          <span className="inspector-frame__neutral">frame-neutral</span>
        ) : (
          <>
            <code>{frame.declared}</code>
            {frame.qualified !== null && frame.qualified !== frame.declared ? (
              <span className="inspector-frame__qualified">{frame.qualified}</span>
            ) : null}
          </>
        )}
      </dd>
    </div>
  );
}

export function ConnectionInspector({
  connection,
  nodes,
  index,
  frames,
  domains,
  diagnostics = [],
  path,
}: ConnectionInspectorProps) {
  const from = endpointFrame(connection.from, nodes, index, path);
  const to = endpointFrame(connection.to, nodes, index, path);
  const reported = frames[connection.id] ?? null;
  const domain = domains[connection.id];
  const isPower = connection.kind === "bond" || connection.kind === "wire";
  const strokes = isPower ? multibondStrokes(domain ?? null) : 1;
  const components = isPower ? multibondComponents(domain ?? null) : 1;

  return (
    <div className="inspector-body" data-testid="inspector-connections">
      <header className="inspector-header inspector-header--summary">
        <div className="inspector-header__text">
          <p className="inspector-header__kicker">Connection</p>
          <h3 className="inspector-header__title">1 connection selected</h3>
          <p className="inspector-header__description">
            Right-click a bond on the canvas to reverse its direction, or delete the selection
            with Del. Select a block to edit its parameters.
          </p>
        </div>
      </header>

      <ul className="inspector-summary" aria-label="Selected connections">
        <li data-testid={`inspector-connection-summary-${connection.id}`}>
          <span className={`inspector-tag inspector-tag--${connection.kind}`}>
            {connection.kind}
          </span>
          <code>
            {endpointText(connection.from, nodes)} → {endpointText(connection.to, nodes)}
          </code>
        </li>
      </ul>

      <section
        className="inspector-section inspector-section--last"
        aria-labelledby={`inspector-frame-title-${connection.id}`}
      >
        <h4 className="inspector-section__title" id={`inspector-frame-title-${connection.id}`}>
          Frame
        </h4>
        {isPower ? (
          <>
            <dl
              className="inspector-frame"
              data-testid={`inspector-connection-frame-${connection.id}`}
              data-frame={reported}
            >
              <div className="inspector-frame__row">
                <dt>model check</dt>
                <dd>
                  {reported === null ? (
                    <span className="inspector-frame__neutral">no frame reported</span>
                  ) : (
                    <code>{reported}</code>
                  )}
                </dd>
              </div>
              <EndpointFrame
                label={endpointText(connection.from, nodes)}
                frame={from}
                testId={`inspector-connection-end-${connection.id}-from`}
              />
              <EndpointFrame
                label={endpointText(connection.to, nodes)}
                frame={to}
                testId={`inspector-connection-end-${connection.id}-to`}
              />
            </dl>
            <p
              className="inspector-frame__explanation"
              data-testid={`inspector-frame-explanation-${connection.id}`}
            >
              {explainBondFrames({
                from: from ?? EMPTY_FRAME,
                to: to ?? EMPTY_FRAME,
                reported,
                e007: frameDiagnostic(diagnostics, connection.id),
              })}
            </p>
            {domain !== undefined ? (
              <p
                className="inspector-note"
                data-testid={`inspector-connection-domain-${connection.id}`}
              >
                {domain} · {components} {components === 1 ? "component" : "components"} ·{" "}
                {strokes} {strokes === 1 ? "stroke" : "strokes"}
              </p>
            ) : null}
          </>
        ) : (
          <p className="inspector-note" data-testid={`inspector-frame-${connection.id}`}>
            Signals do not carry a reference frame; only power bonds and wires do.
          </p>
        )}
      </section>
    </div>
  );
}
