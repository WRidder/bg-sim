/**
 * Hover values at the cursor (plan 7.3 and 7.5).
 *
 * Hovering a bond or a port opens a small read-out with `e`, `f` and
 * `P = e·f` at the global inspect time. The component listens to pointer moves
 * on the canvas itself and only changes React state when the *target* changes;
 * the tooltip follows the cursor by writing `left/top` directly, so a mouse
 * move never re-renders the canvas.
 *
 * Data comes from the existing run cache (`runDataCache`) and, on a miss, one
 * `/data?ids=…&px=0` request per target (debounced, abortable, then cached).
 * Nothing is fetched per mouse move. With no run, a hint says to run first.
 */

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type RefObject } from "react";

import type { Model, ModelConnection } from "../../contracts/model";
import { useDiagnosticsStore } from "../../diagnostics/store";
import { formatCursorTime } from "../../plot/format";
import { fetchRunData } from "../../plot/runApi";
import { runDataCache } from "../../plot/runCache";
import { useInspectTime, useRunStore } from "../../plot/runStore";
import {
  connectionPowerPort,
  powerHoverRows,
  powerHoverSignalIds,
  powerUnits,
  signalHoverRow,
  signalHoverSignalId,
  signalUnit,
  valueAtNearestSample,
  type HoverRow,
  type HoverVariable,
} from "./hoverValues";
import "./hover.css";

export type HoverTargetKind = "bond" | "wire" | "signal" | "port";

/** What the pointer is over; `key` makes pointer moves cheap to compare. */
export interface HoverTarget {
  key: string;
  kind: HoverTargetKind;
  connectionId: string | null;
  nodeId: string | null;
  port: string | null;
  /** A port from `data-kind="power"` (a signal port otherwise). */
  power: boolean;
}

/**
 * Resolve the hover target from a DOM event target. The important hooks are
 * the same ones the e2e tests use: `edge-<id>`, `data-port`, `data-kind`.
 */
export function hoverTargetFromElement(element: Element | null): HoverTarget | null {
  if (element === null) {
    return null;
  }
  const portElement = element.closest<HTMLElement>("[data-port]");
  if (portElement !== null) {
    const nodeId = portElement.getAttribute("data-node-id");
    const port = portElement.getAttribute("data-port");
    if (nodeId === null || port === null || port.length === 0) {
      return null;
    }
    const power = portElement.getAttribute("data-kind") === "power";
    return {
      key: `port:${nodeId}:${port}`,
      kind: "port",
      connectionId: null,
      nodeId,
      port,
      power,
    };
  }
  const edgeElement = element.closest<Element>('[data-testid^="edge-"]');
  if (edgeElement !== null) {
    const testId = edgeElement.getAttribute("data-testid") ?? "";
    if (!testId.startsWith("edge-")) {
      return null;
    }
    const connectionId = testId.slice("edge-".length);
    const kind = edgeElement.getAttribute("data-kind");
    if (kind !== "bond" && kind !== "wire" && kind !== "signal") {
      return null;
    }
    return {
      key: `${kind}:${connectionId}`,
      kind,
      connectionId,
      nodeId: null,
      port: null,
      power: kind !== "signal",
    };
  }
  return null;
}

interface LoadedHover {
  runId: string;
  label: string;
  kind: "power" | "signal";
  time: Float64Array;
  values: Record<string, Float64Array>;
  /** Power only: the ids of e, f and P in the current run. */
  powerIds: Record<HoverVariable, string> | null;
  units: Partial<Record<HoverVariable | "value", string>>;
}

type ReadoutState =
  | { state: "idle" }
  | { state: "loading"; message: string }
  | { state: "hint"; message: string }
  | { state: "error"; message: string }
  | { state: "ready"; hover: LoadedHover };

export interface HoverReadoutProps {
  canvasRef: RefObject<HTMLElement | null>;
  model: Model | null;
  /** Names of the open subsystem path, e.g. `Bondgraph`. */
  pathPrefix: string;
}

const DEBOUNCE_MS = 120;

function connectionFor(model: Model, id: string | null): ModelConnection | null {
  if (id === null) {
    return null;
  }
  return model.diagram.connections.find((connection) => connection.id === id) ?? null;
}

