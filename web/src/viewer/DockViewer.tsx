import { useMemo, useState } from "react";

import type { BuiltScene } from "../scene/build";
import { SceneView } from "../scene/SceneView";
import { BindingsEditor } from "./BindingsEditor";
import { PlaybackBar, playbackKeyHandler } from "./PlaybackBar";
import { useBindableSignals, useModelBindings, useViewerPlayback } from "./playbackHook";
import type { ViewerProps } from "./Viewer";

export interface DockViewerProps {
  /** False while the 3D View dock tab is not the active one. */
  active: boolean;
  /** Test seam, see `ViewerProps.createEngine`. */
  createEngine?: ViewerProps["createEngine"];
}

/**
 * The body of the dock's 3D View tab: the viewer with the open model's SDF scene (W5.2), the playback bar
 * and the binding table (W5.3), or the empty scene with a note on how to add one.
 */
export default function DockViewer({ active, createEngine }: DockViewerProps) {
  const [built, setBuilt] = useState<BuiltScene | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const bindings = useModelBindings();
  const signals = useBindableSignals();
  const { playback, snapshot, streamError } = useViewerPlayback(built, active);
  const onKeyDown = useMemo(() => playbackKeyHandler(playback), [playback]);

  const extras =
    built === null ? null : (
      <>
        <PlaybackBar
          playback={playback}
          snapshot={snapshot}
          streamError={streamError}
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
  return <SceneView active={active} createEngine={createEngine} onBuilt={setBuilt} highlight={hover} onKeyDown={onKeyDown} extras={extras} />;
}
