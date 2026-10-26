/**
 * One port glyph of plan 7.3:
 *
 * * power port — a filled square;
 * * signal input — a hollow triangle pointing in;
 * * signal output — a filled triangle pointing out;
 * * vector ports — a double outline;
 * * Generic / unresolved — grey and dashed;
 * * the domain letter (E/T/R/H/G) appears on hover, so colour is never the
 *   only cue.
 */

import { Handle, Position } from "@xyflow/react";

import type { DomainName } from "../../contracts/catalog";
import type { PortDragState } from "../connectionAnalysis";
import { domainColor, signalColor, type PortPosition } from "../geometry";
import type { PortSpec } from "../nodeInterface";

export interface PortHandleProps {
  nodeId: string;
  port: PortSpec;
  position: PortPosition;
  /** The domain actually drawn (Generic ports adopt their bond island). */
  domain: DomainName;
  state: PortDragState;
}

const DOMAIN_LETTER: Record<DomainName, string> = {
  Electrical: "E",
  Translation: "T",
  Rotation: "R",
  Hydraulic: "H",
  Generic: "G",
};

const SIGNAL_TYPE_LABEL: Record<string, string> = {
  Real: "1.25 px, solid",
  Bool: "dashed",
  Int: "dotted",
};

export function PortHandle({ nodeId, port, position, domain, state }: PortHandleProps) {
  const side = position.side;
  const isPower = port.kind === "power";
  const colour = isPower ? domainColor(domain) : signalColor(port.type);
  const direction =
    port.kind === "input" ? "input" : port.kind === "output" ? "output" : "power";
  const vector = port.size.length > 0;
  const generic = isPower && domain === "Generic";
  const title = isPower
    ? `${port.name} · power · ${domain}${vector ? ` · ${port.size.join("x")}` : ""}`
    : `${port.name} · ${direction} · ${port.type}${vector ? ` · ${port.size.join("x")}` : ""} · ${SIGNAL_TYPE_LABEL[port.type] ?? ""}`;

  const handlePosition =
    side === "left"
      ? Position.Left
      : side === "right"
        ? Position.Right
        : side === "top"
          ? Position.Top
          : Position.Bottom;

  return (
    <Handle
      id={port.name}
      type={port.kind === "input" ? "target" : "source"}
      position={handlePosition}
      className={[
        "port-handle",
        `port-handle--${side}`,
        isPower ? "port-handle--power" : `port-handle--${direction}`,
        generic ? "is-generic" : "",
        vector ? "is-vector" : "",
        port.type === "Bool" ? "is-bool" : "",
        port.type === "Int" ? "is-int" : "",
        `is-${state}`,
      ]
        .filter(Boolean)
        .join(" ")}
      style={
        side === "top" || side === "bottom"
          ? { left: position.x, color: colour }
          : { top: position.y, color: colour }
      }
      data-testid={`port-${nodeId}-${port.name}`}
      data-node-id={nodeId}
      data-port={port.name}
      data-kind={port.kind}
      data-direction={direction}
      data-domain={domain}
      data-type={port.type}
      data-state={state}
      data-side={side}
      title={title}
    >
      {isPower ? (
        <span className="port-glyph port-glyph--power" aria-hidden="true" />
      ) : (
        <svg
          className="port-glyph port-glyph--signal"
          viewBox="0 0 10 10"
          width="11"
          height="11"
          aria-hidden="true"
        >
          <path
            d="M1 1 L9 5 L1 9 Z"
            fill={port.kind === "output" ? "currentColor" : "none"}
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinejoin="round"
          />
        </svg>
      )}
      <span className="port-letter" aria-hidden="true">
        {DOMAIN_LETTER[domain]}
      </span>
      <span className="port-name" aria-hidden="true">
        {port.name}
      </span>
    </Handle>
  );
}
