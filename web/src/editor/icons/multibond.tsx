/**
 * Schematic glyphs for the composite multibond blocks (bodies, joints, pose
 * blocks, contact, drives). Drawn on the same 24x24 grid and stroke style as
 * the other glyphs in `index.tsx`. 2D and 3D variants share one motif and
 * differ by a small detail (a third axis, a perspective edge).
 */

import type { ReactNode } from "react";

type Glyph = () => ReactNode;

/** Frame triad at (x, y): two axes for planar, a third oblique one for spatial. */
function triad(x: number, y: number, dim: 2 | 3, s = 1, rot = 0): ReactNode {
  return (
    <g transform={`translate(${x} ${y}) rotate(${rot}) scale(${s})`} strokeWidth={1.6 / s}>
      <path d="M0 0V-8M-2 -5.6L0 -8L2 -5.6" />
      <path d="M0 0H8M5.6 -2L8 0L5.6 2" />
      {dim === 3 ? <path d="M0 0L-5 5M-5 2.6V5H-2.6" /> : null}
      <circle cx="0" cy="0" r="1.1" fill="currentColor" stroke="none" />
    </g>
  );
}

/** A small corner marker for the Compliant/Friction/Limit/Rigid variants. */
const MARKERS = {
  compliant: <path d="M13.5 21H15l1.2-2.8 2.2 5.6 2.2-5.6L21.8 21H23" />,
  friction: <path d="M13.5 22.5h9.5M15.5 22.5l2.5-4.5M18.5 22.5l2.5-4.5M21.5 22.5l1.8-3.2" />,
  limit: <path d="M13.5 17.5v6M22.5 17.5v6M13.5 20.5h9" />,
  rigid: <circle cx="18" cy="20.5" r="2.6" fill="currentColor" />,
} as const;

type Variant = keyof typeof MARKERS;

function withMarker(motif: ReactNode, variant: Variant): ReactNode {
  return (
    <>
      <g transform="translate(-0.5 -1.5) scale(0.82)" strokeWidth={1.95}>
        {motif}
      </g>
      {MARKERS[variant]}
    </>
  );
}

/** A toothed wheel: a circle with radial tick teeth. */
function gear(cx: number, cy: number, r: number): ReactNode {
  const teeth = 8;
  const parts: string[] = [];
  for (let i = 0; i < teeth; i += 1) {
    const a = (i / teeth) * Math.PI * 2;
    const x1 = cx + Math.cos(a) * r;
    const y1 = cy + Math.sin(a) * r;
    const x2 = cx + Math.cos(a) * (r + 1.7);
    const y2 = cy + Math.sin(a) * (r + 1.7);
    parts.push(`M${x1.toFixed(2)} ${y1.toFixed(2)}L${x2.toFixed(2)} ${y2.toFixed(2)}`);
  }
  return (
    <>
      <circle cx={cx} cy={cy} r={r} />
      <path d={parts.join("")} strokeWidth={1.8} />
      <circle cx={cx} cy={cy} r="1" fill="currentColor" stroke="none" />
    </>
  );
}

function letterM(x: number, y: number): ReactNode {
  return (
    <text
      x={x}
      y={y}
      textAnchor="middle"
      fontSize="8"
      fontFamily="var(--font-ui)"
      fill="currentColor"
      stroke="none"
    >
      M
    </text>
  );
}

// ----------------------------------------------------------------- motifs

function body(dim: 2 | 3): ReactNode {
  return dim === 2 ? (
    <>
      <rect x="3" y="4" width="18" height="16" rx="1.5" />
      {triad(8, 15, 2, 0.9)}
    </>
  ) : (
    <>
      <path d="M3 9h13v12H3zM3 9l5-5h13v12l-5 5M16 9l5-5" />
      {triad(8, 18, 3, 0.55)}
    </>
  );
}

function revolute(dim: 2 | 3): ReactNode {
  return (
    <>
      <circle cx="12" cy="12" r="3.6" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
      <path d="M9.4 14.6L3 21M14.6 9.4L21 3" />
      {dim === 3 ? <path d="M12 8.4V2M10 4l2-2 2 2M12 15.6V22" /> : null}
    </>
  );
}

function prismatic(dim: 2 | 3): ReactNode {
  return dim === 2 ? (
    <>
      <path d="M2 17h20M2 20h20" />
      <rect x="8" y="8" width="8" height="9" rx="1" />
      <path d="M5 12.5H2.5M19 12.5h2.5" />
    </>
  ) : (
    <>
      <path d="M2 21l4-5h16l-4 5zM6 16l-1-1M22 16l-1-1" />
      <path d="M9 15V8h7v7" />
      <path d="M9 8l2-2h7l-2 2M16 8l2-2v7" />
    </>
  );
}

