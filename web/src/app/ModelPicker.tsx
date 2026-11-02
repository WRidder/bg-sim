import { lazy, Suspense, useCallback, useEffect, useState } from "react";

import { listModelCards, ProjectApiError, type ModelCardInfo } from "../state/modelApi";
import { EmptyState } from "./EmptyState";
import { libraryUrl } from "./leaveProject";
import { ModelCardGrid } from "./ModelCardGrid";
import { errorMessage, nameIssue, navigation, openSession } from "./openSession";
import { projectTabUrl, readScreenTab } from "./route";
import { TabStrip } from "./TabStrip";

// The docs browser pulls in the Markdown stack (KaTeX); it loads when the Docs tab is opened.
const ProjectDocsBrowser = lazy(() => import("../docs/ProjectDocsBrowser"));

export interface ModelPickerProps {
  project: string;
}

type PickerTab = "models" | "docs";

const PICKER_TABS = [
  { id: "models", label: "Models" },
  { id: "docs", label: "Docs" },
] as const;

const TAB_KEY = "bgsim.projectTab.";

/** The tab the URL asks for (`tab=docs`), else the one last used in this project. */
function initialTab(project: string): PickerTab {
  const { tab } = readScreenTab();
  if (tab === "docs" || tab === "models") {
    return tab;
  }
  try {
    return localStorage.getItem(TAB_KEY + project) === "docs" ? "docs" : "models";
  } catch {
    return "models";
  }
}

/**
 * The page a project opens on (`?project=` without a model), in two tabs. **Models** (the
 * default): a card per model of the project, in the look of the example gallery, with a short
 * description; the user picks the model to edit, **New model** starts an empty one.
 * **Docs**: every docs page of the project (project docs and each model's docs) in one tree
 * with a reading pane (`?project=p&tab=docs&page=project:<id>`). **All projects** goes back to
 * the start page.
 */
export function ModelPicker({ project }: ModelPickerProps) {
  const [tab, setTab] = useState<PickerTab>(() => initialTab(project));
  const [docsPage, setDocsPage] = useState<string | null>(() => readScreenTab().page);
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

  // The tab and the docs page live in the URL (deep links) and the tab per project in storage.
  useEffect(() => {
    try {
      localStorage.setItem(TAB_KEY + project, tab);
    } catch {
      // Only a convenience; ignore blocked storage.
    }
    const url = projectTabUrl(project, tab === "docs" ? "docs" : null, tab === "docs" ? docsPage : null);
    if (url !== window.location.href) {
      window.history.replaceState(window.history.state, "", url);
    }
  }, [project, tab, docsPage]);

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

        {status !== "missing" ? (
          <div className="model-picker__tabs">
            <TabStrip tabs={PICKER_TABS} active={tab} onSelect={setTab} ariaLabel="Project" idPrefix="picker" />
            <div
              className="model-picker__panel"
              role="tabpanel"
              id={`picker-panel-${tab}`}
              aria-labelledby={`picker-tab-${tab}`}
              data-testid={`picker-panel-${tab}`}
            >
              {tab === "models" ? (
                status === "ready" && cards.length > 0 ? (
                  <section className="start-page__section" aria-labelledby="picker-models-heading">
                    <h2 className="start-page__heading" id="picker-models-heading">
                      Models
                    </h2>
                    <ModelCardGrid project={project} cards={cards} busy={busy} onOpen={(model) => void open(model)} />
                  </section>
                ) : null
              ) : (
                <Suspense fallback={<EmptyState title="Loading the docs" hint="One moment." />}>
                  <ProjectDocsBrowser project={project} page={docsPage} onPageChange={setDocsPage} />
                </Suspense>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </main>
  );
}
