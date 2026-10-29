/**
 * The Open dialog (plan 7.2): switch project or model, start a new project or
 * model, or copy an example. The URL is the session route (`?project=&model=`),
 * so opening a model navigates to a linkable URL after saving the current
 * document; a model that does not exist yet opens as a new empty document
 * (the same rule as `src/state/session.ts`).
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  createProject,
  listExamples,
  listProjects,
  ProjectApiError,
  type ProjectSummary,
} from "../state/modelApi";
import { useDocumentStore } from "../state/documentStore";
import { DEFAULT_MODEL } from "../state/session";
import {
  errorMessage,
  firstModel,
  importSample as importSampleProject,
  nameIssue,
  openSession as openSessionRoute,
  SampleImportError,
} from "./openSession";
import { useDialogFocus } from "./useDialogFocus";

export interface OpenDialogProps {
  open: boolean;
  onClose: () => void;
}

export function OpenDialog({ open, onClose }: OpenDialogProps) {
  const currentProject = useDocumentStore((state) => state.project);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [examples, setExamples] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(currentProject);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [newProject, setNewProject] = useState("");
  const [newModel, setNewModel] = useState("");
  const dialog = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const [projectList, exampleList] = await Promise.all([listProjects(), listExamples()]);
      setProjects(projectList);
      setExamples(exampleList);
      setSelected((current) => {
        if (current !== null && projectList.some((entry) => entry.name === current)) {
          return current;
        }
        const openProjectName = useDocumentStore.getState().project;
        if (
          openProjectName !== null &&
          projectList.some((entry) => entry.name === openProjectName)
        ) {
          return openProjectName;
        }
        return projectList[0]?.name ?? null;
      });
      setStatus("ready");
    } catch (cause) {
      setStatus("error");
      setError(errorMessage(cause));
    }
  }, []);

  useEffect(() => {
    if (!open) {
      return;
    }
    setNewProject("");
    setNewModel("");
    setBusy(null);
    void load();
  }, [load, open]);

  useDialogFocus(open, dialog, onClose);

  const openSession = useCallback(async (project: string, model: string) => {
    setBusy(`open:${project}/${model}`);
    const result = await openSessionRoute(project, model);
    setBusy(null);
    if (!result.ok) {
      setError(result.error);
    }
  }, []);

  const createNewProject = useCallback(async () => {
    const issue = nameIssue(newProject, "project");
    if (issue !== null) {
      setError(issue);
      return;
    }
    const name = newProject.trim();
    setBusy("project");
    setError(null);
    try {
      const created = await createProject(name);
      await openSession(created.name, firstModel(created.models) ?? DEFAULT_MODEL);
    } catch (cause) {
      if (cause instanceof ProjectApiError && cause.status === 409) {
        setSelected(name);
        setError(`A project named “${name}” already exists. Select it on the left to open it.`);
      } else {
        setError(errorMessage(cause));
      }
    } finally {
      setBusy(null);
    }
  }, [newProject, openSession]);

  const createNewModel = useCallback(async () => {
    if (selected === null) {
      return;
    }
    const issue = nameIssue(newModel, "model");
    if (issue !== null) {
      setError(issue);
      return;
    }
    setBusy("model");
    setError(null);
    await openSession(selected, newModel.trim());
    setBusy(null);
  }, [newModel, openSession, selected]);

  const importSample = useCallback(
    async (sample: string) => {
      setBusy(`sample:${sample}`);
      setError(null);
      try {
        const result = await importSampleProject(sample, new Set(projects.map((entry) => entry.name)));
        if (!result.ok) {
          setError(result.error);
        }
      } catch (cause) {
        if (cause instanceof SampleImportError) {
          if (cause.conflict) {
            await load();
          }
          if (cause.project !== null) {
            setSelected(cause.project);
          }
          setError(cause.message);
        } else {
          setError(errorMessage(cause));
        }
      } finally {
        setBusy(null);
      }
    },
    [load, projects],
  );

  if (!open) {
    return null;
  }

  const selectedProject = projects.find((entry) => entry.name === selected) ?? null;
  const models = selectedProject?.models ?? [];

  return (
    <div
      className="dialog-backdrop"
      data-testid="open-dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        className="open-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="open-dialog-title"
        data-testid="open-dialog"
        ref={dialog}
        tabIndex={-1}
      >
        <header className="open-dialog__header">
          <h2 className="open-dialog__title" id="open-dialog-title">
            Open a project or model
          </h2>
          <button
            type="button"
            className="icon-button"
            data-testid="open-dialog-close"
            aria-label="Close"
            title="Close (Esc)"
            onClick={onClose}
          >
            ✕
          </button>
        </header>

        {error !== null ? (
          <p className="open-dialog__error" role="alert" data-testid="open-dialog-error">
            {error}
          </p>
        ) : null}

        <div className="open-dialog__body">
          <section className="open-dialog__column" aria-label="Projects">
            <div className="open-dialog__column-head">
              <h3 className="open-dialog__heading">Projects</h3>
              <span className="open-dialog__count">
                {status === "ready" ? projects.length : "…"}
              </span>
            </div>
            {status === "loading" ? (
              <p className="open-dialog__empty">Loading the project list…</p>
            ) : null}
            {status === "ready" && projects.length === 0 ? (
              <p className="open-dialog__empty">
                No projects yet. Create one below or import a sample.
              </p>
            ) : null}
            <ul className="open-dialog__list" data-testid="open-project-list">
              {projects.map((entry) => (
                <li key={entry.name}>
                  <button
                    type="button"
                    className={`open-dialog__row${entry.name === selected ? " is-selected" : ""}`}
                    data-testid={`project-option-${entry.name}`}
                    aria-pressed={entry.name === selected}
                    onClick={() => {
                      setSelected(entry.name);
                      setError(null);
                    }}
                    onDoubleClick={() => {
                      if (entry.models.length > 0) {
                        void openSession(entry.name, entry.models[0] ?? DEFAULT_MODEL);
                      }
                    }}
                  >
                    <span className="open-dialog__name">{entry.name}</span>
                    <span className="open-dialog__meta">
                      {entry.models.length} model{entry.models.length === 1 ? "" : "s"}
                      {entry.valid ? "" : " · invalid"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <form
              className="open-dialog__form"
              onSubmit={(event) => {
                event.preventDefault();
                void createNewProject();
              }}
            >
              <input
                className="open-dialog__input"
                data-testid="new-project-name"
                placeholder="New project name"
                aria-label="New project name"
                value={newProject}
                onChange={(event) => setNewProject(event.target.value)}
              />
              <button
                type="submit"
                className="button"
                data-testid="create-project"
                disabled={busy !== null || newProject.trim().length === 0}
              >
                New project
              </button>
            </form>
          </section>

          <section className="open-dialog__column" aria-label="Models and examples">
            <div className="open-dialog__column-head">
              <h3 className="open-dialog__heading">{selected ?? "Models"}</h3>
              <span className="open-dialog__count">{models.length}</span>
            </div>
            {selected === null ? (
              <p className="open-dialog__empty">Select a project to see its models.</p>
            ) : models.length === 0 ? (
              <p className="open-dialog__empty">No models yet. Start one below.</p>
            ) : (
              <ul className="open-dialog__list" data-testid="open-model-list">
                {models.map((model) => (
                  <li key={model}>
                    <button
                      type="button"
                      className="open-dialog__row"
                      data-testid={`model-option-${model}`}
                      disabled={busy !== null}
                      onClick={() => void openSession(selected, model)}
                    >
                      <span className="open-dialog__name">{model}</span>
                      <span className="open-dialog__meta">open</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {selected !== null ? (
              <form
                className="open-dialog__form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void createNewModel();
                }}
              >
                <input
                  className="open-dialog__input"
                  data-testid="new-model-name"
                  placeholder="New model name"
                  aria-label="New model name"
                  value={newModel}
                  onChange={(event) => setNewModel(event.target.value)}
                />
                <button
                  type="submit"
                  className="button"
                  data-testid="create-model"
                  disabled={busy !== null || newModel.trim().length === 0}
                >
                  New model
                </button>
              </form>
            ) : null}

            <div className="open-dialog__examples">
              <div className="open-dialog__column-head">
                <h3 className="open-dialog__heading">Samples</h3>
                <span className="open-dialog__count">{examples.length}</span>
              </div>
              <p className="open-dialog__note">
                Samples are read-only templates. Opening one imports a copy into your
                projects; the sample itself is never changed.
              </p>
              {examples.length === 0 ? (
                <p className="open-dialog__empty">No samples are installed.</p>
              ) : (
                <ul className="open-dialog__list" data-testid="open-sample-list">
                  {examples.map((example) => (
                    <li key={example}>
                      <button
                        type="button"
                        className="open-dialog__row"
                        data-testid={`sample-option-${example}`}
                        disabled={busy !== null}
                        title={`Import ${example} as a new project`}
                        onClick={() => void importSample(example)}
                      >
                        <span className="open-dialog__name">{example}</span>
                        <span className="open-dialog__meta">import a copy</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
