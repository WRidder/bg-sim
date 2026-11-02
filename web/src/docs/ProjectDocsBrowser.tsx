/**
 * The Docs tab of the project page (`?project=p&tab=docs`): every docs page of the project in
 * one tree (the project docs first, then one node per model with its page tree) and the
 * selected page rendered next to it, with the renderer of the Docs tab. Reading only: each page
 * has an Edit action that opens a model with its Docs tab on that page (project pages open in
 * the Project section of the first model's Docs tab). `page:`, `project:` and `model:` links
 * navigate within this view.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState } from "../app/EmptyState";
import { navigation } from "../app/openSession";
import { modelDocsUrl, modelUrl } from "../app/route";
import { fetchPage, type DocsIndex } from "./docsApi";
import { formatDocsRef, modelPagesOf, parseDocsRef, type LinkContext } from "./docsLinks";
import { useDocsIndexStore } from "./docsStore";
import { MarkdownView, type LinkActions } from "./MarkdownView";
import { allIds, findPage, pathTo, type Docs, type DocsPage } from "./pageTree";
import "./docs.css";

export interface ProjectDocsBrowserProps {
  project: string;
  /** The selected page in the URL form (`project:<id>`, `model:<name>/<id>`), or `null`. */
  page: string | null;
  /** Called with the URL form of a newly selected page. */
  onPageChange: (page: string) => void;
}

/** A page of one of the project's wikis: `model === null` is the project docs. */
interface Selection {
  model: string | null;
  id: string;
}

function docsOf(index: DocsIndex, model: string | null): Docs | null {
  if (model === null) {
    return index.project;
  }
  return index.models.find((entry) => entry.name === model)?.docs ?? null;
}

/** The page the URL names, if it exists; otherwise the first page of the project. */
function resolveSelection(index: DocsIndex, page: string | null): Selection | null {
  const ref = parseDocsRef(page);
  if (ref?.wiki === "project" && findPage(index.project.pages, ref.id) !== null) {
    return { model: null, id: ref.id };
  }
  if (ref?.wiki === "model" && ref.model !== null) {
    const docs = docsOf(index, ref.model);
    const id = ref.id ?? docs?.pages[0]?.id ?? null;
    if (docs !== null && id !== null && findPage(docs.pages, id) !== null) {
      return { model: ref.model, id };
    }
  }
  const first = index.project.pages[0];
  if (first !== undefined) {
    return { model: null, id: first.id };
  }
  for (const entry of index.models) {
    const head = entry.docs.pages[0];
    if (head !== undefined) {
      return { model: entry.name, id: head.id };
    }
  }
  return null;
}

function refOf(selection: Selection): string {
  return selection.model === null
    ? formatDocsRef({ wiki: "project", id: selection.id })
    : formatDocsRef({ wiki: "model", model: selection.model, id: selection.id });
}

