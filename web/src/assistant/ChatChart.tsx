/**
 * A small chart in the chat, in SVG: lines, points or bars of a code cell, signals of a run,
 * or one signal against another. Theme colours come from CSS; the pointer reads off the values.
 */

import { useMemo, useState, type PointerEvent } from "react";

import { SIGNAL_PALETTE } from "../plot/colors";
import { extentOf, formatNumber, sortOrder, thin, ticks, type Extent } from "./chartModel";

const WIDTH = 480;
const HEIGHT = 220;
const LEFT = 52;
const RIGHT = 12;
const TOP = 10;
const BOTTOM = 32;

export interface ChatChartSeries {
  name: string;
  y: readonly (number | null)[];
}

export interface ChatChartProps {
  xLabel: string;
  style: "line" | "points" | "bar";
  x: readonly number[];
  series: readonly ChatChartSeries[];
  /** Keep the data's order (a phase portrait): the line follows it instead of rising x. */
  trajectory?: boolean;
}

function scale(extent: Extent, from: number, to: number): (value: number) => number {
  return (value) => from + ((value - extent.min) / (extent.max - extent.min)) * (to - from);
}

function pathOf(xs: readonly number[], ys: readonly (number | null)[], px: (v: number) => number, py: (v: number) => number): string {
  let path = "";
  let pen = false;
  xs.forEach((x, i) => {
    const y = ys[i];
    if (y === null || y === undefined || !Number.isFinite(y)) {
      pen = false;
      return;
    }
    path += `${pen ? "L" : "M"}${px(x).toFixed(1)} ${py(y).toFixed(1)}`;
    pen = true;
  });
  return path;
}

export function ChatChart({ xLabel, style, x, series, trajectory = false }: ChatChartProps) {
  const [hover, setHover] = useState<number | null>(null);

  const drawn = useMemo(() => {
    const order = trajectory ? x.map((_, i) => i) : sortOrder(x);
    const sortedX = order.map((i) => x[i]!);
    const sortedY = series.map((s) => order.map((i) => s.y[i] ?? null));
    const keep = thin(sortedX.length, sortedY);
    const xs = keep.map((i) => sortedX[i]!);
    const ys = sortedY.map((column) => keep.map((i) => column[i] ?? null));
    return { xs, ys };
  }, [x, series, trajectory]);

  const xExtent = extentOf([drawn.xs]);
  let yExtent = extentOf(drawn.ys);
  if (xExtent === null || yExtent === null) {
    return <p className="assistant-figure__empty">Nothing to draw: the data has no finite values.</p>;
  }
  if (style === "bar") {
    yExtent = { min: Math.min(0, yExtent.min), max: Math.max(0, yExtent.max) };
  }
  const px = scale(xExtent, LEFT, WIDTH - RIGHT);
  const py = scale(yExtent, HEIGHT - BOTTOM, TOP);
  const colors = series.map((_, i) => SIGNAL_PALETTE[i % SIGNAL_PALETTE.length]!);
  const barWidth = Math.max(1, ((WIDTH - LEFT - RIGHT) / drawn.xs.length) * 0.8);

  const onMove = (event: PointerEvent<SVGSVGElement>): void => {
    if (drawn.xs.length === 0) {
      return;
    }
    const box = event.currentTarget.getBoundingClientRect();
    const at = ((event.clientX - box.left) / box.width) * WIDTH;
    let best = 0;
    drawn.xs.forEach((value, i) => {
      if (Math.abs(px(value) - at) < Math.abs(px(drawn.xs[best]!) - at)) {
        best = i;
      }
    });
    setHover(best);
  };

  return (
    <div className="assistant-chart">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`${style} chart of ${series.map((s) => s.name).join(", ")} against ${xLabel}`}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {ticks(yExtent).map((tick) => (
          <g key={tick} className="assistant-chart__tick">
            <line x1={LEFT} x2={WIDTH - RIGHT} y1={py(tick)} y2={py(tick)} />
            <text x={LEFT - 6} y={py(tick) + 3} textAnchor="end">
              {formatNumber(tick)}
            </text>
          </g>
        ))}
        {ticks(xExtent).map((tick) => (
          <g key={tick} className="assistant-chart__tick">
            <line x1={px(tick)} x2={px(tick)} y1={TOP} y2={HEIGHT - BOTTOM} />
            <text x={px(tick)} y={HEIGHT - BOTTOM + 13} textAnchor="middle">
              {formatNumber(tick)}
            </text>
          </g>
        ))}
        <text className="assistant-chart__label" x={(LEFT + WIDTH - RIGHT) / 2} y={HEIGHT - 4} textAnchor="middle">
          {xLabel}
        </text>
        {drawn.ys.map((column, index) => {
          const color = colors[index]!;
          if (style === "line") {
            return (
              <path key={index} d={pathOf(drawn.xs, column, px, py)} fill="none" stroke={color} strokeWidth={1.5} />
            );
          }
          return (
            <g key={index} fill={color}>
              {drawn.xs.map((value, i) => {
                const y = column[i];
                if (y === null || y === undefined || !Number.isFinite(y)) {
                  return null;
                }
                if (style === "points") {
                  return <circle key={i} cx={px(value)} cy={py(y)} r={2.2} />;
                }
                const share = barWidth / drawn.ys.length;
                const zero = py(0);
                return (
                  <rect
                    key={i}
                    x={px(value) - barWidth / 2 + index * share}
                    width={share}
                    y={Math.min(py(y), zero)}
                    height={Math.abs(py(y) - zero)}
                  />
                );
              })}
            </g>
          );
        })}
        {hover === null ? null : (
          <line className="assistant-chart__cursor" x1={px(drawn.xs[hover]!)} x2={px(drawn.xs[hover]!)} y1={TOP} y2={HEIGHT - BOTTOM} />
        )}
      </svg>
      <ul className="assistant-chart__legend">
        {hover === null ? null : (
          <li>
            {xLabel} = {formatNumber(drawn.xs[hover]!)}
          </li>
        )}
        {series.map((item, index) => (
          <li key={item.name}>
            <span className="assistant-chart__swatch" style={{ background: colors[index] }} aria-hidden="true" />
            {item.name}
            {hover === null ? null : ` = ${formatNumber(drawn.ys[index]![hover] ?? null)}`}
          </li>
        ))}
      </ul>
    </div>
  );
}
