/**
 * The two custom xyflow node types (plan 7.2/7.3): a block card with its port
 * glyphs and a `0`/`1` junction circle whose bonds attach at the rim.
 *
 * `data-state` on the node root is the assertion hook for the end-to-end
 * tests: it carries the document facts (id, name, ref, position, rotation,
 * flip) so a test can compare the model without scraping styling.
 */

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import type { DomainName } from "../../contracts/catalog";
import type { ModelPoint } from "../../contracts/model";
import type { PortDragState } from "../connectionAnalysis";
import { JUNCTION_NODE_SIZE, type NodeLayout, type Side } from "../geometry";
import { BlockIcon } from "../icons";
import type { NodeInterface } from "../nodeInterface";
import { useQuickConnect } from "../quickConnect";
import { PortHandle } from "./PortHandle";

export interface BlockNodeData extends Record<string, unknown> {
  nodeId: string;
  name: string;
  interface: NodeInterface;
  layout: NodeLayout;
  position: ModelPoint;
  rotation: number;
  flipX: boolean;
  portStates: Record<string, PortDragState>;
  portDomains: Record<string, DomainName>;
  /** A bond-graph element draws as its letter, without a card. */
  bond: boolean;
  /** A normal library block draws as a square icon with an outside label. */
  compact: boolean;
  /** Which side of the element the instance name hangs on. */
  labelSide: Side;
}

export type BlockNodeType = Node<BlockNodeData, "block" | "subsystem">;

export interface JunctionNodeData extends Record<string, unknown> {
  nodeId: string;
  name: string;
  junction: "0" | "1";
  position: ModelPoint;
}

export type JunctionNodeType = Node<JunctionNodeData, "junction">;

export function nodeState(
  nodeId: string,
  name: string,
  ref: string | null,
  junction: "0" | "1" | null,
  position: ModelPoint,
  rotation: number,
  flipX: boolean,
): string {
  return JSON.stringify({
    id: nodeId,
    name,
    ref,
    junction,
    x: position.x,
    y: position.y,
    rotation,
    flipX,
  });
}

export function BlockNode({ data, selected }: NodeProps<BlockNodeType>) {
  const { interface: iface, layout } = data;
  const quick = useQuickConnect();
  const state = nodeState(
    data.nodeId,
    data.name,
    iface.ref,
    null,
    data.position,
    data.rotation,
    data.flipX,
  );

  const portHandles = iface.ports.map((port) => {
    const position = layout.ports.get(port.name);
    if (position === undefined) {
      return null;
    }
    return (
      <PortHandle
        key={port.name}
        nodeId={data.nodeId}
        port={port}
        position={position}
        domain={data.portDomains[port.name] ?? port.domain}
        state={data.portStates[port.name] ?? "idle"}
      />
    );
  });

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>): void => {
    if (quick.enabled) {
      quick.start(event, data.nodeId);
    }
  };

  if (data.bond) {
    return (
      <div
        className={`bond-node${selected ? " is-selected" : ""}`}
        style={{ width: layout.width, height: layout.height }}
        data-testid="diagram-node"
        data-node-id={data.nodeId}
        data-node-name={data.name}
        data-node-ref={iface.ref ?? ""}
        data-node-bond="true"
        data-label-side={data.labelSide}
        data-state={state}
        title={`${data.name} (${iface.title})`}
        onPointerDown={onPointerDown}
      >
        <span
          className="bond-node__glyph bond-letter"
          data-icon={iface.icon}
          data-glyph-length={iface.title.length}
        >
          {iface.title}
        </span>
        <span
          className={`bond-node__label bond-node__label--${data.labelSide}`}
          data-testid={`node-label-${data.nodeId}`}
        >
          {data.name}
        </span>
        {portHandles}
      </div>
    );
  }

  if (data.compact) {
    return (
      <div
        className={`block-node is-compact${selected ? " is-selected" : ""}`}
        style={{ width: layout.width, height: layout.height }}
        data-testid="diagram-node"
        data-node-id={data.nodeId}
        data-node-name={data.name}
        data-node-ref={iface.ref ?? ""}
        data-node-compact="true"
        data-label-side={data.labelSide}
        data-state={state}
        title={`${data.name} (${iface.title})`}
        onPointerDown={onPointerDown}
      >
        <div
          className="block-node__body"
          style={{
            transform: `rotate(${data.rotation}deg) scaleX(${data.flipX ? -1 : 1})`,
          }}
        >
          <BlockIcon icon={iface.icon} name={iface.title} size={36} />
        </div>
        <span
          className={`block-node__label block-node__label--${data.labelSide}`}
          data-testid={`node-label-${data.nodeId}`}
        >
          {data.name}
        </span>
        {portHandles}
      </div>
    );
  }

  return (
    <div
      className={`block-node${selected ? " is-selected" : ""}`}
      style={{ width: layout.width, height: layout.height }}
      data-testid="diagram-node"
      data-node-id={data.nodeId}
      data-node-name={data.name}
      data-node-ref={iface.ref ?? ""}
      data-state={state}
      title={`${data.name} (${iface.title})`}
      onPointerDown={onPointerDown}
    >
      <div className="block-node__header">
        <span className="block-node__name">{data.name}</span>
        <span className="block-node__kind">{iface.title}</span>
      </div>
      <div
        className="block-node__body"
        style={{
          transform: `rotate(${data.rotation}deg) scaleX(${data.flipX ? -1 : 1})`,
        }}
      >
        <BlockIcon icon={iface.icon} name={iface.title} size={38} />
      </div>
      {portHandles}
    </div>
  );
}

const JUNCTION_HANDLES: readonly {
  id: string;
  position: Position;
}[] = [
  { id: "j-left", position: Position.Left },
  { id: "j-right", position: Position.Right },
  { id: "j-top", position: Position.Top },
  { id: "j-bottom", position: Position.Bottom },
];

export function JunctionNode({ data, selected }: NodeProps<JunctionNodeType>) {
  const quick = useQuickConnect();
  const state = nodeState(data.nodeId, data.name, null, data.junction, data.position, 0, false);
  return (
    <div
      className={`junction-node${selected ? " is-selected" : ""}`}
      style={{ width: JUNCTION_NODE_SIZE, height: JUNCTION_NODE_SIZE }}
      data-testid="diagram-node"
      data-node-id={data.nodeId}
      data-node-name={data.name}
      data-node-junction={data.junction}
      data-state={state}
      title={`${data.junction} junction (${data.name})`}
      onPointerDown={(event) => {
        if (quick.enabled) {
          quick.start(event, data.nodeId);
        }
      }}
    >
      <span className="junction-node__label">{data.junction}</span>
      {JUNCTION_HANDLES.map((handle) => (
        <Handle
          key={handle.id}
          id={handle.id}
          type="source"
          position={handle.position}
          className="junction-handle"
          data-testid={`port-${data.nodeId}-${handle.id}`}
          data-node-id={data.nodeId}
          data-port=""
          data-kind="power"
          data-domain="Generic"
          data-state="idle"
        />
      ))}
    </div>
  );
}
