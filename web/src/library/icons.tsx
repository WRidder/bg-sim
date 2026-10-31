/**
 * Inline SVG icons of the library panel, drawn like src/debug/icons.tsx: a 16x16 grid in
 * `currentColor`, so the button colour applies in both themes. The icons are decorative; the
 * button carries the accessible name.
 */

import type { ShapeKind } from "../contracts/model";

export interface LibraryIconProps {
  /** Rendered width and height in px (default 16). */
  size?: number;
  className?: string;
}

/** Quick settings: an eight-tooth cog with a round hole. */
export function CogIcon({ size = 16, className }: LibraryIconProps) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 16 16"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        fillRule="evenodd"
        d="M6.53 2.7L6.75 0.71L9.25 0.71L9.47 2.7L10.71 3.21L12.27 1.96L14.04 3.73L12.79 5.29L13.3 6.53L15.29 6.75L15.29 9.25L13.3 9.47L12.79 10.71L14.04 12.27L12.27 14.04L10.71 12.79L9.47 13.3L9.25 15.29L6.75 15.29L6.53 13.3L5.29 12.79L3.73 14.04L1.96 12.27L3.21 10.71L2.7 9.47L0.71 9.25L0.71 6.75L2.7 6.53L3.21 5.29L1.96 3.73L3.73 1.96L5.29 3.21Z M10.4 8a2.4 2.4 0 1 0 -4.8 0a2.4 2.4 0 1 0 4.8 0Z"
      />
    </svg>
  );
}

/** Disclosure: a chevron pointing right; CSS rotates it down when the section is open. */
export function ChevronIcon({ size = 16, className }: LibraryIconProps) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M6 3.5L10.5 8L6 12.5" />
    </svg>
  );
}

/** List view: three rows, each a small square and a line. */
export function ListViewIcon({ size = 16, className }: LibraryIconProps) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 16 16"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M1.5 2.5h2.5v2.5h-2.5Z M1.5 6.75h2.5v2.5h-2.5Z M1.5 11h2.5v2.5h-2.5Z M5.75 3h8.75v1.5h-8.75Z M5.75 7.25h8.75v1.5h-8.75Z M5.75 11.5h8.75v1.5h-8.75Z"
      />
    </svg>
  );
}

/** Grid view: a 3x3 grid of squares, like the three-column tiles. */
export function GridViewIcon({ size = 16, className }: LibraryIconProps) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 16 16"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M1.5 1.5h3.5v3.5h-3.5Z M6.25 1.5h3.5v3.5h-3.5Z M11 1.5h3.5v3.5h-3.5Z M1.5 6.25h3.5v3.5h-3.5Z M6.25 6.25h3.5v3.5h-3.5Z M11 6.25h3.5v3.5h-3.5Z M1.5 11h3.5v3.5h-3.5Z M6.25 11h3.5v3.5h-3.5Z M11 11h3.5v3.5h-3.5Z"
      />
    </svg>
  );
}

/**
 * A background shape of the library's Shapes category, drawn in `currentColor` on a 40x40 grid:
 * the outline of a rectangle, rounded rectangle or ellipse, a diagonal line, or an arrow.
 */
export function ShapeGlyph({ kind, size = 16, className }: LibraryIconProps & { kind: ShapeKind }) {
  const stroke = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2.5,
    strokeLinecap: "round",
  } as const;
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 40 40"
      aria-hidden="true"
      focusable="false"
      data-shape-glyph={kind}
    >
      {kind === "rectangle" ? <rect x="5" y="10" width="30" height="20" {...stroke} /> : null}
      {kind === "roundedRectangle" ? (
        <rect x="5" y="10" width="30" height="20" rx="6" {...stroke} />
      ) : null}
      {kind === "ellipse" ? <ellipse cx="20" cy="20" rx="15" ry="10" {...stroke} /> : null}
      {kind === "line" ? <line x1="7" y1="31" x2="33" y2="9" {...stroke} /> : null}
      {kind === "arrow" ? (
        <>
          <line x1="7" y1="31" x2="28" y2="13.2" {...stroke} />
          <path d="M34 8 L22.4 11.2 L28.2 18.1 Z" fill="currentColor" />
        </>
      ) : null}
    </svg>
  );
}
