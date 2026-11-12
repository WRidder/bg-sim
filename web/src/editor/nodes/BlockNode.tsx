/**
 * The two custom xyflow node types (plan 7.2/7.3): a block card with its port
 * glyphs and a `0`/`1` junction circle whose bonds attach at the rim.
 *
 * `data-state` on the node root is the assertion hook for the end-to-end
 * tests: it carries the document facts (id, name, ref, position, rotation,
 * flip) so a test can compare the model without scraping styling.
 */

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { useMemo } from "react";

import type { DomainName } from "../../contracts/catalog";
import type { ModelNodeImage, ModelPoint } from "../../contracts/model";
import type { PortDragState } from "../connectionAnalysis";
import { JUNCTION_NODE_SIZE, type NodeLayout, type Side } from "../geometry";
import { BlockIcon, BondLetterText, bondLetterFor, dimDescription } from "../icons";
import { nodeImageFitStyle, nodeImageSrc } from "../nodeImage";
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
  /** A subsystem's `ui.image`, drawn in the card body instead of the icon; null for none. */
  image: ModelNodeImage | null;
  /** Inside a subsystem: internal port name -> the subsystem port(s) exposing it. */
  exposed: Readonly<Record<string, string>>;
  /**
   * An instance of a library subsystem: the definition's name and how many of its
   * pinned values this instance sets itself. Null for every other node.
   */
  linked: { definition: string; changed: number } | null;
}

/** The mark of an instance of a library subsystem: a link, the definition, its own values. */
function LinkBadge({ nodeId, linked }: { nodeId: string; linked: NonNullable<BlockNodeData["linked"]> }) {
  const own =
    linked.changed === 0
      ? "all values as in the library"
      : `${linked.changed} ${linked.changed === 1 ? "value" : "values"} set on this instance`;
  return (
    <span
      className="block-node__link"
      data-testid={`node-link-${nodeId}`}
      data-definition={linked.definition}
      data-changed={linked.changed}
      title={`Instance of the library subsystem ${linked.definition}: ${own}`}
    >
      <svg viewBox="0 0 16 16" width="11" height="11" aria-hidden="true">
        <path
          d="M6.5 9.5l3-3M7 4.5l1-1a2.5 2.5 0 013.5 3.5l-1 1M9 11.5l-1 1A2.5 2.5 0 014.5 9l1-1"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      </svg>
      <span className="block-node__link-name">{linked.definition}</span>
      {linked.changed > 0 ? (
        <span className="block-node__link-changed" data-testid={`node-link-changed-${nodeId}`}>
          {linked.changed}
        </span>
      ) : null}
    </span>
  );
}

export type BlockNodeType = Node<BlockNodeData, "block" | "subsystem">;

export interface JunctionNodeData extends Record<string, unknown> {
  nodeId: string;
  name: string;
  junction: "0" | "1";
  position: ModelPoint;
  /** The subsystem port(s) exposing this junction, or null. */
  exposed: string | null;
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

/**
 * The image of a subsystem card. Only ever an `<img>` with a data: URL: an SVG shown this
 * way cannot run scripts or fetch anything, which inline SVG markup could.
 */
function NodeImage({ nodeId, image }: { nodeId: string; image: ModelNodeImage }) {
  const src = useMemo(() => nodeImageSrc(image), [image]);
  return (
    <div className="block-node__body block-node__body--image">
      <img
        className="block-node__image"
        src={src}
        alt=""
        draggable={false}
        style={nodeImageFitStyle(image.fit)}
        data-testid={`node-image-${nodeId}`}
        data-fit={image.fit}
        data-mime={image.mime}
      />
    </div>
  );
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
        exposed={data.exposed[port.name] ?? null}
      />
    );
  });

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>): void => {
    if (quick.enabled) {
      quick.start(event, data.nodeId);
    }
  };

  if (data.bond) {
    const letter = bondLetterFor(iface.icon, iface.title) ?? { letter: iface.title, dim: null };
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
          data-glyph-length={letter.letter.length}
          data-dim={letter.dim ?? undefined}
          role={letter.dim === null ? undefined : "img"}
          aria-label={letter.dim === null ? undefined : iface.title}
          aria-description={letter.dim === null ? undefined : dimDescription(letter.dim)}
        >
          <BondLetterText letter={letter.letter} dim={letter.dim} />
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
          <BlockIcon icon={iface.icon} name={iface.title} size={44} />
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
      {data.image !== null ? (
        <NodeImage nodeId={data.nodeId} image={data.image} />
      ) : (
        <div
          className="block-node__body"
          style={{
            transform: `rotate(${data.rotation}deg) scaleX(${data.flipX ? -1 : 1})`,
          }}
        >
          <BlockIcon icon={iface.icon} name={iface.title} size={38} />
        </div>
      )}
      {data.linked !== null ? <LinkBadge nodeId={data.nodeId} linked={data.linked} /> : null}
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
      className={`junction-node${selected ? " is-selected" : ""}${data.exposed !== null ? " is-exposed" : ""}`}
      style={{ width: JUNCTION_NODE_SIZE, height: JUNCTION_NODE_SIZE }}
      data-testid="diagram-node"
      data-node-id={data.nodeId}
      data-node-name={data.name}
      data-node-junction={data.junction}
      data-state={state}
      data-exposed={data.exposed ?? undefined}
      title={`${data.junction} junction (${data.name})${data.exposed !== null ? ` · exposed as ${data.exposed}` : ""}`}
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