function signalIdsFor(
  model: Model,
  target: HoverTarget,
  pathPrefix: string,
): { label: string; kind: "power" | "signal"; ids: string[] } | null {
  if (target.kind === "port") {
    const node = model.diagram.nodes.find((entry) => entry.id === target.nodeId);
    if (node === undefined || target.port === null) {
      return null;
    }
    if (target.power) {
      const ids = powerHoverSignalIds(pathPrefix, node.name, target.port);
      return { label: `${node.name}/${target.port}`, kind: "power", ids: [ids.e, ids.f, ids.P] };
    }
    return {
      label: `${node.name}/${target.port}`,
      kind: "signal",
      ids: [signalHoverSignalId(pathPrefix, node.name, target.port)],
    };
  }

  const connection = connectionFor(model, target.connectionId);
  if (connection === null) {
    return null;
  }
  if (connection.kind === "signal") {
    const endpoint =
      connection.from.port !== undefined
        ? { node: connection.from.node, port: connection.from.port }
        : connection.to.port !== undefined
          ? { node: connection.to.node, port: connection.to.port }
          : null;
    if (endpoint === null) {
      return null;
    }
    const node = model.diagram.nodes.find((entry) => entry.id === endpoint.node);
    if (node === undefined) {
      return null;
    }
    return {
      label: `${node.name}/${endpoint.port}`,
      kind: "signal",
      ids: [signalHoverSignalId(pathPrefix, node.name, endpoint.port)],
    };
  }
  const port = connectionPowerPort(model, connection);
  if (port === null) {
    return null;
  }
  const ids = powerHoverSignalIds(pathPrefix, port.path, port.port);
  return {
    label: `${port.path}/${port.port}`,
    kind: "power",
    ids: [ids.e, ids.f, ids.P],
  };
}

function positionAt(element: HTMLElement | null, x: number, y: number): void {
  if (element === null) {
    return;
  }
  const width = element.offsetWidth || 220;
  const height = element.offsetHeight || 90;
  const left = Math.max(4, Math.min(x + 16, window.innerWidth - width - 8));
  const top = Math.max(4, Math.min(y + 16, window.innerHeight - height - 8));
  element.style.left = `${Math.round(left)}px`;
  element.style.top = `${Math.round(top)}px`;
}

