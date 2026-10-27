/**
 * Custom edge renderers for the three connection kinds of plan 5.5:
 *
 * * **bond** — straight/polyline with the half arrow at `to`, the adopted
 *   domain colour and an optional causal stroke;
 * * **wire** — orthogonal, one dot at the shared node when 3+ ports join;
 * * **signal** — orthogonal with an arrowhead, ink 1.25 px, dashed for Bool,
 *   dotted for Int, and an optional unit-factor badge.
 */

import { BaseEdge, EdgeLabelRenderer, type Edge, type EdgeProps } from "@xyflow/react";

import type { DomainName, ValueType } from "../../contracts/catalog";
import type { ConnectionKind } from "../../contracts/model";
import {
  arrowHeadPath,
  domainColor,
  halfArrowPath,
  hubPath,
  midpoint,
  offsetPoint,
  orthogonalPath,
  routedPath,
  signalColor,
  signalDash,
  SIGNAL_ARROW_SIZE,
  SIGNAL_DOT_RADIUS,
  type Anchor,
  type Point,
  type Side,
} from "../geometry";
import { causalStrokeBar } from "./causalStroke";
import "./edges.css";

export interface EditorEdgeData extends Record<string, unknown> {
  kind: ConnectionKind;
  domain: DomainName;
  /** The client analysis before a worker check overrides `domain`. */
  baseDomain: DomainName;
  signalType: ValueType | null;
  route: Point[];
  sourceAnchor: { point: Point; side: Side };
  targetAnchor: { point: Point; side: Side };
  wireHub: Point | null;
  label: string | null;
  unitFactor: string | null;
  /** Where the causal stroke sits, when a model check provides it. */
  causalStroke: "from" | "to" | null;
  /** Endpoint port names the node no longer exposes (plan 7.7, E101). */
  missingPorts: string[];
}

export type EditorEdgeType = "bond" | "wire" | "signal";
export type EditorEdge = Edge<EditorEdgeData, EditorEdgeType>;

function anchors(data: EditorEdgeData): { a: Anchor; b: Anchor } {
  return { a: data.sourceAnchor, b: data.targetAnchor };
}

function labelPosition(data: EditorEdgeData): Point {
  const { a, b } = anchors(data);
  if (data.wireHub !== null) {
    return data.wireHub;
  }
  const middle = midpoint(a.point, b.point);
  return { x: middle.x, y: middle.y - 10 };
}

function EdgeLabel({ id, data }: { id: string; data: EditorEdgeData }) {
  const point = labelPosition(data);
  const badge =
    data.unitFactor === null
      ? null
      : data.unitFactor.startsWith("\u00d7")
        ? data.unitFactor
        : `\u00d7${data.unitFactor}`;
  if (data.label === null && badge === null) {
    return null;
  }
  return (
    <EdgeLabelRenderer>
      <div
        className="editor-edge__label"
        style={{
          transform: `translate(-50%, -50%) translate(${point.x}px, ${point.y}px)`,
        }}
      >
        {data.label !== null ? <span>{data.label}</span> : null}
        {badge !== null ? (
          <span
            className="editor-edge__factor"
            data-testid={`unit-badge-${id}`}
            title={`Unit conversion ${badge}; the compiler scales this signal`}
          >
            {badge}
          </span>
        ) : null}
      </div>
    </EdgeLabelRenderer>
  );
}

function Halo({ path }: { path: string }) {
  return <path className="editor-edge__halo" d={path} />;
}

/**
 * A connection whose endpoint port disappeared from an inline block's
 * interface. It turns red immediately, before the next `model.check` reports
 * E101, and names the missing port on hover.
 */
