/**
 * The port glyph of a library row (plan 7.2, W-MB3).
 *
 * A power port shows one tick per bond stroke: one for a scalar domain, two for
 * Planar, three for Spatial (D-MB12). The glyph is one logical port, exactly as
 * on the canvas, and its accessible name says the domain, component count and
 * stroke count.
 */

import type { DomainName } from "../contracts/catalog";
import { domainColor, multibondComponents, multibondStrokes } from "../editor/geometry";

export interface PortGlyphProps {
  domain: DomainName;
  /** Port name, spoken in the accessible label. */
  name?: string;
  /** Declared frame; omitted or null is frame-neutral and is not spoken. */
  frame?: string | null;
}

const Y: Record<1 | 2 | 3, readonly number[]> = {
  1: [6],
  2: [3.5, 8.5],
  3: [2, 6, 10],
};

/**
 * `Planar multibond port p, 3 components, 2 strokes, frame body`; a scalar port
 * reads `Rotation scalar port shaft, 1 component, 1 stroke`.
 */
export function portGlyphLabel(
  domain: DomainName,
  name?: string,
  frame?: string | null,
): string {
  const strokes = multibondStrokes(domain);
  const components = multibondComponents(domain);
  const who = name === undefined ? "port" : `port ${name}`;
  const frameText = frame === null || frame === undefined || frame.trim() === "" ? "" : `, frame ${frame.trim()}`;
  return strokes === 1
    ? `${domain} scalar ${who}, ${components} component, 1 stroke${frameText}`
    : `${domain} multibond ${who}, ${components} components, ${strokes} strokes${frameText}`;
}

export function PortGlyph({ domain, name, frame }: PortGlyphProps) {
  const strokes = multibondStrokes(domain);
  const tokens = Y[strokes];
  return (
    <svg
      className="library-port-glyph"
      width="20"
      height="12"
      viewBox="0 0 20 12"
      role="img"
      aria-label={portGlyphLabel(domain, name, frame)}
      data-domain={domain}
      data-strokes={strokes}
      data-glyph={strokes > 1 ? "multibond" : "scalar"}
    >
      {tokens.map((y) => (
        <line
          key={y}
          x1="1"
          y1={y}
          x2="19"
          y2={y}
          stroke={domainColor(domain)}
          strokeWidth="1.5"
        />
      ))}
    </svg>
  );
}