/** The hover tooltip; mount once inside the canvas. */
export function HoverReadout({ canvasRef, model, pathPrefix }: HoverReadoutProps) {
  const runId = useRunStore((state) => state.runId);
  const manifest = useRunStore((state) => state.manifest);
  const status = useRunStore((state) => state.status);
  const inspectTime = useInspectTime();
  const hasInspectTime = inspectTime !== null;
  const checkSignals = useDiagnosticsStore((state) => state.signals);
  const [target, setTarget] = useState<HoverTarget | null>(null);
  const [readout, setReadout] = useState<ReadoutState>({ state: "idle" });
  const tooltipRef = useRef<HTMLDivElement>(null);
  const pointRef = useRef({ x: 0, y: 0 });
  const pointerInside = useRef(false);

  // Pointer plumbing: one listener on the canvas, no per-move React state.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas === null) {
      return;
    }
    const onMove = (event: PointerEvent): void => {
      pointerInside.current = true;
      pointRef.current = { x: event.clientX, y: event.clientY };
      const next = hoverTargetFromElement(event.target as Element | null);
      setTarget((current) => (current?.key === next?.key ? current : next));
      positionAt(tooltipRef.current, event.clientX, event.clientY);
    };
    const onLeave = (): void => {
      pointerInside.current = false;
      setTarget(null);
    };
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerleave", onLeave);
    return () => {
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
    };
  }, [canvasRef]);

  // Reset when the target changes; the fetch effect below fills it again.
  useEffect(() => {
    if (target === null) {
      setReadout({ state: "idle" });
    }
  }, [target]);

  // Data loading: debounced, abortable, and cached. The inspect time is not a
  // dependency: the ready render reads it through `getInspectTime`.
  useEffect(() => {
    if (target === null || model === null) {
      return;
    }
    const spec = signalIdsFor(model, target, pathPrefix);
    if (spec === null) {
      setReadout({ state: "hint", message: "This element has no recorded power port." });
      return;
    }
    if (runId === null || manifest === null) {
      setReadout({ state: "hint", message: "Run the model to see e, f and P here." });
      return;
    }
    if (status === "running" || status === "starting") {
      setReadout({ state: "hint", message: "The run is still running; values appear when it finishes." });
      return;
    }
    if (!hasInspectTime) {
      setReadout({
        state: "hint",
        message: "Hover a plot to set the inspect time, then read e, f and P here.",
      });
      return;
    }
    const available = new Set(manifest.signals.map((signal) => signal.id));
    const ids = spec.ids.filter((id) => available.has(id));
    if (ids.length === 0) {
      setReadout({
        state: "hint",
        message: "This run recorded no effort, flow or power for this port.",
      });
      return;
    }
    const powerIds =
      spec.kind === "power"
        ? {
            e: spec.ids[0] as string,
            f: spec.ids[1] as string,
            P: spec.ids[2] as string,
          }
        : null;
    const units =
      powerIds !== null
        ? powerUnits(powerIds, [manifest.signals, checkSignals])
        : { value: signalUnit(ids[0] as string, [manifest.signals, checkSignals]) ?? "" };

    const cached = ids.map((id) => runDataCache.get(runId, id, null, 0));
    const allCached = cached.every((frame) => frame !== undefined);
    const applyFrames = (
      time: Float64Array,
      frames: readonly { values: Float64Array }[],
    ): void => {
      const values: Record<string, Float64Array> = {};
      ids.forEach((id, index) => {
        const frame = frames[index];
        if (frame !== undefined) {
          values[id] = frame.values;
        }
      });
      setReadout({
        state: "ready",
        hover: {
          runId,
          label: spec.label,
          kind: spec.kind,
          time,
          values,
          powerIds,
          units,
        },
      });
    };
    if (allCached) {
      const first = cached[0];
      if (first !== undefined) {
        applyFrames(
          first.time,
          cached as { values: Float64Array }[],
        );
        return;
      }
    }

    setReadout({ state: "loading", message: "Reading the run data…" });
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void fetchRunData(runId, ids, null, 0, controller.signal)
        .then((frame) => {
          if (controller.signal.aborted) {
            return;
          }
          const frames = ids.map((_signalId, index) => ({
            values: frame.values[index] ?? new Float64Array(0),
          }));
          frames.forEach((entry, index) => {
            const id = ids[index];
            if (id !== undefined && entry.values.length > 0) {
              runDataCache.set(runId, id, null, 0, {
                time: frame.time,
                values: entry.values,
              });
            }
          });
          applyFrames(frame.time, frames);
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) {
            return;
          }
          setReadout({
            state: "error",
            message: error instanceof Error ? error.message : String(error),
          });
        });
    }, DEBOUNCE_MS);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [target, model, pathPrefix, runId, manifest, status, hasInspectTime, checkSignals]);

  // Reposition after the tooltip appears (the pointer may have moved while the
  // request was in flight).
  useLayoutEffect(() => {
    if (target !== null) {
      positionAt(tooltipRef.current, pointRef.current.x, pointRef.current.y);
    }
  }, [target, readout.state]);

  const visible = target !== null && readout.state !== "idle" && pointerInside.current;

  const rows = useMemo<HoverRow[]>(() => {
    if (readout.state !== "ready" || inspectTime === null) {
      return [];
    }
    const hover = readout.hover;
    if (hover.kind === "power") {
      if (hover.powerIds === null) {
        return powerHoverRows(null, null, hover.units);
      }
      const effort = valueAtNearestSample(
        hover.time,
        hover.values[hover.powerIds.e],
        inspectTime,
      );
      const flow = valueAtNearestSample(
        hover.time,
        hover.values[hover.powerIds.f],
        inspectTime,
      );
      return powerHoverRows(effort, flow, hover.units);
    }
    const id = Object.keys(hover.values)[0];
    const value =
      id === undefined ? null : valueAtNearestSample(hover.time, hover.values[id], inspectTime);
    return [signalHoverRow(value, hover.units.value)];
  }, [readout, inspectTime]);

  return (
    <div
      ref={tooltipRef}
      className="editor-hover"
      data-testid="hover-readout"
      data-state={readout.state}
      data-visible={visible ? "true" : "false"}
      role="status"
      aria-live="polite"
      aria-hidden={visible ? undefined : true}
      hidden={!visible}
    >
      {target !== null && readout.state === "ready" ? (
        <div className="editor-hover__header">
          <span className="editor-hover__title">{readout.hover.label}</span>
          <span className="editor-hover__time">
            t = {formatCursorTime(inspectTime)}
          </span>
        </div>
      ) : null}
      {readout.state === "ready" ? (
        <table className="editor-hover__rows">
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} data-testid={`hover-row-${row.key}`}>
                <th scope="row">{row.label}</th>
                <td>{row.value}</td>
                <td className="editor-hover__unit">{row.unit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="editor-hover__message">
          {readout.state === "idle" ? "" : readout.message}
        </p>
      )}
    </div>
  );
}
