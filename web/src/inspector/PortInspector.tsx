/**
 * The inspector for one selected subsystem port terminal (inside the
 * subsystem). The name is editable (an identifier, unique among the
 * subsystem's ports; outside connections follow the rename); kind,
 * direction, domain, type, size and unit come from the internal port when the
 * port was exposed, and the "maps to" line names that internal port.
 */

import { useRef, useState } from "react";

import type { ModelNode, ModelSubsystemPort } from "../contracts/model";
import { domainLetter, formatSize } from "../editor/connectionRules";
import { domainColor, signalColor } from "../editor/geometry";
import { requestSubsystemPortDelete } from "../editor/PortDeleteConfirm";
import type { OutsideLink } from "../editor/subsystemBoundary";
import { endpointLabel, subsystemPortNameIssue, terminalKindOf } from "../editor/subsystemPorts";
import { enclosingInstance, instanceCount } from "../library/linkedSubsystems";
import { useDocumentStore } from "../state/documentStore";
import { TextField } from "./fields";
import "../editor/nodes/portTerminal.css";

export interface PortInspectorProps {
  port: ModelSubsystemPort;
  ports: readonly ModelSubsystemPort[];
  /** The subsystem's instance name. */
  subsystemName: string;
  /** The nested diagram's nodes (for the "maps to" line). */
  nodes: readonly ModelNode[];
  outside: readonly OutsideLink[];
  onReveal: () => void;
}

const KIND_TEXT = {
  input: "Signal input",
  output: "Signal output",
  power: "Power port",
} as const;

export function PortInspector({ port, ports, subsystemName, nodes, outside, onReveal }: PortInspectorProps) {
  const [problem, setProblem] = useState<string | null>(null);
  // The new name the user was asked to confirm (a port of a library subsystem).
  const pendingRename = useRef<string | null>(null);
  const kind = terminalKindOf(port);
  const colour = port.kind === "power" ? domainColor(port.domain) : signalColor(port.type);
  const mapsTo = endpointLabel(nodes, port.node, port.port);
  const missing = !nodes.some((node) => node.id === port.node);
  return (
    <div className="inspector-body" data-testid="inspector-port" data-port-name={port.name}>
      <header className="inspector-header">
        <div className="inspector-header__icon" aria-hidden="true">
          <span className="inspector-port-swatch" style={{ color: colour }} />
        </div>
        <div className="inspector-header__text">
          <p className="inspector-header__kicker">Subsystem port of {subsystemName}</p>
          <h3 className="inspector-header__title" data-testid="inspector-title">
            {KIND_TEXT[kind]}
          </h3>
          <p className="inspector-header__description">
            The outer block shows this port; a connection to it there reaches the internal port it
            maps to.
          </p>
        </div>
      </header>

      <section className="inspector-section" aria-labelledby="inspector-port-name-title">
        <h4 className="inspector-section__title" id="inspector-port-name-title">
          Name
        </h4>
        <TextField
          id="inspector-port-name"
          testId="inspector-port-name"
          label="Port name"
          value={port.name}
          issue={(text) => subsystemPortNameIssue(ports, port.name, text.trim())}
          onCommit={(text) => {
            const state = useDocumentStore.getState();
            const next = text.trim();
            // A port of a library subsystem is the port of every instance: ask once.
            const shared =
              state.doc === null ? null : enclosingInstance(state.doc, state.activePath);
            if (shared !== null && state.doc !== null && next !== port.name && pendingRename.current !== next) {
              pendingRename.current = next;
              const count = instanceCount(state.doc, shared.name);
              return `This renames the port in all ${count} ${count === 1 ? "instance" : "instances"} of ${shared.name}. Connections in this model follow; another model of the project that uses ${shared.name} loses its connection to ${port.name}. Press Enter again to rename.`;
            }
            pendingRename.current = null;
            const result = state.renameSubsystemPort(port.name, text);
            return result.ok ? null : (result.error ?? "The name was refused.");
          }}
          description={`Outside ${subsystemName} connections name this port; they follow a rename.`}
        />
      </section>

      <section className="inspector-section" aria-labelledby="inspector-port-facts-title">
        <h4 className="inspector-section__title" id="inspector-port-facts-title">
          Port
        </h4>
        <dl className="inspector-facts" data-testid="inspector-port-facts">
          <dt>Kind</dt>
          <dd data-testid="inspector-port-kind">
            {port.kind === "signal" ? `signal ${port.direction}` : "power"}
          </dd>
          {port.kind === "power" ? (
            <>
              <dt>Domain</dt>
              <dd data-testid="inspector-port-domain">
                <span className="inspector-port-letter" style={{ color: colour }}>
                  {domainLetter(port.domain)}
                </span>{" "}
                {port.domain}
              </dd>
              {port.frame !== undefined && port.frame !== null ? (
                <>
                  <dt>Frame</dt>
                  <dd>
                    <code>{port.frame}</code>
                  </dd>
                </>
              ) : null}
            </>
          ) : (
            <>
              <dt>Type</dt>
              <dd data-testid="inspector-port-type">{port.type}</dd>
              <dt>Size</dt>
              <dd>{formatSize(port.size)}</dd>
              <dt>Unit</dt>
              <dd data-testid="inspector-port-unit">{port.unit ?? "—"}</dd>
            </>
          )}
          <dt>Maps to</dt>
          <dd data-testid="inspector-port-maps-to">
            <code>{mapsTo}</code>
            {missing ? <span className="inspector-tag inspector-tag--live">missing</span> : null}
          </dd>
        </dl>
      </section>

      <section className="inspector-section" aria-labelledby="inspector-port-outside-title">
        <h4 className="inspector-section__title" id="inspector-port-outside-title">
          Outside {subsystemName}
          <span className="inspector-section__count">{outside.length}</span>
        </h4>
        {outside.length === 0 ? (
          <p className="inspector-port-unconnected" data-testid="inspector-port-unconnected">
            Unconnected: nothing outside {subsystemName} connects to {port.name} yet.
          </p>
        ) : (
          <ul className="inspector-summary" aria-label="Outside connections">
            {outside.map((link) => (
              <li key={link.connectionId} data-testid={`inspector-port-outside-${link.connectionId}`}>
                <code>{link.peer}</code>
              </li>
            ))}
          </ul>
        )}
        <div className="inspector-actions">
          <button
            type="button"
            className="button inspector-button"
            data-testid="inspector-port-reveal"
            onClick={onReveal}
          >
            Show on the parent diagram
          </button>
          <button
            type="button"
            className="button inspector-button"
            data-testid="inspector-port-delete"
            onClick={() => setProblem(requestSubsystemPortDelete([port.name], "ports"))}
          >
            Delete port
          </button>
        </div>
        {problem !== null ? (
          <p className="inspector-warning" role="alert">
            {problem}
          </p>
        ) : null}
      </section>
    </div>
  );
}
