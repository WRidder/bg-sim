/**
 * The Diagram tab of the centre area (plan 7.2): session status, the canvas and
 * the hidden document snapshot that the end-to-end tests compare across a
 * reload. Auto-save runs here, next to the editor it saves.
 */

import { useCatalogStore } from "../library/catalogStore";
import { useDocumentStore } from "../state/documentStore";
import { useModelAutosave } from "../state/persistence";
import { useProjectSession } from "../state/session";
import { useInlineInterfaceSync } from "../code/inlineSync";
import { Canvas } from "./Canvas";

export function DiagramTab() {
  const { status, error, retry } = useProjectSession();
  const doc = useDocumentStore((state) => state.doc);
  const saveError = useDocumentStore((state) => state.saveError);
  const modelName = useDocumentStore((state) => state.modelName);
  const index = useCatalogStore((state) => state.index);

  useModelAutosave();
  useInlineInterfaceSync();

  if (status === "idle" || status === "loading" || (status === "ready" && (doc === null || index === null))) {
    return (
      <div className="diagram-state" data-testid="diagram-loading" role="status">
        <p>Opening {modelName ?? "the model"}…</p>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="diagram-state diagram-state--error" data-testid="diagram-error" role="alert">
        <p className="diagram-state__title">The model could not be opened</p>
        <p className="diagram-state__detail">{error ?? "The backend did not answer."}</p>
        <button type="button" className="button" onClick={retry} data-testid="diagram-retry">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="diagram" data-testid="diagram-tab">
      {saveError !== null ? (
        <div className="diagram__banner" role="alert" data-testid="save-error">
          {saveError}
        </div>
      ) : null}
      <Canvas />
      <pre hidden data-testid="document-json">
        {JSON.stringify(doc)}
      </pre>
    </div>
  );
}
