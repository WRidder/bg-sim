/**
 * The three screens of the app, chosen by the URL:
 *
 * - no `?project=`: the start page (recent projects and the example gallery);
 * - `?project=p` without a model: the model picker of project `p` (a card per model);
 * - `?project=p&model=m`: the editor with model `m` open (a linkable, deep-linkable URL).
 */

export type AppRoute =
  | { kind: "start" }
  | { kind: "picker"; project: string }
  | { kind: "editor"; project: string; model: string };

function currentSearch(search?: string): string {
  return search ?? (typeof window === "undefined" ? "" : window.location.search);
}

function param(params: URLSearchParams, name: string): string {
  return params.get(name)?.trim() ?? "";
}

export function readAppRoute(search?: string): AppRoute {
  const params = new URLSearchParams(currentSearch(search));
  const project = param(params, "project");
  if (project.length === 0) {
    return { kind: "start" };
  }
  const model = param(params, "model");
  return model.length === 0 ? { kind: "picker", project } : { kind: "editor", project, model };
}

/**
 * Whether the URL names a project (`?project=`). Without one the app shows the
 * start page instead of opening the default `demo` project, so the first screen
 * is the example gallery rather than an empty canvas.
 */
export function hasProjectRoute(search?: string): boolean {
  return readAppRoute(search).kind !== "start";
}

function currentHref(href?: string): string {
  return href ?? window.location.href;
}

/** The URL of the model picker of `project` (the current URL with `model` removed). */
export function projectUrl(project: string, href?: string): string {
  const url = new URL(currentHref(href));
  url.searchParams.set("project", project);
  url.searchParams.delete("model");
  return url.toString();
}

/** The editor URL of `project`/`model`. */
export function modelUrl(project: string, model: string, href?: string): string {
  const url = new URL(currentHref(href));
  url.searchParams.set("project", project);
  url.searchParams.set("model", model);
  return url.toString();
}
