import { useEffect, useMemo, useState, type KeyboardEventHandler, type ReactNode } from "react";

import { EmptyState } from "../app/EmptyState";
import type { Diagnostic } from "../contracts/diagnostic";
import { useDiagnosticsStore } from "../diagnostics/store";
import { useDocumentStore } from "../state/documentStore";
import { Viewer, type ViewerProps } from "../viewer/Viewer";
import type { ViewerScene } from "../viewer/viewerScene";
import { fetchSceneText, meshSource, SceneFetchError } from "./api";
import { buildScene, type BuiltScene } from "./build";
import { resolveScene, type TreeEntry } from "./resolve";
import { e305, parseSdf } from "./sdf";
import { SceneTree } from "./SceneTree";
import "./scene.css";

/** `none`: the model has no scene. `loading`, `loaded`, `error`: the state of loading `scene.file`. */
export type SceneStatus = "none" | "loading" | "loaded" | "error";

interface Outcome {
  /** `project/file` the outcome belongs to. */
  readonly key: string;
  readonly built: BuiltScene | null;
  readonly tree: readonly TreeEntry[];
}

export interface SceneViewProps {
  /** False while the 3D View dock tab is not the active one. */
  active: boolean;
  /** Test seam, see `ViewerProps.createEngine`. */
  createEngine?: ViewerProps["createEngine"];
  /** The built scene once it exists, null while loading, after an error and on unmount (W5.3 bindings). */
  onBuilt?: (built: BuiltScene | null) => void;
  /** An entity to outline besides the selection (hover in the binding table). */
  highlight?: string | null;
  /** Keys pressed while the 3D view has focus (space toggles playback). */
  onKeyDown?: KeyboardEventHandler<HTMLDivElement>;
  /** Rendered under the viewer in the stage (playback bar, binding table). */
  extras?: ReactNode;
  /** Appended to the viewer toolbar (Detach / Dock, W5.5). */
  toolbarEnd?: ReactNode;
}

const NO_REFS: readonly string[] = [];

function describe(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * The 3D View: loads the open model's SDF scene (`doc.scene.file`) into the viewer, fits the
 * camera, lists the scene as a tree beside the view and publishes the scene's E305/E306
 * diagnostics to the Diagnostics panel. `data-state` is `none`, `loading`, `loaded` or `error`.
 */
export function SceneView({ active, createEngine, onBuilt, highlight = null, onKeyDown, extras, toolbarEnd }: SceneViewProps) {
  const project = useDocumentStore((state) => state.project);
  const sceneFile = useDocumentStore((state) => state.doc?.scene?.file ?? null);
  const [viewer, setViewer] = useState<ViewerScene | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const key = project !== null && sceneFile !== null ? `${project}/${sceneFile}` : null;

  useEffect(() => {
    if (viewer === null || project === null || sceneFile === null || key === null) return;
    const abort = new AbortController();
    let built: BuiltScene | null = null;
    const publish = (diagnostics: readonly Diagnostic[]) => {
      useDiagnosticsStore.getState().setViewerDiagnostics(diagnostics);
    };
    void (async () => {
      try {
        const text = await fetchSceneText(project, sceneFile, abort.signal);
        const parsed = parseSdf(text, sceneFile);
        const resolved = parsed.scene === null ? null : resolveScene(parsed.scene);
        const sdfScene = resolved?.scene ?? null;
        if (sdfScene === null) {
          publish([...parsed.diagnostics, ...(resolved?.diagnostics ?? [])]);
          setOutcome({ key, built: null, tree: [] });
          return;
        }
        const result = await buildScene(viewer, sdfScene, { loadMesh: meshSource(project, abort.signal), signal: abort.signal });
        built = result.scene;
        if (abort.signal.aborted) return;
        viewer.fit();
        publish([...parsed.diagnostics, ...result.diagnostics]);
        setOutcome({ key, built: result.scene, tree: sdfScene.tree });
      } catch (error) {
        if (abort.signal.aborted) return;
        const detail = describe(error);
        publish([
          e305(null, detail, error instanceof SceneFetchError ? "fix the scene field of the model or the file, then reopen the 3D View" : "check the scene file and reopen the 3D View"),
        ]);
        setOutcome({ key, built: null, tree: [] });
      }
    })();
    return () => {
      abort.abort();
      built?.dispose();
      publish([]);
      setSelected(null);
    };
  }, [viewer, project, sceneFile, key]);

  const current = outcome !== null && outcome.key === key ? outcome : null;
  const status: SceneStatus = key === null ? "none" : current === null ? "loading" : current.built === null ? "error" : "loaded";
  const built = current?.built ?? null;
  useEffect(() => {
    onBuilt?.(built);
    return () => {
      onBuilt?.(null);
    };
  }, [built, onBuilt]);
  const selection = useMemo(() => {
    if (built === null) return NO_REFS;
    const refs = new Set<string>();
    if (selected !== null) for (const r of built.visualsOf(selected)) refs.add(r);
    if (highlight !== null) for (const r of built.visualsOf(highlight)) refs.add(r);
    return refs.size === 0 ? NO_REFS : [...refs];
  }, [built, selected, highlight]);

  let overlay;
  if (status === "none") {
    overlay = (
      <EmptyState
        title="No 3D scene"
        hint={'This model has no 3D scene. To add one, store an SDF file in the project\'s scenes/ folder and set the model\'s scene to it (for example "scenes/robot.sdf"). Drag to orbit, right-drag to pan, scroll to zoom.'}
      />
    );
  } else if (status === "loading") {
    overlay = <EmptyState title="Loading the scene" hint={`Reading ${sceneFile ?? "the scene"}.`} />;
  } else if (status === "error") {
    overlay = <EmptyState title="The scene could not be shown" hint="The Diagnostics tab says why (E305). Fix the scene file, then reopen the 3D View." />;
  }

  return (
    <div className="scene-view" data-testid="scene-view" data-state={status} data-scene={sceneFile ?? ""}>
      {status === "loaded" && current !== null ? <SceneTree tree={current.tree} selected={selected} onSelect={setSelected} /> : null}
      <div className="scene-view__stage" tabIndex={0} role="group" aria-label="3D view" onKeyDown={onKeyDown} data-testid="scene-stage">
        <div className="scene-view__viewer">
          <Viewer active={active} createEngine={createEngine} onReady={setViewer} onSelect={setSelected} selection={selection} overlay={overlay} toolbarEnd={toolbarEnd} />
        </div>
        {extras}
      </div>
    </div>
  );
}
