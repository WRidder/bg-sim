import { EmptyState } from "../app/EmptyState";
import { Viewer, type ViewerProps } from "./Viewer";

export interface DockViewerProps {
  /** False while the 3D View dock tab is not the active one. */
  active: boolean;
  /** Test seam, see `ViewerProps.createEngine`. */
  createEngine?: ViewerProps["createEngine"];
}

/**
 * The body of the dock's 3D View tab. Models have no scene yet (scenes arrive with the SDF
 * loader, W5.2), so the empty scene is drawn with an explanation over it.
 */
export default function DockViewer({ active, createEngine }: DockViewerProps) {
  return (
    <Viewer
      active={active}
      createEngine={createEngine}
      overlay={
        <EmptyState
          title="No scene"
          hint="This model has no 3D scene yet. Open a model with a 3D scene to see it here; drag to orbit, right-drag to pan, scroll to zoom."
        />
      }
    />
  );
}
