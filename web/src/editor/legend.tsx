/**
 * The canvas legend (plan 7.3): domains, port glyphs, the causal stroke and the
 * unit-factor badge in one accessible corner panel.
 *
 * The legend is data-driven so the unit test can assert the content without a
 * browser, and every entry carries a description for screen readers. Colours
 * are the theme tokens; Generic is drawn dashed and grey, and the error and
 * warning colours never appear here.
 */

import { DOMAIN_LEGEND } from "./geometry";
import "./legend.css";

export interface LegendDomain {
  id: string;
  label: string;
  /** A CSS custom property value, so the legend follows the theme. */
  token: string;
  dashed: boolean;
}

export interface LegendKey {
  id: "power" | "in" | "out" | "causal" | "unit";
  label: string;
  description: string;
}

/** Every domain of plan 7.3, including Planar (not a contract domain yet). */
export const LEGEND_DOMAINS: readonly LegendDomain[] = [
  ...DOMAIN_LEGEND.map((entry) => ({
    id: entry.domain,
    label: entry.label,
    token:
      entry.domain === "Electrical"
        ? "var(--domain-electrical)"
        : entry.domain === "Translation"
          ? "var(--domain-translation)"
          : entry.domain === "Rotation"
            ? "var(--domain-rotation)"
            : entry.domain === "Hydraulic"
              ? "var(--domain-hydraulic)"
              : "var(--domain-generic)",
    dashed: entry.domain === "Generic",
  })),
  { id: "Planar", label: "Planar", token: "var(--domain-planar)", dashed: false },
];

export const LEGEND_KEYS: readonly LegendKey[] = [
  {
    id: "power",
    label: "power",
    description: "Power port: a filled square; bonds carry effort and flow.",
  },
  {
    id: "in",
    label: "in",
    description: "Signal input: a hollow triangle pointing into the block.",
  },
  {
    id: "out",
    label: "out",
    description: "Signal output: a filled triangle pointing out of the block.",
  },
  {
    id: "causal",
    label: "causal",
    description:
      "Causal stroke: the perpendicular bar marks the end where effort is the input.",
  },
  {
    id: "unit",
    label: "units",
    description:
      "Unit factor badge: the compiler scales this signal, here by 0.001 (mm to m).",
  },
];

function KeyGlyph({ id }: { id: LegendKey["id"] }) {
  switch (id) {
    case "power":
      return <span className="editor-legend__glyph editor-legend__glyph--power" aria-hidden="true" />;
    case "in":
      return <span className="editor-legend__glyph editor-legend__glyph--input" aria-hidden="true" />;
    case "out":
      return <span className="editor-legend__glyph editor-legend__glyph--output" aria-hidden="true" />;
    case "causal":
      return (
        <svg
          className="editor-legend__causal"
          width="20"
          height="12"
          viewBox="0 0 20 12"
          aria-hidden="true"
        >
          <line x1="0" y1="6" x2="20" y2="6" stroke="var(--domain-electrical)" strokeWidth="2" />
          <line x1="14" y1="1.5" x2="14" y2="10.5" stroke="var(--domain-electrical)" strokeWidth="2.4" />
        </svg>
      );
    case "unit":
      return (
        <span className="editor-legend__unit" aria-hidden="true">
          ×0.001
        </span>
      );
    default:
      return null;
  }
}

/** The bottom-left canvas legend. */
export function CanvasLegend() {
  return (
    <div
      className="editor-legend"
      data-testid="canvas-legend"
      role="group"
      aria-label="Canvas legend: domains, port glyphs, causal strokes and unit factors"
    >
      <span className="editor-legend__title">Domains</span>
      {LEGEND_DOMAINS.map((entry) => (
        <span
          className="editor-legend__item"
          key={entry.id}
          data-testid={`legend-domain-${entry.id}`}
          title={`${entry.label} domain${entry.dashed ? " (unresolved, dashed)" : ""}`}
        >
          <span
            className={`editor-legend__swatch${entry.dashed ? " is-generic" : ""}`}
            style={{ background: entry.token }}
            aria-hidden="true"
          />
          {entry.label}
        </span>
      ))}
      <span className="editor-legend__separator" aria-hidden="true" />
      {LEGEND_KEYS.map((entry) => (
        <span
          className="editor-legend__item"
          key={entry.id}
          data-testid={`legend-${entry.id}`}
          title={entry.description}
        >
          <KeyGlyph id={entry.id} />
          {entry.label}
        </span>
      ))}
    </div>
  );
}
