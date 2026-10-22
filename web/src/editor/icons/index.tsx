/**
 * SVG glyphs for the M1 catalog `icon` ids (plan 7.3).
 *
 * Bond-graph elements are not pictures: they render as their letters in a
 * serif font (the classic look). Every other catalog icon id has a simple
 * schematic symbol here, drawn on a 24x24 grid with `currentColor` so it is
 * legible at 40 px in both themes.
 */

import type { ReactNode } from "react";

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
  return icon.startsWith("bg-") || Object.hasOwn(GLYPHS, icon);
}

/** Every explicit SVG icon id (the bond-graph letters are separate). */
export function svgIconIds(): string[] {
  return Object.keys(GLYPHS);
}

export function BlockIcon({ icon, name, size = 40, className }: BlockIconProps) {
  if (icon.startsWith("bg-")) {
    return (
      <span
        className={`bond-letter${className ? ` ${className}` : ""}`}
        data-icon={icon}
        style={{ fontSize: Math.round(size * 0.62), lineHeight: `${size}px` }}
        aria-hidden="true"
      >
        {name}
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