function PageList({
  pages,
  model,
  selected,
  onSelect,
  depth,
}: {
  pages: readonly DocsPage[];
  model: string | null;
  selected: Selection | null;
  onSelect: (selection: Selection) => void;
  depth: number;
}) {
  return (
    <ul className="project-docs__list">
      {pages.map((page) => {
        const current = selected !== null && selected.model === model && selected.id === page.id;
        return (
          <li key={page.id}>
            <button
              type="button"
              className="project-docs__page"
              style={{ paddingLeft: `calc(var(--space-2) * ${depth} + var(--space-2))` }}
              aria-current={current ? "page" : undefined}
              data-testid={`project-docs-page-${model === null ? ":project" : model}-${page.id}`}
              onClick={() => onSelect({ model, id: page.id })}
            >
              {page.title}
            </button>
            {page.children.length > 0 ? (
              <PageList pages={page.children} model={model} selected={selected} onSelect={onSelect} depth={depth + 1} />
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

export function ProjectDocsBrowser({ project, page, onPageChange }: ProjectDocsBrowserProps) {
  const status = useDocsIndexStore((state) => state.status);
  const error = useDocsIndexStore((state) => state.error);
  const loadedFor = useDocsIndexStore((state) => state.project);
  const index = useDocsIndexStore((state) => state.index);
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    void useDocsIndexStore.getState().load(project, true);
  }, [project]);

  const ready = index !== null && loadedFor === project;
  const selection = useMemo(() => (ready ? resolveSelection(index, page) : null), [ready, index, page]);
  const key = selection === null ? null : refOf(selection);

  useEffect(() => {
    if (selection === null || key === null || texts[key] !== undefined) {
      return;
    }
    let live = true;
    fetchPage(project, selection.model, selection.id).then(
      (text) => {
        if (live) {
          setTexts((previous) => ({ ...previous, [key]: text }));
        }
      },
      (cause: unknown) => {
        if (live) {
          setProblem(cause instanceof Error ? cause.message : String(cause));
        }
      },
    );
    return () => {
      live = false;
    };
  }, [project, selection, key, texts]);

  const select = useCallback(
    (next: Selection) => {
      setProblem(null);
      setNotice(null);
      onPageChange(refOf(next));
    },
    [onPageChange],
  );

  const links = useMemo<LinkContext | null>(() => {
    if (!ready || selection === null) {
      return null;
    }
    const docs = docsOf(index, selection.model);
    return {
      pageIds: allIds(docs?.pages ?? []),
      wiki: selection.model === null ? "project" : "model",
      // Block and signal links need the open model; here they say so.
      model: null,
      signalIds: null,
      projectPageIds: allIds(index.project.pages),
      modelPages: modelPagesOf(index.models),
    };
  }, [ready, index, selection]);

  const actions = useMemo<LinkActions>(
    () => ({
      openPage: (id) => {
        if (selection !== null) {
          select({ model: selection.model, id });
        }
      },
      openProjectPage: (id) => select({ model: null, id }),
      openModelPage: (model, id) => select({ model, id }),
      showBlock: (target) => setNotice(`Open the model to show ${target.name} in its diagram.`),
      plotSignal: (id) => setNotice(`Open the model to plot ${id}.`),
      notify: setNotice,
    }),
    [select, selection],
  );

  if (status === "error" && !ready) {
    return (
      <div className="project-docs__state" role="alert" data-testid="project-docs-error">
        <p>The docs of the project could not be loaded: {error}</p>
        <button type="button" className="button" onClick={() => void useDocsIndexStore.getState().load(project, true)}>
          Retry
        </button>
      </div>
    );
  }
  if (!ready) {
    return <EmptyState title="Loading the docs" hint="One moment." />;
  }

  // The project docs are edited in the Project section of a model's Docs tab.
  const editModel = index.models.find((entry) => entry.inProject)?.name ?? index.models[0]?.name ?? null;
  const docs = selection === null ? null : docsOf(index, selection.model);
  const current = selection === null || docs === null ? null : findPage(docs.pages, selection.id);
  const crumbs = selection === null || docs === null ? [] : (pathTo(docs.pages, selection.id) ?? []);
  const text = key === null ? undefined : texts[key];

  const editUrl =
    selection === null
      ? null
      : selection.model === null
        ? editModel === null
          ? null
          : modelDocsUrl(project, editModel, `project:${selection.id}`)
        : modelDocsUrl(project, selection.model, selection.id);

  return (
    <div className="project-docs" data-testid="project-docs">
      <nav className="project-docs__tree" aria-label="Docs of the project" data-testid="project-docs-tree">
        <section className="project-docs__group" data-testid="project-docs-group-project">
          <h3 className="project-docs__heading">Project</h3>
          {index.project.pages.length === 0 ? (
            <p className="project-docs__none">No project docs. Add them in a model&apos;s Docs tab.</p>
          ) : (
            <PageList pages={index.project.pages} model={null} selected={selection} onSelect={select} depth={0} />
          )}
        </section>
        {index.models.map((entry) => (
          <section
            key={entry.name}
            className="project-docs__group"
            data-testid={`project-docs-group-${entry.name}`}
            data-empty={entry.docs.pages.length === 0 ? "true" : undefined}
          >
            <h3 className="project-docs__heading">
              {entry.name}
              {entry.docs.pages.length === 0 ? <span className="project-docs__none-tag"> · no docs</span> : null}
            </h3>
            {entry.error !== null ? (
              <p className="project-docs__none" title={entry.error}>
                The docs could not be read.
              </p>
            ) : (
              <PageList pages={entry.docs.pages} model={entry.name} selected={selection} onSelect={select} depth={0} />
            )}
          </section>
        ))}
      </nav>

      <article className="project-docs__reader" data-testid="project-docs-reader" aria-label="Docs page">
        {selection === null || current === null ? (
          <EmptyState
            title="No docs yet"
            hint="Open a model and write its docs in the Docs tab; pages shared by every model go into the project docs (Add project docs there)."
          />
        ) : (
          <>
            <div className="docs-toolbar project-docs__toolbar">
              <nav className="docs-crumbs" aria-label="Page path" data-testid="project-docs-crumbs">
                <span>{selection.model === null ? "Project docs" : selection.model}</span>
                {crumbs.map((id) => (
                  <span key={id}>
                    <span aria-hidden="true"> / </span>
                    {findPage(docs?.pages ?? [], id)?.title}
                  </span>
                ))}
              </nav>
              <span className="docs-toolbar__spacer" />
              {selection.model !== null ? (
                <a
                  className="button docs-toolbar__button"
                  href={modelUrl(project, selection.model)}
                  data-testid="project-docs-open-model"
                  onClick={(event) => {
                    if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && selection.model !== null) {
                      event.preventDefault();
                      navigation.assign(modelUrl(project, selection.model));
                    }
                  }}
                >
                  Open model
                </a>
              ) : null}
              {editUrl !== null ? (
                <a
                  className="button docs-toolbar__button"
                  href={editUrl}
                  data-testid="project-docs-edit"
                  title={
                    selection.model === null
                      ? `Edit the page in the Project section of the Docs tab of ${editModel ?? "a model"}`
                      : `Edit the page in the Docs tab of ${selection.model}`
                  }
                  onClick={(event) => {
                    if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
                      event.preventDefault();
                      navigation.assign(editUrl);
                    }
                  }}
                >
                  Edit
                </a>
              ) : null}
            </div>
            {problem !== null ? (
              <p className="docs-banner docs-banner--error" role="alert">
                {problem}
              </p>
            ) : null}
            {notice !== null ? (
              <p className="docs-banner" role="status" data-testid="project-docs-notice">
                {notice}{" "}
                <button type="button" className="docs-banner__close" onClick={() => setNotice(null)}>
                  Dismiss
                </button>
              </p>
            ) : null}
            <div className="docs-preview project-docs__body" data-testid="project-docs-body" tabIndex={0}>
              {text === undefined ? (
                <EmptyState title="Loading the page" hint="One moment." />
              ) : text.trim() === "" ? (
                <p className="docs-preview__empty">This page is empty.</p>
              ) : links !== null ? (
                <MarkdownView text={text} project={project} model={selection.model} links={links} actions={actions} />
              ) : null}
            </div>
          </>
        )}
      </article>
    </div>
  );
}

export default ProjectDocsBrowser;
