/**
 * One figure of the chat: signals of a run, a code cell's chart, table or matrix, or a level of
 * a model's diagram. A figure is drawn from its event alone, so a reloaded chat shows it again;
 * only a run's signals are fetched, and a run deleted since then says so.
 */

import { useEffect, useRef, useState } from "react";

import { requestPlotsTab } from "../app/dockBus";
import type {
  AssistantDiagramFigure,
  AssistantFigure,
  AssistantImageFigure,
  AssistantPlotFigure,
  AssistantTableFigure,
} from "../contracts/assistant";
import { fetchRunData } from "../plot/runApi";
import { useRunStore } from "../plot/runStore";
import { ChatChart, type ChatChartSeries } from "./ChatChart";
import { colorAt, COLOR_BAR, formatNumber } from "./chartModel";

const PLOT_PIXELS = 800;
const NODE_WIDTH = 100;
const NODE_HEIGHT = 60;
const MARGIN = 20;

interface PlotData {
  x: number[];
  series: ChatChartSeries[];
}

function RunPlot({ figure }: { figure: AssistantPlotFigure }) {
  const [data, setData] = useState<PlotData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ids = figure.x === undefined ? figure.signals : [figure.x, ...figure.signals];
  const key = ids.join("\n");

  useEffect(() => {
    const abort = new AbortController();
    const window =
      figure.t0 === undefined || figure.t1 === undefined ? null : { t0: figure.t0, t1: figure.t1 };
    fetchRunData(figure.runId, key.split("\n"), window, PLOT_PIXELS, abort.signal).then(
      (frame) => {
        const columns = frame.values.map((column) => Array.from(column));
        const shown = figure.x === undefined ? columns : columns.slice(1);
        setData({
          x: figure.x === undefined ? Array.from(frame.time) : columns[0]!,
          series: shown.map((y, index) => ({ name: figure.signals[index] ?? "", y })),
        });
      },
      (cause: unknown) => {
        if (!abort.signal.aborted) {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      },
    );
    return () => abort.abort();
  }, [figure.runId, figure.t0, figure.t1, figure.x, figure.signals, key]);

  const toDock = (): void => {
    const store = useRunStore.getState();
    store.addSignals(figure.signals);
    requestPlotsTab();
  };

  if (error !== null) {
    return <p className="assistant-figure__empty">Run {figure.runId} cannot be read: {error}</p>;
  }
  if (data === null) {
    return <p className="assistant-figure__empty">Loading {figure.runId}…</p>;
  }
  return (
    <>
      <ChatChart
        xLabel={figure.x ?? "t [s]"}
        style="line"
        x={data.x}
        series={data.series}
        trajectory={figure.x !== undefined}
      />
      <button type="button" className="assistant-link" onClick={toDock}>
        Show in the Plots dock
      </button>
    </>
  );
}

function TableView({ figure }: { figure: AssistantTableFigure }) {
  return (
    <div className="assistant-table">
      <table>
        <thead>
          <tr>
            {figure.columns.map((column, index) => (
              <th key={index} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {figure.rows.map((row, index) => (
            <tr key={index}>
              {row.map((cell, column) => (
                <td key={column}>{formatNumber(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {figure.truncated === true ? <p className="assistant-figure__note">Only the first rows are shown.</p> : null}
    </div>
  );
}

function ImageView({ figure }: { figure: AssistantImageFigure }) {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const rows = figure.rows;
  const height = rows.length;
  const width = rows[0]?.length ?? 0;

  useEffect(() => {
    const context = canvas.current?.getContext("2d");
    if (!context || width === 0) {
      return;
    }
    const image = context.createImageData(width, height);
    const span = figure.max - figure.min || 1;
    rows.forEach((row, y) => {
      row.forEach((cell, x) => {
        const value = typeof cell === "boolean" ? Number(cell) : cell;
        if (value === null || !Number.isFinite(value)) {
          return; // transparent
        }
        const at = (y * width + x) * 4;
        image.data.set([...colorAt((value - figure.min) / span), 255], at);
      });
    });
    context.putImageData(image, 0, 0);
  }, [rows, width, height, figure.min, figure.max]);

  return (
    <div className="assistant-image">
      <canvas
        ref={canvas}
        width={width}
        height={height}
        role="img"
        aria-label={`${height} by ${width} matrix, from ${formatNumber(figure.min)} to ${formatNumber(figure.max)}`}
        style={{ aspectRatio: `${Math.max(width, 1)} / ${Math.max(height, 1)}` }}
      />
      <div className="assistant-image__bar">
        <span>{formatNumber(figure.min)}</span>
        <span className="assistant-image__ramp" style={{ background: COLOR_BAR }} aria-hidden="true" />
        <span>{formatNumber(figure.max)}</span>
      </div>
    </div>
  );
}

function DiagramView({ figure }: { figure: AssistantDiagramFigure }) {
  const { nodes, edges } = figure;
  if (nodes.length === 0) {
    return <p className="assistant-figure__empty">This diagram is empty.</p>;
  }
  const left = Math.min(...nodes.map((n) => n.x)) - MARGIN;
  const top = Math.min(...nodes.map((n) => n.y)) - MARGIN;
  const right = Math.max(...nodes.map((n) => n.x)) + NODE_WIDTH + MARGIN;
  const bottom = Math.max(...nodes.map((n) => n.y)) + NODE_HEIGHT + MARGIN;
  const center = new Map(nodes.map((n) => [n.id, { x: n.x + NODE_WIDTH / 2, y: n.y + NODE_HEIGHT / 2 }]));
  return (
    <svg
      className="assistant-diagram"
      viewBox={`${left} ${top} ${right - left} ${bottom - top}`}
      role="img"
      aria-label={`Diagram of ${figure.model}: ${nodes.map((n) => n.name).join(", ")}`}
    >
      {edges.map((edge, index) => {
        const from = center.get(edge.from);
        const to = center.get(edge.to);
        return from === undefined || to === undefined ? null : (
          <line
            key={index}
            className={`assistant-diagram__edge assistant-diagram__edge--${edge.kind}`}
            x1={from.x}
            y1={from.y}
            x2={to.x}
            y2={to.y}
          />
        );
      })}
      {nodes.map((node) => (
        <g key={node.id} className={`assistant-diagram__node assistant-diagram__node--${node.kind}`}>
          {node.kind === "junction" ? (
            <circle cx={node.x + NODE_WIDTH / 2} cy={node.y + NODE_HEIGHT / 2} r={18} />
          ) : (
            <rect x={node.x} y={node.y} width={NODE_WIDTH} height={NODE_HEIGHT} rx={5} />
          )}
          <text x={node.x + NODE_WIDTH / 2} y={node.y + NODE_HEIGHT / 2 + (node.kind === "junction" ? 5 : -2)} textAnchor="middle">
            {node.kind === "junction" ? node.label : node.name}
          </text>
          {node.kind === "junction" ? null : (
            <text className="assistant-diagram__type" x={node.x + NODE_WIDTH / 2} y={node.y + NODE_HEIGHT / 2 + 14} textAnchor="middle">
              {node.label}
            </text>
          )}
        </g>
      ))}
    </svg>
  );
}

function Body({ figure }: { figure: AssistantFigure }) {
  switch (figure.kind) {
    case "plot":
      return <RunPlot figure={figure} />;
    case "chart":
      return <ChatChart xLabel={figure.xLabel} style={figure.style} x={figure.x} series={figure.series} />;
    case "table":
      return <TableView figure={figure} />;
    case "image":
      return <ImageView figure={figure} />;
    case "diagram":
      return <DiagramView figure={figure} />;
  }
}

export function FigureCard({ figure }: { figure: AssistantFigure }) {
  return (
    <figure className="assistant-figure" data-testid={`figure-${figure.kind}`}>
      {figure.title === "" ? null : <figcaption>{figure.title}</figcaption>}
      <Body figure={figure} />
    </figure>
  );
}
