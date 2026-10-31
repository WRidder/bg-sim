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

/** A small letter in the top-left corner (the controlling quantity of a controlled source). */
function cornerLabel(text: string): ReactNode {
  return (
    <text
      x="3.5"
      y="7"
      textAnchor="middle"
      fontSize={6.5}
      fontStyle="italic"
      fontFamily="var(--font-ui)"
      fill="currentColor"
      stroke="none"
    >
      {text}
    </text>
  );
}

/** A small text mark centred at (x, y), for fractions and corner tags. */
function small(text: string, x: number, y: number, size = 6): ReactNode {
  return (
    <text
      x={x}
      y={y}
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
  "src-stop": () => (
    <>
      <path d="M8.7 3.5h6.6l4.7 4.7v6.6l-4.7 4.7H8.7L4 14.8V8.2z" />
      <rect x="9" y="9" width="6" height="5" fill="currentColor" stroke="none" />
    </>
  ),
  "src-assertion": () => (
    <>
      <path d="M12 3.5l9 16H3z" />
      <path d="M12 9.5v5" />
      <circle cx="12" cy="17" r="0.6" fill="currentColor" />
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

  // ------------------------------------------------ signal & control blocks
  "cont-transfer-function": () => (
    <>
      {small("N(s)", 12, 9.5)}
      <path d="M5 12h14" />
      {small("D(s)", 12, 19)}
    </>
  ),
  "cont-zero-pole": () => (
    <>
      <path d="M2 12h20M14 3v18" opacity="0.35" />
      <circle cx="10" cy="12" r="1.8" />
      <path d="M4 6.5l3 3M7 6.5l-3 3M4 14.5l3 3M7 14.5l-3 3" />
    </>
  ),
  "cont-notch": () => (
    <>
      <path d="M2 7h7.5l2.5 11 2.5-11H22" />
      <path d="M2 21h20" opacity="0.35" />
    </>
  ),
  "cont-butterworth": () => (
    <>
      <path d="M2 7h9c3 0 5 3 8 11" />
      <path d="M2 21h20" opacity="0.35" />
      {small("Bw", 18, 10)}
    </>
  ),
  "cont-bessel": () => (
    <>
      <path d="M2 7h5c4 0 7 4 13 11" />
      <path d="M2 21h20" opacity="0.35" />
      {small("Bs", 18, 10)}
    </>
  ),
  "cont-band-pass": () => (
    <>
      <path d="M2 18c4 0 6-11 10-11s6 11 10 11" />
      <path d="M2 21h20" opacity="0.35" />
    </>
  ),
  "cont-mux2": () => (
    <>
      <path d="M2 8h10M2 16h10M16 12h6" />
      <rect x="12" y="4" width="4" height="16" rx="1" fill="currentColor" />
    </>
  ),
  "cont-mux3": () => (
    <>
      <path d="M2 7h10M2 12h10M2 17h10M16 12h6" />
      <rect x="12" y="4" width="4" height="16" rx="1" fill="currentColor" />
    </>
  ),
  "cont-mux4": () => (
    <>
      <path d="M2 6h10M2 10h10M2 14h10M2 18h10M16 12h6" />
      <rect x="12" y="4" width="4" height="16" rx="1" fill="currentColor" />
    </>
  ),
  "cont-demux2": () => (
    <>
      <path d="M2 12h6M12 8h10M12 16h10" />
      <rect x="8" y="4" width="4" height="16" rx="1" fill="currentColor" />
    </>
  ),
  "cont-demux3": () => (
    <>
      <path d="M2 12h6M12 7h10M12 12h10M12 17h10" />
      <rect x="8" y="4" width="4" height="16" rx="1" fill="currentColor" />
    </>
  ),
  "cont-demux4": () => (
    <>
      <path d="M2 12h6M12 6h10M12 10h10M12 14h10M12 18h10" />
      <rect x="8" y="4" width="4" height="16" rx="1" fill="currentColor" />
    </>
  ),
  "cont-multiport-switch": () => (
    <>
      <path d="M2 6h6M2 12h6M2 18h6M16 12h6" />
      <path d="M16 12L8.5 6.5" />
      <circle cx="16" cy="12" r="1.2" fill="currentColor" />
      <path d="M12 21v-4" opacity="0.5" />
    </>
  ),
  "cont-backlash": () => (
    <>
      <path d="M2 12h20M12 2v20" opacity="0.35" />
      <path d="M5 18.5l6-13h8l-6 13z" />
    </>
  ),
  "cont-variable-delay": () => (
    <>
      <rect x="3.5" y="5.5" width="17" height="13" rx="1.5" />
      {label("τ(t)", 7)}
      <path d="M12 21v-2.5" />
    </>
  ),
  "cont-wrap-to-pi": () => (
    <>
      <path d="M2 18l7-12v12l7-12v12l6-10" />
      <path d="M2 6h20M2 18h20" opacity="0.35" strokeDasharray="2 2" />
    </>
  ),
  "cont-polynomial": () => (
    <>
      <rect x="3.5" y="5.5" width="17" height="13" rx="1.5" />
      {label("p(u)", 7)}
    </>
  ),
  "cont-rounding": () => (
    <>
      <path d="M3 20L21 4" opacity="0.35" strokeDasharray="2 2" />
      <path d="M3 20h4v-4h4v-4h4V8h4V4" />
    </>
  ),
  "cont-hit-crossing": () => (
    <>
      <path d="M2 12h20" opacity="0.35" />
      <path d="M2 19c5 0 7-14 12-14 3 0 5 3 8 3" />
      <circle cx="9.3" cy="12" r="1.8" fill="currentColor" stroke="none" />
    </>
  ),
  "cont-luenberger": () => (
    <>
      <rect x="3.5" y="5.5" width="17" height="13" rx="1.5" />
      {label("x̂ L", 7)}
    </>
  ),
  "disc-memory": () => (
    <>
      <rect x="3.5" y="5.5" width="17" height="13" rx="1.5" />
      {label("mem", 7)}
    </>
  ),
  "disc-derivative": () => (
    <>
      <rect x="3.5" y="5.5" width="17" height="13" rx="1.5" />
      {label("Δu/T", 6.5)}
    </>
  ),
  "disc-kalman": () => (
    <>
      <rect x="3.5" y="5.5" width="17" height="13" rx="1.5" />
      {label("KF", 7)}
      <path d="M6 21h3v-1.5h3V21h3v-1.5h3" opacity="0.5" />
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
  "elec-opamp": () => (
    <>
      <path d="M6 3.5v17L20 12z" />
      <path d="M2 8h4M2 16h4M20 12h2.5" />
      <path d="M7.5 8h2.5M7.5 16h2.5M8.75 14.75v2.5" />
    </>
  ),
  // Controlled sources: the diamond, the controlled quantity inside (+/- a voltage, an
  // arrow a current) and the controlling quantity (v or i) in the corner.
  "elec-vcvs": () => (
    <>
      <path d="M12 3l8 9-8 9-8-9z" />
      <path d="M12 7.5v4M10 9.5h4M10 15h4" />
      {cornerLabel("v")}
    </>
  ),
  "elec-vccs": () => (
    <>
      <path d="M12 3l8 9-8 9-8-9z" />
      <path d="M12 16.5v-9M9.5 10L12 7.5 14.5 10" />
      {cornerLabel("v")}
    </>
  ),
  "elec-ccvs": () => (
    <>
      <path d="M12 3l8 9-8 9-8-9z" />
      <path d="M12 7.5v4M10 9.5h4M10 15h4" />
      {cornerLabel("i")}
    </>
  ),
  "elec-cccs": () => (
    <>
      <path d="M12 3l8 9-8 9-8-9z" />
      <path d="M12 16.5v-9M9.5 10L12 7.5 14.5 10" />
      {cornerLabel("i")}
    </>
  ),
  "elec-mutual-inductance": () => (
    <>
      <path d="M3 9.5a3 3 0 0 1 6 0 3 3 0 0 1 6 0 3 3 0 0 1 6 0" />
      <path d="M3 14.5a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0" />
      <path d="M3 12h18" opacity="0.35" />
      <circle cx="3" cy="5" r="1.1" fill="currentColor" stroke="none" />
      <circle cx="3" cy="19" r="1.1" fill="currentColor" stroke="none" />
    </>
  ),
  "elec-battery": () => (
    <>
      <path d="M2 12h7.5M15 12h7M9.5 5v14" />
      <path d="M14 8.5v7" strokeWidth={3} />
      <path d="M4 6.5h3M5.5 5v3" />
    </>
  ),
  "elec-mosfet": () => (
    <>
      <path d="M2 17h6M8 7v10" />
      <path d="M10.5 6v3M10.5 10.5v3M10.5 15v3" />
      <path d="M10.5 7.5H16V2.5M10.5 16.5H16V21.5M10.5 12H16v4.5" />
      <path d="M12.5 10.5L10.8 12l1.7 1.5" />
      <path d="M19 9v6M17.5 13l1.5-2 1.5 2M17.5 11h3" opacity="0.6" />
    </>
  ),
  "elec-igbt": () => (
    <>
      <path d="M2 16h5M7 8v10" />
      <path d="M9.5 6.5v11" />
      <path d="M9.5 9.5l6-4V2.5M9.5 14.5l6 4v3" />
      <path d="M13 18.8l2.5-.3-1-2.3" />
      <path d="M19.5 9v6M18 13l1.5-2 1.5 2M18 11h3" opacity="0.6" />
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
  "rot-hard-stop": () => (
    <>
      <path d="M5.5 17a6.5 6.5 0 0 1 13 0" opacity="0.5" />
      <path d="M3 13.5l4.5 2M21 13.5l-4.5 2" />
      <path d="M12 17l2.5-6" />
      <circle cx="12" cy="17" r="1.4" fill="currentColor" stroke="none" />
    </>
  ),
  "rot-clutch": () => (
    <>
      <path d="M2 12h5M17 12h5" />
      <rect x="7" y="4.5" width="3" height="15" rx="0.8" />
      <rect x="14" y="4.5" width="3" height="15" rx="0.8" />
      <path d="M12 9.5v5" opacity="0.35" />
    </>
  ),
  "rot-brake": () => (
    <>
      <path d="M2 12h7" />
      <rect x="9" y="4" width="3" height="16" rx="0.8" />
      <path d="M14 8v8" strokeWidth={2.4} />
      <path d="M18 4v16M18 6l3-3M18 11l3-3M18 16l3-3M14 12h4" />
    </>
  ),
  "rot-planetary-gear": () => (
    <>
      <circle cx="12" cy="12" r="9.5" />
      <circle cx="12" cy="12" r="2.6" />
      <circle cx="12" cy="5.8" r="2.2" />
      <circle cx="17.4" cy="15.1" r="2.2" />
      <circle cx="6.6" cy="15.1" r="2.2" />
    </>
  ),
  "rot-belt-drive": () => (
    <>
      <circle cx="6" cy="12" r="3.5" />
      <circle cx="17" cy="12" r="5.5" />
      <path d="M6 8.5l11-2M6 15.5l11 2" />
      <circle cx="6" cy="12" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="17" cy="12" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
  "rot-worm-gear": () => (
    <>
      <circle cx="12" cy="8.5" r="6" />
      <circle cx="12" cy="8.5" r="1.4" fill="currentColor" stroke="none" />
      <path d="M2 19h20" opacity="0.35" />
      <path d="M5 16.5l2 5M9 16.5l2 5M13 16.5l2 5M17 16.5l2 5" />
    </>
  ),

  // ------------------------------------------------------------------- thermal
  "th-heat-capacitor": () => (
    <>
      <rect x="4.5" y="6.5" width="15" height="11" rx="1.5" />
      {label("C", 8)}
      <path d="M8 20.5c1-1 2-1 3 0s2 1 3 0 2-1 3 0" opacity="0.5" />
    </>
  ),
  "th-conductor": () => (
    <>
      <path d="M2 12h4M18 12h4" />
      <rect x="6" y="8" width="12" height="8" />
      <path d="M8 8l4 8M12 8l4 8" opacity="0.5" />
    </>
  ),
  "th-resistor": () => (
    <>
      <path d="M2 12h4M18 12h4" />
      <rect x="6" y="8" width="12" height="8" />
      {label("R", 6.5)}
    </>
  ),
  "th-convection": () => (
    <>
      <path d="M4 4v16" />
      <path d="M8 18c2-2 0-4 2-6s0-4 2-6M13 18c2-2 0-4 2-6s0-4 2-6M18 18c2-2 0-4 2-6s0-4 2-6" />
    </>
  ),
  "th-variable-convection": () => (
    <>
      <path d="M4 4v16" />
      <path d="M8 18c2-2 0-4 2-6s0-4 2-6M13 18c2-2 0-4 2-6s0-4 2-6" />
      <path d="M15 20l6-16M19 6l2-2 .5 3" />
    </>
  ),
  "th-radiation": () => (
    <>
      <path d="M4 4v16M20 4v16" />
      <path d="M7 8l4 0M9 6l2 2-2 2M13 16h4M15 14l2 2-2 2" />
      <path d="M7 12c1-1.5 2-1.5 3 0s2 1.5 3 0 2-1.5 3 0" opacity="0.6" />
    </>
  ),
  "th-fixed-temperature": () => (
    <>
      <path d="M10 4a2 2 0 0 1 4 0v10a4 4 0 1 1-4 0z" />
      <circle cx="12" cy="17" r="1.8" fill="currentColor" stroke="none" />
      <path d="M12 9v6" />
    </>
  ),
  "th-prescribed-temperature": () => (
    <>
      <path d="M10 4a2 2 0 0 1 4 0v10a4 4 0 1 1-4 0z" />
      <circle cx="12" cy="17" r="1.8" fill="currentColor" stroke="none" />
      <path d="M17 6l4 0M17 10h4" opacity="0.6" />
    </>
  ),
  "th-heat-flow-source": () => (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M7 12h9M13 9l3 3-3 3" />
    </>
  ),
  "th-prescribed-heat-flow": () => (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M7 12h9M13 9l3 3-3 3" />
      <path d="M12 2v2" opacity="0.6" />
    </>
  ),
  "th-temperature-sensor": () => (
    <>
      <path d="M10 4a2 2 0 0 1 4 0v10a4 4 0 1 1-4 0z" />
      <circle cx="12" cy="17" r="1.8" fill="currentColor" stroke="none" />
      <path d="M16 12h5M19 10l2 2-2 2" opacity="0.8" />
    </>
  ),
  "th-heat-flow-sensor": () => (
    <>
      <circle cx="12" cy="12" r="8.5" />
      {label("Q", 8)}
      <path d="M2 12h1.5M20.5 12H22" />
    </>
  ),
  "th-resistor-heated": () => (
    <>
      <path d="M2 10h4l2-4 3 8 3-8 3 8 2-4h3" />
      <path d="M8 20c1-1 2-1 3 0s2 1 3 0 2-1 3 0" opacity="0.6" />
    </>
  ),
  "th-dc-motor": () => (
    <>
      <circle cx="12" cy="11" r="7.5" />
      {label("M", 8)}
      <path d="M8 21.5c1-1 2-1 3 0s2 1 3 0 2-1 3 0" opacity="0.6" />
    </>
  ),

  // ----------------------------------------------- hydraulic (ISO 1219-like)
  "hyd-pressure-source": () => (
    <>
      <circle cx="12" cy="13" r="7" />
      {label("p", 8)}
      <path d="M12 6V2" />
    </>
  ),
  "hyd-flow-source": () => (
    <>
      <circle cx="12" cy="12" r="7" />
      {label("Q", 7.5)}
      <path d="M2 12h3M19 12h3" />
    </>
  ),
  "hyd-tank": () => (
    <>
      <path d="M4.5 9v10.5h15V9" />
      <path d="M12 2.5V16" />
    </>
  ),
  "hyd-volume": () => (
    <>
      <rect x="5" y="8" width="14" height="11" rx="1.5" />
      <path d="M12 2.5V8" />
      <path d="M7.5 15.5h9" opacity="0.4" />
    </>
  ),
  "hyd-orifice": () => (
    <>
      <path d="M2 12h20" />
      <path d="M9.5 6.5c2 3.5 2 7.5 0 11M14.5 6.5c-2 3.5-2 7.5 0 11" />
    </>
  ),
  "hyd-variable-orifice": () => (
    <>
      <path d="M2 12h20" />
      <path d="M9.5 6.5c2 3.5 2 7.5 0 11M14.5 6.5c-2 3.5-2 7.5 0 11" />
      <path d="M5.5 19.5L18.5 4.5M18.5 4.5l-3.6.9M18.5 4.5l-.7 3.6" />
    </>
  ),
  "hyd-check-valve": () => (
    <>
      <path d="M2 12h6M16.7 12H22" />
      <path d="M12 6.8L8 12l4 5.2" />
      <circle cx="13.4" cy="12" r="3.2" />
    </>
  ),
  "hyd-relief-valve": () => (
    <>
      <rect x="5" y="5" width="11" height="14" />
      <path d="M9 22v-5M9 7V2" />
      <path d="M12 16.5V7.5M12 7.5l-1.5 2.5M12 7.5l1.5 2.5" />
      <path d="M16 12h1l1-2 1.5 4 1.5-4 1 2" />
      <path d="M9 20H3v-8h2" strokeDasharray="1.6 1.4" opacity="0.7" />
    </>
  ),
  "hyd-directional-valve": () => (
    <>
      <path d="M1.5 8h21v8h-21zM8.5 8v8M15.5 8v8" />
      <path d="M3.5 15v-5.5M3.5 9.5l-1 1.6M3.5 9.5l1 1.6M6.5 9.5V15M6.5 15l-1-1.6M6.5 15l1-1.6" />
      <path d="M10.5 8v3M9.3 11h2.4M13.5 16v-3M12.3 13h2.4" />
      <path d="M17.5 9.5l3 5.5M20.5 9.5l-3 5.5" />
      <path d="M10.5 16v4M13.5 16v4M10.5 8V4M13.5 8V4" opacity="0.45" />
    </>
  ),
  "hyd-accumulator": () => (
    <>
      <rect x="7" y="3" width="10" height="16" rx="5" />
      <path d="M7 11h10" />
      <path d="M12 5.5l-2.2 3.3h4.4z" fill="currentColor" stroke="none" />
      <path d="M12 19v3.5" />
    </>
  ),
  "hyd-pipe": () => (
    <>
      <path d="M3.5 9h17M3.5 15h17M3.5 6.5v11M20.5 6.5v11" />
      <path d="M8 12h8M16 12l-2.4-1.6M16 12l-2.4 1.6" opacity="0.6" />
    </>
  ),
  "hyd-flow-control": () => (
    <>
      <rect x="3" y="4" width="18" height="16" rx="1" />
      <path d="M12 4v16" opacity="0.35" />
      <path d="M9.5 7.5c1.6 3 1.6 6 0 9M14.5 7.5c-1.6 3-1.6 6 0 9" />
      <path d="M7 17.5L17 6.5M17 6.5l-3 .7M17 6.5l-.6 3" />
      <path d="M5.5 16.5v-6M5.5 10.5l-1 1.6M5.5 10.5l1 1.6" />
    </>
  ),

  // ------------------------------------------------------- vacuum gripping (contact group)
  "ct-suction-cup": () => (
    <>
      <path d="M8 2.5h8M12 2.5v3" />
      <path d="M9 5.5h6l-1 2.2 1.6 2.3-1.6 2.3 1.6 2.3" />
      <path d="M9 5.5l1 2.2-1.6 2.3 1.6 2.3-1.6 2.3" />
      <path d="M8.4 14.6L4.5 18.5h15l-3.9-3.9" />
      <path d="M2.5 20.5h19" opacity="0.55" />
      <path d="M18.5 9.5h3M20 8v3" opacity="0.6" />
    </>
  ),
  "ct-vacuum-generator": () => (
    <>
      <circle cx="12" cy="12" r="7.5" />
      <path d="M12 4.5L8.2 16.5M12 4.5l3.8 12" />
      <path d="M2 12h2.5M19.5 12H22" />
      <path d="M9 19.5h6" opacity="0.6" />
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
  "conv-fixed-pump": () => (
    <>
      <circle cx="12" cy="13" r="7" />
      <path d="M12 6.2l-2.8 4.3h5.6z" fill="currentColor" stroke="none" />
      <path d="M12 6V2M2 13h3M2 11.2h3" />
    </>
  ),
  "conv-variable-pump": () => (
    <>
      <circle cx="12" cy="13" r="7" />
      <path d="M12 6.2l-2.8 4.3h5.6z" fill="currentColor" stroke="none" />
      <path d="M12 6V2M2 13h3M2 11.2h3" />
      <path d="M6 21L18.5 6.5M18.5 6.5l-3.5 1M18.5 6.5l-.9 3.5" />
    </>
  ),
  "conv-hydraulic-motor": () => (
    <>
      <circle cx="12" cy="13" r="7" />
      <path d="M12 10.6L9.2 6.4h5.6z" fill="currentColor" stroke="none" />
      <path d="M12 6V2M19 13h3M19 11.2h3" />
    </>
  ),
  "conv-hydraulic-cylinder": () => (
    <>
      <path d="M2.5 7h13v10h-13z" />
      <path d="M9.5 7v10M9.5 12H22" />
      <path d="M5 17v4M13 17v4" opacity="0.6" />
    </>
  ),
  "conv-pressure-sensor": () => (
    <>
      <circle cx="12" cy="10" r="7" />
      <path d="M12 10l4-3.5" />
      <circle cx="12" cy="10" r="1.2" fill="currentColor" stroke="none" />
      <path d="M12 17v5" />
    </>
  ),
  "conv-flow-sensor": () => (
    <>
      <circle cx="12" cy="12" r="6.5" />
      <path d="M2 12h20M15 12l-2.6-1.8M15 12l-2.6 1.8" />
    </>
  ),

  // ------------------------------------------- motion profiles & drive electronics
  // The profiles draw their velocity over one move; the drive electronics their schematic.
  "mot-trapezoidal-profile": () => (
    <>
      <path d="M3 18l5-11h8l5 11" />
      <path d="M2 18h20" opacity="0.35" />
    </>
  ),
  "mot-s-curve-profile": () => (
    <>
      <path d="M3 18c3 0 3-11 7-11h4c4 0 4 11 7 11" />
      <path d="M2 18h20" opacity="0.35" />
    </>
  ),
  "mot-cycloidal-profile": () => (
    <>
      <path d="M2 18c5 0 5-12 10-12s5 12 10 12" />
      <path d="M2 18h20" opacity="0.35" />
    </>
  ),
  "mot-polynomial-profile": () => (
    <>
      <path d="M3 18C11 18 13 6 21 6" />
      <path d="M2 18h20M21 4v16" opacity="0.35" />
      <circle cx="3" cy="18" r="1" />
      <circle cx="21" cy="6" r="1" />
    </>
  ),
  "mot-harmonic-profile": () => (
    <>
      <path d="M3 18Q12 -3 21 18" />
      <path d="M2 18h20" opacity="0.35" />
    </>
  ),
  "mot-pwm": () => (
    <>
      <path d="M2 17V7h2v10h3V7h4v10h2V7h6v10h3" />
      <path d="M2 20h20" opacity="0.35" />
    </>
  ),
  "mot-pwm-average": () => (
    <>
      <path d="M2 17V7h2v10h3V7h4v10h2V7h6v10h3" opacity="0.35" />
      <path d="M2 13l6-1 6-1.5 8-1.5" />
    </>
  ),
  "mot-encoder": () => (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="1.2" />
      <path d="M12 3.5v3M12 17.5v3M3.5 12h3M17.5 12h3M6 6l2 2M16 16l2 2M18 6l-2 2M8 16l-2 2" />
    </>
  ),
  "mot-adc": () => (
    <>
      <path d="M3.5 5.5h13l4 6.5-4 6.5h-13z" />
      {label("A/D", 6)}
    </>
  ),
  "mot-dac": () => (
    <>
      <path d="M20.5 5.5h-13l-4 6.5 4 6.5h13z" />
      {label("D/A", 6)}
    </>
  ),
  "mot-h-bridge": () => (
    <>
      <path d="M3 4h18M3 20h18M7 4v4M7 16v4M17 4v4M17 16v4" />
      <path d="M7 8l2 3.5M7 16l2-3.5M17 8l2 3.5M17 16l2-3.5" />
      <path d="M7 12h3M14 12h3" />
      <rect x="10" y="10.5" width="4" height="3" />
    </>
  ),
  "mot-power-amplifier": () => (
    <>
      <path d="M5 5v14l13-7z" />
      <path d="M2 12h3M18 12h4M10 3v4.5M10 21v-4.5" />
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
