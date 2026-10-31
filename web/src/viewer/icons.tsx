/**
 * Monochrome line icons for the 3D view toolbar, after the ctrlX cell view
 * (`framework/hmi/src/viewer/icons.tsx`, plan 7.6): 24 px grid, currentColor.
 */

import type { ReactElement, ReactNode } from "react";

import type { CameraPreset } from "./viewerScene";

function Icon({ children }: { readonly children: ReactNode }): ReactElement {
  return (
    <svg
      viewBox="0 0 24 24"
      width={18}
      height={18}
      aria-hidden="true"
      className="viewer__icon"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinejoin="round"
      strokeLinecap="round"
    >
      {children}
    </svg>
  );
}

const CUBE_TOP = "M12 3 20 7.5 12 12 4 7.5Z";
const CUBE_LEFT = "M4 7.5 12 12v9l-8-4.5Z";
const CUBE_RIGHT = "M20 7.5 12 12v9l8-4.5Z";

function Cube({ fill }: { readonly fill?: "top" | "left" | "right" }): ReactElement {
  return (
    <Icon>
      {fill === "top" ? <path d={CUBE_TOP} fill="currentColor" /> : null}
      {fill === "left" ? <path d={CUBE_LEFT} fill="currentColor" /> : null}
      {fill === "right" ? <path d={CUBE_RIGHT} fill="currentColor" /> : null}
      <path d={CUBE_TOP} />
      <path d={CUBE_LEFT} />
      <path d={CUBE_RIGHT} />
    </Icon>
  );
}

/** View directions: the cube face looked at is filled; iso shows the plain cube. */
export const ViewIcons: Record<CameraPreset, () => ReactElement> = {
  iso: () => (
    <Icon>
      <path d={CUBE_TOP} />
      <path d={CUBE_LEFT} />
      <path d={CUBE_RIGHT} />
      <circle cx={12} cy={12} r={1.6} fill="currentColor" />
    </Icon>
  ),
  top: () => <Cube fill="top" />,
  front: () => <Cube fill="left" />,
  side: () => <Cube fill="right" />,
};

export const FitIcon = (): ReactElement => (
  <Icon>
    <path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" />
    <rect x={9} y={9} width={6} height={6} rx={0.5} />
  </Icon>
);

export const OrthographicIcon = (): ReactElement => (
  <Icon>
    <path d="M4 8h10v10H4Z" />
    <path d="M4 8l6-4h10l-6 4M14 18l6-4V4" />
  </Icon>
);

export const FullscreenIcon = (): ReactElement => (
  <Icon>
    <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
  </Icon>
);

export const ExitFullscreenIcon = (): ReactElement => (
  <Icon>
    <path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" />
  </Icon>
);

/** Open in a separate window: a window with an arrow leaving it. */
export const DetachIcon = (): ReactElement => (
  <Icon>
    <path d="M13 4h7v7M20 4l-9 9" />
    <path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
  </Icon>
);

/** Back into the dock: an arrow into a panel at the bottom of a window. */
export const DockIcon = (): ReactElement => (
  <Icon>
    <rect x={3} y={4} width={18} height={16} rx={1} />
    <path d="M3 14h18" />
    <path d="M12 6v6M9.5 9.5 12 12l2.5-2.5" />
  </Icon>
);
