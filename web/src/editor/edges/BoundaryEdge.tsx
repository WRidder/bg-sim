/**
 * The dashed boundary wire from a subsystem port terminal to the internal
 * port it maps to. It is drawn, not a model connection: it cannot be
 * selected, reconnected or deleted.
 *
 * Its end mark follows the direction: a signal input's arrowhead points into
 * the internal port, a signal output's into the terminal; a power wire
 * carries the bond half arrow at the internal port (positive power flows
 * into the subsystem).
 */

import type { Edge, EdgeProps } from "@xyflow/react";

import { arrowHeadPath, halfArrowPath, offsetPoint, orthogonalPath, type Anchor } from "../geometry";
import type { TerminalKind } from "../subsystemPorts";

export interface BoundaryEdgeData extends Record<string, unknown> {
  portName: string;
  terminalKind: TerminalKind;
  colour: string;
  /** The terminal end. */
  terminal: Anchor;
  /** The internal port end. */
  internal: Anchor;
}

export type BoundaryEdgeType = Edge<BoundaryEdgeData, "boundary">;

/** How far back from the tip a mark takes its direction (the last wire segment). */
const MARK_RUN = 14;

export interface BoundaryMark {
  /** `arrow`: a filled signal arrowhead; `half-arrow`: the bond's power half arrow. */
  kind: "arrow" | "half-arrow";
  /** Which end it sits on. */
  at: "terminal" | "internal";
  d: string;
}

/** The direction mark at one end of a boundary wire. */
export function boundaryMark(
  kind: TerminalKind,
  terminal: Anchor,
  internal: Anchor,
): BoundaryMark {
  // The orthogonal wire meets each end along that end's side, so a point
  // MARK_RUN out from the tip on that side lies on the last segment.
  switch (kind) {
    case "input":
      return {
        kind: "arrow",
        at: "internal",
        d: arrowHeadPath(offsetPoint(internal.point, internal.side, MARK_RUN), internal.point),
      };
    case "output":
      return {
        kind: "arrow",
        at: "terminal",
        d: arrowHeadPath(offsetPoint(terminal.point, terminal.side, MARK_RUN), terminal.point),
      };
    case "power":
    default:
      return {
        kind: "half-arrow",
        at: "internal",
        d: halfArrowPath(offsetPoint(internal.point, internal.side, MARK_RUN), internal.point),
      };
  }
}

export function BoundaryEdge({ data }: EdgeProps<BoundaryEdgeType>) {
  if (data === undefined) {
    return null;
  }
  const path = orthogonalPath(data.terminal, data.internal);
  const mark = boundaryMark(data.terminalKind, data.terminal, data.internal);
  return (
    <g
      className="editor-edge editor-edge--boundary"
      data-testid={`boundary-wire-${data.portName}`}
      data-kind={data.terminalKind}
    >
      <path
        className="editor-edge__boundary"
        d={path}
        fill="none"
        stroke={data.colour}
        strokeWidth={1.4}
        strokeDasharray="5 4"
        pointerEvents="none"
      />
      {mark.kind === "arrow" ? (
        <path
          className="editor-edge__boundary-arrow"
          data-testid={`boundary-mark-${data.portName}`}
          data-mark={mark.kind}
          data-mark-at={mark.at}
          d={mark.d}
          fill={data.colour}
          stroke="none"
          pointerEvents="none"
        />
      ) : (
        <path
          className="editor-edge__boundary-half-arrow"
          data-testid={`boundary-mark-${data.portName}`}
          data-mark={mark.kind}
          data-mark-at={mark.at}
          d={mark.d}
          fill="none"
          stroke={data.colour}
          strokeWidth={1.8}
          strokeLinecap="round"
          pointerEvents="none"
        />
      )}
    </g>
  );
}
