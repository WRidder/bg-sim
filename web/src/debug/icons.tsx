/**
 * Inline SVG icons of the run bar and the debug controls (plan 7.9), in the style of the VS Code and
 * Chrome DevTools debug toolbars. Every icon is drawn on a 16x16 grid in `currentColor`, so the button
 * colour (and its dimmed disabled state) applies in both themes. The icons are decorative: the button
 * carries the accessible name (`aria-label`) and the tooltip.
 */

import type { ReactNode } from "react";

export interface DebugIconProps {
  /** Rendered width and height in px (default 16). */
  size?: number;
  className?: string;
}

function Icon({ size = 16, className, children }: DebugIconProps & { children: ReactNode }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

/** Run: a play triangle. */
export function RunIcon(props: DebugIconProps) {
  return (
    <Icon {...props}>
      <path d="M4.5 2.75v10.5L13 8z" fill="currentColor" />
    </Icon>
  );
}

/** Debug (start a debug run): a bug. */
export function DebugIcon(props: DebugIconProps) {
  return (
    <Icon {...props}>
      <path d="M5.5 4.5a2.5 2.5 0 0 1 5 0" />
      <rect x="4.5" y="5" width="7" height="8.75" rx="3.5" fill="currentColor" stroke="none" />
      <path d="M2.5 6.5l2 1M13.5 6.5l-2 1M2 10h2.5M14 10h-2.5M2.5 13.5l2-1.25M13.5 13.5l-2-1.25" />
    </Icon>
  );
}

/** Stop: a square. */
export function StopIcon(props: DebugIconProps) {
  return (
    <Icon {...props}>
      <rect x="3" y="3" width="10" height="10" rx="1.25" fill="currentColor" stroke="none" />
    </Icon>
  );
}

/** Continue: a bar and a play triangle. */
export function ContinueIcon(props: DebugIconProps) {
  return (
    <Icon {...props}>
      <rect x="2.5" y="3" width="2.25" height="10" rx="0.5" fill="currentColor" stroke="none" />
      <path d="M7 3v10l6.5-5z" fill="currentColor" />
    </Icon>
  );
}

/** Pause: two bars. */
export function PauseIcon(props: DebugIconProps) {
  return (
    <Icon {...props}>
      <rect x="3.5" y="3" width="3" height="10" rx="0.75" fill="currentColor" stroke="none" />
      <rect x="9.5" y="3" width="3" height="10" rx="0.75" fill="currentColor" stroke="none" />
    </Icon>
  );
}

/** Step into (the finest step, one statement): an arrow down to a dot. */
export function StepIntoIcon(props: DebugIconProps) {
  return (
    <Icon {...props}>
      <path d="M8 1.75v7.5M4.75 6l3.25 3.25L11.25 6" />
      <circle cx="8" cy="13" r="1.75" fill="currentColor" stroke="none" />
    </Icon>
  );
}

/** Step over (the rest of the tick): a curved arrow over a dot. */
export function StepOverIcon(props: DebugIconProps) {
  return (
    <Icon {...props}>
      <path d="M2.25 9.5a5.9 5.9 0 0 1 11-2.5" />
      <path d="M13.75 3.5v3.75H10" />
      <circle cx="8" cy="13" r="1.75" fill="currentColor" stroke="none" />
    </Icon>
  );
}

/** More commands: three dots. */
export function MoreIcon(props: DebugIconProps) {
  return (
    <Icon {...props}>
      <circle cx="3" cy="8" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="8" cy="8" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="13" cy="8" r="1.4" fill="currentColor" stroke="none" />
    </Icon>
  );
}

/** Run to (a time): an arrow up to a bar, like "Run to cursor". */
export function RunToIcon(props: DebugIconProps) {
  return (
    <Icon {...props}>
      <path d="M1.75 8h8.5M7.25 4.75L10.5 8l-3.25 3.25" />
      <path d="M13.5 2.75v10.5" />
    </Icon>
  );
}
