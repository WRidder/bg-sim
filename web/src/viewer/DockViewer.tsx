import { SceneView } from "../scene/SceneView";
import type { ViewerProps } from "./Viewer";

export interface DockViewerProps {
  /** False while the 3D View dock tab is not the active one. */
  active: boolean;
  /** Test seam, see `ViewerProps.createEngine`. */
  createEngine?: ViewerProps["createEngine"];
}

/**
 * The body of the dock's 3D View tab: the viewer with the open model's SDF scene (W5.2), or the
 * empty scene with a note on how to add one.
 */
export default function DockViewer({ active, createEngine }: DockViewerProps) {
  return <SceneView active={active} createEngine={createEngine} />;
}
