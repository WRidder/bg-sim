import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { COMPACT_NODE_SIZE } from "../editor/geometry";
import { ProbeGlyph } from "./ProbeGlyph";
import "./probe.css";

export interface ProbeNodeData extends Record<string, unknown> {
  probeId: string;
  name: string;
  linkCount: number;
}

export type ProbeNodeType = Node<ProbeNodeData, "probe">;

/** The 3x3 probe block. Its right-hand handle starts a probe lead drag. */
export function ProbeNode({ data, selected }: NodeProps<ProbeNodeType>) {
  return (
    <div
      className={`block-node is-compact probe-node${selected ? " is-selected" : ""}`}
      style={{ width: COMPACT_NODE_SIZE, height: COMPACT_NODE_SIZE }}
      data-testid="probe-node"
      data-probe-id={data.probeId}
      data-node-name={data.name}
      title={`${data.name} (oscilloscope probe, ${data.linkCount} lead${data.linkCount === 1 ? "" : "s"})`}
    >
      <div className="block-node__body">
        <ProbeGlyph size={44} />
      </div>
      <span className="block-node__label block-node__label--bottom">{data.name}</span>
      <Handle
        id="probe"
        type="source"
        position={Position.Right}
        className="probe-handle"
        aria-label={`Drag a probe lead from ${data.name}`}
      />
    </div>
  );
}