function MissingPorts({
  id,
  path,
  names,
  point,
}: {
  id: string;
  path: string;
  names: string[];
  point: Point;
}) {
  return (
    <>
      <path className="editor-edge__missing" d={path} />
      <EdgeLabelRenderer>
        <div
          className="editor-edge__missing-label"
          data-testid={`edge-missing-${id}`}
          style={{ transform: `translate(-50%, -50%) translate(${point.x}px, ${point.y - 14}px)` }}
          title={`Port ${names.map((name) => `\`${name}\``).join(", ")} no longer exists in the block source`}
        >
          missing {names.join(", ")}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

export function BondEdge({ id, data, selected }: EdgeProps<EditorEdge>) {
  if (data === undefined) {
    return null;
  }
  const { a, b } = anchors(data);
  const route = data.route;
  const path =
    route.length > 0
      ? routedPath(a.point, route, b.point)
      : `M ${a.point.x} ${a.point.y} L ${b.point.x} ${b.point.y}`;
  const tail = route.length > 0 ? route[route.length - 1] ?? a.point : a.point;
  const colour = domainColor(data.domain);
  const dashed = data.domain === "Generic";
  const broken = data.missingPorts.length > 0;
  const causalBar = causalStrokeBar(a.point, b.point, data.causalStroke);

  return (
    <g
      className={`editor-edge editor-edge--bond${selected ? " is-selected" : ""}${broken ? " is-port-missing" : ""}`}
      data-testid={`edge-${id}`}
      data-kind="bond"
      data-domain={data.domain}
      data-bgsim-client-domain={data.baseDomain}
      data-port-missing={data.missingPorts.join(",")}
    >
      {selected ? <Halo path={path} /> : null}
      {broken ? <MissingPorts id={id} path={path} names={data.missingPorts} point={midpoint(a.point, b.point)} /> : null}
      <BaseEdge
        id={id}
        path={path}
        interactionWidth={18}
        style={{
          stroke: colour,
          strokeWidth: 2.2,
          strokeDasharray: dashed ? "4 3" : undefined,
          fill: "none",
        }}
      />
      <path
        className="editor-edge__half-arrow"
        d={halfArrowPath(tail, b.point)}
        stroke={colour}
        strokeWidth={2.2}
        fill="none"
        strokeLinecap="round"
      />
      {causalBar !== null ? (
        <line
          className="editor-edge__causal"
          data-testid={`causal-stroke-${id}`}
          data-stroke-at={causalBar.strokeAt}
          x1={causalBar.x1}
          y1={causalBar.y1}
          x2={causalBar.x2}
          y2={causalBar.y2}
          stroke={colour}
          strokeWidth={2.6}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      ) : null}
      <EdgeLabel id={id} data={data} />
    </g>
  );
}

export function WireEdge({ id, data, selected }: EdgeProps<EditorEdge>) {
  if (data === undefined) {
    return null;
  }
  const { a, b } = anchors(data);
  const hub = data.wireHub;
  const path =
    hub === null
      ? data.route.length > 0
        ? routedPath(a.point, data.route, b.point)
        : orthogonalPath(a, b)
      : hubPath(a.point, hub, b.point);
  const colour = domainColor(data.domain);
  const dashed = data.domain === "Generic";
  const broken = data.missingPorts.length > 0;

  return (
    <g
      className={`editor-edge editor-edge--wire${selected ? " is-selected" : ""}${broken ? " is-port-missing" : ""}`}
      data-testid={`edge-${id}`}
      data-kind="wire"
      data-domain={data.domain}
      data-bgsim-client-domain={data.baseDomain}
      data-port-missing={data.missingPorts.join(",")}
    >
      {selected ? <Halo path={path} /> : null}
      {broken ? <MissingPorts id={id} path={path} names={data.missingPorts} point={midpoint(a.point, b.point)} /> : null}
      <BaseEdge
        id={id}
        path={path}
        interactionWidth={18}
        style={{
          stroke: colour,
          strokeWidth: 2.2,
          strokeDasharray: dashed ? "4 3" : undefined,
          fill: "none",
        }}
      />
      {hub !== null ? (
        <circle
          className="editor-edge__node-dot"
          cx={hub.x}
          cy={hub.y}
          r={3.6}
          fill={colour}
          stroke="var(--color-surface)"
          strokeWidth={1}
        />
      ) : null}
      <EdgeLabel id={id} data={data} />
    </g>
  );
}

export function SignalEdge({ id, data, selected }: EdgeProps<EditorEdge>) {
  if (data === undefined) {
    return null;
  }
  const { a, b } = anchors(data);
  // A signal edge starts at the tip of the output arrow outside the source
  // block and stops at the outer edge of the solid input dot.
  const start = offsetPoint(a.point, a.side, SIGNAL_ARROW_SIZE);
  const tip = offsetPoint(b.point, b.side, SIGNAL_DOT_RADIUS);
  const startAnchor: Anchor = { ...a, point: start };
  const targetAnchor: Anchor = { ...b, point: tip };
  const path =
    data.route.length > 0
      ? routedPath(start, data.route, tip)
      : orthogonalPath(startAnchor, targetAnchor);
  const colour = signalColor(data.signalType);
  // The filled arrow points into the target and ends on the dot's outer edge.
  const from = offsetPoint(tip, b.side, 14);
  const dash = signalDash(data.signalType);
  const broken = data.missingPorts.length > 0;

  return (
    <g
      className={`editor-edge editor-edge--signal${selected ? " is-selected" : ""}${broken ? " is-port-missing" : ""}`}
      data-testid={`edge-${id}`}
      data-kind="signal"
      data-signal-type={data.signalType ?? ""}
      data-port-missing={data.missingPorts.join(",")}
    >
      {selected ? <Halo path={path} /> : null}
      {broken ? <MissingPorts id={id} path={path} names={data.missingPorts} point={midpoint(a.point, b.point)} /> : null}
      <BaseEdge
        id={id}
        path={path}
        interactionWidth={18}
        style={{
          stroke: colour,
          strokeWidth: "var(--signal-real-width)",
          strokeDasharray: dash,
          fill: "none",
        }}
      />
      <path
        className="editor-edge__arrow"
        d={arrowHeadPath(from, b.point)}
        fill={colour}
        stroke="none"
      />
      <EdgeLabel id={id} data={data} />
    </g>
  );
}
