/**
 * SVG glyphs for the M1 catalog `icon` ids (plan 7.3).
 *
 * Bond-graph elements are not pictures: they render as their letters in a
 * serif font (the classic look). Every other catalog icon id has a simple
 * schematic symbol here, drawn on a 24x24 grid with `currentColor` so it is
 * legible at 40 px in both themes.
 */

import type { ReactNode } from "react";

import { bondLetterFor, dimDescription, isLetterIcon, type BondDim } from "./letters";
import { MULTIBOND_GLYPHS } from "./multibond";

export { MULTIBOND_LETTERS, bondLetterFor, dimDescription, isLetterIcon } from "./letters";
export type { BondDim, BondLetter } from "./letters";

export interface BlockIconProps {
  icon: string;
  /** The block name; bond-graph elements render it as their letter glyph. */
  name: string;
  size?: number;
  className?: string;
}

type Glyph = () => ReactNode;

function label(text: string, size = 8): ReactNode {
  return (
    <text
      x="12"
      y="15.5"
      textAnchor="middle"
      fontSize={size}
      fontFamily="var(--font-ui)"
      fill="currentColor"
      stroke="none"
    >
      {text}
    </text>
  );
}

const GLYPHS: Record<string, Glyph> = {
  ...MULTIBOND_GLYPHS,
  // ---------------------------------------------------------- sources & sinks
  "src-constant": () => (
    <>
      <path d="M2 15h20" />
      <path d="M12 9v6" />
      <path d="M9.5 9h5" />
    </>
  ),
  "src-step": () => (
    <>
      <path d="M2 18h7V8h13" />
      <path d="M2 21h20" opacity="0.35" />
    </>
  ),
  "src-sine": () => (
    <>
      <path d="M2 14c2.5-7 5.5-7 8 0s5.5 7 8 0" />
      <path d="M2 12h20" opacity="0.35" />
    </>
  ),
  "src-ramp": () => (
    <>
      <path d="M2 18h6L20 6" />
      <path d="M2 21h20" opacity="0.35" />
    </>
  ),
  "src-pulse": () => (
    <>
      <path d="M2 17h3V7h5v10h5V7h5v10h2" />
      <path d="M2 21h20" opacity="0.35" />
    </>
  ),
  "src-sawtooth": () => (
    <>
      <path d="M2 17l6-10v10l6-10v10l6-10v10" />
      <path d="M2 21h20" opacity="0.35" />
    </>
  ),
  "src-triangle": () => (
    <>
      <path d="M2 17l4.5-10 4.5 10 4.5-10 4.5 10" />
      <path d="M2 21h20" opacity="0.35" />
    </>
  ),
  "src-trapezoid": () => (
    <>
      <path d="M2 17h2l2-10h4l2 10h2l2-10h4l2 10" />
      <path d="M2 21h20" opacity="0.35" />
    </>
  ),
  "src-multi-sine": () => (
    <>
      <path d="M2 10.8L2.6 9L3.3 7.9L3.9 7.6L4.5 8.1L5.1 8.9L5.8 9.6L6.4 9.9L7 9.5L7.6 8.6L8.3 7.5L8.9 6.6L9.5 6.4L10.1 7.2L10.8 8.7L11.4 10.9L12 13.2L12.6 15L13.3 16.1L13.9 16.4L14.5 15.9L15.1 15.1L15.8 14.4L16.4 14.1L17 14.5L17.6 15.4L18.3 16.5L18.9 17.4L19.5 17.6L20.1 16.8L20.8 15.3L21.4 13.1L22 10.8" />
      <path d="M2 12h20" opacity="0.35" />
    </>
  ),
  "src-exp-sine": () => (
    <>
      <path d="M2 12L2.5 7.2L3 5.2L3.5 6.5L4 10.1L4.5 14.1L5 16.6L5.5 16.7L6 14.7L6.5 11.7L7 9.2L7.5 8.4L8 9.3L8.5 11.3L9 13.3L9.5 14.5L10 14.4L10.5 13.2L11 11.7L11.5 10.4L12 10.1L12.5 10.6L13 11.7L13.5 12.8L14 13.4L14.5 13.2L15 12.6L15.5 11.7L16 11.1L16.5 11L17 11.3L17.5 11.9L18 12.5L18.5 12.7L19 12.6L19.5 12.3L20 11.8L20.5 11.5L21 11.5L21.5 11.7L22 12" />
      <path d="M2 12h20" opacity="0.35" />
    </>
  ),
  "src-exponentials": () => (
    <>
      <path d="M2 19L2.8 14.9L3.7 12.2L4.5 10.4L5.3 9.3L6.2 8.5L7 8L7.8 7.6L8.7 7.4L9.5 7.3L10.3 7.2L11.2 8L12 11.5L12.8 13.8L13.7 15.5L14.5 16.6L15.3 17.3L16.2 17.9L17 18.2L17.8 18.5L18.7 18.6L19.5 18.8L20.3 18.8L21.2 18.9L22 18.9" />
      <path d="M2 21h20" opacity="0.35" />
    </>
  ),
  "src-chirp": () => (
    <>
      <path d="M2 12L2.4 11.2L2.8 10.3L3.3 9.4L3.7 8.5L4.1 7.6L4.5 6.9L4.9 6.3L5.3 6L5.8 6.1L6.2 6.5L6.6 7.4L7 8.7L7.4 10.3L7.8 12.2L8.3 14.1L8.7 15.9L9.1 17.2L9.5 17.9L9.9 17.8L10.3 16.8L10.8 15L11.2 12.6L11.6 10L12 7.8L12.4 6.3L12.8 6.1L13.3 7.2L13.7 9.6L14.1 12.6L14.5 15.6L14.9 17.6L15.3 17.9L15.8 16.4L16.2 13.4L16.6 9.8L17 7L17.4 6L17.8 7.3L18.3 10.6L18.7 14.5L19.1 17.4L19.5 17.8L19.9 15.5L20.3 11.3L20.8 7.5L21.2 6L21.6 7.8L22 12" />
      <path d="M2 12h20" opacity="0.35" />
    </>
  ),
  "src-noise": () => (
    <>
      <path d="M2 12l1.5-4 1.5 7 1.5-9 1.5 6 1.5-3 1.5 8 1.5-7 1.5 4 1.5-6 1.5 9 1.5-5 1.5 2 1.5-3" />
      <path d="M2 12h20" opacity="0.35" />
    </>
  ),
  "src-uniform-noise": () => (
    <>
      <path d="M2 6h20M2 18h20" opacity="0.35" />
      <path d="M2 9h2v6h2v-8h2v10h2v-4h2v3h2V7h2v8h2v-6h2v8h2V9" />
    </>
  ),
  "src-white-noise": () => (
    <>
      <path d="M2 12h1.5V8h1.5v7h1.5V6h1.5v9h1.5v-5h1.5v8h1.5V7h1.5v6h1.5V9h1.5v5h1.5V8h1.5v4H22" />
      <path d="M2 21h20" opacity="0.35" />
    </>
  ),
  "src-prbs": () => (
    <>
      <path d="M2 17h3V7h2v10h5V7h6v10h2V7h2" />
      <path d="M2 12h20" opacity="0.35" />
      <circle cx="19" cy="20" r="0.6" />
    </>
  ),
  "src-random-walk": () => (
    <>
      <path d="M2 14l1.5-1 1.5 2 1.5-3 1.5 1 1.5-4 1.5 2 1.5-1 1.5 3 1.5-5 1.5 1 1.5-2 1.5 3 1.5-4" />
      <path d="M2 21h20" opacity="0.35" />
    </>
  ),
  "src-time": () => (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7v5l3.5 2" />
    </>
  ),
  "src-time-table": () => (
    <>
      <path d="M2 18h4v-6h4v3h4V7h4v5h4" />
      <path d="M2 21h20" opacity="0.35" />
    </>
  ),
  "src-repeating-table": () => (
    <>
      <path d="M2 17h3V8h3v5h3v4h3V8h3v5h3v4h2" />
      <path d="M11 4v17" opacity="0.35" strokeDasharray="2 2" />
      <path d="M2 21h20" opacity="0.35" />
    </>
  ),
  "src-csv": () => (
    <>
      <rect x="4.5" y="3.5" width="15" height="17" rx="1.5" />
      <path d="M4.5 8.5h15M4.5 13.5h15M10 3.5v17" opacity="0.5" />
    </>
  ),
  "src-csv-sampled": () => (
    <>
      <rect x="3.5" y="3.5" width="12" height="14" rx="1.5" />
      <path d="M3.5 8h12M3.5 12.5h12M8 3.5v14" opacity="0.5" />
      <path d="M13 21h3v-4h3v2h3" />
    </>
  ),
  "src-scope": () => (
    <>
      <rect x="3" y="4.5" width="18" height="13" rx="1.5" />
      <path d="M5.5 11c1.5-4 3-4 4.5 0s3 4 4.5 0 3-4 4.5 0" />
      <path d="M9 21h6M12 17.5V21" />
    </>
  ),
  "src-recorder": () => (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="3.5" fill="currentColor" stroke="none" />
    </>
  ),

  // ---------------------------------------------------------------- continuous
  "cont-gain": () => (
    <>
      <path d="M4 6l15 6-15 6z" />
      {label("k", 7)}
    </>
  ),
  "cont-sum": () => (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M8 12h8M12 8v8" />
    </>
  ),
  "cont-integrator": () => (
    <>
      <rect x="4.5" y="4.5" width="15" height="15" rx="1.5" />
      <path d="M10 9c1.5-1.5 3-1 3 1v4c0 2 1.5 2.5 3 1" />
    </>
  ),
  "cont-pi": () => (
    <>
      <rect x="3.5" y="5.5" width="17" height="13" rx="1.5" />
      {label("PI", 7)}
    </>
  ),

  // ---------------------------------------------------------------- electrical
  "elec-resistor": () => <path d="M2 12h4l2-5 3 10 3-10 3 10 2-5h3" />,
  "elec-capacitor": () => <path d="M2 12h7M15 12h7M9.5 5v14M14.5 5v14" />,
  "elec-inductor": () => (
    <>
      <path d="M2 13h2a3 3 0 0 1 6 0 3 3 0 0 1 6 0 3 3 0 0 1 6 0" />
      <path d="M2 17h20" opacity="0.35" />
    </>
  ),
  "elec-ground": () => <path d="M12 3v8M4 11h16M7 15h10M10 19h4" />,
  "elec-voltage-source": () => (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M8.5 12h7M12 8.5v7" opacity="0.9" />
      <path d="M6 4l-3 3M18 4l3 3" opacity="0.35" />
    </>
  ),

  // --------------------------------------------------------------- translation
  "mech-mass": () => (
    <>
      <rect x="4.5" y="6.5" width="15" height="11" rx="1.5" />
      {label("m", 9)}
    </>
  ),
  "mech-spring": () => <path d="M2 12h3l2-6 3 12 3-12 3 12 2-6h3" />,
  "mech-damper": () => (
    <>
      <rect x="3.5" y="8" width="10" height="8" rx="1" />
      <path d="M13.5 12H21M18 8v8" />
    </>
  ),
  "mech-fixed": () => (
    <path d="M12 3v11M3 14h18M5 14l-2 4M9 14l-2 4M13 14l-2 4M17 14l-2 4M21 14l-2 4" />
  ),
  "mech-force-source": () => (
    <>
      <path d="M3 12h11M10 8l4 4-4 4" />
      <path d="M18 5v14" />
    </>
  ),

  // ------------------------------------------------------------------ rotation
  "rot-inertia": () => (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
      <path d="M12 4v3M12 17v3M4 12h3M17 12h3" />
    </>
  ),
  "rot-torsion-spring": () => (
    <>
      <path d="M2 12h3c0-3 6-3 6 0s6 3 6 0 3-2 3 0h2" />
      <path d="M2 17h20" opacity="0.35" />
    </>
  ),
  "rot-damper": () => (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4v8l5 4" />
      <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
    </>
  ),
  "rot-fixed-shaft": () => (
    <path d="M2 12h13M15 4v16M15 6l-2 3M15 12l-2 3M15 18l-2 3" />
  ),
  "rot-torque-source": () => (
    <path d="M19.5 12a7.5 7.5 0 1 1-3-6M16 3.5V8h-4.5" />
  ),
  "rot-gear": () => (
    <>
      <path d="M12 3l1.4 2.1 2.4-.8.5 2.5 2.5.5-.8 2.4L20 12l-2.1 1.4.8 2.4-2.5.5-.5 2.5-2.4-.8L12 20l-1.4-2.1-2.4.8-.5-2.5-2.5-.5.8-2.4L4 12l2.1-1.4-.8-2.4 2.5-.5.5-2.5 2.4.8z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),

  // ------------------------------------------------------- converters & sensors
  "conv-dc-motor": () => (
    <>
      <circle cx="12" cy="12" r="8.5" />
      {label("M", 8)}
      <path d="M3.5 7h-2M3.5 17h-2" opacity="0.35" />
    </>
  ),
  "conv-speed-sensor": () => (
    <>
      <circle cx="12" cy="12" r="8.5" />
      {label("n", 8)}
      <path d="M12 12l4-3" />
    </>
  ),
  "conv-angle-sensor": () => (
    <>
      <circle cx="12" cy="12" r="8.5" />
      {label("\u03c6", 8)}
      <path d="M12 12V6.5" />
    </>
  ),

  // ------------------------------------------------------------- placeholders
  junction: () => (
    <>
      <circle cx="12" cy="12" r="8.5" />
      {label("0", 8)}
    </>
  ),
  "inline-block": () => (
    <>
      <rect x="4" y="4" width="16" height="16" rx="2" strokeDasharray="3 2" />
      <path d="M9 9h6M9 12h6M9 15h4" opacity="0.6" />
    </>
  ),
  "subsystem-block": () => (
    <>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <path d="M3.5 9.5h17" opacity="0.5" />
      <path d="M7 4.5v15M17 4.5v15" opacity="0.35" />
    </>
  ),
};

function FallbackGlyph(): ReactNode {
  return (
    <>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M8 12h8M12 8v8" opacity="0.6" />
    </>
  );
}

/** True when the catalog icon id has a renderer (a letter glyph or an SVG). */
export function hasIcon(icon: string): boolean {
  return isLetterIcon(icon) || Object.hasOwn(GLYPHS, icon);
}

/** Every explicit SVG icon id (the bond-graph and multibond letters are separate). */
export function svgIconIds(): string[] {
  return Object.keys(GLYPHS);
}

/**
 * A bond-graph letter with its optional superscript dimension mark. The mark is
 * absolutely positioned so the letter keeps the footprint of the 1D letters.
 */
export function BondLetterText({ letter, dim }: { letter: string; dim: BondDim | null }) {
  return (
    <span className="bond-letter__text">
      {letter}
      {dim === null ? null : (
        <sup className="bond-letter__dim" data-dim={dim} aria-hidden="true">
          {dim === 2 ? "²" : "³"}
        </sup>
      )}
    </span>
  );
}

export function BlockIcon({ icon, name, size = 40, className }: BlockIconProps) {
  const letter = bondLetterFor(icon, name);
  if (letter !== null) {
    return (
      <span
        className={`bond-letter${className ? ` ${className}` : ""}`}
        data-icon={icon}
        data-dim={letter.dim ?? undefined}
        style={{ fontSize: Math.round(size * 0.62), lineHeight: `${size}px` }}
        aria-hidden="true"
        title={letter.dim === null ? undefined : `${name} (${dimDescription(letter.dim)})`}
      >
        <BondLetterText letter={letter.letter} dim={letter.dim} />
      </span>
    );
  }
  const Glyph = GLYPHS[icon];
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={className}
      data-icon={icon}
      role="img"
      aria-label={name}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {Glyph === undefined ? <FallbackGlyph /> : <Glyph />}
    </svg>
  );
}

/** A junction glyph for the library (the canvas draws its own circle node). */
export function JunctionGlyph({ kind, size = 40 }: { kind: "0" | "1"; size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      role="img"
      aria-label={`${kind} junction`}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
    >
      <circle cx="12" cy="12" r="8.5" />
      <text
        x="12"
        y="15.5"
        textAnchor="middle"
        fontSize={9}
        fontFamily="var(--font-ui)"
        fill="currentColor"
        stroke="none"
      >
        {kind}
      </text>
    </svg>
  );
}