export const MULTIBOND_GLYPHS: Record<string, Glyph> = {
  // ---------------------------------------------------------------- bodies
  "pl-rigid-body-2d": () => body(2),
  "sp-rigid-body-3d": () => body(3),
  "ct-impact-body-3d": () => (
    <>
      <path d="M5 13h9v8H5zM5 13l3-3h9v8l-3 3M14 13l3-3" />
      <path d="M2 21.5h20" />
      <path d="M19.5 2.5v6M16.5 5.5h6" />
    </>
  ),
  "ct-impact-inertia-3d": () => (
    <>
      <circle cx="11" cy="11.5" r="6" />
      <ellipse cx="11" cy="11.5" rx="6" ry="2.2" />
      <path d="M2 19.5h20" />
      <path d="M19.5 2.5v6M16.5 5.5h6" />
    </>
  ),

  // ---------------------------------------------------------------- joints
  "mb-revolute-2d": () => revolute(2),
  "pl-revolute-2d-compliant": () => withMarker(revolute(2), "compliant"),
  "pl-revolute-2d-friction": () => withMarker(revolute(2), "friction"),
  "pl-revolute-2d-limit": () => withMarker(revolute(2), "limit"),
  "pl-revolute-2d-rigid": () => withMarker(revolute(2), "rigid"),
  "sp-revolute-3d": () => revolute(3),
  "sp-revolute-3d-compliant": () => withMarker(revolute(3), "compliant"),
  "sp-revolute-3d-friction": () => withMarker(revolute(3), "friction"),
  "sp-revolute-3d-limit": () => withMarker(revolute(3), "limit"),
  "pl-prismatic-2d": () => prismatic(2),
  "sp-prismatic-3d": () => prismatic(3),
  "sp-prismatic-3d-compliant": () => withMarker(prismatic(3), "compliant"),
  "sp-prismatic-3d-friction": () => withMarker(prismatic(3), "friction"),
  "sp-prismatic-3d-limit": () => withMarker(prismatic(3), "limit"),
  "sp-helical-3d": () => (
    <>
      <path d="M6 3h12M10 3v18M14 3v18M10 21l2 1.5 2-1.5" />
      <path d="M10 7l4-1.5M10 11l4-1.5M10 15l4-1.5M10 19l4-1.5" />
    </>
  ),
  "sp-cylindrical-3d": () => (
    <>
      <path d="M12 2v5M12 17v5" />
      <path d="M6.5 8v8M17.5 8v8M6.5 8a5.5 2 0 0 1 11 0M6.5 8a5.5 2 0 0 0 11 0M6.5 16a5.5 2 0 0 0 11 0" />
      <path d="M20.5 9.5a4 4 0 0 1 0 5M20.5 14.5l-2-.2M20.5 14.5l.3-2" />
    </>
  ),
  "sp-universal-3d": () => (
    <>
      <path d="M12 2v20M2 12h20" />
      <path d="M12 6.5l5.5 5.5-5.5 5.5L6.5 12z" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
    </>
  ),
  "sp-spherical-3d": () => (
    <>
      <path d="M5 11v1.5a7 7 0 0 0 14 0V11" />
      <circle cx="12" cy="10.5" r="4" />
      <path d="M12 6.5V2M12 19.5V22" />
    </>
  ),
  "sp-planar-3d": () => (
    <>
      <path d="M2 21l5-7h15l-5 7z" />
      <path d="M9 12V5h6v7" />
      <path d="M9 5l1.8-2H17l-2 2M15 12l2-2.2V3" />
    </>
  ),
  "pl-free-2d": () => (
    <>
      <rect x="8.5" y="8.5" width="7" height="7" rx="1" />
      <path d="M12 7V2M10 4l2-2 2 2M12 17v5M10 20l2 2 2-2M7 12H2M4 10l-2 2 2 2M17 12h5M20 10l2 2-2 2" />
    </>
  ),
  "sp-free-3d": () => (
    <>
      <rect x="8.5" y="8.5" width="7" height="7" rx="1" />
      <path d="M12 7V2M10 4l2-2 2 2M17 12h5M20 10l2 2-2 2M7 17l-4.5 4.5M2.5 18.5v3h3" />
    </>
  ),
  "pl-fixed-joint-2d": () => (
    <>
      <rect x="2.5" y="7.5" width="8" height="9" rx="1" />
      <rect x="13.5" y="7.5" width="8" height="9" rx="1" />
      <path d="M10.5 12h3" />
      <circle cx="12" cy="12" r="2.4" fill="currentColor" />
      <path d="M12 3.5v2.5M12 18v2.5" opacity="0.45" />
    </>
  ),

  // ------------------------------------------------------------ pose blocks
  "pl-joint-pose-2d": () => (
    <>
      {triad(5, 19, 2, 0.9)}
      <path d="M7 14.5L14.8 9" />
      <circle cx="17.5" cy="7.5" r="3.2" />
      <circle cx="17.5" cy="7.5" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
  "pl-local-pose-2d": () => (
    <>
      {triad(4, 20, 2, 0.95)}
      {triad(14, 11, 2, 0.8, -25)}
      <path d="M4 20L14 11" strokeDasharray="2 2" opacity="0.5" />
    </>
  ),
  "sp-local-pose-3d": () => (
    <>
      {triad(6, 19, 3, 0.9)}
      {triad(15, 11, 3, 0.7, -20)}
      <path d="M6 19L15 11" strokeDasharray="2 2" opacity="0.5" />
    </>
  ),
  "mb-compose-pose-2d": () => (
    <>
      {triad(3, 20, 2, 0.6)}
      {triad(14, 20, 2, 0.6, -20)}
      <path d="M5 13.5L9.5 8M16 13.5L14.5 8" />
      <circle cx="12" cy="6" r="3.2" />
    </>
  ),
  "mb-compose-pose-3d": () => (
    <>
      {triad(5, 19, 3, 0.55)}
      {triad(16, 19, 3, 0.55, -20)}
      <path d="M6 13L9.5 8M17 13L14.5 8" />
      <circle cx="12" cy="6" r="3.2" />
    </>
  ),
  "pl-pose-integrator-2d": () => (
    <>
      {triad(4, 20, 2, 0.8)}
      <path d="M19 2.5c-2.2-1.4-3.8-.4-3.8 2v10c0 2.4-1.6 3.4-3.8 2" />
    </>
  ),
  "mb-pose-integrator-3d": () => (
    <>
      {triad(6, 19, 3, 0.8)}
      <path d="M19 2.5c-2.2-1.4-3.8-.4-3.8 2v10c0 2.4-1.6 3.4-3.8 2" />
    </>
  ),

  // --------------------------------------------------------------- contact
  "ct-contact-point": () => (
    <>
      <path d="M2 18h20" />
      <circle cx="9.5" cy="13.5" r="4.5" />
      <path d="M19 18V5M16.8 7.3L19 4.8l2.2 2.5" />
    </>
  ),
  "ct-contact-surface": () => (
    <>
      <path d="M2 13h20" />
      <path d="M4 13l-2 3.5M8 13l-2 3.5M12 13l-2 3.5M16 13l-2 3.5M20 13l-2 3.5M24 13l-2 3.5" />
      <path d="M12 13V3M9.8 5.3L12 2.8l2.2 2.5" />
    </>
  ),
  "ct-switched-pivot-3d": () => (
    <>
      <path d="M2 20.5h20" />
      <path d="M7 20L4 9l9-3 4 9z" transform="rotate(-8 7 20)" />
      <circle cx="7" cy="20" r="2" fill="currentColor" />
      <path d="M14.5 5l5-3" />
      <circle cx="14.5" cy="5" r="1" fill="currentColor" stroke="none" />
      <circle cx="21.5" cy="5" r="1" fill="currentColor" stroke="none" />
    </>
  ),

  // ---------------------------------------------------------------- drives
  "drv-electric-drive": () => (
    <>
      <circle cx="9.5" cy="12" r="6.5" />
      {letterM(9.5, 15)}
      <path d="M16 12h6.5M20 9.5v5" />
      <path d="M2 5.5h3M2 18.5h3" opacity="0.5" />
    </>
  ),
  "drv-current-drive": () => (
    <>
      <circle cx="10" cy="17" r="5" />
      {letterM(10, 20)}
      <path d="M15 17h7.5M20 14.5v5" />
      <circle cx="5.5" cy="5.5" r="3.5" />
      <text
        x="5.5"
        y="7.6"
        textAnchor="middle"
        fontSize="6"
        fontStyle="italic"
        fontFamily="var(--font-ui)"
        fill="currentColor"
        stroke="none"
      >
        i
      </text>
      <path d="M9 5.5h1.5V12M8.7 10.2L10.5 12l1.8-1.8" />
    </>
  ),
  "drv-gearbox": () => (
    <>
      {gear(7.5, 8, 3.6)}
      {gear(15.5, 15.5, 4.8)}
    </>
  ),
  "drv-reaction-wheel": () => (
    <>
      <rect x="3" y="17" width="18" height="4.5" rx="1" />
      <circle cx="12" cy="9.5" r="6.5" />
      <circle cx="12" cy="9.5" r="1.2" fill="currentColor" stroke="none" />
      <path d="M12 3v13M5.5 9.5h13" opacity="0.5" />
      <path d="M12 16v1" />
    </>
  ),
};
