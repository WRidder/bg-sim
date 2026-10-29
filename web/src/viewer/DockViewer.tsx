import { useMemo, useState } from "react";

import type { BuiltScene } from "../scene/build";
import { SceneView } from "../scene/SceneView";
import { BindingsEditor } from "./BindingsEditor";
import { PlaybackBar, playbackKeyHandler } from "./PlaybackBar";
import { useBindableSignals, useModelBindings, useViewerPlayback } from "./playbackHook";
import { useViewerDetachStore } from "./detachStore";
import type { ViewerProps } from "./Viewer";

export interface DockViewerProps {
  /** False while the 3D View dock tab is not the active one. */
  active: boolean;
  /** Test seam, see `ViewerProps.createEngine`. */
  createEngine?: ViewerProps["createEngine"];
  /** The popup window this view is shown in (W5.5); absent in the dock. Playback frames run on its clock. */
  hostWindow?: Window;
}

/**
 * The body of the dock's 3D View tab: the viewer with the open model's SDF scene (W5.2), the playback bar
 * and the binding table (W5.3), or the empty scene with a note on how to add one.
 */
export default function DockViewer({ active, createEngine, hostWindow }: DockViewerProps) {
  const detach = useViewerDetachStore((s) => s.detach);
  const attach = useViewerDetachStore((s) => s.attach);
  const detachError = useViewerDetachStore((s) => s.error);
  const detached = hostWindow !== undefined;
  const [built, setBuilt] = useState<BuiltScene | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const bindings = useModelBindings();
  const signals = useBindableSignals();
  const { playback, snapshot, streamError, streamNote } = useViewerPlayback(built, active, hostWindow ?? null);
  const onKeyDown = useMemo(() => playbackKeyHandler(playback), [playback]);

  const extras =
    built === null ? null : (
      <>
        <PlaybackBar
          playback={playback}
          snapshot={snapshot}
          streamError={streamError}
          streamNote={streamNote}
          hasBindings={bindings.length > 0}
          bindingsOpen={editing}
          onToggleBindings={() => {
            setEditing((v) => !v);
            setHover(null);
          }}
        />
        {editing ? <BindingsEditor built={built} bindings={bindings} signals={signals} onHover={setHover} /> : null}
      </>
    );
  return (
    <SceneView active={active} createEngine={createEngine} onBuilt={setBuilt} highlight={hover} onKeyDown={onKeyDown} extras={extras}
      toolbarEnd={
        <>
          <button
            type="button"
            className="viewer__button"
            data-testid={detached ? "dock-viewer-button" : "detach-viewer"}
            title={detached ? "Move the 3D view back into the bottom dock" : "Open the 3D view in a separate browser window"}
            onClick={() => {
              if (detached) attach();
              else detach();
            }}
          >
            {detached ? "Dock" : "Detach"}
          </button>
          {detachError !== null && !detached ? (
            <span className="viewer__note" role="alert" data-testid="viewer-detach-error">
              {detachError}
            </span>
          ) : null}
        </>
      }
    />
  );
}
