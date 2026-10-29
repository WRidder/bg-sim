import { useCallback, useEffect, useMemo, useState } from "react";

import { ExampleGallery } from "../examples/ExampleGallery";
import { galleryExamples } from "../examples/gallery";
import {
  createProject,
  listExamples,
  listProjects,
  ProjectApiError,
  type ProjectSummary,
} from "../state/modelApi";
import { DEFAULT_MODEL } from "../state/session";
import {
  errorMessage,
  firstModel,
  importSample,
  nameIssue,
  openSession,
  SampleImportError,
} from "./openSession";

const RECENT_LIMIT = 6;

function byModifiedDescending(a: ProjectSummary, b: ProjectSummary): number {
  return (b.modified ?? "").localeCompare(a.modified ?? "") || a.name.localeCompare(b.name);
}

function modifiedText(value: string | null): string {
  if (value === null) {
    return "";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString();
}

/**
 * The start page (plan 7.8): shown while no project is open. It offers a new
 * project, the most recent projects and the example gallery. Samples are
 * read-only templates; "Open sample" imports an editable copy.
 */
export function StartPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [examples, setExamples] = useState<string[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [newProject, setNewProject] = useState("");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const [projectList, exampleList] = await Promise.all([listProjects(), listExamples()]);
      setProjects(projectList);
      setExamples(galleryExamples(exampleList));
      setStatus("ready");
    } catch (cause) {
      setStatus("error");
      setError(errorMessage(cause));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const recent = useMemo(
    () => [...projects].sort(byModifiedDescending).slice(0, RECENT_LIMIT),
    [projects],
  );

  const create = useCallback(async () => {
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
      const result = await openSession(created.name, firstModel(created.models) ?? DEFAULT_MODEL);
      if (!result.ok) {
        setError(result.error);
      }
    } catch (cause) {
      if (cause instanceof ProjectApiError && cause.status === 409) {
        setError(
          `A project named “${name}” already exists. Open it from the recent projects, or choose another name.`,
        );
      } else {
        setError(errorMessage(cause));
      }
    } finally {
      setBusy(null);
    }
  }, [newProject]);

  const openSample = useCallback(
    async (sample: string) => {
      setBusy(sample);
      setError(null);
      try {
        const result = await importSample(sample, new Set(projects.map((entry) => entry.name)));
        if (!result.ok) {
          setError(result.error);
        }
      } catch (cause) {
        if (cause instanceof SampleImportError && cause.conflict) {
          await load();
        }
        setError(errorMessage(cause));
      } finally {
        setBusy(null);
      }
    },
    [load, projects],
  );

  const openRecent = useCallback(async (entry: ProjectSummary) => {
    setBusy(`recent:${entry.name}`);
    const result = await openSession(entry.name, entry.models[0] ?? DEFAULT_MODEL);
    setBusy(null);
    if (!result.ok) {
      setError(result.error);
    }
  }, []);

  return (
    <main className="start-page" id="main" data-testid="start-page" data-state={status}>
      <div className="start-page__inner">
        <header className="start-page__hero">
          <h1 className="start-page__title">Model, simulate and see it move</h1>
          <p className="start-page__lead">
            Draw bond graphs, block diagrams and equations on one canvas, run them on the Julia
            worker and play the result in 3D. Start from a sample or create an empty project.
          </p>
          <form
            className="start-page__new"
            onSubmit={(event) => {
              event.preventDefault();
              void create();
            }}
          >
            <label className="start-page__label" htmlFor="start-new-project-name">
              New project
            </label>
            <input
              id="start-new-project-name"
              className="open-dialog__input start-page__input"
              data-testid="start-new-project-name"
              placeholder="Project name, e.g. my-motor"
              value={newProject}
              onChange={(event) => setNewProject(event.target.value)}
            />
            <button
              type="submit"
              className="button button--primary"
              data-testid="start-create-project"
              disabled={busy !== null || newProject.trim().length === 0}
            >
              {busy === "project" ? "Creating…" : "Create project"}
            </button>
            <span className="start-page__shortcut">
              Press <kbd>Ctrl</kbd>+<kbd>O</kbd> to open a project, <kbd>?</kbd> for all shortcuts.
            </span>
          </form>
        </header>

        {error !== null ? (
          <p className="start-page__error" role="alert" data-testid="start-page-error">
            <span aria-hidden="true">⚠ </span>
            {error}
          </p>
        ) : null}

        <section className="start-page__section" aria-labelledby="recent-heading">
          <h2 className="start-page__heading" id="recent-heading">
            Recent projects
          </h2>
          {status === "loading" ? (
            <p className="start-page__empty">Loading your projects…</p>
          ) : status === "error" ? (
            <p className="start-page__empty">
              The backend did not answer. Check that <code>uv run bgsim</code> is running, then{" "}
              <button type="button" className="button" onClick={() => void load()}>
                Retry
              </button>
            </p>
          ) : recent.length === 0 ? (
            <p className="start-page__empty" data-testid="recent-empty">
              No projects yet. Create one above, or open a sample below to get an editable copy.
            </p>
          ) : (
            <ul className="start-page__recent" data-testid="recent-projects">
              {recent.map((entry) => (
                <li key={entry.name}>
                  <button
                    type="button"
                    className="start-page__recent-item"
                    data-testid={`recent-project-${entry.name}`}
                    disabled={busy !== null || entry.models.length === 0}
                    title={
                      entry.models.length === 0
                        ? "This project has no models yet; open it from the Open dialog to add one."
                        : `Open ${entry.name}`
                    }
                    onClick={() => void openRecent(entry)}
                  >
                    <span className="open-dialog__name">{entry.name}</span>
                    <span className="start-page__recent-meta">
                      {entry.models.length} model{entry.models.length === 1 ? "" : "s"}
                      {entry.valid ? "" : " · invalid"}
                      {modifiedText(entry.modified) !== "" ? ` · ${modifiedText(entry.modified)}` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="start-page__section" aria-labelledby="gallery-heading">
          <h2 className="start-page__heading" id="gallery-heading">
            Example gallery
          </h2>
          <p className="start-page__note">
            Samples are read-only templates. “Open sample” imports an editable copy into your
            projects.
          </p>
          {status === "ready" && examples.length === 0 ? (
            <p className="start-page__empty" data-testid="gallery-empty">
              No samples are installed. Create an empty project above to start from scratch.
            </p>
          ) : (
            <ExampleGallery
              examples={examples}
              busy={busy !== null && examples.includes(busy) ? busy : null}
              onOpen={(example) => void openSample(example)}
            />
          )}
        </section>
      </div>
    </main>
  );
}
