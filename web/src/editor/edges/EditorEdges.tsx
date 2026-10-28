/**
 * Custom edge renderers for the three connection kinds of plan 5.5:
 *
 * * **bond** — straight/polyline with the half arrow at `to`, the adopted
 *   domain colour and an optional causal stroke;
 * * **wire** — orthogonal, one dot at the shared node when 3+ ports join;
 * * **signal** — orthogonal with an arrowhead, ink 1.25 px, dashed for Bool,
 *   dotted for Int, and an optional unit-factor badge.
 */

import { BaseEdge, EdgeLabelRenderer, useReactFlow, type Edge, type EdgeProps } from "@xyflow/react";
import {
  useRef,
  useState,
  useSyncExternalStore,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

import type { DomainName, ValueType } from "../../contracts/catalog";
import type { ConnectionKind } from "../../contracts/model";
import { useDocumentStore } from "../../state/documentStore";
import {
  arrowHeadPath,
  bundleCausalBar,
  domainColor,
  halfArrowPath,
  hubPath,
  midpoint,
  offsetPoint,
  offsetPolyline,
  orthogonalPath,
  cornerAngleMarker,
  multibondBundleHalf,
  multibondComponents,
  multibondOffsets,
  multibondPath,
  multibondStrokes,
  rightAngleMarker,
  routedPath,
  signalColor,
  signalDash,
  SIGNAL_ARROW_SIZE,
  SIGNAL_DOT_RADIUS,
  snapRouteVertex,
  MULTIBOND_ARROW_SIZE,
  MULTIBOND_STROKE_WIDTH,
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
  /** The instance-qualified reference frame of the bond's ports, if named. */
  frame: string | null;
  /** Endpoint port names the node no longer exposes (plan 7.7, E101). */
  missingPorts: string[];
  /** Whether routing vertices follow the canvas snap preference. */
  snap: boolean;
}

export type EditorEdgeType = "bond" | "wire" | "signal";
export type EditorEdge = Edge<EditorEdgeData, EditorEdgeType>;

/**
 * The route vertex under the pointer, kept outside React because the flow
 * renderer remounts an edge whenever its doc data changes. Component state
 * would reset on the first pointer move and the corner marker would vanish.
 */
let draggedVertex: { edgeId: string; index: number } | null = null;
const draggedVertexListeners = new Set<() => void>();

function setDraggedVertex(next: { edgeId: string; index: number } | null): void {
  draggedVertex = next;
  for (const listener of draggedVertexListeners) {
    listener();
  }
}

function draggedVertexOf(edgeId: string): number | null {
  return draggedVertex !== null && draggedVertex.edgeId === edgeId
    ? draggedVertex.index
    : null;
}

function useDraggedVertex(edgeId: string): number | null {
  return useSyncExternalStore(
    (listener) => {
      draggedVertexListeners.add(listener);
      return () => {
        draggedVertexListeners.delete(listener);
      };
    },
    () => draggedVertexOf(edgeId),
  );
}

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

/** How far above the label chip the frame pill sits, so the two never overlap. */
export const FRAME_BADGE_OFFSET = 26;

/** Where the frame pill would sit: above the bond's label, on the centre line. */
export function frameBadgePosition(data: EditorEdgeData): Point {
  const point = labelPosition(data);
  return { x: point.x, y: point.y - FRAME_BADGE_OFFSET };
}

/**
 * Hover state of one edge. The frame badge is shown on hover or selection
 * (plan 7.2); pointer handlers go on the edge group, whose transparent hit
 * path the pointer actually crosses.
 */
function useEdgeHover(): {
  hovered: boolean;
  hoverProps: {
    onMouseEnter: () => void;
    onMouseLeave: () => void;
  };
} {
  const [hovered, setHovered] = useState(false);
  return {
    hovered,
    hoverProps: {
      onMouseEnter: () => {
        setHovered(true);
      },
      onMouseLeave: () => {
        setHovered(false);
      },
    },
  };
}

/**
 * The `frame: <name>` pill of a bond that carries frame metadata (plan 7.2,
 * D-MB5). It is rendered in the edge label layer above the instance label and
 * the unit badge, and it is text, not colour, so it does not rely on the theme.
 */
function FrameBadge({
  id,
  data,
  visible,
}: {
  id: string;
  data: EditorEdgeData;
  visible: boolean;
}) {
  if (!visible || data.frame === null) {
    return null;
  }
  const point = frameBadgePosition(data);
  return (
    <EdgeLabelRenderer>
      <div
        className="editor-edge__frame"
        data-testid={`frame-badge-${id}`}
        data-frame={data.frame}
        style={{
          transform: `translate(-50%, -50%) translate(${point.x}px, ${point.y}px)`,
        }}
        title={`Reference frame ${data.frame}`}
      >
        frame: {data.frame}
      </div>
    </EdgeLabelRenderer>
  );
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

/**
 * Draggable waypoints of a selected connection. Each pointer move writes the
 * snapped position to the document, so the routed line follows the handle
 * immediately; the whole drag coalesces into one undo step. Double-click
 * removes a waypoint. While a vertex is dragged, a square marks a 90 degree
 * corner and an arc with a label marks a 45 or 135 degree corner.
 */
function RouteHandles({
  id,
  route,
  from,
  to,
  selected,
  snap,
}: {
  id: string;
  route: readonly Point[];
  /** The fixed ends of the route; they bound its first and last vertex. */
  from: Point;
  to: Point;
  selected: boolean | undefined;
  snap: boolean;
}) {
  const { screenToFlowPosition } = useReactFlow();
  const routeRef = useRef(route);
  routeRef.current = route;
  const lastClickRef = useRef<{ index: number; time: number } | null>(null);
  /** The vertex the pointer is moving, so its corner can show the marker. */
  const dragging = useDraggedVertex(id);
  if (!selected || route.length === 0) {
    return null;
  }
  const before =
    dragging === null ? undefined : dragging > 0 ? route[dragging - 1] : from;
  const corner = dragging === null ? undefined : route[dragging];
  const after =
    dragging === null ? undefined : dragging < route.length - 1 ? route[dragging + 1] : to;
  const hasCorner = before !== undefined && corner !== undefined && after !== undefined;
  const rightAngle = hasCorner ? rightAngleMarker(before, corner, after) : null;
  const cornerAngle = hasCorner ? cornerAngleMarker(before, corner, after) : null;
  const commit = (index: number, raw: Point): void => {
    const point = snap ? snapRouteVertex(raw) : raw;
    const next = routeRef.current.map((entry, entryIndex) =>
      entryIndex === index ? point : entry,
    );
    useDocumentStore.getState().setConnectionRoute(id, next);
  };
  const remove = (index: number): void => {
    lastClickRef.current = null;
    const next = routeRef.current.filter((_, entryIndex) => entryIndex !== index);
    useDocumentStore.getState().setConnectionRoute(id, next);
  };
  /** A double-click removes the vertex; detect it ourselves because pointer
   * capture on the small SVG target can swallow the native dblclick. */
  const clickVertex = (event: ReactMouseEvent<SVGCircleElement>, index: number): void => {
    event.stopPropagation();
    const now = Date.now();
    const previous = lastClickRef.current;
    if (previous !== null && previous.index === index && now - previous.time < 400) {
      remove(index);
      return;
    }
    lastClickRef.current = { index, time: now };
  };
  const startDrag = (event: ReactPointerEvent<SVGCircleElement>, index: number): void => {
    event.stopPropagation();
    useDocumentStore.getState().beginGesture("route-drag");
    let moved = false;
    const cleanup = (): void => {
      window.removeEventListener("pointermove", move, true);
      window.removeEventListener("pointerup", finish, true);
      window.removeEventListener("pointercancel", cancel, true);
      setDraggedVertex(null);
    };
    const move = (moveEvent: PointerEvent): void => {
      if (!moved) {
        moved = true;
        setDraggedVertex({ edgeId: id, index });
      }
      commit(
        index,
        screenToFlowPosition(
          {
            x: moveEvent.clientX,
            y: moveEvent.clientY,
          },
          { snapToGrid: false },
        ),
      );
    };
    const finish = (upEvent: PointerEvent): void => {
      cleanup();
      if (moved) {
        lastClickRef.current = null;
        commit(
          index,
          screenToFlowPosition(
            {
              x: upEvent.clientX,
              y: upEvent.clientY,
            },
            { snapToGrid: false },
          ),
        );
      }
      useDocumentStore.getState().endGesture();
    };
    const cancel = (): void => {
      cleanup();
      useDocumentStore.getState().endGesture();
    };
    window.addEventListener("pointermove", move, true);
    window.addEventListener("pointerup", finish, true);
    window.addEventListener("pointercancel", cancel, true);
  };
  return (
    <g className="editor-edge__vertices" data-testid={`connection-vertices-${id}`}>
      {rightAngle !== null ? (
        <path
          className="editor-edge__right-angle"
          data-testid={`connection-right-angle-${id}`}
          d={rightAngle}
        />
      ) : null}
      {cornerAngle !== null ? (
        <g
          className="editor-edge__angle"
          data-testid={`connection-angle-${cornerAngle.angle}-${id}`}
          data-angle={cornerAngle.angle}
        >
          <path className="editor-edge__angle-arc" d={cornerAngle.arc} />
          <text
            className="editor-edge__angle-label"
            x={cornerAngle.label.x}
            y={cornerAngle.label.y}
          >
            {cornerAngle.text}
          </text>
        </g>
      ) : null}
      {route.map((point, index) => (
        <g key={`${id}-vertex-${index}`}>
          <circle
            cx={point.x}
            cy={point.y}
            r={10}
            className="editor-edge__vertex-hit"
            data-testid={`connection-vertex-${id}-${index}`}
            onPointerDown={(event) => startDrag(event, index)}
            onClick={(event) => clickVertex(event, index)}
          >
            <title>Drag to route; double-click to remove</title>
          </circle>
          <circle cx={point.x} cy={point.y} r={4.5} className="editor-edge__vertex" />
        </g>
      ))}
    </g>
  );
}

/**
 * A multibond bond (plan 7.1/7.2, D-MB12): two parallel strokes for Planar,
 * three for Spatial, one half arrow per stroke at the `to` end, **one** causal
 * bar across the bundle, one selection halo around the centre path and one
 * frame pill above the label.
 */
export function MultiBond({
  id,
  data,
  selected,
}: {
  id: string;
  data: EditorEdgeData;
  selected: boolean | undefined;
}) {
  const { hovered, hoverProps } = useEdgeHover();
  const { a, b } = anchors(data);
  const route = data.route;
  const points: Point[] = [a.point, ...route, b.point];
  const strokes = multibondStrokes(data.domain);
  const offsets = multibondOffsets(strokes);
  const colour = domainColor(data.domain);
  const broken = data.missingPorts.length > 0;
  const bundleHalf = multibondBundleHalf(strokes);
  const centrePath = multibondPath(points, 0);
  const strokeAt = data.causalStroke;
  const barFrom =
    strokeAt === "to"
      ? route.length > 0
        ? route[route.length - 1] ?? a.point
        : a.point
      : route.length > 0
        ? route[0] ?? b.point
        : b.point;
  const barTo = strokeAt === "to" ? b.point : a.point;
  const bar = strokeAt === null ? null : bundleCausalBar(barFrom, barTo, bundleHalf);
  const ariaLabel = `${data.domain} multibond, ${multibondComponents(data.domain)} components, ${strokes} strokes`;

  return (
    <g
      className={`editor-edge editor-edge--bond editor-edge--multibond${selected ? " is-selected" : ""}${broken ? " is-port-missing" : ""}`}
      data-testid={`edge-${id}`}
      data-kind="bond"
      data-domain={data.domain}
      data-bgsim-client-domain={data.baseDomain}
      data-port-missing={data.missingPorts.join(",")}
      data-multibond-strokes={String(strokes)}
      role="group"
      aria-label={ariaLabel}
      {...hoverProps}
    >
      {selected ? <Halo path={centrePath} /> : null}
      {broken ? (
        <MissingPorts
          id={id}
          path={centrePath}
          names={data.missingPorts}
          point={midpoint(a.point, b.point)}
        />
      ) : null}
      {/* The visible strokes carry the colour; BaseEdge supplies only the hit area. */}
      <BaseEdge
        id={id}
        path={centrePath}
        interactionWidth={18 + 2 * bundleHalf}
        style={{
          stroke: "transparent",
          strokeWidth: MULTIBOND_STROKE_WIDTH,
          fill: "none",
        }}
      />
      {offsets.map((offset, index) => {
        const offsetPoints = offsetPolyline(points, offset);
        const tip = offsetPoints[offsetPoints.length - 1] ?? b.point;
        const from = offsetPoints[offsetPoints.length - 2] ?? a.point;
        return (
          <g key={`${id}-stroke-${index}`} className="editor-edge__multibond">
            <path
              className="editor-edge__multibond-stroke"
              data-stroke-index={index}
              data-offset={offset}
              d={multibondPath(points, offset)}
              stroke={colour}
              strokeWidth={MULTIBOND_STROKE_WIDTH}
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              className="editor-edge__half-arrow editor-edge__multibond-arrow"
              data-stroke-index={index}
              d={halfArrowPath(from, tip, MULTIBOND_ARROW_SIZE)}
              stroke={colour}
              strokeWidth={MULTIBOND_STROKE_WIDTH}
              fill="none"
              strokeLinecap="round"
            />
          </g>
        );
      })}
      {bar !== null ? (
        <line
          className="editor-edge__causal editor-edge__causal--bundle"
          data-testid={`causal-stroke-${id}`}
          data-stroke-at={strokeAt}
          x1={bar.x1}
          y1={bar.y1}
          x2={bar.x2}
          y2={bar.y2}
          stroke={colour}
          strokeWidth={2.6}
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      ) : null}
      <EdgeLabel id={id} data={data} />
      <FrameBadge id={id} data={data} visible={hovered || selected === true} />
      <RouteHandles
        id={id}
        route={route}
        from={a.point}
        to={b.point}
        selected={selected}
        snap={data.snap}
      />
    </g>
  );
}

function BondEdgeBody({
  id,
  data,
  selected,
}: {
  id: string;
  data: EditorEdgeData;
  selected: boolean | undefined;
}) {
  const { hovered, hoverProps } = useEdgeHover();
  const { a, b } = anchors(data);
  const route = data.route;
  const path =
    route.length > 0
      ? routedPath(a.point, route, b.point)
      : `M ${a.point.x} ${a.point.y} L ${b.point.x} ${b.point.y}`;
  const tail = route.length > 0 ? route[route.length - 1] ?? a.point : a.point;
  const colour = domainColor(data.domain);
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
      {...hoverProps}
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
      <FrameBadge id={id} data={data} visible={hovered || selected === true} />
      <RouteHandles
        id={id}
        route={route}
        from={a.point}
        to={b.point}
        selected={selected}
        snap={data.snap}
      />
    </g>
  );
}

/**
 * A power bond: one stroke for a scalar domain, a `MultiBond` bundle for a
 * Planar or Spatial domain (plan 7.1). The scalar rendering is unchanged.
 */
export function BondEdge({ id, data, selected }: EdgeProps<EditorEdge>) {
  if (data === undefined) {
    return null;
  }
  if (multibondStrokes(data.domain) > 1) {
    return <MultiBond id={id} data={data} selected={selected} />;
  }
  return <BondEdgeBody id={id} data={data} selected={selected} />;
}

export function WireEdge({ id, data, selected }: EdgeProps<EditorEdge>) {
  if (data === undefined) {
    return null;
  }
  const { a, b } = anchors(data);
  const hub = data.wireHub;
  const path =
    data.route.length > 0
      ? routedPath(a.point, data.route, b.point)
      : hub === null
        ? orthogonalPath(a, b)
        : hubPath(a.point, hub, b.point);
  const colour = domainColor(data.domain);
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
      <RouteHandles
        id={id}
        route={data.route}
        from={a.point}
        to={b.point}
        selected={selected}
        snap={data.snap}
      />
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
      <RouteHandles
        id={id}
        route={data.route}
        from={start}
        to={tip}
        selected={selected}
        snap={data.snap}
      />
    </g>
  );
}
