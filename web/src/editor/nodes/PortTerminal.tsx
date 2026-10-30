/**
 * Subsystem port terminals on the inner canvas (virtual xyflow nodes; the
 * model stores only the subsystem's `ports`).
 *
 * * `PortTerminalNode` — a pill with the port name, coloured like the port
 *   glyphs, and a second line naming the outside connection (`← Traj.q_ref`,
 *   `→ PD.q +1`, or `unconnected` in the warning colour). Clicking that line
 *   leaves the subsystem and selects the outside connection(s).
 * * `PortGhostNode` — "+ input" / "+ output" / "+ power": drop a connection
 *   from an internal port on it to expose that port.
 */

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { createContext, useContext } from "react";

import type { DomainName, ValueType } from "../../contracts/catalog";
import type { Side } from "../geometry";
import type { TerminalKind } from "../subsystemPorts";
import "./portTerminal.css";

export interface TerminalActions {
  /** Leave the subsystem and select the outside connection(s) of `portName`. */
  reveal: (portName: string) => void;
}

export const TerminalActionsContext = createContext<TerminalActions>({
  reveal: () => undefined,
});

export interface TerminalNodeData extends Record<string, unknown> {
  portName: string;
  kind: TerminalKind;
  /** The drawn domain (a Generic port adopts its bond island); Generic for signals. */
  domain: DomainName;
  type: ValueType;
  colour: string;
  /** The edge the boundary wire leaves from. */
  handleSide: Side;
  width: number;
  height: number;
  outside: string;
  outsideTitle: string;
  connected: boolean;
  /** `V1.u`: the internal port the terminal maps to. */
  mapsTo: string;
  /** The internal node or port no longer exists. */
  broken: boolean;
}

export type TerminalNodeType = Node<TerminalNodeData, "terminal">;

export interface GhostNodeData extends Record<string, unknown> {
  kind: TerminalKind;
  handleSide: Side;
  /** During a connection drag: whether the dragged port may be exposed here. */
  state: "idle" | "compatible" | "incompatible";
}

export type GhostNodeType = Node<GhostNodeData, "terminalGhost">;

function handlePosition(side: Side): Position {
  switch (side) {
    case "left":
      return Position.Left;
    case "right":
      return Position.Right;
    case "top":
      return Position.Top;
    case "bottom":
    default:
      return Position.Bottom;
  }
}

const KIND_TITLE: Record<TerminalKind, string> = {
  input: "signal input",
  output: "signal output",
  power: "power port",
};

export function PortTerminalNode({ data, selected }: NodeProps<TerminalNodeType>) {
  const { reveal } = useContext(TerminalActionsContext);
  const title = `${data.portName} · exposed ${KIND_TITLE[data.kind]}${
    data.kind === "power" ? ` · ${data.domain}` : ` · ${data.type}`
  } · maps to ${data.mapsTo}${data.broken ? " (missing)" : ""}. Double-click to show the outside connection.`;
  return (
    <div
      className={[
        "port-terminal",
        `port-terminal--${data.kind}`,
        selected ? "is-selected" : "",
        data.broken ? "is-broken" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      style={{ width: data.width, height: data.height, color: data.colour }}
      data-testid={`port-terminal-${data.portName}`}
      data-port-name={data.portName}
      data-kind={data.kind}
      data-domain={data.domain}
      data-handle-side={data.handleSide}
      data-maps-to={data.mapsTo}
      data-connected={data.connected ? "true" : "false"}
      title={title}
    >
      <span className="port-terminal__name">{data.portName}</span>
      <button
        type="button"
        className={`port-terminal__link nodrag${data.connected ? "" : " is-unconnected"}`}
        data-testid={`port-terminal-link-${data.portName}`}
        title={data.outsideTitle}
        onClick={(event) => {
          // The node's own click would select the terminal again after the
          // parent diagram opened (and drop the revealed selection).
          event.stopPropagation();
          reveal(data.portName);
        }}
        onDoubleClick={(event) => event.stopPropagation()}
      >
        {data.outside}
      </button>
      <Handle
        id="t"
        type="source"
        position={handlePosition(data.handleSide)}
        isConnectable={false}
        className="port-terminal__handle"
      />
    </div>
  );
}

const GHOST_TITLE: Record<TerminalKind, string> = {
  input: "Drag an internal signal input onto + input to expose it as a subsystem input",
  output: "Drag an internal signal output onto + output to expose it as a subsystem output",
  power: "Drag an internal power port or junction onto + power to expose it as a subsystem power port",
};

export function PortGhostNode({ data }: NodeProps<GhostNodeType>) {
  return (
    <div
      className={`port-ghost port-ghost--${data.kind} is-${data.state}`}
      data-testid={`port-ghost-${data.kind}`}
      data-state={data.state}
      data-terminal-ghost={data.kind}
      title={GHOST_TITLE[data.kind]}
    >
      <span className="port-ghost__label" aria-hidden="true">
        + {data.kind}
      </span>
      <Handle
        id="g"
        type="source"
        position={handlePosition(data.handleSide)}
        className="port-ghost__handle"
        data-terminal-ghost={data.kind}
        aria-label={GHOST_TITLE[data.kind]}
      />
    </div>
  );
}
