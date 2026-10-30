/**
 * The dashed boundary wire from a subsystem port terminal to the internal
 * port it maps to. It is drawn, not a model connection: it cannot be
 * selected, reconnected or deleted.
 */

import type { Edge, EdgeProps } from "@xyflow/react";

import { orthogonalPath, type Anchor } from "../geometry";
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

export function BoundaryEdge({ data }: EdgeProps<BoundaryEdgeType>) {
  if (data === undefined) {
    return null;
  }
  const path = orthogonalPath(data.terminal, data.internal);
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
      <circle
        cx={data.terminal.point.x}
        cy={data.terminal.point.y}
        r={2.4}
        fill={data.colour}
        pointerEvents="none"
      />
    </g>
  );
}
