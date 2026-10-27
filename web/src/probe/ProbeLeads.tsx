/**
 * A probe lead is a side-channel line. It never enters the model equations; it
 * only points from the probe block/window at the tapped connection.
 */

import { useMemo } from "react";
import { useViewport } from "@xyflow/react";

import type { Model, ModelConnection } from "../contracts/model";
import type { CatalogIndex } from "../library/catalogIndex";
import { useDocumentStore } from "../state/documentStore";
import {
  COMPACT_NODE_SIZE,
  connectionAnchors,
  type Point,
} from "../editor/geometry";
import { ProbeGlyph } from "./ProbeGlyph";
import { useProbeUi } from "./probeUi";
import "./probe.css";

function connectionTapPoint(
  model: Model,
  index: CatalogIndex,
  connection: ModelConnection,
): Point {
  const anchors = connectionAnchors(model, index, connection);
  const points = [anchors.source.point, ...(connection.route ?? []), anchors.target.point];
  const middle = Math.max(0, Math.floor((points.length - 1) / 2));
  const start = points[middle]!;
  const end = points[middle + 1] ?? start;
  return { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 };
}

interface ScreenFrame {
  x: number;
  y: number;
  width: number;
  height: number;
}

function frameStart(frame: ScreenFrame, target: Point): Point {
  const centre = {
    x: frame.x + frame.width / 2,
    y: frame.y + frame.height / 2,
  };
  const dx = target.x - centre.x;
  const dy = target.y - centre.y;
  if (Math.abs(dx) * frame.height >= Math.abs(dy) * frame.width) {
    return {
      x: dx >= 0 ? frame.x + frame.width : frame.x,
      y: Math.min(
        frame.y + frame.height - 8,
        Math.max(frame.y + 8, centre.y + (dy / Math.max(1, Math.abs(dx))) * (frame.width / 2)),
      ),
    };
  }
  return {
    x: Math.min(
      frame.x + frame.width - 8,
      Math.max(frame.x + 8, centre.x + (dx / Math.max(1, Math.abs(dy))) * (frame.height / 2)),
    ),
    y: dy >= 0 ? frame.y + frame.height : frame.y,
  };
}

export function ProbeLeads({
  model,
  index,
}: {
  model: Model;
  index: CatalogIndex;
}) {
  const viewport = useViewport();
  const activeLinkId = useProbeUi((state) => state.activeLinkId);
  const setActiveLink = useProbeUi((state) => state.setActiveLink);
  const probes = model.diagram.probes ?? [];

  const leads = useMemo(() => {
    const toScreen = (point: Point): Point => ({
      x: viewport.x + point.x * viewport.zoom,
      y: viewport.y + point.y * viewport.zoom,
    });
    return probes.flatMap((probe) =>
      probe.links.map((link) => {
        const connection = model.diagram.connections.find(
          (entry) => entry.id === link.connection,
        );
        if (connection === undefined) {
          return null;
        }
        const tap = toScreen(connectionTapPoint(model, index, connection));
        const start =
          probe.kind === "block"
            ? frameStart(
                {
                  x: viewport.x + probe.position.x * viewport.zoom,
                  y: viewport.y + probe.position.y * viewport.zoom,
                  width: COMPACT_NODE_SIZE * viewport.zoom,
                  height: COMPACT_NODE_SIZE * viewport.zoom,
                },
                tap,
              )
            : frameStart(
                {
                  x: probe.panelPosition?.x ?? probe.position.x,
                  y: probe.panelPosition?.y ?? probe.position.y,
                  width: probe.size?.width ?? 380,
                  height: probe.size?.height ?? 240,
                },
                tap,
              );
        const angle = (Math.atan2(tap.y - start.y, tap.x - start.x) * 180) / Math.PI;
        return { probe, link, start, tap, angle };
      }),
    );
  }, [model, index, probes, viewport.x, viewport.y, viewport.zoom]);

  return (
    <svg className="probe-leads" aria-hidden="true">
      {leads.map((lead) => {
        if (lead === null) {
          return null;
        }
        const active = activeLinkId === lead.link.id;
        return (
          <g
            key={lead.link.id}
            className={`probe-lead${active ? " is-active" : ""}`}
            data-testid={`probe-lead-${lead.link.id}`}
          >
            <line
              className="probe-lead__hit"
              x1={lead.start.x}
              y1={lead.start.y}
              x2={lead.tap.x}
              y2={lead.tap.y}
              onClick={(event) => {
                event.stopPropagation();
                setActiveLink(lead.link.id);
                useDocumentStore.getState().setSelection([lead.probe.id], []);
              }}
            />
            <line
              className="probe-lead__line"
              x1={lead.start.x}
              y1={lead.start.y}
              x2={lead.tap.x}
              y2={lead.tap.y}
            />
            <g transform={`translate(${lead.tap.x} ${lead.tap.y}) rotate(${lead.angle + 45})`}>
              <ProbeGlyph size={15} />
            </g>
          </g>
        );
      })}
    </svg>
  );
}
