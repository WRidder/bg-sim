import { useCallback, useEffect, useState } from "react";

import { listModelCards, ProjectApiError, type ModelCardInfo } from "../state/modelApi";
import { libraryUrl } from "./leaveProject";
import { ModelCardGrid } from "./ModelCardGrid";
import { errorMessage, nameIssue, navigation, openSession } from "./openSession";

export interface ModelPickerProps {
  project: string;
}

/**
 * The page a project opens on (`?project=` without a model): a card per model
 * of the project, in the look of the example gallery, with a short description.
 * The user picks the model to edit; **New model** starts an empty one and
 * **All projects** goes back to the start page.
 */
export function ModelPicker({ project }: ModelPickerProps) {
  const [cards, setCards] = useState<ModelCardInfo[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "missing" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [newModel, setNewModel] = useState("");

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      setCards(await listModelCards(project));
      setStatus("ready");
    } catch (cause) {
      if (cause instanceof ProjectApiError && cause.status === 404) {
        setStatus("missing");
        return;
      }
      setStatus("error");
      setError(errorMessage(cause));
    }
  }, [project]);

  useEffect(() => {
    void load();
  }, [load]);

  const open = useCallback(
    async (model: string) => {
      setBusy(model);
      setError(null);
      const result = await openSession(project, model);
      if (!result.ok) {
        setBusy(null);
        setError(result.error);
      }
    },
    [project],
  );

  const create = useCallback(() => {
    const issue = nameIssue(newModel, "model");
    if (issue !== null) {
      setError(issue);
      return;
    }
    const name = newModel.trim();
    if (cards.some((card) => card.name.toLowerCase() === name.toLowerCase())) {
      setError(`The project already has a model named “${name}”. Open its card, or choose another name.`);
      return;
    }
    void open(name);
  }, [cards, newModel, open]);

  const back = (
    <a
      className="model-picker__back"
      href={libraryUrl()}
      data-testid="picker-back"
      onClick={(event) => {
        if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
          event.preventDefault();
          navigation.assign(libraryUrl());
        }
      }}
    >
      <span aria-hidden="true">← </span>All projects
    </a>
  );

  return (
    <main className="start-page model-picker" id="main" data-testid="model-picker" data-state={status}>
      <div className="start-page__inner">
        <header className="model-picker__hero">
          {back}
          <h1 className="model-picker__title" data-testid="picker-project">
            {project}
          </h1>
          <p className="model-picker__lead">
            {status === "ready"
              ? cards.length === 0
                ? "This project has no models yet. Start one below."
                : `${cards.length} model${cards.length === 1 ? "" : "s"}. Choose the one to open in the editor.`
              : status === "loading"
                ? "Loading the models…"
                : ""}
          </p>
          {status === "ready" ? (
            <form
              className="start-page__new"
              onSubmit={(event) => {
                event.preventDefault();
                create();
              }}
            >
              <label className="start-page__label" htmlFor="picker-new-model-name">
                New model
              </label>
              <input
                id="picker-new-model-name"
                className="open-dialog__input start-page__input"
                data-testid="picker-new-model-name"
                placeholder="Model name, e.g. Model2"
                value={newModel}
                onChange={(event) => setNewModel(event.target.value)}
              />
              <button
                type="submit"
                className="button"
                data-testid="picker-create-model"
                disabled={busy !== null || newModel.trim().length === 0}
              >
                Create model
              </button>
            </form>
          ) : null}
        </header>

        {error !== null ? (
          <p className="start-page__error" role="alert" data-testid="picker-error">
            <span aria-hidden="true">⚠ </span>
            {error}
          </p>
        ) : null}

        {status === "missing" ? (
          <p className="start-page__empty" data-testid="picker-missing">
            There is no project named “{project}”. Go back to all projects to open or create one.
          </p>
        ) : null}
        {status === "error" ? (
          <p className="start-page__empty">
            The models could not be listed.{" "}
            <button type="button" className="button" onClick={() => void load()}>
              Retry
            </button>
          </p>
        ) : null}

        {status === "ready" && cards.length > 0 ? (
          <section className="start-page__section" aria-labelledby="picker-models-heading">
            <h2 className="start-page__heading" id="picker-models-heading">
              Models
            </h2>
            <ModelCardGrid project={project} cards={cards} busy={busy} onOpen={(model) => void open(model)} />
          </section>
        ) : null}
      </div>
    </main>
  );
}
