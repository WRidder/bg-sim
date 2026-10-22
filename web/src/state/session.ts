/**
 * Opening a project and a model for the editor (plan 3.3, 3.7).
 *
 * A local single-user app has one project open at a time. The route is read
 * from the URL (`?project=<p>&model=<m>`), which makes a workspace linkable and
 * lets the end-to-end tests use a fresh project per run. Without parameters the
 * app opens `demo/Model1`, creating the project on first use.
 *
 * The fast path is: open (or create) the project, load the catalog, load the
 * model; a missing model is a new unsaved document, not an error.
 */

import { useEffect } from "react";

import type { Model } from "../contracts/model";
import { fetchCatalog } from "../library/catalogClient";
import { useCatalogStore } from "../library/catalogStore";
import { useDocumentStore, type DocumentStatus } from "./documentStore";
import { ensureProject, getModel } from "./modelApi";
import { createEmptyModel } from "./modelFactory";

export const DEFAULT_PROJECT = "demo";
export const DEFAULT_MODEL = "Model1";

export interface SessionRoute {
  project: string;
  model: string;
}

function clean(value: string | null, fallback: string): string {
  const trimmed = value?.trim() ?? "";
  return trimmed.length > 0 ? trimmed : fallback;
}

/** The project and model named by the URL, with the local defaults. */
export function readSessionRoute(search?: string): SessionRoute {
  const raw =
    search ?? (typeof window === "undefined" ? "" : window.location.search);
  const params = new URLSearchParams(raw);
  return {
    project: clean(params.get("project"), DEFAULT_PROJECT),
    model: clean(params.get("model"), DEFAULT_MODEL),
  };
}

let sessionPromise: Promise<void> | null = null;
let generation = 0;

/**
 * Load the session once. Concurrent callers (React StrictMode renders twice)
 * share one promise; `force` starts a new attempt after an error.
 */
export function startSession(force = false): Promise<void> {
  if (sessionPromise !== null && !force) {
    return sessionPromise;
  }
  const attempt = ++generation;
  if (force) {
    sessionPromise = null;
  }
  const route = readSessionRoute();

  useDocumentStore.getState().setStatus("loading");
  useCatalogStore.getState().setLoading();

  const promise = (async () => {
    try {
      await ensureProject(route.project);
      const catalog = await fetchCatalog(route.project);
      if (attempt !== generation) {
        return;
      }
      useCatalogStore.getState().setCatalog(catalog);

      const model = await getModel(route.project, route.model);
      if (attempt !== generation) {
        return;
      }
      const document: Model = model ?? createEmptyModel(route.model, catalog.language);
      useDocumentStore
        .getState()
        .openDocument(route.project, route.model, document, { persisted: model !== null });
    } catch (error) {
      if (attempt !== generation) {
        return;
      }
      const message =
        error instanceof Error ? error.message : `Could not open the project: ${String(error)}`;
      useCatalogStore.getState().setError(message);
      useDocumentStore.getState().setStatus("error", message);
    }
  })();

  sessionPromise = promise;
  return promise;
}

/** Retry the session after a failure (the canvas error state's button). */
export function retrySession(): void {
  void startSession(true);
}

export interface SessionState {
  status: DocumentStatus;
  error: string | null;
  retry: () => void;
}

export function useProjectSession(): SessionState {
  const status = useDocumentStore((state) => state.status);
  const error = useDocumentStore((state) => state.loadError);

  useEffect(() => {
    if (status === "idle") {
      void startSession();
    }
  }, [status]);

  return { status, error, retry: retrySession };
}

/** Test hook: forget the shared promise and any in-flight attempt. */
export function resetSessionCache(): void {
  sessionPromise = null;
  generation += 1;
}
