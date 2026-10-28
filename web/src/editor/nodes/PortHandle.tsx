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
import {
  domainColor,
  multibondStrokes,
  signalColor,
  type PortPosition,
  SIGNAL_ARROW_HALF,
  SIGNAL_ARROW_SIZE,
} from "../geometry";
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
  Planar: "P",
  Spatial: "S",
};

const SIGNAL_TYPE_LABEL: Record<string, string> = {
  Real: "1.25 px, solid",
  Bool: "dashed",
  Int: "dotted",
};

/**
 * The signal glyph is drawn pointing right. Rotate it so an input points into
 * the block and an output points away, whichever edge the connection uses.
 */
function arrowRotation(side: PortPosition["side"], direction: string): number {
  const input = direction === "input";
  switch (side) {
    case "left":
      return input ? 0 : 180;
    case "right":
      return input ? 180 : 0;
    case "top":
      return input ? 90 : 270;
    case "bottom":
      return input ? 270 : 90;
    default:
      return 0;
  }
}

export function PortHandle({ nodeId, port, position, domain, state }: PortHandleProps) {
  const side = position.side;
  const isPower = port.kind === "power";
  const colour = isPower ? domainColor(domain) : signalColor(port.type);
  const direction =
    port.kind === "input" ? "input" : port.kind === "output" ? "output" : "power";
  const vector = port.size.length > 0;
  const generic = isPower && domain === "Generic";
  // A multibond port stays one logical point (plan 7.2): the port glyph shows
  // N parallel ticks for the N strokes, and no second port is created.
  const strokes = isPower ? multibondStrokes(domain) : 1;
  const title = isPower
    ? `${port.name} · power · ${domain}${vector ? ` · ${port.size.join("x")}` : ""}`
    : `${port.name} · ${direction} · ${port.type}${vector ? ` · ${port.size.join("x")}` : ""} · ${SIGNAL_TYPE_LABEL[port.type] ?? ""}`;
  const isSignalInput = !isPower && port.kind === "input";
  const rotation = isPower ? 0 : arrowRotation(side, direction);
  // Place an output arrow outside the block border, with its base on the
  // border and its tip where the outgoing line starts. Inputs are solid dots.
  const outward = SIGNAL_ARROW_HALF;
  const shiftX =
    isPower || isSignalInput
      ? 0
      : side === "left"
        ? -outward
        : side === "right"
          ? outward
          : 0;
  const shiftY =
    isPower || isSignalInput
      ? 0
      : side === "top"
        ? -outward
        : side === "bottom"
          ? outward
          : 0;

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
      data-glyph={isPower ? (strokes > 1 ? "multibond" : "square") : isSignalInput ? "dot" : "arrow"}
      data-strokes={isPower ? strokes : undefined}
      data-arrow-rotation={isPower || isSignalInput ? undefined : rotation}
      title={title}
      aria-label={title}
    >
      {isPower && strokes > 1 ? (
        <span className="port-glyph port-glyph--multibond" aria-hidden="true">
          {Array.from({ length: strokes }, (_, index) => (
            <span key={index} className="port-glyph__tick" />
          ))}
        </span>
      ) : isPower ? (
        <span className="port-glyph port-glyph--power" aria-hidden="true" />
      ) : isSignalInput ? (
        <span className="port-glyph port-glyph--in" aria-hidden="true" />
      ) : (
        <svg
          className="port-glyph port-glyph--signal"
          viewBox="0 0 10 10"
          width={SIGNAL_ARROW_SIZE}
          height={SIGNAL_ARROW_SIZE}
          aria-hidden="true"
          style={{
            transform: `translate(${shiftX}px, ${shiftY}px) rotate(${rotation}deg)`,
          }}
        >
          <path
            d="M1 1 L9 5 L1 9 Z"
            fill="currentColor"
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
